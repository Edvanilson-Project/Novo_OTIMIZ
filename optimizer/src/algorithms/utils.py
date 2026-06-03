"""
Utilitários compartilhados pelos algoritmos de busca (SA, TS, GA).

Funções:
  - sort_block_trips(blocks)    — re-ordena viagens por start_time em cada bloco
  - block_is_feasible(block)    — verifica sobreposição básica (gap >= 0)
  - blocks_are_feasible(blocks) — verifica todos os blocos
  - quick_cost_sorted(blocks)   — custo rápido com trips já ordenadas
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
from collections import OrderedDict

from ..domain.models import Block, Trip, VehicleType

_EDGE_FEASIBILITY_CACHE: OrderedDict[Tuple[Any, ...], bool] = OrderedDict()
_FEASIBILITY_CACHE: OrderedDict[Tuple[Any, ...], bool] = OrderedDict()


def select_vehicle_type(
    vehicle_types: List[VehicleType],
    depot_id: Optional[int] = None,
) -> Optional[VehicleType]:
    """Seleciona o tipo de veículo mais adequado para um bloco.

    Critérios (em ordem):
    1. Se depot_id fornecido, prefere tipos cujo depot_id coincide.
    2. Entre candidatos, escolhe o de menor fixed_cost.
    3. Fallback: primeiro da lista (comportamento anterior).

    Retorna None se a lista estiver vazia.
    """
    if not vehicle_types:
        return None
    if len(vehicle_types) == 1:
        return vehicle_types[0]

    # Candidatos compatíveis com o depot, ou todos se sem restrição de depot
    if depot_id is not None:
        depot_match = [v for v in vehicle_types if v.depot_id is None or v.depot_id == depot_id]
        candidates = depot_match if depot_match else vehicle_types
    else:
        candidates = vehicle_types

    return min(candidates, key=lambda v: (v.fixed_cost, v.id))


def clear_feasibility_caches():
    """Limpa os caches globais de viabilidade para liberar memória."""
    _EDGE_FEASIBILITY_CACHE.clear()
    _FEASIBILITY_CACHE.clear()


def is_connection_feasible(
    current: Trip,
    nxt: Trip,
    *,
    min_layover: int = 8,
    min_break: int = 30,
    enforce_min_interval: bool = False,
    connection_tolerance: int = 0,
    strict_zero_gap_validation: bool = False,
    strict_operational_mode: bool = False,
    strict_hard_constraints: bool = False,
) -> bool:
    # Garante que inteiros sejam usados no cálculo
    min_layover = int(min_layover)
    min_break = int(min_break)
    connection_tolerance = int(connection_tolerance)

    """Centraliza a lógica de viabilidade de conexão VSP com cache de aresta."""
    # PERF: Cache de aresta nível 1 (O(1) após primeiro hit)
    params_key = frozenset(
        {
            ("ml", min_layover),
            ("mb", min_break),
            ("emi", enforce_min_interval),
            ("ct", connection_tolerance),
            ("szgv", strict_zero_gap_validation),
            ("som", strict_operational_mode),
            ("shc", strict_hard_constraints),
        }
    )
    deadhead = int(current.deadhead_times.get(nxt.origin_id, 0))
    # Chave robusta contra alterações dinâmicas no frontend (What-If)
    cache_key = (
        current.id,
        current.start_time,
        current.end_time,
        getattr(current, "destination_id", None),
        nxt.id,
        nxt.start_time,
        nxt.end_time,
        getattr(nxt, "origin_id", None),
        deadhead,
        params_key,
    )
    if cache_key in _EDGE_FEASIBILITY_CACHE:
        _EDGE_FEASIBILITY_CACHE.move_to_end(cache_key)
        return _EDGE_FEASIBILITY_CACHE[cache_key]

    res = _is_connection_feasible_logic(
        current,
        nxt,
        min_layover=min_layover,
        min_break=min_break,
        enforce_min_interval=enforce_min_interval,
        connection_tolerance=connection_tolerance,
        strict_zero_gap_validation=strict_zero_gap_validation,
        strict_operational_mode=strict_operational_mode,
        strict_hard_constraints=strict_hard_constraints,
    )

    if len(_EDGE_FEASIBILITY_CACHE) >= 20000:
        _EDGE_FEASIBILITY_CACHE.popitem(last=False)
    _EDGE_FEASIBILITY_CACHE[cache_key] = res
    return res


def _is_connection_feasible_logic(
    current: Trip,
    nxt: Trip,
    *,
    min_layover: int = 8,
    min_break: int = 30,
    enforce_min_interval: bool = False,
    connection_tolerance: int = 0,
    strict_zero_gap_validation: bool = False,
    strict_operational_mode: bool = False,
    strict_hard_constraints: bool = False,
) -> bool:
    """Centraliza a lógica de viabilidade de conexão VSP.

    Regras:
    1. gap < 0: Inviável (sobreposição).
    2. gap == 0: Só viável se for mesmo trip_group_id ou continuação de segmento.
    3. enforce_min_interval and gap < min_layover: Inviável (tempo técnico de terminal).
       Nota: min_break (descanso CCT do motorista) é aplicado no CSP, NÃO aqui.
       O veículo pode operar continuamente — apenas min_layover (tempo de
       terminal/turnaround) é exigido entre viagens consecutivas no mesmo bloco.
    4. gap + tolerance < max(min_layover, deadhead): Inviável (deadhead operacional).
    """
    gap = int(nxt.start_time) - int(current.end_time)

    if gap < 0:
        return False

    is_contiguous_pair = (
        gap == 0
        and getattr(current, "trip_group_id", None) is not None
        and current.trip_group_id == getattr(nxt, "trip_group_id", None)
    )

    is_same_trip_segment = False
    if hasattr(nxt, "is_continuation_of"):
        is_same_trip_segment = nxt.is_continuation_of(current)

    if gap == 0:
        if not (is_contiguous_pair or is_same_trip_segment):
            return False

        # Upgrade de qualidade: validação geográfica em gap zero
        if strict_zero_gap_validation:
            if getattr(current, "destination_id", None) != getattr(nxt, "origin_id", None):
                return False

        return True

    # BUG FIX: Previously used min_break (driver CCT, e.g. 30 min) here,
    # which is a DRIVER rest constraint — not a VEHICLE constraint.
    # The vehicle can operate continuously; only min_layover (technical
    # terminal turnaround, e.g. 10 min) is required between trips.
    # min_break is correctly enforced in the CSP (crew scheduling).
    if enforce_min_interval and gap < min_layover:
        return False

    deadhead = int(current.deadhead_times.get(nxt.origin_id, 0))
    required = max(min_layover, deadhead)

    # 4. Strict Hard Constraints: Rejeita tolerâncias (Segurança operacional total)
    if strict_operational_mode or strict_hard_constraints:
        return gap >= required

    # 5. Fallback com tolerância
    return (gap + connection_tolerance) >= required



def extract_connection_params(vsp_params: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai e padroniza parâmetros de conexão do vsp_params."""
    return {
        "min_layover": int(vsp_params.get("min_layover_minutes", 8) or 8),
        "min_break": int(vsp_params.get("min_break_minutes", 30) or 30),
        "enforce_min_interval": bool(vsp_params.get("enforce_min_interval", False)),
        "connection_tolerance": int(vsp_params.get("connection_tolerance_minutes", 0) or 0),
        "allow_multi_line": bool(vsp_params.get("allow_multi_line_block", True)),
        "max_vehicle_shift": int(vsp_params.get("max_vehicle_shift_minutes", 960) or 960),
        "strict_zero_gap_validation": bool(vsp_params.get("strict_zero_gap_validation", False)),
        "strict_operational_mode": bool(vsp_params.get("strict_operational_mode", False)),
        "strict_hard_constraints": bool(vsp_params.get("strict_hard_constraints", False)),
    }


