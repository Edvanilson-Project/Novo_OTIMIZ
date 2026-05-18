"""
Timetable Slack Optimization — reduz PVR ajustando start_times dentro de janelas.

MOTIVAÇÃO (Optibus 2024, "industry first"):
  Operadores frequentemente têm tolerância de ±N minutos em horários de partida.
  Explorar esse grau de liberdade pode reduzir o PVR (Peak Vehicle Requirement)
  em 5–15% sem degradar o serviço ao passageiro.

ALGORITMO — "Gap-closing local search":
  1. Roda greedy para obter blocos iniciais (baseline).
  2. Para cada par de blocos (B_a, B_b) onde B_a.last → B_b.first é quase viável:
     - Testa combinações de ajuste em [-slack, +slack] × [-slack, +slack] (passo: step_minutes)
     - Encontra o ajuste de menor perturbação (|Δa| + |Δb|) que torna a conexão viável
     - Aplica o ajuste e funde os dois blocos em um só
  3. Repete até nenhuma fusão ser possível (convergência).
  4. Retorna trips com start/end_times ajustados.

GARANTIAS:
  - Nenhum trip é ajustado além de slack_minutes para fora do horário original.
  - Nenhuma viagem é removida ou adicionada.
  - Todos os trip_ids permanecem inalterados.
  - Não modifica trips in-place — retorna cópias.

INTEGRAÇÃO:
  Ativado via vsp_params["timetable_slack_minutes"] > 0.
  Roda como pré-processamento antes do VSP principal (greedy, B&P, etc.).
"""

from __future__ import annotations

import copy
import logging
from typing import Dict, List, Optional, Tuple

from ...domain.models import Trip
from .greedy import GreedyVSP

_log = logging.getLogger(__name__)

_DEFAULT_STEP = 5  # passo de ajuste em minutos
_DEFAULT_MAX_PASSES = 8  # máximo de passagens sobre pares de blocos


def _gap(last: Trip, first: Trip, delta_last: int = 0, delta_first: int = 0) -> int:
    """Gap entre fim de last (ajustado) e início de first (ajustado)."""
    return (first.start_time + delta_first) - (last.end_time + delta_last)


def _find_min_delta(
    last: Trip,
    first: Trip,
    slack: int,
    step: int,
    min_layover: int,
) -> Optional[Tuple[int, int]]:
    """
    Encontra (delta_last, delta_first) de menor perturbação total que torna
    a conexão last→first viável.

    Conexão viável: gap ≥ max(min_layover, deadhead(last→first)).
    Perturbação = |delta_last| + |delta_first| (minimizada).

    Retorna (0, 0) se já viável. Retorna None se impossível dentro do slack.
    """
    deadhead = int(last.deadhead_times.get(first.origin_id, 0))
    required_gap = max(min_layover, deadhead)

    current_gap = _gap(last, first)
    if current_gap >= required_gap:
        return (0, 0)

    deficit = required_gap - current_gap
    if deficit > 2 * slack:
        return None  # impossível — gap muito grande para fechar com slack disponível

    # Varrer todos os (dl, df) ∈ [-slack, +slack]² em passos de step,
    # ordenados por perturbação total crescente.
    candidates: List[Tuple[int, int, int]] = []  # (abs_sum, dl, df)
    for dl in range(-slack, slack + 1, step):
        for df in range(-slack, slack + 1, step):
            if _gap(last, first, dl, df) >= required_gap:
                candidates.append((abs(dl) + abs(df), dl, df))

    if not candidates:
        return None

    candidates.sort()
    _, dl, df = candidates[0]
    return (dl, df)


def _adjusted_trip(trip: Trip, delta: int) -> Trip:
    """Retorna cópia de trip com start_time e end_time deslocados por delta."""
    t = copy.copy(trip)
    t.start_time = trip.start_time + delta
    t.end_time = trip.end_time + delta
    return t


