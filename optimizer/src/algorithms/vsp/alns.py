"""
VSP — Adaptive Large Neighborhood Search (ALNS).

Implementação baseada em Ropke & Pisinger (2006) e na biblioteca N-Wouda/ALNS.

Referências:
  [1] Ropke, S., Pisinger, D. (2006) "An adaptive large neighborhood search
      heuristic for the pickup and delivery problem with time windows",
      Transportation Science 40(4):455-472.
  [2] Pisinger, D., Ropke, S. (2010) "Large neighborhood search", Handbook
      of Metaheuristics, pp. 399-419.
  [3] Sarasola B. et al. (2024) "A review and ranking of operators in ALNS
      for VRPs", EJOR 318(2):399-426.

Estrutura:
  - Estado: List[List[int]] (blocos como listas de trip_ids)
  - Destroy operators: random_removal, worst_removal, shaw_removal
  - Repair operators: greedy_insertion, regret_insertion
  - Operator selection: roulette wheel com pesos adaptativos
  - Acceptance: Record-to-Record Travel (RRT) ou SA simples

Diferenças vs SA puro existente:
  - ALNS destrói uma porção GRANDE (10-40% das trips) por iteração
  - Reconstrói com inserção gulosa/regret
  - Operadores ganham/perdem peso conforme performance
  - Tende a escapar de ótimos locais que SA fica preso
"""

from __future__ import annotations

import logging
import math
import random
import time
from typing import Dict, List, Optional, Tuple

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from ..utils import is_connection_feasible, quick_cost_from_trips, select_vehicle_type
from .greedy import GreedyVSP

settings = get_settings()
_log = logging.getLogger(__name__)


# ─── Operator scores (Ropke & Pisinger 2006, §4.2) ──────────────────────────
_SIGMA_BEST = 33.0  # nova melhor solução global
_SIGMA_BETTER = 9.0  # melhor que atual mas não global
_SIGMA_ACCEPTED = 13.0  # pior mas aceita
_REACTION_FACTOR = 0.1  # quão rápido pesos se adaptam (0.1 = lento, 0.5 = rápido)


def _state_cost(state: List[List[int]], trip_map: Dict[int, Trip], vsp_params: Dict) -> float:
    """Soma quick_cost de cada bloco. Compatível com função de custo do SA existente.

    IMPORTANTE: usa os mesmos parâmetros e defaults do SA/Tabu para garantir
    que as comparações entre algoritmos sejam feitas na mesma escala de custo.
    BUG-ALNS-01 (corrigido): `fixed_vehicle_cost` era 900.0 (hardcoded); corrigido
      para ler de vsp_params com default 800.0 (consistente com SA/Tabu/Greedy).
    BUG-ALNS-02 (corrigido): `crew_cost_weight` era lido via `cost_duty` (errado);
      corrigido para `crew_cost_weight` (a chave usada em todos os outros algoritmos).
    BUG-ALNS-03 (corrigido): `idle_cost_per_minute` default era 0.25; corrigido
      para 0.5 (mesmo default de SA/Tabu/Greedy).
    """
    sequences: List[List[Trip]] = []
    for block in state:
        if not block:
            continue
        sequences.append([trip_map[tid] for tid in block])
    if not sequences:
        return 0.0
    fvc = float(vsp_params.get("fixed_vehicle_activation_cost", 800.0))
    return float(
        quick_cost_from_trips(
            sequences,
            fixed_vehicle_cost=fvc,
            idle_cost_per_minute=float(vsp_params.get("idle_cost_per_minute", 0.5)),
            max_work_minutes=float(vsp_params.get("max_work_minutes", 480.0)),
            crew_cost_weight=float(vsp_params.get("crew_cost_weight", fvc * 0.5)),
            deadhead_cost_per_minute=float(vsp_params.get("deadhead_cost_per_minute", 1.0)),
        )
    )


def _is_feasible_chain(
    block: List[int],
    trip_map: Dict[int, Trip],
    min_layover: int,
    enforce_min_interval: bool,
    connection_tolerance: int,
    min_break: int = 30,
) -> bool:
    # BUG-ALNS-06 fix: min_break (CCT do motorista, ex: 30min) é diferente de
    # min_layover (turnaround técnico do veículo, ex: 8min). A versão anterior
    # usava min_layover como min_break, o que é semanticamente incorreto.
    for i in range(len(block) - 1):
        if not is_connection_feasible(
            trip_map[block[i]],
            trip_map[block[i + 1]],
            min_layover=min_layover,
            min_break=min_break,
            enforce_min_interval=enforce_min_interval,
            connection_tolerance=connection_tolerance,
        ):
            return False
    return True


# ─── DESTROY OPERATORS ──────────────────────────────────────────────────────


