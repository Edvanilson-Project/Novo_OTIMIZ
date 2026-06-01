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
import logging
from typing import Dict, List, Optional

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from .greedy import GreedyVSP, build_preferred_pairs
from ..utils import (
    is_connection_feasible,
    quick_cost_from_trips,
    preferred_pair_penalty_from_trips,
    select_vehicle_type,
)

settings = get_settings()
logger = logging.getLogger(__name__)


def _blocks_are_feasible(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
    min_break: int = 30,
    enforce_min_interval: bool = False,
    connection_tolerance: int = 0,
    strict_zero_gap_validation: bool = False,
    strict_operational_mode: bool = False,
    strict_hard_constraints: bool = False,
    same_depot_required: bool = False,
) -> bool:
    """Verifica viabilidade dos blocos usando trip_map (acesso O(1))."""
    for block in state:
        if not block:
            continue

        if same_depot_required:
            depots = {trip_map[tid].depot_id for tid in block if trip_map[tid].depot_id is not None}
            if len(depots) > 1:
                return False

        for i in range(len(block) - 1):
            if not is_connection_feasible(
                trip_map[block[i]],
                trip_map[block[i + 1]],
                min_layover=min_gap,
                min_break=min_break,
                enforce_min_interval=enforce_min_interval,
                connection_tolerance=connection_tolerance,
                strict_zero_gap_validation=strict_zero_gap_validation,
                strict_operational_mode=strict_operational_mode,
                strict_hard_constraints=strict_hard_constraints,
            ):
                return False

    return True


def _copy_state(state: List[List[int]]) -> List[List[int]]:
    """Cópia profunda eficiente do estado (lista de listas de ints)."""
    return [block[:] for block in state]


