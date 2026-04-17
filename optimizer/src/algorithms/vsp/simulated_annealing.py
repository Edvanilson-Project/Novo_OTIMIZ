"""
VSP — Simulated Annealing (SA) OTIMIZADO.

Estado interno: List[List[int]] (blocos como listas de trip_ids).
Isso elimina o overhead de instanciação de classes Block e Trip durante
o loop de otimização, proporcionando ganhos significativos de performance.

Vizinhança: três operadores de perturbação
  1. Reloc  — move 1 viagem para outro bloco
  2. Swap2  — troca 1 viagem entre dois blocos distintos
  3. Split  — divide um bloco em dois em posição aleatória
Aceita soluções piores com P = exp(-Δcost / T).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from .greedy import GreedyVSP, build_preferred_pairs

settings = get_settings()


def _quick_cost(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    fixed_vehicle_cost: float = 800.0,
    idle_cost_per_minute: float = 0.5,
    max_work_minutes: float = 480.0,
    crew_cost_weight: float = 400.0,
) -> float:
    """Calcula custo rápido usando trip_map para acesso O(1) aos dados das viagens."""
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
    """Verifica viabilidade dos blocos usando trip_map (acesso O(1))."""
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


def _reloc(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
) -> Optional[List[List[int]]]:
    """Move 1 viagem aleatória de um bloco para outro."""
    if len(state) < 2:
        return None
    
    original = _copy_state(state)
    src = random.randint(0, len(state) - 1)
    if not state[src]:
        return None
    
    trip_idx = random.randint(0, len(state[src]) - 1)
    trip_id = state[src][trip_idx]
    del state[src][trip_idx]
    
    dst = random.choice([i for i in range(len(state)) if i != src])
    state[dst].append(trip_id)
    
    state = [b for b in state if b]
    
    if not _blocks_are_feasible(state, trip_map, min_gap):
        return original
    
    return state


def _swap2(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
) -> Optional[List[List[int]]]:
    """Troca 1 viagem entre dois blocos distintos."""
    if len(state) < 2:
        return None
    
    original = _copy_state(state)
    i, j = random.sample(range(len(state)), 2)
    if not state[i] or not state[j]:
        return None
    
    ii = random.randint(0, len(state[i]) - 1)
    jj = random.randint(0, len(state[j]) - 1)
    state[i][ii], state[j][jj] = state[j][jj], state[i][ii]
    
    for block in state:
        block.sort(key=lambda tid: trip_map[tid].start_time)
    
    if not _blocks_are_feasible(state, trip_map, min_gap):
        return original
    
    return state


def _split(
    state: List[List[int]],
) -> Optional[List[List[int]]]:
    """Divide um bloco aleatório em dois na posição aleatória."""
    if not state:
        return None
    
    state = _copy_state(state)
    idx = random.randint(0, len(state) - 1)
    if len(state[idx]) < 2:
        return None
    
    cut = random.randint(1, len(state[idx]) - 1)
    new_block = state[idx][cut:]
    state[idx] = state[idx][:cut]
    
    if new_block:
        state.append(new_block)
    
    return state


def _merge(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
) -> Optional[List[List[int]]]:
    """Combina dois blocos em um, reduzindo o número de veículos."""
    if len(state) < 2:
        return None
    
    original = _copy_state(state)
    i, j = random.sample(range(len(state)), 2)
    state[i].extend(state[j])
    del state[j]
    
    for block in state:
        block.sort(key=lambda tid: trip_map[tid].start_time)
    
    if not _blocks_are_feasible(state, trip_map, min_gap):
        return original
    
    return state


_OPERATORS = [_reloc, _swap2, _split, _merge]


class SimulatedAnnealingVSP(BaseAlgorithm, IVSPAlgorithm):
    """SA para VSP com resfriamento geométrico (versão otimizada)."""

    def __init__(self, vsp_params=None):
        super().__init__(name="sa_vsp", time_budget_s=settings.hybrid_time_budget_seconds)
        self.initial_temp = float(settings.sa_initial_temp)
        self.cooling_rate = float(settings.sa_cooling_rate)
        self.vsp_params = vsp_params or {}
        self._block_counter = 0

    def _next_block_id(self) -> int:
        self._block_counter += 1
        return self._block_counter

    def _state_to_blocks(
        self,
        state: List[List[int]],
        trip_map: Dict[int, Trip],
    ) -> List[Block]:
        """Reconstrói objetos Block a partir do estado leve (final do algoritmo)."""
        blocks = []
        for block_ids in state:
            if not block_ids:
                continue
            trips = [trip_map[tid] for tid in block_ids]
            block = Block(
                id=self._next_block_id(),
                trips=trips,
            )
            blocks.append(block)
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

        min_temp = 0.1
        iteration = 0
        restarts = 0

        while not self._check_timeout():
            temp = self.initial_temp
            
            if restarts > 0:
                current_state = _copy_state(best_state)
                current_cost = best_cost
                for _ in range(min(5 + restarts, 20)):
                    op = random.choice(_OPERATORS)
                    if op is _split:
                        perturbed = _split(current_state)
                    else:
                        perturbed = op(current_state, trip_map, min_gap)
                    if perturbed:
                        current_state = perturbed
                        current_cost = cost_fn(current_state)

            while temp > min_temp and not self._check_timeout():
                iteration += 1

                op = random.choice(_OPERATORS)
                if op is _split:
                    candidate = _split(current_state)
                else:
                    candidate = op(current_state, trip_map, min_gap)

                if not candidate:
                    temp *= self.cooling_rate
                    continue

                candidate_cost = cost_fn(candidate)
                delta = candidate_cost - current_cost

                if delta < 0 or math.exp(-delta / temp) > random.random():
                    current_state = candidate
                    current_cost = candidate_cost

                if current_cost < best_cost:
                    best_state = _copy_state(current_state)
                    best_cost = current_cost

                temp *= self.cooling_rate

            restarts += 1

        best_blocks = self._state_to_blocks(best_state, trip_map)
        
        for block in best_blocks:
            block.trips.sort(key=lambda t: t.start_time)

        return VSPSolution(
            blocks=best_blocks,
            algorithm=self.name,
            iterations=iteration,
            elapsed_ms=self._elapsed_ms(),
            meta={"restarts": restarts},
        )