def _random_removal(
    state: List[List[int]],
    n_remove: int,
    rng: random.Random,
) -> Tuple[List[List[int]], List[int]]:
    """Remove n_remove trips aleatórias do estado."""
    all_trips = [(b_idx, t_idx, tid) for b_idx, b in enumerate(state) for t_idx, tid in enumerate(b)]
    if len(all_trips) <= n_remove:
        n_remove = max(1, len(all_trips) // 2)
    sample = rng.sample(all_trips, n_remove)
    sample_set = {(b, t) for b, t, _ in sample}
    removed = [tid for _, _, tid in sample]
    new_state = [
        [tid for t_idx, tid in enumerate(block) if (b_idx, t_idx) not in sample_set]
        for b_idx, block in enumerate(state)
    ]
    new_state = [b for b in new_state if b]  # remove blocos vazios
    return new_state, removed


def _worst_removal(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    n_remove: int,
    rng: random.Random,
) -> Tuple[List[List[int]], List[int]]:
    """Remove n_remove trips com maior 'custo de bloco isolado' (proxy de desperdício)."""
    # Heurística simples: trips que ficam sozinhas em blocos pequenos são "ruins"
    candidates = []
    for b_idx, block in enumerate(state):
        for t_idx, tid in enumerate(block):
            trip = trip_map[tid]
            # Score: trips em blocos curtos têm score alto (mais desejáveis para remover)
            score = 1.0 / max(1, len(block))
            score += trip.duration / 1000.0  # trips mais longas ligeiramente mais propensas
            score += rng.random() * 0.1  # pequeno ruído para evitar determinismo
            candidates.append((score, b_idx, t_idx, tid))
    candidates.sort(reverse=True)
    selected = candidates[:n_remove]
    selected_set = {(b, t) for _, b, t, _ in selected}
    removed = [tid for _, _, _, tid in selected]
    new_state = [
        [tid for t_idx, tid in enumerate(block) if (b_idx, t_idx) not in selected_set]
        for b_idx, block in enumerate(state)
    ]
    new_state = [b for b in new_state if b]
    return new_state, removed


def _shaw_removal(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    n_remove: int,
    rng: random.Random,
) -> Tuple[List[List[int]], List[int]]:
    """Remove trips relacionadas (próximas no tempo / mesma linha) — Shaw 1997.

    Ideia: remover cluster de trips que provavelmente se beneficiariam de
    reorganização conjunta.
    """
    all_tids = [tid for block in state for tid in block]
    if not all_tids:
        return state, []

    seed_tid = rng.choice(all_tids)
    seed_trip = trip_map[seed_tid]
    # Score de relacionamento: |diff start_time| + 100 * (line diferente)
    scored = []
    for tid in all_tids:
        if tid == seed_tid:
            continue
        t = trip_map[tid]
        rel = abs(t.start_time - seed_trip.start_time)
        if t.line_id != seed_trip.line_id:
            rel += 200
        scored.append((rel, tid))
    scored.sort()
    removed_set = {seed_tid}
    for _, tid in scored[: n_remove - 1]:
        removed_set.add(tid)
    removed = list(removed_set)
    new_state = [[tid for tid in block if tid not in removed_set] for block in state]
    new_state = [b for b in new_state if b]
    return new_state, removed


# ─── REPAIR OPERATORS ───────────────────────────────────────────────────────


def _greedy_insertion(
    partial: List[List[int]],
    to_insert: List[int],
    trip_map: Dict[int, Trip],
    min_layover: int,
    enforce_min_interval: bool,
    connection_tolerance: int,
    rng: random.Random,
) -> List[List[int]]:
    """Insere cada trip removida no melhor (mais barato/viável) ponto."""
    state = [b[:] for b in partial]
    for tid in to_insert:
        trip = trip_map[tid]
        best_insert: Optional[Tuple[float, int, int]] = None  # (cost_delta, b_idx, pos)
        for b_idx, block in enumerate(state):
            for pos in range(len(block) + 1):
                # tenta inserir trip em block[pos]
                candidate = block[:pos] + [tid] + block[pos:]
                if not _is_feasible_chain(
                    candidate,
                    trip_map,
                    min_layover,
                    enforce_min_interval,
                    connection_tolerance,
                ):
                    continue
                # custo barato: minimiza idle inserido
                # BUG-ALNS-01 fix: delta=0.0 para pos=0 subestimava custo de inserção
                # no início do bloco, fazendo o ALNS preferir sempre o início.
                # Correto: calcular o gap real que a trip introduz (idle antes do 1º elemento).
                if pos == 0:
                    delta = float(trip_map[block[0]].start_time - trip.end_time) if block else 0.0
                elif pos == len(block):
                    delta = float(trip.start_time - trip_map[block[-1]].end_time)
                else:
                    prev_end = trip_map[block[pos - 1]].end_time
                    next_start = trip_map[block[pos]].start_time
                    delta = (trip.start_time - prev_end) + (next_start - trip.end_time)
                if best_insert is None or delta < best_insert[0]:
                    best_insert = (delta, b_idx, pos)
        if best_insert is None:
            # cria novo bloco
            state.append([tid])
        else:
            _, b_idx, pos = best_insert
            state[b_idx].insert(pos, tid)
    return state


def _regret_insertion(
    partial: List[List[int]],
    to_insert: List[int],
    trip_map: Dict[int, Trip],
    min_layover: int,
    enforce_min_interval: bool,
    connection_tolerance: int,
    rng: random.Random,
) -> List[List[int]]:
    """Regret-k insertion: insere primeiro a trip com maior diferença entre
    melhor e segundo melhor ponto de inserção (Potvin & Rousseau 1993).
    """
    state = [b[:] for b in partial]
    pending = list(to_insert)
    while pending:
        best_regret = -1.0
        best_tid: Optional[int] = None
        best_target: Optional[Tuple[int, int]] = None
        for tid in pending:
            trip = trip_map[tid]
            options: List[Tuple[float, int, int]] = []
            for b_idx, block in enumerate(state):
                for pos in range(len(block) + 1):
                    candidate = block[:pos] + [tid] + block[pos:]
                    if not _is_feasible_chain(
                        candidate,
                        trip_map,
                        min_layover,
                        enforce_min_interval,
                        connection_tolerance,
                    ):
                        continue
                    # BUG-ALNS-02 fix: mesmo delta=0.0 para pos=0 que BUG-ALNS-01.
                    if pos == 0:
                        delta = float(trip_map[block[0]].start_time - trip.end_time) if block else 0.0
                    elif pos == len(block):
                        delta = float(trip.start_time - trip_map[block[-1]].end_time)
                    else:
                        prev_end = trip_map[block[pos - 1]].end_time
                        next_start = trip_map[block[pos]].start_time
                        delta = (trip.start_time - prev_end) + (next_start - trip.end_time)
                    options.append((delta, b_idx, pos))
            options.sort()
            if not options:
                regret = 1e9  # forçar inserção em novo bloco com prioridade
                target = (-1, -1)
            elif len(options) == 1:
                regret = 1e6
                target = (options[0][1], options[0][2])
            else:
                regret = options[1][0] - options[0][0]
                target = (options[0][1], options[0][2])
            if regret > best_regret:
                best_regret = regret
                best_tid = tid
                best_target = target
        # insere a trip com maior regret
        if best_tid is None:
            break
        pending.remove(best_tid)
        b_idx, pos = best_target  # type: ignore[misc]
        if b_idx == -1:
            state.append([best_tid])
        else:
            state[b_idx].insert(pos, best_tid)
    return state


# ─── ALNS MAIN LOOP ─────────────────────────────────────────────────────────


class ALNSVSP(BaseAlgorithm, IVSPAlgorithm):
    """Adaptive Large Neighborhood Search para VSP.

    Uso:
        alns = ALNSVSP(vsp_params={...})
        alns.time_budget_s = 30.0
        sol = alns.solve(trips, vehicle_types, depot_id)
    """

    def __init__(self, vsp_params: Optional[Dict] = None):
        super().__init__(name="alns_vsp", time_budget_s=30.0)
        self.vsp_params = vsp_params or {}

    def _p(self, key: str, default):
        return self.vsp_params.get(key, default)

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)

        # Solução inicial via Greedy (warm start)
        seed = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
        if not seed.blocks:
            return seed

        trip_map: Dict[int, Trip] = {int(t.id): t for t in trips}
        state: List[List[int]] = [[int(t.id) for t in b.trips] for b in seed.blocks]
        best_state = [b[:] for b in state]
        current_cost = _state_cost(state, trip_map, self.vsp_params)
        best_cost = current_cost

        rng = random.Random(int(self._p("random_seed", time.time() * 1000)))
        min_layover = int(self._p("min_layover_minutes", 8) or 8)
        enforce_min_interval = bool(self._p("enforce_min_interval", False))
        connection_tolerance = int(self._p("connection_tolerance_minutes", 0) or 0)

        # Destroy degree: 10–40% das trips por iteração (Ropke & Pisinger §3.4)
        n_trips = len(trips)
        min_destroy = max(2, n_trips // 10)
        max_destroy = max(min_destroy + 1, n_trips // 4)

        # Operadores e pesos iniciais (todos iguais)
        destroy_ops = [("random", _random_removal), ("worst", _worst_removal), ("shaw", _shaw_removal)]
        repair_ops = [("greedy", _greedy_insertion), ("regret", _regret_insertion)]
        d_weights = {name: 1.0 for name, _ in destroy_ops}
        r_weights = {name: 1.0 for name, _ in repair_ops}
        d_scores = {name: 0.0 for name, _ in destroy_ops}
        r_scores = {name: 0.0 for name, _ in repair_ops}
        d_count = {name: 0 for name, _ in destroy_ops}
        r_count = {name: 0 for name, _ in repair_ops}

        # SA acceptance: T0 = ~5% do current_cost
        temperature = max(1.0, current_cost * 0.05)
        cooling = 0.997

        iterations = 0
        update_period = 50  # atualiza pesos a cada 50 iterações

        while not self._check_timeout():
            iterations += 1

            # Roulette wheel
            d_name, d_fn = self._roulette(destroy_ops, d_weights, rng)
            r_name, r_fn = self._roulette(repair_ops, r_weights, rng)
            d_count[d_name] += 1
            r_count[r_name] += 1

            # Destroy
            n_remove = rng.randint(min_destroy, max_destroy)
            if d_name == "random":
                partial, removed = d_fn(state, n_remove, rng)  # type: ignore[arg-type]
            else:
                partial, removed = d_fn(state, trip_map, n_remove, rng)  # type: ignore[arg-type]

            # Repair
            new_state = r_fn(
                partial,
                removed,
                trip_map,
                min_layover,
                enforce_min_interval,
                connection_tolerance,
                rng,
            )

            new_cost = _state_cost(new_state, trip_map, self.vsp_params)

            # Score por outcome
            if new_cost < best_cost:
                state = new_state
                current_cost = new_cost
                best_state = [b[:] for b in new_state]
                best_cost = new_cost
                d_scores[d_name] += _SIGMA_BEST
                r_scores[r_name] += _SIGMA_BEST
            elif new_cost < current_cost:
                state = new_state
                current_cost = new_cost
                d_scores[d_name] += _SIGMA_BETTER
                r_scores[r_name] += _SIGMA_BETTER
            else:
                # SA acceptance
                delta = new_cost - current_cost
                if rng.random() < math.exp(-delta / max(1.0, temperature)):
                    state = new_state
                    current_cost = new_cost
                    d_scores[d_name] += _SIGMA_ACCEPTED
                    r_scores[r_name] += _SIGMA_ACCEPTED

            temperature *= cooling

            # Update weights periodicamente
            if iterations % update_period == 0:
                for name in d_weights:
                    if d_count[name] > 0:
                        avg = d_scores[name] / d_count[name]
                        d_weights[name] = (
                            (1 - _REACTION_FACTOR) * d_weights[name] + _REACTION_FACTOR * avg
                        )
                        d_scores[name] = 0.0
                        d_count[name] = 0
                for name in r_weights:
                    if r_count[name] > 0:
                        avg = r_scores[name] / r_count[name]
                        r_weights[name] = (
                            (1 - _REACTION_FACTOR) * r_weights[name] + _REACTION_FACTOR * avg
                        )
                        r_scores[name] = 0.0
                        r_count[name] = 0

        # Reconstrói VSPSolution a partir de best_state
        # BUG-ALNS-04 fix: seleciona vehicle_type por bloco usando depot da primeira
        # trip, consistente com GreedyVSP e GeneticVSP. Antes usava select_vehicle_type()
        # sem depot_id, atribuindo o tipo mais barato globalmente a todos os blocos,
        # o que é incorreto em operações multi-depot.
        # BUG-ALNS-05 fix: pré-calcula greedy_cost em variável para evitar duplo cálculo no log.
        _greedy_cost = _state_cost([[int(t.id) for t in b.trips] for b in seed.blocks], trip_map, self.vsp_params)
        blocks_out: List[Block] = []
        for b_idx, block_ids in enumerate(best_state):
            if not block_ids:
                continue
            chain = [trip_map[tid] for tid in block_ids]
            blk_depot = chain[0].depot_id if chain else None
            vt = select_vehicle_type(vehicle_types, blk_depot)
            blk = Block(id=b_idx + 1, trips=chain, vehicle_type_id=vt.id if vt else None)
            blocks_out.append(blk)

        _log.info(
            "[ALNS] iterations=%d best_cost=%.2f vs greedy_cost=%.2f reduction=%.1f%%",
            iterations,
            best_cost,
            _greedy_cost,
            (1 - best_cost / max(1.0, _greedy_cost)) * 100,
        )

        return VSPSolution(
            blocks=blocks_out,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
            meta={
                "alns_iterations": iterations,
                "alns_destroy_weights": dict(d_weights),
                "alns_repair_weights": dict(r_weights),
                "alns_best_cost": round(best_cost, 2),
            },
        )

    def _roulette(self, operators, weights: Dict[str, float], rng: random.Random):
        names = [n for n, _ in operators]
        ws = [max(0.01, weights[n]) for n in names]
        total = sum(ws)
        pick = rng.random() * total
        acc = 0.0
        for (name, fn), w in zip(operators, ws):
            acc += w
            if pick <= acc:
                return name, fn
        return operators[-1]