def compute_idle_cost(gap: int, vsp_params: Dict[str, Any]) -> float:
    """Calcula custo de ociosidade (idle) padronizado."""
    return gap * float(vsp_params.get("idle_cost_per_minute", 0.25))


def sort_block_trips(blocks: List[Block]) -> None:
    """Ordena in-place a lista interna de cada bloco de forma segura."""
    for b in blocks:
        if b.trips:
            b.trips = sorted(b.trips, key=lambda t: t.start_time)


def quick_cost_sorted(
    blocks: List[Block],
    fixed_vehicle_cost: float = 800.0,
    idle_cost_per_minute: float = 0.5,
    max_work_minutes: float = 480.0,
    crew_cost_weight: float = 400.0,
    deadhead_cost_per_minute: float = 1.0,
) -> float:
    """Estimativa de custo rápida (compatibilidade com Block).

    BUG-PIPELINE-03 (corrigido 2026-06-02): parâmetro deadhead_cost_per_minute
    não era repassado para quick_cost_from_trips. Com deadhead=R$10/min (Empresa 16),
    o pipeline não conseguia distinguir soluções SA (menos deadhead) de MCNF, e
    sempre selecionava MCNF mesmo sendo inferior pelo objetivo real.
    """
    return quick_cost_from_trips(
        [b.trips for b in blocks], fixed_vehicle_cost, idle_cost_per_minute,
        max_work_minutes, crew_cost_weight, deadhead_cost_per_minute
    )


