"""
Utilitários compartilhados pelos algoritmos de busca (SA, TS, GA).

Funções:
  - sort_block_trips(blocks)    — re-ordena viagens por start_time em cada bloco
  - block_is_feasible(block)    — verifica sobreposição básica (gap >= 0) 
  - blocks_are_feasible(blocks) — verifica todos os blocos
  - quick_cost_sorted(blocks)   — custo rápido com trips já ordenadas
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..domain.models import Block


def sort_block_trips(blocks: List[Block]) -> List[Block]:
    """
    Ordena as viagens dentro de cada bloco por start_time.
    Retorna os mesmos objetos (modifica in-place).
    """
    for b in blocks:
        b.trips.sort(key=lambda t: (t.start_time, t.end_time))
    return blocks


def block_is_feasible(block: Block, min_gap: int = 8) -> bool:
    """
    Retorna True se as viagens no bloco não se sobrepõem e o gap é suficiente.
    - gap >= max(min_gap, deadhead_times) entre o fim de uma viagem e o início da próxima
    - deadhead_times codifica layover mínimo por terminal
    - Contiguous trip_group pairs (ida/volta with gap=0) are exempt
    Presume que trips estão ordenadas por start_time.
    """
    trips = block.trips
    for i in range(len(trips) - 1):
        cur = trips[i]
        nxt = trips[i + 1]
        gap = nxt.start_time - cur.end_time
        # Contiguous trip_group pair (ida/volta): no layover needed
        if (
            gap == 0
            and getattr(cur, "trip_group_id", None) is not None
            and cur.trip_group_id == getattr(nxt, "trip_group_id", None)
        ):
            continue
        dest = cur.destination_id
        orig = nxt.origin_id
        if gap < min_gap:
            return False
        needed_deadhead = int(cur.deadhead_times.get(orig, 0))
        if gap < max(min_gap, needed_deadhead):
            return False
        # Cross-line é permitido quando allow_multi_line_block=true (default)
    return True


def blocks_are_feasible(blocks: List[Block], min_gap: int = 8) -> bool:
    """Retorna True se TODOS os blocos são fisicamente viáveis."""
    return all(block_is_feasible(b, min_gap) for b in blocks)


def quick_cost_sorted(
    blocks: List[Block],
    fixed_vehicle_cost: float = 800.0,
    idle_cost_per_minute: float = 0.5,
    max_work_minutes: float = 480.0,
    crew_cost_weight: float = 400.0,
) -> float:
    """
    Estimativa de custo rápida para SA/Tabu/GA.
    Considera veículos, ociosidade E tripulação estimada.
    - crew_cost_weight: custo de cada tripulante extra necessário no bloco
    - max_work_minutes: jornada máxima de trabalho (além disso, precisa outro tripulante)
    """
    total = 0.0
    for b in blocks:
        trips = b.trips  # assumes sort_block_trips() already called
        total += fixed_vehicle_cost
        block_work = sum(t.duration for t in trips)
        if trips and max_work_minutes > 0:
            block_spread = trips[-1].end_time - trips[0].start_time
            min_crew = max(
                -(-block_work // int(max_work_minutes)),  # ceil division by work
                -(-block_spread // int(max_work_minutes + 80)),  # ceil division by spread
            )
            total += max(0, min_crew - 1) * crew_cost_weight
        for i in range(len(trips) - 1):
            gap = trips[i + 1].start_time - trips[i].end_time
            if gap < 0:
                total += abs(gap) * 50.0  # penalidade forte por overlap
            else:
                total += gap * idle_cost_per_minute
    return total


def preferred_pair_penalty(
    blocks: List[Block],
    preferred_pairs: Dict[int, int],
    pair_break_penalty: float = 1000.0,
    paired_trip_bonus: float = 40.0,
    hard_pairing_penalty: float = 0.0,
) -> float:
    """Pontua preservação de pares preferenciais/trip_group no VSP."""
    if not preferred_pairs:
        return 0.0

    trip_to_block: Dict[int, int] = {}
    consecutive_pairs: set[Tuple[int, int]] = set()
    for block in blocks:
        for trip in block.trips:
            trip_to_block[trip.id] = block.id
        for index in range(len(block.trips) - 1):
            current = block.trips[index]
            nxt = block.trips[index + 1]
            if preferred_pairs.get(current.id) == nxt.id:
                consecutive_pairs.add(tuple(sorted((current.id, nxt.id))))

    total = 0.0
    seen_pairs: set[Tuple[int, int]] = set()
    for trip_id, pair_id in preferred_pairs.items():
        signature = tuple(sorted((trip_id, pair_id)))
        if signature in seen_pairs:
            continue
        seen_pairs.add(signature)

        block_a = trip_to_block.get(trip_id)
        block_b = trip_to_block.get(pair_id)
        if signature in consecutive_pairs:
            total -= paired_trip_bonus
        elif block_a is None or block_b is None or block_a != block_b:
            total += hard_pairing_penalty or pair_break_penalty
        else:
            total += pair_break_penalty

    return total
