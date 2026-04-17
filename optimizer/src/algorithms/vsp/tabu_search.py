"""
VSP — Tabu Search (TS) OTIMIZADO.

Estado interno: List[List[int]] (blocos como listas de trip_ids).
Vizinhança: Reloc (mover 1 viagem entre blocos) + Merge.
Lista tabu: conjunto de (trip_id, from_idx, to_idx) recentemente movidos — evita reversões.
Critério de aspiração: aceita movimento tabu se melhora o global.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from .greedy import GreedyVSP, build_preferred_pairs

settings = get_settings()

Move = Tuple[int, int, int, int]


def _quick_cost(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    fixed_vehicle_cost: float = 800.0,
    idle_cost_per_minute: float = 0.5,
    max_work_minutes: float = 480.0,
    crew_cost_weight: float = 400.0,
) -> float:
    """Calcula custo rápido usando trip_map para acesso O(1)."""
    vehicle_cost = len(state) * fixed_vehicle_cost
    idle_time = 0
    work_time = 0
    
    for block in state:
        if not block:
            continue
        first_trip = trip_map[block[0]]
        last_trip = trip_map[block[-1]]
        block_start = first_trip.start_time
        block_end = last_trip.end_time
        idle_time += (block_end - block_start)
        for tid in block:
            work_time += trip_map[tid].duration
    
    idle_penalty = idle_time * idle_cost_per_minute
    crew_penalty = max(0, work_time - max_work_minutes) * crew_cost_weight
    
    return vehicle_cost + idle_penalty + crew_penalty


def _blocks_are_feasible(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
) -> bool:
    """Verifica viabilidade dos blocos usando trip_map."""
    for block in state:
        if not block:
            continue
        
        prev_end = None
        for i, tid in enumerate(block):
            trip = trip_map[tid]
            if prev_end is not None:
                gap = trip.start_time - prev_end
                if gap < min_gap:
                    return False
                needed = trip_map[block[i-1]].deadhead_times.get(trip.origin_id, 0)
                if gap < needed:
                    return False
            prev_end = trip.end_time
    
    return True


def _preferred_pair_penalty(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    preferred_pairs: Dict[int, int],
    pair_break_penalty: float,
    paired_trip_bonus: float,
    hard_pairing_penalty: float,
) -> float:
    """Calcula penalidade de pares usando trip_map."""
    penalty = 0.0
    
    for block in state:
        for i, tid in enumerate(block):
            if tid not in preferred_pairs:
                continue
            expected_partner = preferred_pairs[tid]
            next_trip = trip_map[block[i+1]] if i + 1 < len(block) else None
            
            if next_trip is None:
                penalty += pair_break_penalty
            elif next_trip.id != expected_partner:
                if hard_pairing_penalty > 0:
                    penalty += hard_pairing_penalty
                else:
                    penalty += pair_break_penalty
            else:
                penalty -= paired_trip_bonus
    
    return penalty


def _copy_state(state: List[List[int]]) -> List[List[int]]:
    """Cópia profunda eficiente do estado (lista de listas de ints)."""
    return [block[:] for block in state]


def _generate_reloc_neighbours(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    sample_n: int = 30,
    min_gap: int = 8,
) -> List[Tuple[Move, List[List[int]]]]:
    """Gera até `sample_n` vizinhos via Relocation e Merge."""
    if len(state) < 2:
        return []
    
    neighbours = []
    attempts = min(sample_n * 3, len(state) * max((len(b) for b in state if b), default=1))
    seen: set = set()

    for _ in range(attempts):
        if len(neighbours) >= sample_n:
            break
        
        src_idx = random.randint(0, len(state) - 1)
        if not state[src_idx]:
            continue
        dst_idx = random.choice([i for i in range(len(state)) if i != src_idx])
        trip_pos = random.randint(0, len(state[src_idx]) - 1)
        insert_pos = random.randint(0, len(state[dst_idx]))
        key = (src_idx, trip_pos, dst_idx, insert_pos)
        if key in seen:
            continue
        seen.add(key)

        new_state = _copy_state(state)
        trip_id = new_state[src_idx].pop(trip_pos)
        new_state[dst_idx].append(trip_id)
        new_state = [b for b in new_state if b]
        
        for block in new_state:
            block.sort(key=lambda tid: trip_map[tid].start_time)
        
        if not _blocks_are_feasible(new_state, trip_map, min_gap):
            continue

        move: Move = (trip_id, src_idx, dst_idx, insert_pos)
        neighbours.append((move, new_state))

    merge_tries = min(sample_n // 3, len(state) * (len(state) - 1) // 2)
    for _ in range(merge_tries):
        if len(neighbours) >= sample_n + merge_tries:
            break
        i, j = random.sample(range(len(state)), 2)
        merge_key = ("merge", i, j, 0)
        if merge_key in seen:
            continue
        seen.add(merge_key)
        
        new_state = _copy_state(state)
        new_state[i].extend(new_state[j])
        del new_state[j]
        
        for block in new_state:
            block.sort(key=lambda tid: trip_map[tid].start_time)
        
        if not _blocks_are_feasible(new_state, trip_map, min_gap):
            continue
        
        move: Move = (-1, j, i, -1)
        neighbours.append((move, new_state))

    return neighbours


class TabuSearchVSP(BaseAlgorithm, IVSPAlgorithm):
    """Busca Tabu para VSP com lista circular e critério de aspiração (versão otimizada)."""

    def __init__(self, vsp_params=None):
        super().__init__(name="tabu_vsp", time_budget_s=settings.hybrid_time_budget_seconds)
        self.tabu_size = settings.ts_tabu_size
        self.max_iterations = settings.ts_max_iterations
        self.vsp_params = vsp_params or {}

    def _state_to_blocks(
        self,
        state: List[List[int]],
        trip_map: Dict[int, Trip],
    ) -> List[Block]:
        """Reconstrói objetos Block a partir do estado leve (final do algoritmo)."""
        blocks = []
        block_id = 1
        for block_ids in state:
            if not block_ids:
                continue
            trips = [trip_map[tid] for tid in block_ids]
            block = Block(id=block_id, trips=trips)
            blocks.append(block)
            block_id += 1
        return blocks

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)
        
        random_seed = self.vsp_params.get("random_seed")
        if random_seed is not None:
            random.seed(int(random_seed))

        trip_map: Dict[int, Trip] = {t.id: t for t in trips}

        fvc = float(self.vsp_params.get("fixed_vehicle_activation_cost", 800.0))
        icpm = float(self.vsp_params.get("idle_cost_per_minute", 0.5))
        max_work = float(self.vsp_params.get("max_work_minutes", 480.0))
        crew_cw = float(self.vsp_params.get("crew_cost_weight", fvc * 0.5))
        pair_break_penalty = float(self.vsp_params.get("pair_break_penalty", fvc * 1.25))
        paired_trip_bonus = float(self.vsp_params.get("paired_trip_bonus", fvc * 0.05))
        min_gap = int(self.vsp_params.get("min_layover_minutes", 8) or 8)
        preferred_pairs = (
            build_preferred_pairs(
                trips,
                int(self.vsp_params.get("min_layover_minutes", 8) or 8),
                int(self.vsp_params.get("preferred_pair_window_minutes", 120) or 120),
            )
            if bool(self.vsp_params.get("preserve_preferred_pairs", True))
            else {}
        )
        hard_pairing_penalty = (
            float(self.vsp_params.get("hard_pairing_penalty", max(pair_break_penalty * 10.0, fvc * 25.0)))
            if bool(self.vsp_params.get("hard_pairing_vehicle_level", False))
            else 0.0
        )

        def cost_fn(state: List[List[int]]) -> float:
            base = _quick_cost(state, trip_map, fvc, icpm, max_work, crew_cw)
            pairs = _preferred_pair_penalty(
                state, trip_map, preferred_pairs,
                pair_break_penalty, paired_trip_bonus, hard_pairing_penalty,
            )
            return base + pairs

        current_sol = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types)
        current_state = [[t.id for t in block.trips] for block in current_sol.blocks]
        current_cost = cost_fn(current_state)

        best_state = _copy_state(current_state)
        best_cost = current_cost

        tabu_list: Deque[Move] = deque(maxlen=self.tabu_size)
        iteration = 0
        stale_count = 0

        while not self._check_timeout():
            iteration += 1

            neighbours = _generate_reloc_neighbours(current_state, trip_map, sample_n=40, min_gap=min_gap)
            if not neighbours:
                stale_count += 1
                if stale_count > 10:
                    break
                continue

            scored = [(move, nb, cost_fn(nb)) for move, nb in neighbours]
            scored.sort(key=lambda x: x[2])

            chosen_move = None
            chosen_state = None
            chosen_cost = float("inf")

            for move, nb, cost in scored:
                if move not in tabu_list or cost < best_cost:
                    chosen_move = move
                    chosen_state = nb
                    chosen_cost = cost
                    break

            if chosen_state is None:
                chosen_move, chosen_state, chosen_cost = scored[0]

            tabu_list.append(chosen_move)
            current_state = chosen_state
            current_cost = chosen_cost

            if current_cost < best_cost:
                best_state = _copy_state(current_state)
                best_cost = current_cost
                stale_count = 0
            else:
                stale_count += 1

            if stale_count > 25:
                current_state = _copy_state(best_state)
                current_cost = best_cost
                tabu_list.clear()
                stale_count = 0

        best_blocks = self._state_to_blocks(best_state, trip_map)
        
        for block in best_blocks:
            block.trips.sort(key=lambda t: t.start_time)

        return VSPSolution(
            blocks=best_blocks,
            algorithm=self.name,
            iterations=iteration,
            elapsed_ms=self._elapsed_ms(),
        )