def quick_cost_from_trips(
    sequences: List[List[Trip]],
    fixed_vehicle_cost: float = 800.0,
    idle_cost_per_minute: float = 0.5,
    max_work_minutes: float = 480.0,
    crew_cost_weight: float = 400.0,
    deadhead_cost_per_minute: float = 1.0,
) -> float:
    """
    Estimativa de custo ultra-rápida usando float puro para metaheurísticas.

    O termo de deadhead distingue conexões no mesmo terminal (deadhead=0) de
    conexões cruzando terminais (deadhead>0, que queimam combustível/tripulação).
    Sem ele o proxy só enxerga o gap ocioso e as metaheurísticas (SA/Tabu)
    encadeiam viagens cross-terminal de baixo gap mas alto custo real.
    """
    import math

    total = 0.0
    for trips in sequences:
        if not trips:
            continue
        total += fixed_vehicle_cost

        # Uso de gerador para evitar alocação de lista extra no sum()
        block_work = sum(t.duration for t in trips)

        if max_work_minutes > 0:
            block_spread = trips[-1].end_time - trips[0].start_time
            # math.ceil é significativamente mais rápido que Decimal operations
            min_crew_work = math.ceil(block_work / max_work_minutes)
            min_crew_spread = math.ceil(block_spread / (max_work_minutes + 80.0))
            min_crew = max(min_crew_work, min_crew_spread)
            total += max(0.0, float(min_crew - 1)) * crew_cost_weight

        for i in range(len(trips) - 1):
            cur = trips[i]
            nxt = trips[i + 1]
            gap = nxt.start_time - cur.end_time
            if gap < 0:
                total += abs(gap) * 50.0  # Penalidade forte por overlap
            else:
                total += gap * idle_cost_per_minute
                if deadhead_cost_per_minute and cur.deadhead_times:
                    deadhead = cur.deadhead_times.get(nxt.origin_id, 0)
                    if deadhead:
                        total += deadhead * deadhead_cost_per_minute
    return total


def preferred_pair_penalty(
    blocks: List[Block],
    preferred_pairs: Dict[int, int],
    pair_break_penalty: float = 1000.0,
    paired_trip_bonus: float = 40.0,
    hard_pairing_penalty: float = 0.0,
) -> float:
    """Pontua preservação de pares preferenciais (compatibilidade com Block)."""
    return preferred_pair_penalty_from_trips(
        [b.trips for b in blocks], preferred_pairs, pair_break_penalty, paired_trip_bonus, hard_pairing_penalty
    )


def preferred_pair_penalty_from_trips(
    sequences: List[List[Trip]],
    preferred_pairs: Dict[int, int],
    pair_break_penalty: float = 1000.0,
    paired_trip_bonus: float = 40.0,
    hard_pairing_penalty: float = 0.0,
) -> float:
    """
    Pontua preservação de pares preferenciais usando float puro para performance.
    """
    if not preferred_pairs:
        return 0.0

    trip_to_block_idx: Dict[int, int] = {}
    consecutive_pairs: set[Tuple[int, int]] = set()

    for idx, trips in enumerate(sequences):
        for trip in trips:
            trip_to_block_idx[trip.id] = idx
        for i in range(len(trips) - 1):
            curr = trips[i]
            nxt = trips[i + 1]
            if preferred_pairs.get(curr.id) == nxt.id:
                # Usa tupla ordenada como chave de par
                consecutive_pairs.add(tuple(sorted((curr.id, nxt.id))))

    total = 0.0
    seen_pairs: set[Tuple[int, int]] = set()

    for trip_id, pair_id in preferred_pairs.items():
        signature = tuple(sorted((trip_id, pair_id)))
        if signature in seen_pairs:
            continue
        seen_pairs.add(signature)

        b_idx_a = trip_to_block_idx.get(trip_id)
        b_idx_b = trip_to_block_idx.get(pair_id)

        if signature in consecutive_pairs:
            total -= paired_trip_bonus
        elif b_idx_a is None or b_idx_b is None or b_idx_a != b_idx_b:
            total += hard_pairing_penalty if hard_pairing_penalty != 0 else pair_break_penalty
        else:
            total += pair_break_penalty

    return total