def _reloc(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
    **kwargs,
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
    state[dst].sort(key=lambda tid: trip_map[tid].start_time)

    state = [b for b in state if b]

    if not _blocks_are_feasible(
        state,
        trip_map,
        min_gap,
        kwargs.get("min_break", 30),
        kwargs.get("enforce_min_interval", False),
        kwargs.get("connection_tolerance", 0),
        kwargs.get("strict_zero_gap_validation", kwargs.get("strict_zero_gap_validation", False)),
        kwargs.get("strict_operational_mode", kwargs.get("strict_operational_mode", False)),
        kwargs.get("strict_hard_constraints", kwargs.get("strict_hard_constraints", False)),
    ):
        return original

    return state


def _swap2(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
    **kwargs,
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

    if not _blocks_are_feasible(
        state,
        trip_map,
        min_gap,
        kwargs.get("min_break", 30),
        kwargs.get("enforce_min_interval", False),
        kwargs.get("connection_tolerance", 0),
        kwargs.get("strict_zero_gap_validation", kwargs.get("strict_zero_gap_validation", False)),
        kwargs.get("strict_operational_mode", kwargs.get("strict_operational_mode", False)),
        kwargs.get("strict_hard_constraints", kwargs.get("strict_hard_constraints", False)),
    ):
        return original

    return state


def _split(
    state: List[List[int]],
    trip_map: Dict[int, Trip] = None,
    min_gap: int = 8,
    **kwargs,
) -> Optional[List[List[int]]]:
    """Divide um bloco aleatório em dois na posição aleatória."""
    if not state:
        return None

    original = _copy_state(state)
    state = _copy_state(state)

    idx = random.randint(0, len(state) - 1)
    if len(state[idx]) < 2:
        return None

    cut = random.randint(1, len(state[idx]) - 1)
    new_block = state[idx][cut:]
    state[idx] = state[idx][:cut]

    if new_block:
        state.append(new_block)

    if trip_map is not None and not _blocks_are_feasible(
        state,
        trip_map,
        min_gap,
        kwargs.get("min_break", 30),
        kwargs.get("enforce_min_interval", False),
        kwargs.get("connection_tolerance", 0),
        kwargs.get("strict_zero_gap_validation", False),
        kwargs.get("strict_operational_mode", False),
        kwargs.get("strict_hard_constraints", False),
    ):
        return original

    return state


def _merge(
    state: List[List[int]],
    trip_map: Dict[int, Trip],
    min_gap: int = 8,
    **kwargs,
) -> Optional[List[List[int]]]:
    """Combina dois blocos em um, reduzindo o número de veículos."""
    if len(state) < 2:
        return None

    original = _copy_state(state)
    i, j = sorted(random.sample(range(len(state)), 2))
    merged_block = [*state[i], *state[j]]
    del state[j]
    state[i] = merged_block
    state[i].sort(key=lambda tid: trip_map[tid].start_time)

    if not _blocks_are_feasible(
        state,
        trip_map,
        min_gap,
        kwargs.get("min_break", 30),
        kwargs.get("enforce_min_interval", False),
        kwargs.get("connection_tolerance", 0),
        kwargs.get("strict_zero_gap_validation", kwargs.get("strict_zero_gap_validation", False)),
        kwargs.get("strict_operational_mode", kwargs.get("strict_operational_mode", False)),
        kwargs.get("strict_hard_constraints", kwargs.get("strict_hard_constraints", False)),
    ):
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
        vehicle_type_id: Optional[int] = None,
    ) -> List[Block]:
        """Reconstrói objetos Block a partir do estado leve (final do algoritmo).

        vehicle_type_id rotula cada bloco com o tipo de veículo mais barato (como
        o greedy faz). Sem isso o CostEvaluator usa o veículo default caro
        (custo fixo/hora padrão), inflando o custo final sem mudar a escala.
        """
        blocks = []
        for block_ids in state:
            if not block_ids:
                continue
            trips = [trip_map[tid] for tid in block_ids]
            block = Block(
                id=self._next_block_id(),
                trips=trips,
                vehicle_type_id=vehicle_type_id,
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
        min_break = self.vsp_params.get("min_break_minutes", 30)
        enforce_min_interval = bool(self.vsp_params.get("enforce_min_interval", False))
        connection_tolerance = int(self.vsp_params.get("connection_tolerance_minutes", 0))
        strict_zgv = bool(self.vsp_params.get("strict_zero_gap_validation", False))
        strict_som = bool(self.vsp_params.get("strict_operational_mode", False))
        strict_shc = bool(self.vsp_params.get("strict_hard_constraints", False))
        same_depot_req = bool(self.vsp_params.get("same_depot_required", False))

        preferred_pairs = (
            build_preferred_pairs(
                trips,
                min_gap,
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

        dhc = float(self.vsp_params.get("deadhead_cost_per_minute", 1.0))

        def cost_fn(state: List[List[int]]) -> float:
            sequences = [[trip_map[tid] for tid in block if tid in trip_map] for block in state]
            base = quick_cost_from_trips(sequences, fvc, icpm, max_work, crew_cw, dhc)
            pairs = preferred_pair_penalty_from_trips(
                sequences,
                preferred_pairs,
                pair_break_penalty,
                paired_trip_bonus,
                hard_pairing_penalty,
            )
            return base + pairs

        current_sol = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types)

        current_state = [[t.id for t in block.trips] for block in current_sol.blocks]
        current_cost = cost_fn(current_state)

        best_state = _copy_state(current_state)
        best_cost = current_cost

        min_temp = float(settings.sa_min_temp)
        iterations_per_temp = int(settings.sa_iterations_per_temp)
        max_iterations = int(self.vsp_params.get("sa_max_iterations", settings.sa_max_iterations))
        iteration = 0
        restarts = 0

        while iteration < max_iterations and not self._check_timeout():
            temp = self.initial_temp

            if restarts > 0:
                current_state = _copy_state(best_state)
                current_cost = best_cost
                # Perturbação mais agressiva para escapar de ótimos locais
                for _ in range(min(10 + restarts * 2, 50)):
                    op = random.choice(_OPERATORS)
                    perturbed = op(
                        current_state,
                        trip_map=trip_map,
                        min_gap=min_gap,
                        min_break=int(min_break) if min_break is not None else 30,
                        enforce_min_interval=enforce_min_interval,
                        connection_tolerance=connection_tolerance,
                        strict_zero_gap_validation=strict_zgv,
                        strict_operational_mode=strict_som,
                        strict_hard_constraints=strict_shc,
                        same_depot_required=same_depot_req,
                    )
                    if perturbed:
                        current_state = perturbed
                        current_cost = cost_fn(current_state)

            while temp > min_temp and not self._check_timeout():
                # Executa um bloco de iterações na mesma temperatura (estabilização térmica)
                for _ in range(iterations_per_temp):
                    if self._check_timeout():
                        break

                    iteration += 1
                    op = random.choice(_OPERATORS)
                    candidate = op(
                        current_state,
                        trip_map=trip_map,
                        min_gap=min_gap,
                        min_break=int(min_break) if min_break is not None else 30,
                        enforce_min_interval=enforce_min_interval,
                        connection_tolerance=connection_tolerance,
                        strict_zero_gap_validation=strict_zgv,
                        strict_operational_mode=strict_som,
                        strict_hard_constraints=strict_shc,
                        same_depot_required=same_depot_req,
                    )

                    if not candidate:
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

        selected_vt = select_vehicle_type(vehicle_types, depot_id)
        best_blocks = self._state_to_blocks(
            best_state, trip_map, selected_vt.id if selected_vt else None
        )

        for block in best_blocks:
            block.trips.sort(key=lambda t: t.start_time)

        return VSPSolution(
            blocks=best_blocks,
            algorithm=self.name,
            iterations=iteration,
            elapsed_ms=self._elapsed_ms(),
            meta={"restarts": restarts},
        )