class TimetableSlackOptimizer:
    """
    Otimizador de horários dentro de janelas de tolerância (slack).

    Reduz PVR fechando gaps entre blocos via ajuste mínimo de start_times.
    Retorna lista de trips ajustadas prontas para o VSP principal.

    Parâmetros:
      slack_minutes:  tolerância máxima de ajuste por viagem (default 0 = desativado)
      step_minutes:   granularidade dos ajustes testados (default 5 min)
      max_passes:     máximo de passagens de fusão (default 8)
      min_layover:    layover mínimo entre viagens no mesmo veículo (default 8 min)
    """

    def __init__(
        self,
        slack_minutes: int = 0,
        step_minutes: int = _DEFAULT_STEP,
        max_passes: int = _DEFAULT_MAX_PASSES,
        min_layover: int = 8,
    ) -> None:
        self.slack = max(0, int(slack_minutes))
        self.step = max(1, int(step_minutes))
        self.max_passes = max(1, int(max_passes))
        self.min_layover = int(min_layover)

    def optimize(
        self,
        trips: List[Trip],
        vehicle_types: list,
        depot_id: Optional[int] = None,
        vsp_params: Optional[Dict] = None,
    ) -> Tuple[List[Trip], Dict]:
        """
        Retorna (adjusted_trips, meta).

        adjusted_trips: trips com start/end_times otimizados (dentro do slack).
        meta: dicionário com estatísticas da otimização.
        """
        if self.slack == 0 or not trips:
            return list(trips), {"slack_applied": False, "pvr_before": 0, "pvr_after": 0, "merges": 0}

        # Rastrear ajustes por trip_id: delta aplicado
        deltas: Dict[int, int] = {t.id: 0 for t in trips}

        # Greedy inicial para obter partição em blocos
        greedy = GreedyVSP(vsp_params=vsp_params or {})
        initial_sol = greedy.solve(trips, vehicle_types, depot_id)
        pvr_before = len(initial_sol.blocks)

        if pvr_before <= 1:
            return list(trips), {
                "slack_applied": False,
                "pvr_before": pvr_before,
                "pvr_after": pvr_before,
                "pvr_reduction": 0,
                "pvr_reduction_pct": 0.0,
                "trips_adjusted": 0,
                "total_merges": 0,
                "passes": 0,
            }

        total_merges = 0

        for pass_n in range(self.max_passes):
            # Reconstruir lista de trips ajustada com deltas atuais
            current_trips = [_adjusted_trip(t, deltas[t.id]) for t in trips]

            # Rodar greedy sobre trips ajustadas
            sol = greedy.solve(current_trips, vehicle_types, depot_id)
            blocks = [b for b in sol.blocks if b.trips]
            blocks.sort(key=lambda b: b.trips[0].start_time)

            pass_merges = 0
            merged_indices: set = set()

            for i, b_a in enumerate(blocks):
                if i in merged_indices:
                    continue
                last = b_a.trips[-1]  # última trip do bloco A (ajustada)

                for j, b_b in enumerate(blocks):
                    if j <= i or j in merged_indices:
                        continue
                    first = b_b.trips[0]  # primeira trip do bloco B (ajustada)

                    # Só tentar quando B começa depois de A terminar (candidato natural)
                    if first.start_time < last.end_time:
                        continue

                    result = _find_min_delta(last, first, self.slack, self.step, self.min_layover)
                    if result is None:
                        continue

                    d_last, d_first = result
                    if d_last == 0 and d_first == 0:
                        # Já viável — skip (greedy deveria ter fundido)
                        continue

                    # Verificar que os ajustes não excedem o slack original
                    last_orig_id = last.id
                    first_orig_id = first.id
                    new_delta_last = deltas[last_orig_id] + d_last
                    new_delta_first = deltas[first_orig_id] + d_first

                    if abs(new_delta_last) > self.slack or abs(new_delta_first) > self.slack:
                        continue

                    # Aplicar ajustes
                    deltas[last_orig_id] = new_delta_last
                    deltas[first_orig_id] = new_delta_first

                    merged_indices.add(j)
                    pass_merges += 1
                    _log.debug(
                        "timetable_slack: trip %d Δ=%+d, trip %d Δ=%+d → merge block %d←%d",
                        last_orig_id,
                        d_last,
                        first_orig_id,
                        d_first,
                        i,
                        j,
                    )
                    break  # cada bloco A funde com no máximo 1 bloco B por passagem

            total_merges += pass_merges
            if pass_merges == 0:
                _log.debug("timetable_slack: convergiu em %d passagens", pass_n + 1)
                break

        # Resultado final: trips com deltas aplicados
        adjusted = [_adjusted_trip(t, deltas[t.id]) for t in trips]

        # PVR final estimado (verificação rápida)
        final_sol = greedy.solve(adjusted, vehicle_types, depot_id)
        pvr_after = len(final_sol.blocks)

        non_zero = sum(1 for d in deltas.values() if d != 0)
        _log.info(
            "timetable_slack: PVR %d→%d (−%d), %d trips ajustadas (slack±%dmin)",
            pvr_before,
            pvr_after,
            pvr_before - pvr_after,
            non_zero,
            self.slack,
        )

        meta = {
            "slack_applied": True,
            "slack_minutes": self.slack,
            "pvr_before": pvr_before,
            "pvr_after": pvr_after,
            "pvr_reduction": pvr_before - pvr_after,
            "pvr_reduction_pct": round((pvr_before - pvr_after) / max(1, pvr_before) * 100, 1),
            "trips_adjusted": non_zero,
            "total_merges": total_merges,
            "passes": min(pass_n + 1, self.max_passes),
        }
        return adjusted, meta