# Cache global de viabilidade de blocos para evitar recomputação massiva.
# PERF: Chave leve usa só IDs (O(n)) no hot path; versão completa (O(5n)) só
#       para debug/what-if, controlada pelo flag `strict_cache`.
def is_block_feasible(
    trips: List[Trip],
    vsp_params: Dict[str, Any],
    *,
    strict_cache: bool = False,
) -> bool:
    """Verifica se uma sequência de viagens é viável como um bloco único com cache LRU.

    Args:
        strict_cache: Se True, inclui timestamps e IDs geográficos na chave do cache
                      para evitar falsos positivos em cenários de what-if/simulação.
                      Se False (padrão), usa apenas IDs — mais rápido nos loops internos.
    """
    if len(trips) <= 1:
        return True

    p = extract_connection_params(vsp_params)
    params_key = frozenset(p.items())

    if strict_cache:
        # Versão completa: segura para what-if onde a trip pode mudar atributos relevantes.
        trips_key = tuple(
            (
                t.id,
                t.start_time,
                t.end_time,
                t.origin_id,
                t.destination_id,
                getattr(t, "line_id", None),
                int(t.deadhead_times.get(trips[i + 1].origin_id, 0)) if i < len(trips) - 1 else None,
            )
            for i, t in enumerate(trips)
        )
    else:
        # Chave ainda leve, mas inclui os campos que alteram viabilidade.
        trips_key = tuple(
            (
                t.id,
                t.start_time,
                t.end_time,
                int(t.deadhead_times.get(trips[i + 1].origin_id, 0)) if i < len(trips) - 1 else None,
            )
            for i, t in enumerate(trips)
        )

    cache_key = (trips_key, params_key)

    if cache_key in _FEASIBILITY_CACHE:
        _FEASIBILITY_CACHE.move_to_end(cache_key)  # LRU
        return _FEASIBILITY_CACHE[cache_key]

    # 1. Verificar max shift (verificação barata → short-circuit)
    if p["max_vehicle_shift"] > 0 and (trips[-1].end_time - trips[0].start_time) > p["max_vehicle_shift"]:
        res = False
    else:
        # 2. Verificar multi-line
        if not p["allow_multi_line"]:
            lines = {int(t.line_id) for t in trips if getattr(t, "line_id", None) is not None}
            res = len(lines) <= 1
        else:
            res = True

        if res:
            # 3. Verificar conexões par a par
            for i in range(len(trips) - 1):
                if not is_connection_feasible(
                    trips[i],
                    trips[i + 1],
                    min_layover=p["min_layover"],
                    min_break=p["min_break"],
                    enforce_min_interval=p["enforce_min_interval"],
                    connection_tolerance=p["connection_tolerance"],
                    strict_zero_gap_validation=p["strict_zero_gap_validation"],
                    strict_operational_mode=p["strict_operational_mode"],
                    strict_hard_constraints=p["strict_hard_constraints"],
                ):
                    res = False
                    break

    # Ejeção LRU: remove o menos recentemente usado quando o cache está cheio
    if len(_FEASIBILITY_CACHE) >= 10000:
        _FEASIBILITY_CACHE.popitem(last=False)

    _FEASIBILITY_CACHE[cache_key] = res
    return res


def compute_block_gap_stats(trips: List[Trip]) -> Dict[str, Any]:
    """Calcula estatísticas de gap para fins de benchmark e auditoria."""
    if len(trips) < 2:
        return {"min_gap": 0, "max_gap": 0, "avg_gap": 0, "gap_count": 0, "negative_gaps": 0}

    gaps = [trips[i + 1].start_time - trips[i].end_time for i in range(len(trips) - 1)]
    negative = sum(1 for g in gaps if g < 0)
    return {
        "min_gap": min(gaps),
        "max_gap": max(gaps),
        "avg_gap": round(sum(gaps) / len(gaps), 1),
        "gap_count": len(gaps),
        "negative_gaps": negative,
    }


class ConstraintEngine:
    """Centraliza a lógica de restrições e viabilidade do solver (ConstraintEngine)."""

    def __init__(self, vsp_params: Dict[str, Any]):
        self.vsp_params = vsp_params
        self.p = extract_connection_params(vsp_params)

    def is_connection_feasible(self, current: Trip, nxt: Trip) -> bool:
        """Verifica se a conexão entre duas viagens é viável."""
        return is_connection_feasible(
            current,
            nxt,
            min_layover=self.p["min_layover"],
            min_break=self.p["min_break"],
            enforce_min_interval=self.p["enforce_min_interval"],
            connection_tolerance=self.p["connection_tolerance"],
            strict_zero_gap_validation=self.p["strict_zero_gap_validation"],
            strict_operational_mode=self.p["strict_operational_mode"],
            strict_hard_constraints=self.p["strict_hard_constraints"],
        )

    def is_block_feasible(self, trips: List[Trip]) -> bool:
        """Verifica se a sequência completa de viagens de um bloco é viável."""
        return is_block_feasible(trips, self.vsp_params)

    def compute_idle_cost(self, gap_minutes: int) -> float:
        """Calcula o custo de ociosidade padronizado."""
        return compute_idle_cost(gap_minutes, self.vsp_params)
