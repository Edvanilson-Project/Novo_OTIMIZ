"""
CSP Guloso parametrizado.

Fluxo:
1. Run-cutting: converte blocos de veículo em tarefas/peças dirigíveis.
2. Duty building: combina tarefas em jornadas legais.
3. Rostering: agrupa jornadas em escalas multi-dia respeitando descanso.

O objetivo operacional continua sendo cobrir todas as tarefas geradas, reduzindo
custos, horas extras, spread excessivo e transferências passivas.
"""
from __future__ import annotations

import copy
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

_log = logging.getLogger(__name__)

from ...core.config import get_settings
from ...domain.interfaces import ICSPAlgorithm
from ...domain.models import Block, CSPSolution, Duty, Trip
from ...services.operational_time_service import build_duty_operational_time_report
from ..base import BaseAlgorithm

settings = get_settings()

_DEF_MAX_SHIFT = getattr(settings, "cct_max_shift_minutes", 560)
_DEF_MAX_WORK = getattr(settings, "cct_max_work_minutes", 480)
_DEF_MAX_DRIVING = getattr(settings, "cct_max_driving_minutes", 270)
_DEF_MIN_BREAK = getattr(settings, "cct_min_break_minutes", 30)


from ..evaluator import _nocturnal_overlap, CostEvaluator


def _shift_type_from_minutes(minutes: int) -> str:
    minute_of_day = minutes % 1440
    if 180 <= minute_of_day < 540:
        return "early"
    if 540 <= minute_of_day < 900:
        return "mid"
    if 900 <= minute_of_day < 1260:
        return "late"
    return "night"


class GreedyCSP(BaseAlgorithm, ICSPAlgorithm):
    MAX_SHIFT_MINUTES = _DEF_MAX_SHIFT
    MAX_DRIVING_MINUTES = _DEF_MAX_DRIVING
    MIN_BREAK_MINUTES = _DEF_MIN_BREAK

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None, **params: Any):
        super().__init__(name="greedy_csp", time_budget_s=30.0)
        self.params = params
        self.vsp_params = vsp_params or {}
        self._next_synthetic_trip_id = -1

        # Sincronização com BaseOptimizationConfig
        self.max_shift = int(params.get("max_shift_minutes", _DEF_MAX_SHIFT))
        self.max_work = int(params.get("max_work_minutes", _DEF_MAX_WORK))
        self.min_work = int(params.get("min_work_minutes", 0))
        self.min_guaranteed_work = int(params.get("min_guaranteed_work_minutes", params.get("min_work_minutes", 420)))
        self.min_shift = int(params.get("min_shift_minutes", 0))
        self.overtime_limit = int(params.get("overtime_limit_minutes", 120))
        self.max_driving = int(params.get("max_driving_minutes", _DEF_MAX_DRIVING))
        self.min_break = int(params.get("min_break_minutes", _DEF_MIN_BREAK))
        self.connection_tolerance = max(0, int(params.get("connection_tolerance_minutes", 0)))
        self.mandatory_break_after = int(params.get("mandatory_break_after_minutes", self.max_driving))
        self.meal_break_minutes = int(params.get("meal_break_minutes", 0))
        self.inter_shift_rest = max(int(params.get("inter_shift_rest_minutes", 660)), 660)
        self.pullout_counts_in_driver_shift = bool(params.get("pullout_counts_in_driver_shift", True))
        self.pullback_counts_in_driver_shift = bool(params.get("pullback_counts_in_driver_shift", True))

        # Custos e Pesos
        self.cost_duty = float(params.get("cost_duty", 500.0))
        self.idle_time_is_paid = bool(params.get("idle_time_is_paid", True))
        self.waiting_time_pay_pct = float(params.get("waiting_time_pay_pct", 0.30))
        self.long_unpaid_break_limit = int(params.get("long_unpaid_break_limit_minutes", 180))
        self.long_unpaid_break_penalty_weight = float(params.get("long_unpaid_break_penalty_weight", 4.0))
        
        # Parâmetros Noturnos
        self.nocturnal_start_hour = int(params.get("nocturnal_start_hour", 22))
        self.nocturnal_end_hour = int(params.get("nocturnal_end_hour", 5))
        self.nocturnal_extra_pct = float(params.get("nocturnal_extra_pct", 0.20))
        self.nocturnal_factor = float(params.get("nocturnal_factor", 1.0))
        self.holiday_extra_pct = float(params.get("holiday_extra_pct", 1.0))
        
        # Regras de Operação
        self.allow_relief_points = bool(params.get("allow_relief_points", False))
        self.enforce_same_depot = bool(params.get("enforce_same_depot_start_end", False))
        self.operator_change_terminals_only = bool(params.get("operator_change_terminals_only", True))
        self.enforce_single_line_duty = bool(params.get("enforce_single_line_duty", False))
        self.operator_single_vehicle_only = bool(params.get("operator_single_vehicle_only", False))
        
        # Limites Adicionais
        self.daily_driving_limit = int(params.get("daily_driving_limit_minutes", 540))
        self.extended_daily_driving_limit = int(params.get("extended_daily_driving_limit_minutes", 600))
        self.max_extended_days = int(params.get("max_extended_driving_days_per_week", 2))
        self.max_unpaid_break = params.get("max_unpaid_break_minutes")
        if self.max_unpaid_break is not None: self.max_unpaid_break = int(self.max_unpaid_break)
        self.max_total_unpaid_break = params.get("max_total_unpaid_break_minutes")
        if self.max_total_unpaid_break is not None: self.max_total_unpaid_break = int(self.max_total_unpaid_break)
        self.weekly_driving_limit = int(params.get("weekly_driving_limit_minutes", 3360))
        self.fortnight_driving_limit = int(params.get("fortnight_driving_limit_minutes", 5400))
        self.weekly_rest = int(params.get("weekly_rest_minutes", 2700))
        self.reduced_weekly_rest = int(params.get("reduced_weekly_rest_minutes", 1440))
        self.allow_reduced_weekly_rest = bool(params.get("allow_reduced_weekly_rest", False))
        
        # Minutos de Layover/Pull
        self.min_layover = int(params.get("min_layover_minutes", self.vsp_params.get("min_layover_minutes", 8)))
        self.pullout = int(params.get("pullout_minutes", 10))
        self.pullback = int(params.get("pullback_minutes", 10))
        
        # Fairness
        self.goal_weights = dict(params.get("goal_weights") or self.vsp_params.get("goal_weights") or {})
        self.fairness_weight = float(params.get("fairness_weight", 0.0))
        self.fairness_target_work = int(params.get("fairness_target_work_minutes", 420))
        self.fairness_tolerance = int(params.get("fairness_tolerance_minutes", 30))
        self.overtime_weight = float(self.goal_weights.get("overtime", 0.0) or 0.0)
        self.spread_weight = float(self.goal_weights.get("spread", 0.0) or 0.0)
        self.passive_transfer_weight = float(self.goal_weights.get("passive_transfer", 1.0) or 1.0)
        self.operational_quality_weight = float(self.goal_weights.get("operational_quality", 1.0) or 1.0)
        self.utilization_weight = float(self.goal_weights.get("utilization", params.get("utilization_weight", 8.0)) or 8.0)
        self.idle_weight = float(self.goal_weights.get("idle", params.get("idle_weight", 1.25)) or 1.25)
        self.fragmentation_weight = float(
            self.goal_weights.get("fragmentation", params.get("fragmentation_weight", 45.0)) or 45.0
        )
        self.short_connection_weight = float(
            self.goal_weights.get("short_connection", params.get("short_connection_weight", 25.0)) or 25.0
        )
        self.min_work_soft_weight = float(
            self.goal_weights.get("min_work_soft", params.get("min_work_soft_weight", 1.5)) or 1.5
        )
        self.utilization_target = float(params.get("duty_utilization_target", 0.30) or 0.30)
        self.semantic_utilization_target = float(
            params.get("operational_semantic_utilization_target", 0.50) or 0.50
        )
        self.semantic_spread_threshold = int(
            params.get("operational_semantic_spread_threshold_minutes", 12 * 60) or 12 * 60
        )
        self.semantic_low_util_weight = float(
            self.goal_weights.get(
                "operational_semantic_low_util",
                params.get("operational_semantic_low_util_weight", 1800.0),
            )
            or 1800.0
        )
        self.semantic_rest_penalty = float(
            self.goal_weights.get(
                "operational_semantic_rest",
                params.get("operational_semantic_rest_penalty", max(60.0, self.idle_weight * 90.0)),
            )
            or max(60.0, self.idle_weight * 90.0)
        )
        self.semantic_break_count_weight = float(
            self.goal_weights.get(
                "operational_semantic_break_count",
                params.get("operational_semantic_break_count_weight", 2.5),
            )
            or 2.5
        )
        self.semantic_max_idle_weight = float(
            self.goal_weights.get(
                "operational_semantic_max_idle",
                params.get("operational_semantic_max_idle_weight", 0.15),
            )
            or 0.15
        )
        self.max_spread_soft = int(params.get("duty_max_spread_soft_minutes", 12 * 60) or 12 * 60)
        self.max_idle_soft = int(params.get("duty_max_idle_soft_minutes", 180) or 180)
        self.min_work_soft = int(
            params.get(
                "duty_min_work_soft_minutes",
                params.get("min_work_minutes", 0) or 180,
            )
            or 180
        )
        self.short_connection_threshold = int(params.get("short_connection_threshold_minutes", 15) or 15)
        self.fragmentation_soft_limit = int(params.get("duty_fragmentation_soft_limit", 2) or 2)
        self.extreme_utilization_threshold = float(
            params.get("extreme_duty_utilization_threshold", 0.25) or 0.25
        )
        self.extreme_spread_threshold = int(
            params.get(
                "extreme_duty_spread_threshold_minutes",
                self.max_spread_soft or 12 * 60,
            )
            or (self.max_spread_soft or 12 * 60)
        )
        self.extreme_total_idle_threshold = int(
            params.get(
                "extreme_duty_total_idle_threshold_minutes",
                max(self.max_idle_soft * 2, 360),
            )
            or max(self.max_idle_soft * 2, 360)
        )
        
        self.trip_group_keep_bonus = float(params.get("trip_group_keep_bonus", 240.0))
        self.trip_group_split_penalty = float(params.get("trip_group_split_penalty", 1000.0))
        self.operator_profiles = params.get("operator_profiles", [])
        self.split_break_first = int(params.get("split_break_first_minutes", 15))
        self.split_break_second = int(params.get("split_break_second_minutes", 30))
        self.strict_union_rules = bool(params.get("strict_union_rules", False))
        self.terminal_location_ids = {
            int(item)
            for item in (params.get("terminal_location_ids") or [])
            if item is not None
        }
        
        self.apply_cct = bool(params.get("apply_cct", True))
        self.enforce_min_interval = bool(
            params.get("enforce_min_interval", params.get("strict_min_interval", False))
        )
        if self.apply_cct and self.enforce_min_interval:
            # Um intervalo positivo entre viagens/tarefas do motorista não pode
            # ser menor que o intervalo mínimo parametrizado.
            self.min_layover = max(self.min_layover, self.min_break)
        
        # Inicializar Evaluador para scoring preciso se desejado
        self.evaluator = params.get("evaluator") or CostEvaluator()
        self.evaluator.set_costs(params)

        # Sanity checks de configuração — não corrige, apenas alerta. Configuração com
        # min_break < 30 não respeita CCT padrão BR para condução contínua, e
        # max_spread_soft > max_shift hard torna o gradiente soft inerte.
        if self.apply_cct and self.mandatory_break_after > 0 and self.min_break < 30:
            _log.warning(
                "[CONFIG] min_break_minutes=%d < 30 — pausa de 30min é padrão CCT após "
                "%dmin de condução contínua. Verifique se é intencional.",
                self.min_break, self.mandatory_break_after,
            )
        if self.max_shift > 0 and self.max_spread_soft > self.max_shift:
            _log.warning(
                "[CONFIG] max_spread_soft (%d) > max_shift hard (%d) — penalty soft "
                "inerte (hard rejeita antes do soft penalizar).",
                self.max_spread_soft, self.max_shift,
            )

        self._extension_diagnostics = self._empty_extension_diagnostics()

    def _block_drive(self, block: Block) -> int:
        return sum(t.duration for t in block.trips)

    def _block_regulatory_work(self, block: Block) -> int:
        real_drive = self._block_drive(block)
        if self.nocturnal_factor <= 1.0:
            return real_drive
        
        noct_min = sum(
            _nocturnal_overlap(t.start_time, t.end_time, self.nocturnal_start_hour, self.nocturnal_end_hour)
            for t in block.trips
        )
        extension = int(round(noct_min * (self.nocturnal_factor - 1.0)))
        return real_drive + extension

    def _service_day(self, block: Block) -> int:
        return block.start_time // 1440

    def _regular_overtime_minutes(self, work_minutes: int) -> int:
        if self.max_work <= 0:
            return 0
        return max(0, int(work_minutes) - self.max_work)

    def _long_unpaid_break_penalty(self, unpaid_break_minutes: float) -> float:
        excess = max(0.0, float(unpaid_break_minutes) - float(self.long_unpaid_break_limit))
        if excess <= 0.0:
            return 0.0
        tier1 = min(excess, 30.0)
        tier2 = min(max(0.0, excess - 30.0), 60.0)
        tier3 = max(0.0, excess - 90.0)
        return self.long_unpaid_break_penalty_weight * (
            tier1 * 1.0 + tier2 * 3.0 + tier3 * 10.0
        )

    def _transfer_needed(self, a: Block, b: Block) -> int:
        last = a.trips[-1]
        first = b.trips[0]
        if first.is_continuation_of(last):
            return 0
        deadhead_needed = int(
            last.deadhead_times.get(first.origin_id, 0)
        )
        return max(self.min_layover, deadhead_needed)

    def _effective_gap(self, gap: int) -> int:
        return gap + self.connection_tolerance

    def _adjustment_needed(self, gap: int, required: int) -> int:
        if gap >= required:
            return 0
        deficit = required - gap
        return deficit if deficit <= self.connection_tolerance else 0

    def _reset_synthetic_trip_ids(self, blocks: Sequence[Block]) -> None:
        existing_ids = [int(trip.id) for block in blocks for trip in block.trips]
        min_existing = min(existing_ids) if existing_ids else 0
        self._next_synthetic_trip_id = min(-1, min_existing - 1)

    def _allocate_synthetic_trip_id(self) -> int:
        synthetic_id = self._next_synthetic_trip_id
        self._next_synthetic_trip_id -= 1
        return synthetic_id

    def _split_trip_for_relief(self, trip: Trip) -> List[Trip]:
        if not self.allow_relief_points:
            return [trip]

        relief_point_id = trip.mid_trip_relief_point_id
        relief_offset = trip.mid_trip_relief_offset_minutes
        trip_duration = int(trip.duration or max(0, trip.end_time - trip.start_time))
        if (
            relief_point_id is None
            or relief_offset is None
            or trip_duration <= 0
            or int(relief_offset) <= 0
            or int(relief_offset) >= trip_duration
        ):
            return [trip]

        split_offset = int(relief_offset)
        split_time = int(trip.start_time) + split_offset
        time_ratio = split_offset / trip_duration

        # Fallback legacy approximation uses time ratio only. When the caller
        # provides physical split ratios, we prefer them for EV-sensitive cost
        # allocation.
        raw_distance_ratio = getattr(trip, "mid_trip_relief_distance_ratio", None)
        raw_elevation_ratio = getattr(trip, "mid_trip_relief_elevation_ratio", None)
        distance_ratio = float(raw_distance_ratio) if raw_distance_ratio is not None else time_ratio
        elevation_ratio = float(raw_elevation_ratio) if raw_elevation_ratio is not None else distance_ratio

        distance_ratio = min(1.0, max(0.0, distance_ratio))
        elevation_ratio = min(1.0, max(0.0, elevation_ratio))

        total_distance = float(trip.distance_km)
        total_elevation = float(trip.elevation_gain_m)
        total_energy = float(trip.energy_kwh)

        first_distance = total_distance * distance_ratio
        first_elevation = total_elevation * elevation_ratio
        energy_ratio = distance_ratio if total_elevation <= 0.0 else ((0.7 * distance_ratio) + (0.3 * elevation_ratio))

        first_segment = copy.deepcopy(trip)
        first_segment.end_time = split_time
        first_segment.duration = split_offset
        first_segment.destination_id = int(relief_point_id)
        first_segment.distance_km = first_distance
        first_segment.energy_kwh = total_energy * energy_ratio
        first_segment.elevation_gain_m = first_elevation
        first_segment.destination_latitude = None
        first_segment.destination_longitude = None
        first_segment.relief_point_id = None
        first_segment.is_relief_point = False
        first_segment.mid_trip_relief_point_id = None
        first_segment.mid_trip_relief_offset_minutes = None
        first_segment.mid_trip_relief_distance_ratio = None
        first_segment.mid_trip_relief_elevation_ratio = None
        first_segment.original_trip_id = int(trip.id)
        first_segment.segment_index = 0
        first_segment.segment_count = 2
        first_segment.trip_group_id = None
        first_segment.idle_after_minutes = 0
        first_segment.is_pull_back = False

        second_segment = copy.deepcopy(trip)
        second_segment.id = self._allocate_synthetic_trip_id()
        second_segment.start_time = split_time
        second_segment.end_time = int(trip.end_time)
        second_segment.duration = trip_duration - split_offset
        second_segment.origin_id = int(relief_point_id)
        second_segment.distance_km = max(0.0, float(trip.distance_km) - first_segment.distance_km)
        second_segment.energy_kwh = max(0.0, float(trip.energy_kwh) - first_segment.energy_kwh)
        second_segment.elevation_gain_m = max(0.0, float(trip.elevation_gain_m) - first_segment.elevation_gain_m)
        second_segment.origin_latitude = None
        second_segment.origin_longitude = None
        second_segment.relief_point_id = None
        second_segment.is_relief_point = False
        second_segment.mid_trip_relief_point_id = None
        second_segment.mid_trip_relief_offset_minutes = None
        second_segment.mid_trip_relief_distance_ratio = None
        second_segment.mid_trip_relief_elevation_ratio = None
        second_segment.original_trip_id = int(trip.id)
        second_segment.segment_index = 1
        second_segment.segment_count = 2
        second_segment.idle_before_minutes = 0
        second_segment.is_pull_out = False

        return [first_segment, second_segment]

    def _expand_block_trips_for_relief(self, block: Block) -> Tuple[List[Trip], int]:
        expanded: List[Trip] = []
        split_count = 0
        for trip in sorted(block.trips, key=lambda item: (item.start_time, item.id)):
            split_trips = self._split_trip_for_relief(trip)
            if len(split_trips) > 1:
                split_count += 1
            expanded.extend(split_trips)
        return expanded, split_count

    def _break_resets(self, state: Dict[str, Any], gap: int) -> Tuple[bool, Dict[str, Any], int]:
        state = {"credit": int(state.get("credit", 0)), "has_long": bool(state.get("has_long", False))}
        effective_gap = self._effective_gap(gap)
        reset_limit = max(self.min_break, self.meal_break_minutes)
        if effective_gap >= reset_limit:
            state["credit"] = 0
            state["has_long"] = False
            return True, state, self._adjustment_needed(gap, reset_limit)

        first_adjustment = 0
        second_adjustment = 0
        if effective_gap >= self.split_break_first:
            state["credit"] += effective_gap
            first_adjustment = self._adjustment_needed(gap, self.split_break_first)
        if effective_gap >= self.split_break_second:
            state["has_long"] = True
            second_adjustment = self._adjustment_needed(gap, self.split_break_second)
        if state["credit"] >= self.split_break_first + self.split_break_second and state["has_long"]:
            state["credit"] = 0
            state["has_long"] = False
            return True, state, max(first_adjustment, second_adjustment)
        return False, state, max(first_adjustment, second_adjustment)

    def _is_relief_boundary(self, current: Trip, nxt: Trip) -> bool:
        if current.destination_id == nxt.origin_id and self._terminal_boundary_allowed(current.destination_id):
            return True
        if current.depot_id is not None and nxt.depot_id is not None and current.depot_id == nxt.depot_id:
            return True
        if self.allow_relief_points:
            if current.is_relief_point or nxt.is_relief_point:
                return True
            if current.relief_point_id is not None and current.relief_point_id in {current.destination_id, nxt.origin_id}:
                return True
            if nxt.relief_point_id is not None and nxt.relief_point_id in {current.destination_id, nxt.origin_id}:
                return True
        return False

    def _valid_operator_change_boundary(self, current: Trip, nxt: Trip) -> bool:
        if current.destination_id == nxt.origin_id and self._terminal_boundary_allowed(current.destination_id):
            return True
        if current.depot_id is not None and nxt.depot_id is not None and current.depot_id == nxt.depot_id:
            return True
        if self.allow_relief_points:
            if current.is_relief_point or nxt.is_relief_point:
                return True
            if current.relief_point_id is not None and current.relief_point_id in {current.destination_id, nxt.origin_id}:
                return True
            if nxt.relief_point_id is not None and nxt.relief_point_id in {current.destination_id, nxt.origin_id}:
                return True
        return False

    def _terminal_boundary_allowed(self, terminal_id: Optional[int]) -> bool:
        if not self.terminal_location_ids:
            return True
        return terminal_id is not None and int(terminal_id) in self.terminal_location_ids

    def _fairness_penalty(self, projected_work: int) -> float:
        if self.fairness_weight <= 0:
            return 0.0
        deviation = abs(projected_work - self.fairness_target_work)
        exceeded = max(0, deviation - self.fairness_tolerance)
        return (exceeded / 60.0) * self.fairness_weight

    def _trip_group_score(self, duty: Duty, task_group_ids: set[int], duties: Sequence[Duty]) -> float:
        if not task_group_ids:
            return 0.0
        duty_groups = {int(item) for item in duty.meta.get("covered_trip_group_ids", [])}
        shared_groups = duty_groups & task_group_ids
        if shared_groups:
            return -self.trip_group_keep_bonus * len(shared_groups)

        external_matches = 0
        for other in duties:
            if other.id == duty.id:
                continue
            other_groups = {int(item) for item in other.meta.get("covered_trip_group_ids", [])}
            external_matches += len(other_groups & task_group_ids)

        if external_matches > 0:
            return self.trip_group_split_penalty * external_matches
        return 0.0

    def _task_group_ids(self, task: Block) -> set[int]:
        cached = task.meta.get("covered_trip_group_ids")
        if cached:
            return {int(item) for item in cached}
        return {
            int(trip.trip_group_id)
            for trip in task.trips
            if getattr(trip, "trip_group_id", None) is not None
        }

    def _duty_has_meal_break(self, duty: Duty) -> bool:
        if "meal_break_found" in duty.meta:
            return bool(duty.meta.get("meal_break_found"))
        _, meal_break_found = self._continuous_drive_stats(duty)
        return meal_break_found

    def _duty_needs_meal_break(
        self,
        duty: Duty,
        *,
        projected_spread: Optional[int] = None,
        projected_has_break: Optional[bool] = None,
    ) -> bool:
        if self.meal_break_minutes <= 0:
            return False
        if not self.apply_cct:
            return False
        spread = int(duty.spread_time if projected_spread is None else projected_spread)
        has_break = self._duty_has_meal_break(duty) if projected_has_break is None else bool(projected_has_break)
        return spread >= 360 and not has_break

    def _meal_break_score(self, duty: Duty, candidate_task: Block, data: Dict[str, Any]) -> float:
        if self.meal_break_minutes <= 0:
            return 0.0
        if not self.apply_cct:
            return 0.0

        projected_spread = int(data.get("new_spread", duty.spread_time))
        if projected_spread < 360:
            return 0.0

        had_break = self._duty_has_meal_break(duty)
        projected_has_break = self._would_have_meal_break(duty, candidate_task)
        raw_gap = int(data.get("gap", 0))
        effective_gap = int(data.get("effective_gap", raw_gap))

        if projected_has_break:
            if not had_break:
                return -min(240.0, float(max(effective_gap, self.meal_break_minutes)))
            if effective_gap >= self.meal_break_minutes:
                return -20.0
            return 0.0

        current_continuous = int(duty.meta.get("continuous_drive", duty.work_time))
        projected_continuous = int(data.get("new_cont", current_continuous + self._block_drive(candidate_task)))
        meal_trigger = max(240, self.mandatory_break_after - max(0, self.meal_break_minutes))

        penalty = 500.0 + max(0.0, float(projected_spread - 360)) * 0.15
        if current_continuous >= meal_trigger:
            penalty += 1000.0
        if projected_continuous >= self.mandatory_break_after:
            penalty += 5000.0
        if raw_gap > 0 and effective_gap < self.meal_break_minutes:
            penalty += 500.0
        if len(duty.tasks) <= 1:
            penalty += 20.0
        return penalty

    def _boundary_idle_minutes(self, trip: Optional[Trip], *, start: bool) -> int:
        if trip is None:
            return 0

        idle_name = "idle_before_minutes" if start else "idle_after_minutes"
        default_idle = self.pullout if start else self.pullback
        explicit_idle = max(0, int(getattr(trip, idle_name, 0) or 0))
        return explicit_idle if explicit_idle > 0 else default_idle

    def _annotate_source_block_boundaries(self, blocks: Sequence[Block]) -> None:
        for block in blocks:
            ordered = sorted(block.trips, key=lambda trip: (trip.start_time, trip.id))
            if not ordered:
                continue

            first_trip = ordered[0]
            last_trip = ordered[-1]
            start_buffer = self._boundary_idle_minutes(first_trip, start=True)
            end_buffer = self._boundary_idle_minutes(last_trip, start=False)

            block.meta.setdefault("source_block_id", block.id)
            block.meta["vehicle_first_trip_id"] = int(first_trip.id)
            block.meta["vehicle_last_trip_id"] = int(last_trip.id)
            block.meta["start_buffer_minutes"] = start_buffer
            block.meta["end_buffer_minutes"] = end_buffer
            block.meta["operational_start_minutes"] = int(first_trip.start_time) - start_buffer
            block.meta["operational_end_minutes"] = int(last_trip.end_time) + end_buffer

    def _duty_span_bounds(self, tasks: Sequence[Block]) -> Tuple[int, int, int, int]:
        ordered_tasks = sorted(
            (task for task in tasks if task.trips),
            key=lambda item: (item.start_time, item.id),
        )
        if not ordered_tasks:
            return 0, 0, 0, 0

        first_task = ordered_tasks[0]
        last_task = ordered_tasks[-1]
        first_trip = first_task.trips[0]
        last_trip = last_task.trips[-1]
        start_buffer = first_task.meta.get("task_start_buffer_minutes")
        end_buffer = last_task.meta.get("task_end_buffer_minutes")
        start_buffer = max(
            0,
            int(start_buffer if start_buffer is not None else self._boundary_idle_minutes(first_trip, start=True)),
        )
        end_buffer = max(
            0,
            int(end_buffer if end_buffer is not None else self._boundary_idle_minutes(last_trip, start=False)),
        )
        duty_start = int(first_trip.start_time) - start_buffer
        duty_end = int(last_trip.end_time) + end_buffer
        return start_buffer, end_buffer, duty_start, duty_end

    def _duty_spread_minutes(self, tasks: Sequence[Block]) -> int:
        _, _, duty_start, duty_end = self._duty_span_bounds(tasks)
        return max(0, duty_end - duty_start)

    def _duty_gap_minutes(self, tasks: Sequence[Block]) -> List[int]:
        ordered = sorted((task for task in tasks if task.trips), key=lambda item: (item.start_time, item.id))
        if len(ordered) < 2:
            return []
        return [
            max(0, int(ordered[index + 1].start_time) - int(ordered[index].end_time))
            for index in range(len(ordered) - 1)
        ]

    def _build_duty_quality_metrics(
        self,
        tasks: Sequence[Block],
        *,
        projected_work: Optional[int] = None,
        projected_spread: Optional[int] = None,
    ) -> Dict[str, Any]:
        ordered = sorted((task for task in tasks if task.trips), key=lambda item: (item.start_time, item.id))
        work_time = int(projected_work if projected_work is not None else sum(self._block_regulatory_work(task) for task in ordered))
        spread_time = int(projected_spread if projected_spread is not None else self._duty_spread_minutes(ordered))
        gaps = self._duty_gap_minutes(ordered)
        total_idle = max(0, spread_time - work_time)
        max_idle = max(gaps, default=0)
        short_connections = sum(1 for gap in gaps if 0 < gap < self.short_connection_threshold)
        utilization = (work_time / spread_time) if spread_time > 0 else 1.0
        return {
            "work_time": work_time,
            "spread_time": spread_time,
            "utilization": utilization,
            "total_idle_time": total_idle,
            "max_idle_time": max_idle,
            "break_count": len(gaps),
            "fragment_count": len(gaps),
            "task_count": len(ordered),
            "short_connection_count": short_connections,
            "gaps": gaps,
        }

    def _build_operational_semantic_metrics(
        self,
        tasks: Sequence[Block],
        *,
        projected_work: Optional[int] = None,
        projected_spread: Optional[int] = None,
        duty_id: int = 0,
    ) -> Dict[str, Any]:
        ordered = sorted((task for task in tasks if task.trips), key=lambda item: (item.start_time, item.id))
        if not ordered:
            return {
                "utilization": 1.0,
                "spread_time": 0,
                "work_time": 0,
                "total_idle_time": 0,
                "max_idle_time": 0,
                "break_count": 0,
                "mandatory_rest_missing": False,
                "mandatory_rest_required": False,
                "has_valid_mandatory_rest": False,
                "invalid_rest_position": False,
                "report": {},
            }

        start_buffer, end_buffer, duty_start, duty_end = self._duty_span_bounds(ordered)
        work_time = int(projected_work if projected_work is not None else sum(self._block_regulatory_work(task) for task in ordered))
        spread_time = int(projected_spread if projected_spread is not None else max(0, duty_end - duty_start))
        synthetic = Duty(id=duty_id or -1, tasks=list(ordered), work_time=work_time, spread_time=spread_time)
        synthetic.meta["start_buffer_minutes"] = start_buffer
        synthetic.meta["end_buffer_minutes"] = end_buffer
        synthetic.meta["duty_start_minutes"] = duty_start
        synthetic.meta["duty_end_minutes"] = duty_end
        synthetic.meta["max_continuous_drive_minutes"] = int(self._continuous_drive_stats(synthetic)[0])
        report = build_duty_operational_time_report(
            synthetic,
            min_break_minutes=self.min_break,
            meal_break_minutes=self.meal_break_minutes,
            mandatory_break_after_minutes=self.mandatory_break_after,
        )
        break_segments = [
            segment
            for segment in (report.get("duty_time_segments") or [])
            if segment.get("type") in {"idle", "normal_break", "mandatory_rest"}
        ]
        non_rest_segments = [
            segment
            for segment in break_segments
            if segment.get("type") in {"idle", "normal_break"}
        ]
        total_idle_time = sum(int(segment.get("duration", 0) or 0) for segment in non_rest_segments)
        max_idle_time = max((int(segment.get("duration", 0) or 0) for segment in non_rest_segments), default=0)
        return {
            "utilization": float(work_time / spread_time) if spread_time > 0 else 1.0,
            "spread_time": spread_time,
            "work_time": work_time,
            "total_idle_time": total_idle_time,
            "max_idle_time": max_idle_time,
            "break_count": len(break_segments),
            "mandatory_rest_missing": bool(
                report.get("mandatory_rest_required") and not report.get("has_valid_mandatory_rest")
            ),
            "mandatory_rest_required": bool(report.get("mandatory_rest_required")),
            "has_valid_mandatory_rest": bool(report.get("has_valid_mandatory_rest")),
            "invalid_rest_position": bool(report.get("invalid_rest_position")),
            "report": report,
        }

    def _operational_semantic_score(
        self,
        metrics: Dict[str, Any],
        *,
        base_cost: float = 0.0,
    ) -> float:
        utilization = float(metrics.get("utilization", 1.0) or 0.0)
        total_idle_time = int(metrics.get("total_idle_time", 0) or 0)
        max_idle_time = int(metrics.get("max_idle_time", 0) or 0)
        break_count = int(metrics.get("break_count", 0) or 0)
        spread_time = int(metrics.get("spread_time", 0) or 0)
        mandatory_rest_missing = bool(metrics.get("mandatory_rest_missing"))
        return float(
            base_cost
            + self.idle_weight * total_idle_time
            + self.semantic_low_util_weight * max(0.0, self.semantic_utilization_target - utilization)
            + self.spread_weight * max(0, spread_time - self.semantic_spread_threshold)
            + self.semantic_rest_penalty * int(mandatory_rest_missing)
            + self.semantic_break_count_weight * break_count
            + self.semantic_max_idle_weight * max_idle_time
        )

    def _operational_quality_penalty(self, metrics: Dict[str, Any]) -> float:
        spread_time = int(metrics.get("spread_time", 0) or 0)
        work_time = int(metrics.get("work_time", 0) or 0)
        utilization = float(metrics.get("utilization", 1.0) or 0.0)
        total_idle = int(metrics.get("total_idle_time", max(0, spread_time - work_time)) or 0)
        max_idle = int(metrics.get("max_idle_time", 0) or 0)
        break_count = int(metrics.get("break_count", 0) or 0)
        short_connections = int(metrics.get("short_connection_count", 0) or 0)

        penalty = 0.0
        if utilization < self.utilization_target and spread_time > 0:
            penalty += (self.utilization_target - utilization) * spread_time * self.utilization_weight
        if self.max_spread_soft > 0 and spread_time > self.max_spread_soft:
            penalty += (spread_time - self.max_spread_soft) * self.spread_weight
        if self.max_idle_soft > 0 and max_idle > self.max_idle_soft:
            penalty += (max_idle - self.max_idle_soft) * self.idle_weight
        if self.min_work_soft > 0 and work_time < self.min_work_soft:
            penalty += (self.min_work_soft - work_time) * self.min_work_soft_weight
        fragment_excess = max(0, break_count - self.fragmentation_soft_limit)
        if fragment_excess > 0:
            penalty += fragment_excess * self.fragmentation_weight
        if short_connections > 0:
            penalty += short_connections * self.short_connection_weight
        if self.max_idle_soft > 0 and total_idle > self.max_idle_soft:
            penalty += (total_idle - self.max_idle_soft) * max(0.15, self.idle_weight * 0.15)
        return penalty * max(0.0, self.operational_quality_weight)

    def _make_task(self, source_block: Block, trips: Sequence[Trip], task_id: int) -> Block:
        source_start_buffer = max(0, int(source_block.meta.get("start_buffer_minutes", 0) or 0))
        source_end_buffer = max(0, int(source_block.meta.get("end_buffer_minutes", 0) or 0))
        first_trip_id = int(source_block.meta.get("vehicle_first_trip_id", trips[0].id if trips else 0))
        last_trip_id = int(source_block.meta.get("vehicle_last_trip_id", trips[-1].id if trips else 0))
        is_source_block_start = bool(trips) and int(trips[0].id) == first_trip_id
        is_source_block_end = bool(trips) and int(trips[-1].id) == last_trip_id
        internal_gaps = [
            max(0, int(trips[index + 1].start_time) - int(trips[index].end_time))
            for index in range(len(trips) - 1)
        ]
        task_group_ids = list(
            dict.fromkeys(
                int(trip.trip_group_id)
                for trip in trips
                if getattr(trip, "trip_group_id", None) is not None
            )
        )
        task = Block(id=task_id, trips=list(trips), vehicle_type_id=source_block.vehicle_type_id)
        task.meta.update(
            {
                "source_block_id": source_block.id,
                "task_id": task_id,
                "relief_start_id": trips[0].origin_id if trips else None,
                "relief_end_id": trips[-1].destination_id if trips else None,
                "task_drive_minutes": sum(t.duration for t in trips),
                "original_trip_ids": list(dict.fromkeys(int(getattr(t, "public_id", t.id)) for t in trips)),
                "contains_mid_trip_relief_segment": any(t.is_mid_trip_segment for t in trips),
                "starts_at_mid_trip_relief": bool(trips and trips[0].starts_at_mid_trip_relief),
                "ends_at_mid_trip_relief": bool(trips and trips[-1].ends_at_mid_trip_relief),
                "mid_trip_original_trip_ids": list(
                    dict.fromkeys(int(getattr(t, "public_id", t.id)) for t in trips if t.is_mid_trip_segment)
                ),
                "is_source_block_start": is_source_block_start,
                "is_source_block_end": is_source_block_end,
                "task_start_buffer_minutes": source_start_buffer if is_source_block_start else 0,
                "task_end_buffer_minutes": source_end_buffer if is_source_block_end else 0,
                "source_start_buffer_minutes": source_start_buffer,
                "source_end_buffer_minutes": source_end_buffer,
                "covered_trip_group_ids": task_group_ids,
                "max_internal_gap_minutes": max(internal_gaps, default=0),
                "meal_break_inside_task": bool(
                    self.meal_break_minutes > 0 and max(internal_gaps, default=0) >= self.meal_break_minutes
                ),
            }
        )
        return task

    def prepare_tasks(self, blocks: List[Block]) -> Tuple[List[Block], Dict[str, Any]]:
        """Executa run-cutting sobre blocos VSP para gerar tarefas de CSP."""
        self._reset_synthetic_trip_ids(blocks)
        self._annotate_source_block_boundaries(blocks)
        tasks: List[Block] = []
        relief_cuts = 0
        mid_trip_relief_splits = 0
        mid_trip_relief_segments = 0
        if self.apply_cct:
            max_chunk_drive = max(60, min(self.max_work, self.mandatory_break_after, self.daily_driving_limit))
            meal_trigger = max(240, self.mandatory_break_after - max(0, self.meal_break_minutes)) if self.meal_break_minutes > 0 else self.mandatory_break_after
        else:
            max_chunk_drive = 10**9
            meal_trigger = 10**9

        for block in sorted(blocks, key=lambda item: (item.start_time, item.id)):
            ordered, block_mid_relief_splits = self._expand_block_trips_for_relief(block)
            mid_trip_relief_splits += block_mid_relief_splits
            mid_trip_relief_segments += sum(1 for trip in ordered if trip.is_mid_trip_segment)
            if not ordered:
                continue

            current: List[Trip] = []
            current_drive = 0
            for index, trip in enumerate(ordered):
                current.append(trip)
                current_drive += trip.duration
                nxt = ordered[index + 1] if index + 1 < len(ordered) else None
                if nxt is None:
                    tasks.append(self._make_task(block, current, self._next_block_id()))
                    break

                gap = nxt.start_time - trip.end_time
                boundary = self._is_relief_boundary(trip, nxt)
                explicit_mid_trip_relief_boundary = (
                    trip.ends_at_mid_trip_relief and nxt.starts_at_mid_trip_relief
                )
                next_duration = nxt.duration
                pair_guard = (
                    trip.trip_group_id is not None
                    and trip.trip_group_id == nxt.trip_group_id
                    and trip.line_id == nxt.line_id
                )

                if (
                    pair_guard
                    and boundary
                    and len(current) > 1
                    and (
                        current_drive + next_duration > max_chunk_drive
                        or (self.meal_break_minutes > 0 and current_drive + next_duration > meal_trigger)
                    )
                ):
                    task = self._make_task(block, current[:-1], self._next_block_id())
                    task.meta["relief_cut"] = True
                    task.meta["split_reason"] = "pre_pair_guard"
                    tasks.append(task)
                    relief_cuts += 1
                    current = [current[-1]]
                    current_drive = current[-1].duration

                should_cut = False
                short_positive_interval = (
                    self.apply_cct
                    and self.enforce_min_interval
                    and 0 < gap < self.min_break
                )

                if short_positive_interval:
                    should_cut = True
                elif gap >= self.min_break and boundary:
                    should_cut = True
                elif explicit_mid_trip_relief_boundary:
                    should_cut = True
                elif boundary and current_drive >= max_chunk_drive:
                    should_cut = True
                elif boundary and current_drive >= meal_trigger:
                    should_cut = True
                elif boundary and current_drive >= self.max_work:
                    should_cut = True
                elif boundary and current_drive + next_duration > max_chunk_drive:
                    should_cut = True
                elif boundary and self.meal_break_minutes > 0 and current_drive + next_duration > meal_trigger:
                    should_cut = True

                if pair_guard and not short_positive_interval:
                    should_cut = False

                if should_cut:
                    task = self._make_task(block, current, self._next_block_id())
                    task.meta["relief_cut"] = True
                    task.meta["split_reason"] = (
                        "explicit_mid_trip_relief" if explicit_mid_trip_relief_boundary else
                        "short_interval" if short_positive_interval else
                        "natural_break" if gap >= self.min_break else
                        "mandatory_break" if current_drive >= max_chunk_drive else
                        "meal_break" if current_drive >= meal_trigger else
                        "work_limit"
                    )
                    tasks.append(task)
                    relief_cuts += 1
                    current = []
                    current_drive = 0

        return tasks, {
            "task_count": len(tasks),
            "source_block_count": len(blocks),
            "relief_cuts": relief_cuts,
            "mid_trip_relief_splits": mid_trip_relief_splits,
            "mid_trip_relief_segments": mid_trip_relief_segments,
            "run_cutting": "terminal_and_intra_trip_relief_and_break_windows",
        }

    def _can_extend(self, duty: Duty, block: Block) -> Tuple[bool, str, Dict[str, Any]]:
        if not duty.tasks:
            return True, "", {}

        # Check for duplicate trips
        covered_trip_ids = set(duty.meta.get("covered_trip_ids", []))
        block_trip_ids = {int(trip.id) for trip in block.trips}
        duplicate_trip_ids = sorted(block_trip_ids & covered_trip_ids)
        if duplicate_trip_ids:
            return False, "duplicate_trip", {"duplicate_trip_ids": duplicate_trip_ids}

        last = duty.tasks[-1]
        gap = block.start_time - last.end_time
        effective_gap = self._effective_gap(gap)
        if gap < 0:
            return False, "overlap", {}
        if (
            self.apply_cct
            and self.enforce_min_interval
            and 0 < gap < self.min_break
        ):
            return False, "min_interval_violation", {"gap": gap, "min_break": self.min_break}

        last_trip = last.trips[-1]
        first_trip = block.trips[0]
        if (
            (last_trip.ends_at_mid_trip_relief or first_trip.starts_at_mid_trip_relief)
            and not first_trip.is_continuation_of(last_trip)
            and last_trip.destination_id != first_trip.origin_id
        ):
            return False, "mid_trip_relief_terminal_mismatch", {}

        last_service_day = self._service_day(last)
        block_service_day = self._service_day(block)
        if block_service_day < last_service_day:
            return False, "service_day_regression", {
                "last_service_day": last_service_day,
                "next_service_day": block_service_day,
            }
        if block_service_day > last_service_day + 1:
            return False, "different_service_day", {
                "last_service_day": last_service_day,
                "next_service_day": block_service_day,
            }

        if self.apply_cct and self.max_unpaid_break is not None and gap > self.max_unpaid_break:
            return False, "max_unpaid_break_exceeded", {"gap": gap, "max_unpaid_break": self.max_unpaid_break}

        transfer_needed = self._transfer_needed(last, block)
        if effective_gap < transfer_needed:
            return False, "transfer_insufficient", {"gap": gap, "transfer_needed": transfer_needed}

        passive_transfer = max(0, transfer_needed - self.min_layover)
        if self.operator_change_terminals_only and not self._valid_operator_change_boundary(last.trips[-1], block.trips[0]):
            return False, "operator_change_non_terminal", {}
        if not self.allow_relief_points and last.trips[-1].destination_id != block.trips[0].origin_id and passive_transfer > 0:
            return False, "relief_point_required", {}

        if self.enforce_single_line_duty:
            duty_lines = set(int(line_id) for line_id in duty.meta.get("line_ids", []))
            block_lines = {int(t.line_id) for t in block.trips}
            if duty_lines and any(line_id not in duty_lines for line_id in block_lines):
                return False, "single_line_duty_required", {}

        if self.operator_single_vehicle_only:
            source_block_id = int(block.meta.get("source_block_id", block.id))
            covered_sources = {
                int(item)
                for item in duty.meta.get("source_block_ids", [])
                if item is not None
            }
            if covered_sources and source_block_id not in covered_sources:
                return False, "operator_single_vehicle_only", {}

        # Cálculo universal dos indicadores de jornada
        new_spread = self._duty_spread_minutes([*duty.tasks, block])
        projected_work = duty.work_time + self._block_regulatory_work(block)
        overtime_minutes = self._regular_overtime_minutes(projected_work)

        had_break, break_state, break_adjustment = self._break_resets(duty.meta.get("break_state", {}), gap)
        block_drive = self._block_drive(block)
        block_regulatory = self._block_regulatory_work(block)
        current_cont = int(duty.meta.get("continuous_drive", 0))
        new_cont = block_drive if had_break else current_cont + block_drive
        daily_drive = int(duty.meta.get("daily_driving", 0)) + block_regulatory
        extended_days_used = int(duty.meta.get("extended_days_used", 0))
        work_since_break = block_regulatory if had_break else int(duty.meta.get("work_since_break", 0)) + block_regulatory

        if self.apply_cct:
            if new_spread > self.max_shift:
                return False, "spread_exceeded", {"new_spread": new_spread, "limit": self.max_shift}

            if overtime_minutes > self.overtime_limit:
                return False, "overtime_hard", {"new_work": projected_work, "limit": self.max_work + self.overtime_limit}

            if new_cont > self.max_driving or work_since_break > self.mandatory_break_after:
                return False, "mandatory_break_required", {"work_since": work_since_break, "limit": self.mandatory_break_after}

            if daily_drive > self.extended_daily_driving_limit:
                return False, "daily_driving_exceeded", {"daily_drive": daily_drive}
            if daily_drive > self.daily_driving_limit and extended_days_used >= self.max_extended_days:
                return False, "daily_extension_quota_exceeded", {"daily_drive": daily_drive}

        start_depot = duty.meta.get("start_depot_id")
        candidate_end_depot = block.trips[-1].depot_id
        if self.enforce_same_depot and start_depot is not None and candidate_end_depot is not None and candidate_end_depot != start_depot:
            return False, "same_depot_required", {}

        transfer_adjustment = self._adjustment_needed(gap, transfer_needed)
        connection_adjustment = max(transfer_adjustment, break_adjustment)

        return True, "", {
            "gap": gap,
            "effective_gap": effective_gap,
            "transfer_needed": transfer_needed,
            "last_service_day": last_service_day,
            "next_service_day": block_service_day,
            "service_day_transition": block_service_day != last_service_day,
            "had_break": had_break,
            "new_spread": new_spread,
            "new_work": projected_work,
            "new_cont": new_cont,
            "work_since_break": work_since_break,
            "daily_drive": daily_drive,
            "extended_days_used": extended_days_used + (1 if daily_drive > self.daily_driving_limit else 0),
            "passive_transfer": passive_transfer,
            "break_state": break_state,
            "connection_adjustment_minutes": connection_adjustment,
            "previous_task_id": int(last.id),
            "next_task_id": int(block.id),
        }

    def _apply_block(self, duty: Duty, block: Block, data: Dict[str, Any]) -> None:
        previous_last_service_day = int(
            duty.meta.get("last_service_day", duty.meta.get("service_day", self._service_day(block)))
        )
        duty.add_task(block)
        start_buffer, end_buffer, duty_start, duty_end = self._duty_span_bounds(duty.tasks)
        duty.work_time = int(data.get("new_work", self._block_regulatory_work(block)))
        duty.spread_time = max(0, duty_end - duty_start)
        gap = int(data.get("gap", 0))
        duty.meta["continuous_drive"] = int(data.get("new_cont", self._block_drive(block)))
        duty.meta["work_since_break"] = int(data.get("work_since_break", self._block_regulatory_work(block)))
        duty.meta["daily_driving"] = int(data.get("daily_drive", self._block_regulatory_work(block)))
        duty.meta["extended_days_used"] = int(data.get("extended_days_used", 0))
        duty.meta["break_state"] = dict(data.get("break_state", duty.meta.get("break_state", {"credit": 0, "has_long": False})))
        duty.meta["duty_start_minutes"] = duty_start
        duty.meta["duty_end_minutes"] = duty_end
        duty.meta["start_buffer_minutes"] = start_buffer
        duty.meta["end_buffer_minutes"] = end_buffer
        duty.meta["waiting_minutes"] = int(duty.meta.get("waiting_minutes", 0)) + max(0, gap - int(data.get("transfer_needed", 0)))
        duty.meta["passive_transfer_minutes"] = int(duty.meta.get("passive_transfer_minutes", 0)) + int(data.get("passive_transfer", 0))
        duty.meta["connection_tolerance_minutes"] = self.connection_tolerance
        meal_break_found = bool(duty.meta.get("meal_break_found", False))
        if len(duty.tasks) > 1 and self.meal_break_minutes > 0 and self._effective_gap(gap) >= self.meal_break_minutes:
            meal_break_found = True
        if bool(block.meta.get("meal_break_inside_task", False)):
            meal_break_found = True
        duty.meta["meal_break_found"] = meal_break_found
        duty.meta.setdefault("service_day", self._service_day(block))
        current_service_day = int(data.get("next_service_day", self._service_day(block)))
        duty.meta["last_service_day"] = current_service_day
        if len(duty.tasks) > 1 and current_service_day != previous_last_service_day:
            duty.meta["crosses_service_day"] = True
            duty.meta["service_day_transition_count"] = int(duty.meta.get("service_day_transition_count", 0)) + 1
            duty.meta.setdefault("service_day_transitions", []).append(
                {
                    "from_service_day": previous_last_service_day,
                    "to_service_day": current_service_day,
                    "task_id": int(block.id),
                    "gap": gap,
                }
            )
        duty.meta.setdefault("start_depot_id", block.trips[0].depot_id)
        duty.meta["end_depot_id"] = block.trips[-1].depot_id
        adjustment_used = int(data.get("connection_adjustment_minutes", 0))
        if adjustment_used > 0:
            duty.meta["connection_tolerance_used_minutes"] = int(duty.meta.get("connection_tolerance_used_minutes", 0)) + adjustment_used
            duty.meta["connection_tolerance_uses"] = int(duty.meta.get("connection_tolerance_uses", 0)) + 1
            duty.meta.setdefault("adjusted_connections", []).append({
                "from_task_id": int(data.get("previous_task_id", 0)),
                "to_task_id": int(data.get("next_task_id", block.id)),
                "gap": gap,
                "effective_gap": int(data.get("effective_gap", gap)),
                "transfer_needed": int(data.get("transfer_needed", 0)),
                "adjustment_minutes": adjustment_used,
            })
        duty.meta.setdefault("line_ids", [])
        for line_id in [t.line_id for t in block.trips]:
            if line_id not in duty.meta["line_ids"]:
                duty.meta["line_ids"].append(line_id)
        duty.meta.setdefault("task_ids", []).append(block.meta.get("task_id", block.id))
        duty.meta.setdefault("source_block_ids", []).append(block.meta.get("source_block_id", block.id))
        duty.meta.setdefault("covered_trip_ids", [])
        for t in block.trips:
            if t.id not in duty.meta["covered_trip_ids"]:
                duty.meta["covered_trip_ids"].append(t.id)
            else:
                raise ValueError(f"Trip {t.id} already in duty {duty.id} covered_trip_ids")
        duty.meta.setdefault("covered_original_trip_ids", [])
        for trip in block.trips:
            original_trip_id = int(getattr(trip, "public_id", trip.id))
            if original_trip_id not in duty.meta["covered_original_trip_ids"]:
                duty.meta["covered_original_trip_ids"].append(original_trip_id)
        duty.meta.setdefault("covered_trip_group_ids", [])
        for group_id in self._task_group_ids(block):
            if group_id not in duty.meta["covered_trip_group_ids"]:
                duty.meta["covered_trip_group_ids"].append(group_id)

    def _empty_extension_phase(self) -> Dict[str, Any]:
        return {
            "attempts": 0,
            "accepted": 0,
            "rejections": 0,
            "cross_day_extensions": 0,
            "reasons": {},
            "samples": [],
        }

    def _empty_extension_diagnostics(self) -> Dict[str, Any]:
        return {
            "duty_build": self._empty_extension_phase(),
            "same_vehicle_merge": self._empty_extension_phase(),
            "cross_vehicle_short_merge": self._empty_extension_phase(),
        }

    def _record_extension_attempt(
        self,
        phase: str,
        duty: Duty,
        block: Block,
        ok: bool,
        reason: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        phase_state = self._extension_diagnostics.setdefault(phase, self._empty_extension_phase())
        phase_state["attempts"] = int(phase_state.get("attempts", 0)) + 1
        data = data or {}

        if ok:
            phase_state["accepted"] = int(phase_state.get("accepted", 0)) + 1
            if data.get("service_day_transition"):
                phase_state["cross_day_extensions"] = int(phase_state.get("cross_day_extensions", 0)) + 1
            return

        phase_state["rejections"] = int(phase_state.get("rejections", 0)) + 1
        if reason:
            reasons = phase_state.setdefault("reasons", {})
            reasons[reason] = int(reasons.get(reason, 0)) + 1

        samples = phase_state.setdefault("samples", [])
        if len(samples) >= 25:
            return

        last_trip = duty.tasks[-1].trips[-1] if duty.tasks and duty.tasks[-1].trips else None
        next_trip = block.trips[0] if block.trips else None
        samples.append(
            {
                "duty_id": int(duty.id),
                "task_id": int(block.id),
                "reason": reason,
                "gap": int(data.get("gap", next_trip.start_time - last_trip.end_time if last_trip and next_trip else 0)),
                "last_service_day": int(data.get("last_service_day", self._service_day(duty.tasks[-1]) if duty.tasks else 0)),
                "next_service_day": int(data.get("next_service_day", self._service_day(block))),
                "last_trip_id": int(last_trip.id) if last_trip is not None else None,
                "next_trip_id": int(next_trip.id) if next_trip is not None else None,
                "last_destination_id": int(last_trip.destination_id) if last_trip is not None else None,
                "next_origin_id": int(next_trip.origin_id) if next_trip is not None else None,
                "duty_source_block_ids": [int(item) for item in duty.meta.get("source_block_ids", []) if item is not None],
                "candidate_source_block_id": int(block.meta.get("source_block_id", block.id)),
            }
        )

    def _extension_diagnostics_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        for phase, state in self._extension_diagnostics.items():
            snapshot[phase] = {
                "attempts": int(state.get("attempts", 0)),
                "accepted": int(state.get("accepted", 0)),
                "rejections": int(state.get("rejections", 0)),
                "cross_day_extensions": int(state.get("cross_day_extensions", 0)),
                "reasons": dict(
                    sorted(
                        ((str(name), int(count)) for name, count in (state.get("reasons") or {}).items()),
                        key=lambda item: (-item[1], item[0]),
                    )
                ),
                "samples": list(state.get("samples", [])),
            }
        return snapshot

    def _quality_summary(self, duties: Sequence[Duty]) -> Dict[str, Any]:
        if not duties:
            return {
                "duties": 0,
                "avg_utilization": 0.0,
                "avg_total_idle_time": 0.0,
                "max_idle_time": 0,
                "low_utilization_duties": 0,
                "high_spread_duties": 0,
                "low_work_duties": 0,
                "fragmented_duties": 0,
                "short_connection_total": 0,
            }

        metrics = [self._build_duty_quality_metrics(duty.tasks, projected_work=duty.work_time, projected_spread=duty.spread_time) for duty in duties]
        return {
            "duties": len(metrics),
            "avg_utilization": round(sum(float(item["utilization"]) for item in metrics) / len(metrics), 4),
            "avg_total_idle_time": round(sum(int(item["total_idle_time"]) for item in metrics) / len(metrics), 2),
            "max_idle_time": max(int(item["max_idle_time"]) for item in metrics),
            "low_utilization_duties": sum(1 for item in metrics if float(item["utilization"]) < self.utilization_target),
            "high_spread_duties": sum(1 for item in metrics if int(item["spread_time"]) > self.max_spread_soft),
            "low_work_duties": sum(1 for item in metrics if self.min_work_soft > 0 and int(item["work_time"]) < self.min_work_soft),
            "fragmented_duties": sum(1 for item in metrics if int(item["break_count"]) > self.fragmentation_soft_limit),
            "short_connection_total": sum(int(item["short_connection_count"]) for item in metrics),
        }

    def _continuous_drive_stats(self, duty: Duty) -> Tuple[int, bool]:
        max_continuous = 0
        meal_break_found = False
        continuous = 0
        all_trips = []
        for block in duty.tasks:
            all_trips.extend(block.trips)
        if not all_trips:
            return 0, False
        all_trips.sort(key=lambda t: t.start_time)
        
        previous_end = None
        for trip in all_trips:
            if previous_end is None:
                continuous = trip.duration
            else:
                gap = trip.start_time - previous_end
                effective_gap = self._effective_gap(gap)
                if effective_gap >= self.meal_break_minutes > 0:
                    meal_break_found = True
                if effective_gap >= self.min_break:
                    continuous = trip.duration
                else:
                    continuous += trip.duration
            max_continuous = max(max_continuous, continuous)
            previous_end = trip.end_time
            
        return max_continuous, meal_break_found

    def _would_have_meal_break(self, duty: Duty, candidate_task: Block) -> bool:
        """Check if adding candidate_task to duty would produce a meal break gap."""
        if self.meal_break_minutes <= 0:
            return True
        all_trips = []
        for block in duty.tasks:
            all_trips.extend(block.trips)
        all_trips.extend(candidate_task.trips)
        if not all_trips:
            return True
        all_trips.sort(key=lambda t: t.start_time)
        previous_end = None
        for trip in all_trips:
            if previous_end is not None:
                if self._effective_gap(trip.start_time - previous_end) >= self.meal_break_minutes:
                    return True
            previous_end = trip.end_time
        return False

    def _profile_priority(self, profile: Dict[str, Any]) -> float:
        if profile.get("seniority_score") is not None:
            return float(profile["seniority_score"])
        if profile.get("seniority_rank") is not None:
            return -float(profile["seniority_rank"])
        return 0.0

    def _assign_operator_profiles(self, roster_state: List[Dict[str, Any]], duties: List[Duty]) -> Dict[str, Any]:
        if not self.operator_profiles:
            return {
                "enabled": False,
                "assigned_rosters": 0,
                "unassigned_rosters": len(roster_state),
                "violations": [],
                "rosters": [],
            }

        duty_by_id = {duty.id: duty for duty in duties}
        available = sorted(
            [dict(profile) for profile in self.operator_profiles],
            key=lambda profile: self._profile_priority(profile),
            reverse=True,
        )
        assignments: List[Dict[str, Any]] = []
        violations: List[str] = []

        def roster_signature(roster: Dict[str, Any]) -> Tuple[int, List[int], int]:
            roster_duties = [duty_by_id[duty_id] for duty_id in roster["duties"] if duty_id in duty_by_id]
            first_start = min((duty.tasks[0].start_time for duty in roster_duties if duty.tasks), default=0)
            line_ids = sorted({trip.line_id for duty in roster_duties for task in duty.tasks for trip in task.trips})
            return first_start, line_ids, len(roster_duties)

        for roster in sorted(roster_state, key=lambda item: roster_signature(item)[0]):
            first_start, line_ids, duty_count = roster_signature(roster)
            shift_type = _shift_type_from_minutes(first_start)

            viable: List[Tuple[Tuple[int, int, float], Dict[str, Any]]] = []
            fallback: List[Tuple[Tuple[int, int, float], Dict[str, Any]]] = []
            for profile in available:
                mandatory_shift_types = set(profile.get("mandatory_shift_types") or [])
                mandatory_line_ids = set(int(item) for item in (profile.get("mandatory_line_ids") or []))
                preferred_shift_types = set(profile.get("preferred_shift_types") or [])
                preferred_line_ids = set(int(item) for item in (profile.get("preferred_line_ids") or []))
                mandatory_ok = (not mandatory_shift_types or shift_type in mandatory_shift_types) and (
                    not mandatory_line_ids or set(line_ids).issubset(mandatory_line_ids)
                )
                preferred_score = int(shift_type in preferred_shift_types) + int(bool(preferred_line_ids) and bool(set(line_ids) & preferred_line_ids))
                ranking = (preferred_score, duty_count, self._profile_priority(profile))
                if mandatory_ok:
                    viable.append((ranking, profile))
                else:
                    fallback.append((ranking, profile))

            chosen: Optional[Dict[str, Any]] = None
            if viable:
                chosen = sorted(viable, key=lambda item: item[0], reverse=True)[0][1]
            elif not self.strict_union_rules and fallback:
                chosen = sorted(fallback, key=lambda item: item[0], reverse=True)[0][1]

            if chosen is None:
                violations.append(f"UNASSIGNED_OPERATOR_PROFILE R{roster['id']} shift={shift_type} lines={line_ids}")
                assignments.append({
                    "roster_id": roster["id"],
                    "operator_id": None,
                    "operator_name": None,
                    "shift_type": shift_type,
                    "line_ids": line_ids,
                })
                continue

            available = [profile for profile in available if int(profile.get("id", 0)) != int(chosen.get("id", -1))]
            assignment = {
                "roster_id": roster["id"],
                "operator_id": int(chosen.get("id")),
                "operator_name": chosen.get("name"),
                "shift_type": shift_type,
                "line_ids": line_ids,
                "seniority_priority": self._profile_priority(chosen),
                "mandatory_shift_types": list(chosen.get("mandatory_shift_types") or []),
                "mandatory_line_ids": list(chosen.get("mandatory_line_ids") or []),
                "preferred_shift_types": list(chosen.get("preferred_shift_types") or []),
                "preferred_line_ids": list(chosen.get("preferred_line_ids") or []),
            }
            assignments.append(assignment)
            for duty_id in roster["duties"]:
                duty = duty_by_id.get(duty_id)
                if duty is None:
                    continue
                duty.meta["operator_id"] = assignment["operator_id"]
                duty.meta["operator_name"] = assignment["operator_name"]
                duty.meta["shift_type"] = shift_type

        return {
            "enabled": True,
            "assigned_rosters": sum(1 for item in assignments if item["operator_id"] is not None),
            "unassigned_rosters": sum(1 for item in assignments if item["operator_id"] is None),
            "violations": violations,
            "rosters": assignments,
        }

    def finalize_selected_duties(self, duties: List[Duty], original_blocks: Optional[List[Block]] = None) -> CSPSolution:
        warnings: List[str] = []
        violations = 0

        covered_source_blocks = {
            int(source_id)
            for duty in duties
            for source_id in duty.meta.get("source_block_ids", [])
        }
        uncovered_source_blocks = [block for block in (original_blocks or []) if int(block.id) not in covered_source_blocks]

        for duty in duties:
            duty.nocturnal_minutes = sum(
                _nocturnal_overlap(t.start_time, t.end_time, self.nocturnal_start_hour, self.nocturnal_end_hour)
                for block in duty.tasks for t in block.trips
            )
            duty.overtime_minutes = self._regular_overtime_minutes(duty.work_time)
            waiting_minutes = int(duty.meta.get("waiting_minutes", max(0, duty.spread_time - duty.work_time)))
            unpaid_total = max(0, duty.spread_time - duty.work_time)
            paid_waiting = int(round(waiting_minutes * self.waiting_time_pay_pct)) if self.idle_time_is_paid else 0
            guaranteed = max(self.min_guaranteed_work, duty.work_time)
            duty.paid_minutes = guaranteed + paid_waiting
            duty.meta["guaranteed_minutes"] = guaranteed
            duty.meta["overtime_extra_pct"] = float(self.params.get("overtime_extra_pct", 0.50))
            duty.meta["nocturnal_extra_pct"] = self.nocturnal_extra_pct
            duty.meta["passive_transfer_minutes"] = int(duty.meta.get("passive_transfer_minutes", 0))
            duty.meta["unpaid_break_total_minutes"] = unpaid_total
            duty.meta["task_windows"] = [
                {"block_id": int(task.id), "start": int(task.start_time), "end": int(task.end_time)}
                for task in duty.tasks
            ]

            windows = duty.meta["task_windows"]
            gaps: List[int] = []
            if len(windows) >= 2:
                for idx in range(len(windows) - 1):
                    gaps.append(max(0, int(windows[idx + 1]["start"]) - int(windows[idx]["end"])))
            duty.meta["task_gap_minutes"] = gaps
            duty.meta["task_long_gaps_over_180"] = sum(1 for g in gaps if g > 180)
            quality_metrics = self._build_duty_quality_metrics(
                duty.tasks,
                projected_work=int(duty.work_time),
                projected_spread=int(duty.spread_time),
            )
            duty.meta["quality_metrics"] = {
                "utilization": round(float(quality_metrics["utilization"]), 4),
                "max_idle_time": int(quality_metrics["max_idle_time"]),
                "total_idle_time": int(quality_metrics["total_idle_time"]),
                "break_count": int(quality_metrics["break_count"]),
                "fragment_count": int(quality_metrics["fragment_count"]),
                "short_connection_count": int(quality_metrics["short_connection_count"]),
                "soft_penalty": round(float(self._operational_quality_penalty(quality_metrics)), 2),
                "thresholds": {
                    "utilization_target": self.utilization_target,
                    "max_spread_soft_minutes": self.max_spread_soft,
                    "max_idle_soft_minutes": self.max_idle_soft,
                    "min_work_soft_minutes": self.min_work_soft,
                    "short_connection_threshold_minutes": self.short_connection_threshold,
                },
            }
            semantic_metrics = self._build_operational_semantic_metrics(
                duty.tasks,
                projected_work=int(duty.work_time),
                projected_spread=int(duty.spread_time),
                duty_id=int(duty.id),
            )
            duty.meta["quality_metrics"]["operational_semantic"] = {
                "utilization": round(float(semantic_metrics["utilization"]), 4),
                "spread_time": int(semantic_metrics["spread_time"]),
                "total_idle_time": int(semantic_metrics["total_idle_time"]),
                "max_idle_time": int(semantic_metrics["max_idle_time"]),
                "break_count": int(semantic_metrics["break_count"]),
                "mandatory_rest_missing": bool(semantic_metrics["mandatory_rest_missing"]),
                "score": round(float(self._operational_semantic_score(semantic_metrics)), 2),
                "thresholds": {
                    "utilization_target": self.semantic_utilization_target,
                    "spread_threshold_minutes": self.semantic_spread_threshold,
                    "rest_penalty": self.semantic_rest_penalty,
                },
            }

            max_continuous_drive, meal_break_found = self._continuous_drive_stats(duty)
            duty.meta["max_continuous_drive_minutes"] = max_continuous_drive
            duty.meta["meal_break_found"] = meal_break_found
            operational_time_report = build_duty_operational_time_report(
                duty,
                min_break_minutes=self.min_break,
                meal_break_minutes=self.meal_break_minutes,
                mandatory_break_after_minutes=self.mandatory_break_after,
            )
            duty.meta["duty_time_segments"] = list(operational_time_report.get("duty_time_segments") or [])
            duty.meta["operational_time_report"] = {
                key: value
                for key, value in operational_time_report.items()
                if key != "duty_time_segments"
            }
            duty.meta["meal_break_found"] = bool(operational_time_report.get("has_valid_mandatory_rest", False))

            if self.apply_cct:
                if self.min_work > 0 and duty.work_time < self.min_work:
                    duty.warnings.append(f"Trabalho abaixo do mínimo: {duty.work_time}min < {self.min_work}min")
                if self.min_shift > 0 and duty.spread_time < self.min_shift:
                    duty.warnings.append(f"Turno abaixo do mínimo: {duty.spread_time}min < {self.min_shift}min")
                if duty.spread_time > self.max_shift:
                    duty.shift_violations += 1
                    duty.warnings.append(f"Spread excedido: {duty.spread_time}min > {self.max_shift}min")
                    violations += 1
                if max_continuous_drive > self.max_driving or max_continuous_drive > self.mandatory_break_after:
                    duty.rest_violations += 1
                    duty.warnings.append(f"Condução contínua excedida: {max_continuous_drive}min")
                    violations += 1
                if operational_time_report.get("invalid_rest_position"):
                    duty.warnings.append(
                        "Pausa longa em soltura/recolhimento nao conta como descanso obrigatorio."
                    )
                if operational_time_report.get("mandatory_rest_required") and not operational_time_report.get("has_valid_mandatory_rest"):
                    duty.rest_violations += 1
                    duty.warnings.append(
                        f"Descanso obrigatorio ausente: 0min < {max(self.min_break, self.meal_break_minutes)}min"
                    )
                    violations += 1
                if duty.overtime_minutes > self.overtime_limit:
                    duty.shift_violations += 1
                    duty.warnings.append(f"Horas extras excedidas: {duty.overtime_minutes}min > {self.overtime_limit}min")
                    violations += 1
                if self.max_total_unpaid_break is not None and unpaid_total > self.max_total_unpaid_break:
                    duty.shift_violations += 1
                    duty.warnings.append(
                        f"Ociosidade total excessiva: {unpaid_total}min > {self.max_total_unpaid_break}min"
                    )
                    violations += 1
                if duty.meta.get("daily_driving", 0) > self.daily_driving_limit:
                    duty.warnings.append("Uso de extensão diária de condução")
            if duty.nocturnal_minutes > 0:
                duty.warnings.append(f"Período noturno aplicado: {duty.nocturnal_minutes}min")
            adjustment_used = int(duty.meta.get("connection_tolerance_used_minutes", 0))
            adjustment_uses = int(duty.meta.get("connection_tolerance_uses", 0))
            if adjustment_used > 0:
                duty.warnings.append(
                    f"Ajuste fino de conexão aplicado: {adjustment_used}min em {adjustment_uses} conexão(ões)"
                )
            if any(t.is_holiday for b in duty.tasks for t in b.trips):
                duty.meta["holiday_extra_pct"] = self.holiday_extra_pct
            if self.enforce_same_depot and duty.meta.get("start_depot_id") is not None and duty.meta.get("end_depot_id") is not None and duty.meta["start_depot_id"] != duty.meta["end_depot_id"]:
                duty.shift_violations += 1
                duty.warnings.append("Jornada não encerra no mesmo depósito")
                violations += 1
            if quality_metrics["utilization"] < self.utilization_target:
                duty.warnings.append(
                    f"Baixa utilização operacional: {quality_metrics['utilization'] * 100:.1f}% < {self.utilization_target * 100:.0f}%"
                )
            if self.max_spread_soft > 0 and duty.spread_time > self.max_spread_soft:
                duty.warnings.append(f"Spread operacional alto: {duty.spread_time}min > {self.max_spread_soft}min")
            if self.max_idle_soft > 0 and quality_metrics["max_idle_time"] > self.max_idle_soft:
                duty.warnings.append(
                    f"Ociosidade máxima alta: {quality_metrics['max_idle_time']}min > {self.max_idle_soft}min"
                )

        roster_state: List[Dict[str, Any]] = []
        group_to_roster: Dict[int, int] = {}
        for duty in sorted(duties, key=lambda item: (item.tasks[0].start_time if item.tasks else 0, item.id)):
            duty_start = int(duty.meta.get("duty_start_minutes", duty.tasks[0].start_time if duty.tasks else 0))
            duty_end = int(duty.meta.get("duty_end_minutes", duty.tasks[-1].end_time if duty.tasks else 0))
            daily_drive = int(duty.meta.get("daily_driving", duty.work_time))
            duty_groups = [int(item) for item in duty.meta.get("covered_trip_group_ids", [])]
            preferred_roster = next((group_to_roster[group_id] for group_id in duty_groups if group_id in group_to_roster), None)
            assigned_roster: Optional[Dict[str, Any]] = None
            sorted_rosters = sorted(roster_state, key=lambda item: item["last_end"], reverse=True)

            def roster_is_compatible(roster: Dict[str, Any]) -> bool:
                gap_since_last = duty_start - int(roster["last_end"])
                if self.apply_cct and gap_since_last < self.inter_shift_rest:
                    return False
                week = duty_start // (7 * 1440)
                fortnight = duty_start // (14 * 1440)
                last_week = int(roster.get("last_week", week))
                if self.apply_cct and week > last_week:
                    required_weekly_rest = self.reduced_weekly_rest if self.allow_reduced_weekly_rest else self.weekly_rest
                    if gap_since_last < required_weekly_rest:
                        return False
                week_drive = roster["week_drive"].get(week, 0) + daily_drive
                fortnight_drive = roster["fortnight_drive"].get(fortnight, 0) + daily_drive
                if self.apply_cct and (week_drive > self.weekly_driving_limit or fortnight_drive > self.fortnight_driving_limit):
                    return False
                return True

            # First pass: try preferred roster only
            if preferred_roster is not None:
                for roster in sorted_rosters:
                    if roster["id"] != preferred_roster:
                        continue
                    if not roster_is_compatible(roster):
                        continue
                    assigned_roster = roster
                    break
            # Second pass: try any compatible roster
            if assigned_roster is None:
                if preferred_roster is not None:
                    warnings.append(f"PAIR_GROUP_ROSTER_SPLIT D{duty.id} expected_roster={preferred_roster}")
                compatible_rosters = [roster for roster in sorted_rosters if roster_is_compatible(roster)]
                if compatible_rosters:
                    compatible_rosters.sort(
                        key=lambda roster: (
                            -len(set(duty_groups) & set(int(item) for item in roster.get("group_ids", set()))),
                            -int(roster["last_end"]),
                            int(roster["id"]),
                        )
                    )
                    assigned_roster = compatible_rosters[0]
            if assigned_roster is not None:
                roster = assigned_roster
                week = duty_start // (7 * 1440)
                fortnight = duty_start // (14 * 1440)
                month = duty_start // (30 * 1440)
                roster["last_end"] = duty_end
                roster["last_week"] = week
                roster["week_drive"][week] = roster["week_drive"].get(week, 0) + daily_drive
                roster["fortnight_drive"][fortnight] = roster["fortnight_drive"].get(fortnight, 0) + daily_drive
                roster["month_drive"][month] = roster["month_drive"].get(month, 0) + daily_drive
                roster["duties"].append(duty.id)
                roster.setdefault("group_ids", set()).update(duty_groups)
            if assigned_roster is None:
                roster_id = len(roster_state) + 1
                assigned_roster = {
                    "id": roster_id,
                    "last_end": duty_end,
                    "last_week": duty_start // (7 * 1440),
                    "week_drive": defaultdict(int),
                    "fortnight_drive": defaultdict(int),
                    "month_drive": defaultdict(int),
                    "duties": [duty.id],
                    "group_ids": set(duty_groups),
                }
                assigned_roster["week_drive"][duty_start // (7 * 1440)] = daily_drive
                assigned_roster["fortnight_drive"][duty_start // (14 * 1440)] = daily_drive
                assigned_roster["month_drive"][duty_start // (30 * 1440)] = daily_drive
                roster_state.append(assigned_roster)
            duty.meta["roster_id"] = assigned_roster["id"]
            for group_id in duty_groups:
                group_to_roster.setdefault(group_id, assigned_roster["id"])

        for roster in roster_state:
            if len(roster["duties"]) >= 6:
                warnings.append(f"ROSTER_{roster['id']}_WEEKLY_REST_REVIEW")

        operator_assignment = self._assign_operator_profiles(roster_state, duties)
        warnings.extend(operator_assignment.get("violations", []))

        return CSPSolution(
            duties=duties,
            uncovered_blocks=uncovered_source_blocks,
            cct_violations=violations,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
            warnings=warnings,
            meta={
                "roster_count": len(roster_state),
                "rosters": [{"id": item["id"], "duties": item["duties"]} for item in roster_state],
                "operator_assignment": operator_assignment,
                "set_covering_objective": "min sum(c_j * x_j)",
                "task_coverage": sum(len(duty.meta.get("task_ids", [])) for duty in duties),
                "quality_summary": self._quality_summary(duties),
            },
        )

    def solve(
        self,
        blocks: List[Block],
        trips: Optional[List[Trip]] = None,
    ) -> CSPSolution:
        self._start_timer()
        self._extension_diagnostics = self._empty_extension_diagnostics()
        if not blocks:
            return CSPSolution(algorithm=self.name, meta={"roster_count": 0})

        tasks, run_cut_meta = self.prepare_tasks(blocks)
        duties: List[Duty] = []
        covered_trip_ids: set[int] = set()
        duplicate_task_skips = 0
        for task in sorted(tasks, key=lambda item: (item.start_time, item.id)):
            task_trip_ids = {
                int(trip.id)
                for trip in task.trips
            }
            duplicated_trip_ids = sorted(task_trip_ids & covered_trip_ids)
            if duplicated_trip_ids:
                duplicate_task_skips += 1
                _log.warning(
                    "[CSP-GREEDY] Skipping duplicated task %s because trips %s are already covered",
                    task.id,
                    duplicated_trip_ids,
                )
                continue
            source_block_id = int(task.meta.get("source_block_id", task.id))
            task_group_ids = {
                int(trip.trip_group_id)
                for trip in task.trips
                if getattr(trip, "trip_group_id", None) is not None
            }
            assigned = False
            feasible_candidates: List[Tuple[float, float, int, int, Duty, Dict[str, Any]]] = []
            ordered_duties = sorted(
                duties,
                key=lambda duty: (
                    0
                    if task_group_ids
                    and any(int(item) in task_group_ids for item in duty.meta.get("covered_trip_group_ids", []))
                    else 1,
                    0 if source_block_id in [int(item) for item in duty.meta.get("source_block_ids", [])] else 1,
                    -duty.work_time,
                    duty.id,
                ),
            )
            for duty in ordered_duties:
                ok, reason, data = self._can_extend(duty, task)
                self._record_extension_attempt("duty_build", duty, task, ok, reason, data)
                if not ok:
                    continue
                projected_work = int(data.get("new_work", duty.work_time + self._block_regulatory_work(task)))
                fairness_penalty = self._fairness_penalty(projected_work)
                gap = float(data.get("gap", 0))
                long_gap_penalty = self._long_unpaid_break_penalty(gap)
                meal_penalty = self._meal_break_score(duty, task, data)
                trip_group_score = self._trip_group_score(duty, task_group_ids, duties)
                overtime_penalty = max(0, projected_work - self.max_work) * self.overtime_weight
                spread_penalty = float(data.get("new_spread", duty.spread_time)) * self.spread_weight
                quality_metrics = self._build_duty_quality_metrics(
                    [*duty.tasks, task],
                    projected_work=projected_work,
                    projected_spread=int(data.get("new_spread", duty.spread_time)),
                )
                quality_penalty = self._operational_quality_penalty(quality_metrics)
                base_candidate_score = (
                    gap
                    + float(data.get("passive_transfer", 0)) * self.passive_transfer_weight
                    + fairness_penalty
                    + long_gap_penalty
                    + meal_penalty
                    + trip_group_score
                    + overtime_penalty
                    + spread_penalty
                    + quality_penalty
                )
                semantic_metrics = self._build_operational_semantic_metrics(
                    [*duty.tasks, task],
                    projected_work=projected_work,
                    projected_spread=int(data.get("new_spread", duty.spread_time)),
                    duty_id=int(duty.id),
                )
                semantic_score = self._operational_semantic_score(
                    semantic_metrics,
                    base_cost=base_candidate_score,
                )
                feasible_candidates.append(
                    (
                        base_candidate_score,
                        semantic_score,
                        int(semantic_metrics["mandatory_rest_missing"]),
                        int(semantic_metrics["max_idle_time"]),
                        duty,
                        data,
                    )
                )
            if feasible_candidates:
                _, _, _, _, duty, data = min(
                    feasible_candidates,
                    key=lambda item: (item[0], item[1], item[2], item[3], item[4].id),
                )
                self._apply_block(duty, task, data)
                covered_trip_ids.update(task_trip_ids)
                assigned = True
            if assigned:
                continue

            duty = Duty(id=self._next_duty_id())
            self._apply_block(
                duty,
                task,
                {
                    "new_work": self._block_regulatory_work(task),
                    "new_spread": self._duty_spread_minutes([task]),
                    "new_cont": self._block_drive(task),
                    "daily_drive": self._block_regulatory_work(task),
                    "extended_days_used": 1 if self._block_regulatory_work(task) > self.daily_driving_limit else 0,
                },
            )
            covered_trip_ids.update(task_trip_ids)
            duties.append(duty)

        duties = self._merge_small_duties(duties)
        duties, relief_reassignment_audit = self._relief_reassignment_postopt(duties, blocks)
        if relief_reassignment_audit.get("accepted_moves"):
            duties = self._merge_small_duties(duties)
        duties, soft_issue_reassignment_audit = self._soft_issue_reassignment_postopt(duties, blocks)

        sol = self.finalize_selected_duties(duties, original_blocks=blocks)
        run_cut_meta["duplicate_task_skips"] = duplicate_task_skips
        sol.meta.update(run_cut_meta)
        sol.meta["duty_merge_diagnostics"] = self._extension_diagnostics_snapshot()
        sol.meta["relief_reassignment_audit"] = relief_reassignment_audit
        sol.meta["soft_issue_reassignment_audit"] = soft_issue_reassignment_audit
        _log.info(
            "[CSP-GREEDY] %d duties (roster_count=%s), avg_work=%d, short(<120)=%d",
            len(duties),
            sol.meta.get("roster_count", "?"),
            sum(d.work_time for d in duties) // max(1, len(duties)),
            sum(1 for d in duties if d.work_time < 120),
        )
        return sol

    # ------------------------------------------------------------------
    # Post-processing: merge small consecutive duties from the same vehicle
    # ------------------------------------------------------------------
    def _merge_small_duties(self, duties: List[Duty]) -> List[Duty]:
        """Tenta mesclar jornadas consecutivas do mesmo veículo se o
        resultado combinado ainda respeitar max_shift e max_work."""
        vehicle_duties: Dict[int, List[Duty]] = {}
        for duty in duties:
            sources = {int(s) for s in duty.meta.get("source_block_ids", [])}
            if len(sources) == 1:
                vid = next(iter(sources))
                vehicle_duties.setdefault(vid, []).append(duty)

        merged_ids: set[int] = set()

        for _vid, vduties in vehicle_duties.items():
            vduties.sort(key=lambda d: d.tasks[0].start_time if d.tasks else 0)

            i = 0
            while i < len(vduties) - 1:
                a = vduties[i]
                b = vduties[i + 1]
                if a.id in merged_ids or b.id in merged_ids:
                    i += 1
                    continue

                # Quick feasibility check before deep-copying
                if not b.tasks or not a.tasks:
                    i += 1
                    continue
                combined_spread = self._duty_spread_minutes([*a.tasks, *b.tasks])
                combined_work = a.work_time + sum(
                    self._block_regulatory_work(t) for t in b.tasks
                )
                if combined_spread > self.max_shift:
                    i += 1
                    continue
                if self._regular_overtime_minutes(combined_work) > self.overtime_limit:
                    i += 1
                    continue

                # Deep simulation: clone a and try appending all tasks from b
                sim = copy.deepcopy(a)
                can_merge = True
                for task in b.tasks:
                    ok, reason, data = self._can_extend(sim, task)
                    self._record_extension_attempt("same_vehicle_merge", sim, task, ok, reason, data)
                    if not ok:
                        can_merge = False
                        break
                    self._apply_block(sim, task, data)

                if can_merge:
                    # Apply for real
                    for task in b.tasks:
                        ok, _, data = self._can_extend(a, task)
                        if ok:
                            self._apply_block(a, task, data)
                    merged_ids.add(b.id)
                    _log.info(
                        "[CSP-MERGE] Merged duty %d into %d (vehicle %d)",
                        b.id, a.id, _vid,
                    )
                    # Don't increment — try merging next duty into updated a
                else:
                    i += 1

        before = len(duties)
        duties = [d for d in duties if d.id not in merged_ids]
        after = len(duties)
        if before != after:
            _log.info("[CSP-MERGE] Merged %d duties: %d → %d", before - after, before, after)

        # --- Phase 2: cross-vehicle merge for short duties ---
        if self.min_work > 0:
            duties = self._cross_vehicle_merge(duties)

        return duties

    def _cross_vehicle_merge(self, duties: List[Duty]) -> List[Duty]:
        """Tenta mesclar jornadas curtas (< min_work) com outra jornada
        próxima temporalmente, respeitando _can_extend para compatibilidade."""
        threshold = self.min_work
        short = [d for d in duties if d.work_time < threshold and d.tasks]
        normal = [d for d in duties if d.work_time >= threshold and d.tasks]
        _log.info("[CSP-CROSS-MERGE] %d short duties (<%dmin), %d normal", len(short), threshold, len(normal))
        if not short:
            return duties

        # Consider merging two shorts together too
        all_candidates = normal + short

        short.sort(key=lambda d: d.tasks[0].start_time)

        merged_ids: set[int] = set()
        for sd in short:
            if sd.id in merged_ids:
                continue
            best_target = None
            best_gap = float("inf")
            best_mode = "append"
            reject_reasons: Dict[str, int] = {}

            for nd in all_candidates:
                if nd.id == sd.id or nd.id in merged_ids:
                    continue
                if not nd.tasks:
                    continue

                # Determine order: which comes first?
                # mode='append': sd comes after nd → append sd tasks to nd
                # mode='prepend': sd comes before nd → use sd as base, append nd tasks
                mode = None
                if sd.tasks[0].start_time >= nd.tasks[-1].end_time:
                    mode = "append"
                    gap = sd.tasks[0].start_time - nd.tasks[-1].end_time
                elif nd.tasks[0].start_time >= sd.tasks[-1].end_time:
                    mode = "prepend"
                    gap = nd.tasks[0].start_time - sd.tasks[-1].end_time
                else:
                    reject_reasons["overlap"] = reject_reasons.get("overlap", 0) + 1
                    continue

                # Quick feasibility
                combined_work = nd.work_time + sd.work_time
                combined_tasks = [*nd.tasks, *sd.tasks] if mode == "append" else [*sd.tasks, *nd.tasks]
                combined_spread = self._duty_spread_minutes(combined_tasks)
                if combined_spread > self.max_shift:
                    reject_reasons["spread"] = reject_reasons.get("spread", 0) + 1
                    continue
                if self._regular_overtime_minutes(combined_work) > self.overtime_limit:
                    reject_reasons["overtime"] = reject_reasons.get("overtime", 0) + 1
                    continue

                if mode == "append":
                    # Try _can_extend for each task in sd appended to nd
                    sim = copy.deepcopy(nd)
                    can_merge = True
                    tasks_to_add = sorted(sd.tasks, key=lambda t: t.start_time)
                    for task in tasks_to_add:
                        ok, reason, data = self._can_extend(sim, task)
                        self._record_extension_attempt("cross_vehicle_short_merge", sim, task, ok, reason, data)
                        if not ok:
                            can_merge = False
                            reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
                            break
                        self._apply_block(sim, task, data)
                else:
                    # prepend: build from sd then append nd tasks
                    sim = copy.deepcopy(sd)
                    can_merge = True
                    tasks_to_add = sorted(nd.tasks, key=lambda t: t.start_time)
                    for task in tasks_to_add:
                        ok, reason, data = self._can_extend(sim, task)
                        self._record_extension_attempt("cross_vehicle_short_merge", sim, task, ok, reason, data)
                        if not ok:
                            can_merge = False
                            reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
                            break
                        self._apply_block(sim, task, data)

                if can_merge and gap < best_gap:
                    best_gap = gap
                    best_target = nd
                    best_mode = mode

            if best_target is not None:
                if best_mode == "append":
                    # Append sd tasks to nd
                    tasks_to_add = sorted(sd.tasks, key=lambda t: t.start_time)
                    for task in tasks_to_add:
                        ok, _, data = self._can_extend(best_target, task)
                        if ok:
                            self._apply_block(best_target, task, data)
                else:
                    # Prepend: rebuild from sd + nd tasks
                    tasks_to_add = sorted(best_target.tasks, key=lambda t: t.start_time)
                    # Reset sd to receive nd tasks
                    all_applied = True
                    for task in tasks_to_add:
                        ok, _, data = self._can_extend(sd, task)
                        if ok:
                            self._apply_block(sd, task, data)
                        else:
                            all_applied = False
                            break
                    if all_applied:
                        # Replace best_target contents with merged sd
                        best_target.tasks = sd.tasks
                        best_target.work_time = sd.work_time
                        best_target.spread_time = sd.spread_time
                        best_target.meta = sd.meta
                    else:
                        # Merge failed at apply time — skip this merge
                        continue
                merged_ids.add(sd.id)
                _log.info(
                    "[CSP-CROSS-MERGE] Merged short duty %d (%dmin) into duty %d via %s (now %dmin work)",
                    sd.id, sd.work_time, best_target.id, best_mode, best_target.work_time,
                )
            else:
                _log.info(
                    "[CSP-CROSS-MERGE] Could not merge duty %d (%dmin): rejects=%s",
                    sd.id, sd.work_time, reject_reasons,
                )

        if merged_ids:
            duties = [d for d in duties if d.id not in merged_ids]
            _log.info("[CSP-CROSS-MERGE] Absorbed %d short duties, %d remain", len(merged_ids), len(duties))
        return duties

    def _task_is_relief_reassignment_candidate(self, task: Block) -> bool:
        if not task.trips:
            return False
        if bool(task.meta.get("starts_at_mid_trip_relief", False)):
            return True
        if bool(task.meta.get("ends_at_mid_trip_relief", False)):
            return True
        return bool(task.meta.get("contains_mid_trip_relief_segment", False))

    def _task_summary(self, task: Block) -> Dict[str, Any]:
        return {
            "task_id": int(task.meta.get("task_id", task.id)),
            "source_block_id": int(task.meta.get("source_block_id", task.id)),
            "trip_ids": [int(getattr(trip, "public_id", trip.id)) for trip in task.trips],
            "task_trip_ids": [int(trip.id) for trip in task.trips],
            "trip_group_ids": sorted(self._task_group_ids(task)),
            "mid_trip_original_trip_ids": [
                int(item) for item in (task.meta.get("mid_trip_original_trip_ids") or [])
            ],
            "start_time": int(task.start_time),
            "end_time": int(task.end_time),
            "relief_start_id": task.meta.get("relief_start_id"),
            "relief_end_id": task.meta.get("relief_end_id"),
            "split_reason": task.meta.get("split_reason"),
            "starts_at_mid_trip_relief": bool(task.meta.get("starts_at_mid_trip_relief", False)),
            "ends_at_mid_trip_relief": bool(task.meta.get("ends_at_mid_trip_relief", False)),
        }

    def _tasks_group_ids(self, tasks: Sequence[Block]) -> set[int]:
        group_ids: set[int] = set()
        for task in tasks:
            group_ids.update(self._task_group_ids(task))
        return group_ids

    def _is_extreme_duty(
        self,
        duty: Duty,
        quality_metrics: Optional[Dict[str, Any]] = None,
    ) -> bool:
        metrics = quality_metrics or duty.meta.get("quality_metrics") or self._build_duty_quality_metrics(
            duty.tasks,
            projected_work=int(duty.work_time),
            projected_spread=int(duty.spread_time),
        )
        utilization = float(metrics.get("utilization", 1.0) or 1.0)
        spread_time = int(metrics.get("spread_time", duty.spread_time) or duty.spread_time)
        total_idle_time = int(
            metrics.get("total_idle_time", max(0, spread_time - int(metrics.get("work_time", duty.work_time) or duty.work_time)))
            or 0
        )
        return (
            utilization < self.extreme_utilization_threshold
            and spread_time > self.semantic_spread_threshold
        )

    def _seed_duty_with_task(self, duty_id: int, task: Block) -> Duty:
        duty = Duty(id=duty_id)
        block_drive = self._block_drive(task)
        self._apply_block(
            duty,
            task,
            {
                "new_work": block_drive,
                "new_spread": self._duty_spread_minutes([task]),
                "new_cont": block_drive,
                "daily_drive": block_drive,
                "extended_days_used": 1 if block_drive > self.daily_driving_limit else 0,
            },
        )
        return duty

    def _rebuild_duty_from_tasks(self, tasks: Sequence[Block], duty_id: int) -> Tuple[Optional[Duty], str]:
        ordered = sorted((task for task in tasks if task.trips), key=lambda item: (item.start_time, item.id))
        if not ordered:
            return None, "empty"

        duty = self._seed_duty_with_task(duty_id, ordered[0])
        for task in ordered[1:]:
            ok, reason, data = self._can_extend(duty, task)
            if not ok:
                return None, reason or "rebuild_failed"
            self._apply_block(duty, task, data)
        return duty, ""

    def _build_relief_reassignment_metrics(self, solution: CSPSolution) -> Dict[str, Any]:
        duties = solution.duties or []
        short_duties = sum(1 for duty in duties if self.min_work > 0 and duty.work_time < self.min_work)
        split_duties = 0
        waiting_minutes = 0
        unpaid_break_minutes = 0
        total_overtime_minutes = 0
        total_paid_minutes = 0
        meal_break_missing = 0
        mandatory_rest_missing = 0
        low_utilization_duties = 0
        high_spread_duties = 0
        extreme_duties = 0
        low_work_duties = 0
        fragmented_duties = 0
        short_connection_total = 0
        max_idle_time = 0
        total_utilization = 0.0
        total_idle_minutes = 0
        total_semantic_score = 0.0
        relief_handoff_map: Dict[int, set[int]] = defaultdict(set)
        duty_group_map: Dict[int, set[int]] = defaultdict(set)
        roster_group_map: Dict[int, set[int]] = defaultdict(set)
        vehicle_switches = 0

        for duty in duties:
            unique_sources: List[int] = []
            for source_block_id in duty.meta.get("source_block_ids", []):
                if source_block_id is None:
                    continue
                parsed_source = int(source_block_id)
                if parsed_source not in unique_sources:
                    unique_sources.append(parsed_source)
            if len(unique_sources) > 1:
                split_duties += 1
                vehicle_switches += len(unique_sources) - 1

            waiting_minutes += int(duty.meta.get("waiting_minutes", 0) or 0)
            unpaid_break_minutes += int(
                duty.meta.get("unpaid_break_total_minutes", max(0, duty.spread_time - duty.work_time)) or 0
            )
            total_overtime_minutes += int(duty.overtime_minutes or 0)
            total_paid_minutes += int(duty.paid_minutes or 0)
            quality_metrics = self._build_duty_quality_metrics(
                duty.tasks,
                projected_work=int(duty.work_time),
                projected_spread=int(duty.spread_time),
            )
            semantic_metrics = self._build_operational_semantic_metrics(
                duty.tasks,
                projected_work=int(duty.work_time),
                projected_spread=int(duty.spread_time),
                duty_id=int(duty.id),
            )
            total_utilization += float(quality_metrics["utilization"])
            max_idle_time = max(max_idle_time, int(semantic_metrics["max_idle_time"]))
            short_connection_total += int(quality_metrics["short_connection_count"])
            total_idle_minutes += int(semantic_metrics["total_idle_time"])
            total_semantic_score += self._operational_semantic_score(semantic_metrics)
            if float(quality_metrics["utilization"]) < self.utilization_target:
                low_utilization_duties += 1
            if self.max_spread_soft > 0 and int(quality_metrics["spread_time"]) > self.max_spread_soft:
                high_spread_duties += 1
            if self._is_extreme_duty(duty, quality_metrics):
                extreme_duties += 1
            if self.min_work_soft > 0 and int(quality_metrics["work_time"]) < self.min_work_soft:
                low_work_duties += 1
            if int(quality_metrics["break_count"]) > self.fragmentation_soft_limit:
                fragmented_duties += 1
            if bool(semantic_metrics["mandatory_rest_missing"]):
                meal_break_missing += 1
                mandatory_rest_missing += 1

            roster_id = duty.meta.get("roster_id")
            for group_id in (duty.meta.get("covered_trip_group_ids") or []):
                parsed_group_id = int(group_id)
                duty_group_map[parsed_group_id].add(int(duty.id))
                if roster_id is not None:
                    roster_group_map[parsed_group_id].add(int(roster_id))

            for trip in duty.all_trips:
                if trip.is_mid_trip_segment:
                    relief_handoff_map[int(trip.public_id)].add(int(duty.id))

        relief_handoffs = sum(1 for assigned_duties in relief_handoff_map.values() if len(assigned_duties) > 1)
        duty_group_splits = sum(1 for duty_ids in duty_group_map.values() if len(duty_ids) > 1)
        roster_group_splits = sum(1 for roster_ids in roster_group_map.values() if len(roster_ids) > 1)
        fragmentation_score = (
            len(duties) * 10000
            + short_duties * 1000
            + split_duties * 800
            + vehicle_switches * 600
            + waiting_minutes
            + max(0, unpaid_break_minutes - waiting_minutes)
            + total_overtime_minutes * 10
        )

        return {
            "crew": int(solution.num_crew),
            "duties": len(duties),
            "violations": int(solution.cct_violations or 0),
            "short_duties": short_duties,
            "split_duties": split_duties,
            "vehicle_switches": vehicle_switches,
            "waiting_minutes": waiting_minutes,
            "unpaid_break_minutes": unpaid_break_minutes,
            "total_overtime_minutes": total_overtime_minutes,
            "total_paid_minutes": total_paid_minutes,
            "avg_utilization": round(total_utilization / max(1, len(duties)), 4),
            "low_utilization_duties": low_utilization_duties,
            "high_spread_duties": high_spread_duties,
            "extreme_duties": extreme_duties,
            "low_work_duties": low_work_duties,
            "fragmented_duties": fragmented_duties,
            "short_connection_total": short_connection_total,
            "max_idle_time": max_idle_time,
            "meal_break_missing": meal_break_missing,
            "mandatory_rest_missing": mandatory_rest_missing,
            "average_idle_minutes": round(total_idle_minutes / max(1, len(duties)), 2),
            "total_idle_minutes": total_idle_minutes,
            "operational_semantic_score": round(total_semantic_score, 2),
            "duty_group_splits": duty_group_splits,
            "roster_group_splits": roster_group_splits,
            "relief_handoffs": relief_handoffs,
            "uncovered_blocks": len(solution.uncovered_blocks or []),
            "fragmentation_score": fragmentation_score,
        }

    def _relief_reassignment_rank(self, metrics: Dict[str, Any]) -> Tuple[int, ...]:
        return (
            int(metrics.get("violations", 0)),
            int(metrics.get("uncovered_blocks", 0)),
            int(metrics.get("mandatory_rest_missing", metrics.get("meal_break_missing", 0))),
            int(metrics.get("meal_break_missing", 0)),
            int(metrics.get("duty_group_splits", 0)),
            int(metrics.get("roster_group_splits", 0)),
            int(metrics.get("extreme_duties", 0)),
            int(metrics.get("crew", 0)),
            int(metrics.get("duties", 0)),
            int(metrics.get("low_utilization_duties", 0)),
            int(metrics.get("high_spread_duties", 0)),
            int(metrics.get("fragmented_duties", 0)),
            int(metrics.get("short_connection_total", 0)),
            int(metrics.get("max_idle_time", 0)),
            int(metrics.get("split_duties", 0)),
            int(metrics.get("vehicle_switches", 0)),
            int(metrics.get("fragmentation_score", 0)),
            int(metrics.get("short_duties", 0)),
            int(metrics.get("total_overtime_minutes", 0)),
            int(metrics.get("waiting_minutes", 0)),
            int(round(float(metrics.get("operational_semantic_score", 0.0) or 0.0))),
        )

    def _evaluate_relief_candidate_duties(
        self,
        duties: Sequence[Duty],
        original_blocks: Optional[List[Block]],
    ) -> Tuple[List[Duty], CSPSolution, Dict[str, Any]]:
        snapshot = copy.deepcopy(self._extension_diagnostics)
        try:
            normalized = copy.deepcopy(
                sorted((duty for duty in duties if duty.tasks), key=lambda item: (item.start_time, item.id))
            )
            normalized = self._merge_small_duties(normalized)
            solution = self.finalize_selected_duties(normalized, original_blocks=original_blocks)
            metrics = self._build_relief_reassignment_metrics(solution)
        finally:
            self._extension_diagnostics = snapshot
        return normalized, solution, metrics

    def _soft_issue_operational_rank(self, metrics: Dict[str, Any]) -> Tuple[int, ...]:
        return (
            int(metrics.get("extreme_duties", 0)),
            int(metrics.get("mandatory_rest_missing", metrics.get("meal_break_missing", 0))),
            int(metrics.get("low_utilization_duties", 0)),
            int(metrics.get("high_spread_duties", 0)),
            int(metrics.get("fragmented_duties", 0)),
            int(metrics.get("short_connection_total", 0)),
            int(metrics.get("max_idle_time", 0)),
            int(metrics.get("total_overtime_minutes", 0)),
            int(metrics.get("waiting_minutes", 0)),
            int(round(float(metrics.get("operational_semantic_score", 0.0) or 0.0))),
        )

    def _soft_issue_candidate_accepted(
        self,
        current_metrics: Dict[str, Any],
        candidate_metrics: Dict[str, Any],
        current_rank: Tuple[int, ...],
        candidate_rank: Tuple[int, ...],
    ) -> bool:
        if candidate_rank < current_rank and self._soft_issue_improved(current_metrics, candidate_metrics):
            return True

        guard_keys = (
            "violations",
            "uncovered_blocks",
            "mandatory_rest_missing",
            "meal_break_missing",
            "duty_group_splits",
            "roster_group_splits",
            "extreme_duties",
            "crew",
        )
        if any(
            int(candidate_metrics.get(key, 0)) > int(current_metrics.get(key, 0))
            for key in guard_keys
        ):
            return False

        if int(candidate_metrics.get("duties", 0)) > int(current_metrics.get("duties", 0)) + 1:
            return False

        return self._soft_issue_operational_rank(candidate_metrics) < self._soft_issue_operational_rank(current_metrics)

    def _evaluate_soft_issue_candidate(
        self,
        *,
        candidate_duties: Sequence[Duty],
        current_metrics: Dict[str, Any],
        current_rank: Tuple[int, ...],
        original_blocks: Optional[List[Block]],
        candidate_sample: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Tuple[int, ...]]]:
        normalized_candidate, _, candidate_metrics = self._evaluate_relief_candidate_duties(
            candidate_duties,
            original_blocks,
        )
        candidate_rank = self._relief_reassignment_rank(candidate_metrics)
        evaluated_sample = {
            **candidate_sample,
            "metrics_before": current_metrics,
            "metrics_after": candidate_metrics,
        }
        if self._soft_issue_candidate_accepted(
            current_metrics,
            candidate_metrics,
            current_rank,
            candidate_rank,
        ):
            return (
                {
                    "duties": normalized_candidate,
                    "metrics": candidate_metrics,
                    "details": evaluated_sample,
                },
                candidate_metrics,
                candidate_rank,
            )
        return None, candidate_metrics, candidate_rank

    def _relief_reassignment_postopt(
        self,
        duties: List[Duty],
        original_blocks: Optional[List[Block]],
    ) -> Tuple[List[Duty], Dict[str, Any]]:
        enabled = bool(self.params.get("enable_relief_reassignment_postopt", True))
        max_passes = max(1, int(self.params.get("relief_reassignment_max_passes", 4) or 4))
        target_limit = max(1, int(self.params.get("relief_reassignment_target_limit", 12) or 12))
        sample_limit = max(10, int(self.params.get("relief_reassignment_sample_limit", 24) or 24))
        audit: Dict[str, Any] = {
            "enabled": enabled,
            "passes": 0,
            "considered": 0,
            "evaluated": 0,
            "feasible_targets": 0,
            "accepted": 0,
            "accepted_moves": [],
            "rejection_reasons": {},
            "samples": [],
            "baseline_metrics": None,
            "final_metrics": None,
            "relief_task_candidates": 0,
            "improved": False,
        }

        if not enabled:
            audit["skipped"] = "disabled"
            return duties, audit

        seeded_duties = [duty for duty in duties if duty.tasks]
        if not seeded_duties:
            audit["skipped"] = "no_duties"
            return duties, audit

        current_duties, _, current_metrics = self._evaluate_relief_candidate_duties(seeded_duties, original_blocks)
        audit["baseline_metrics"] = current_metrics
        audit["final_metrics"] = current_metrics
        audit["relief_task_candidates"] = sum(
            1
            for duty in current_duties
            for task in duty.tasks
            if self._task_is_relief_reassignment_candidate(task)
        )

        if audit["relief_task_candidates"] == 0:
            audit["skipped"] = "no_relief_candidates"
            return current_duties, audit

        def record_rejection(reason: str, sample: Dict[str, Any]) -> None:
            reason_key = reason or "unknown"
            audit["rejection_reasons"][reason_key] = int(audit["rejection_reasons"].get(reason_key, 0)) + 1
            if len(audit["samples"]) < sample_limit:
                audit["samples"].append(sample)

        current_rank = self._relief_reassignment_rank(current_metrics)

        for pass_index in range(max_passes):
            audit["passes"] = pass_index + 1
            best_candidate: Optional[Dict[str, Any]] = None
            best_rank: Optional[Tuple[int, ...]] = None

            for source_duty in sorted(current_duties, key=lambda item: (item.start_time, item.id)):
                for task_index, task in enumerate(source_duty.tasks):
                    if not self._task_is_relief_reassignment_candidate(task):
                        continue

                    source_remaining = [candidate_task for idx, candidate_task in enumerate(source_duty.tasks) if idx != task_index]
                    source_rebuilt: Optional[Duty] = None
                    if source_remaining:
                        source_rebuilt, source_reason = self._rebuild_duty_from_tasks(source_remaining, source_duty.id)
                        if source_rebuilt is None:
                            record_rejection(
                                f"source_rebuild_{source_reason}",
                                {
                                    "reason": f"source_rebuild_{source_reason}",
                                    "source_duty_id": int(source_duty.id),
                                    "target_duty_id": None,
                                    "mode": None,
                                    "task": self._task_summary(task),
                                },
                            )
                            continue

                    candidate_targets = [
                        duty
                        for duty in current_duties
                        if duty.id != source_duty.id and duty.tasks
                    ]
                    candidate_targets.sort(
                        key=lambda duty: (
                            min(
                                abs(int(task.start_time) - int(duty.tasks[-1].end_time)),
                                abs(int(duty.tasks[0].start_time) - int(task.end_time)),
                            ),
                            duty.id,
                        )
                    )

                    for target_duty in candidate_targets[:target_limit]:
                        for mode in ("append", "prepend"):
                            audit["considered"] = int(audit.get("considered", 0)) + 1
                            if mode == "append":
                                if int(target_duty.tasks[-1].end_time) > int(task.start_time):
                                    record_rejection(
                                        "append_target_overlap",
                                        {
                                            "reason": "append_target_overlap",
                                            "source_duty_id": int(source_duty.id),
                                            "target_duty_id": int(target_duty.id),
                                            "mode": mode,
                                            "task": self._task_summary(task),
                                        },
                                    )
                                    continue
                                target_task_sequence = [*target_duty.tasks, task]
                            else:
                                if int(task.end_time) > int(target_duty.tasks[0].start_time):
                                    record_rejection(
                                        "prepend_target_overlap",
                                        {
                                            "reason": "prepend_target_overlap",
                                            "source_duty_id": int(source_duty.id),
                                            "target_duty_id": int(target_duty.id),
                                            "mode": mode,
                                            "task": self._task_summary(task),
                                        },
                                    )
                                    continue
                                target_task_sequence = [task, *target_duty.tasks]

                            target_rebuilt, target_reason = self._rebuild_duty_from_tasks(
                                target_task_sequence,
                                target_duty.id,
                            )
                            if target_rebuilt is None:
                                record_rejection(
                                    f"{mode}_target_{target_reason}",
                                    {
                                        "reason": f"{mode}_target_{target_reason}",
                                        "source_duty_id": int(source_duty.id),
                                        "target_duty_id": int(target_duty.id),
                                        "mode": mode,
                                        "task": self._task_summary(task),
                                    },
                                )
                                continue

                            audit["feasible_targets"] = int(audit.get("feasible_targets", 0)) + 1

                            candidate_duties: List[Duty] = []
                            for existing_duty in current_duties:
                                if existing_duty.id == source_duty.id:
                                    if source_rebuilt is not None:
                                        candidate_duties.append(source_rebuilt)
                                    continue
                                if existing_duty.id == target_duty.id:
                                    candidate_duties.append(target_rebuilt)
                                    continue
                                candidate_duties.append(existing_duty)

                            normalized_candidate, _, candidate_metrics = self._evaluate_relief_candidate_duties(
                                candidate_duties,
                                original_blocks,
                            )
                            audit["evaluated"] = int(audit.get("evaluated", 0)) + 1
                            candidate_rank = self._relief_reassignment_rank(candidate_metrics)
                            candidate_sample = {
                                "source_duty_id": int(source_duty.id),
                                "target_duty_id": int(target_duty.id),
                                "mode": mode,
                                "task": self._task_summary(task),
                                "metrics_before": current_metrics,
                                "metrics_after": candidate_metrics,
                            }

                            if candidate_rank < current_rank:
                                if best_candidate is None or candidate_rank < (best_rank or candidate_rank):
                                    best_candidate = {
                                        "duties": normalized_candidate,
                                        "metrics": candidate_metrics,
                                        "details": candidate_sample,
                                    }
                                    best_rank = candidate_rank
                                continue

                            record_rejection(
                                "not_better",
                                {
                                    **candidate_sample,
                                    "reason": "not_better",
                                },
                            )

            if best_candidate is None:
                break

            current_duties = best_candidate["duties"]
            current_metrics = best_candidate["metrics"]
            current_rank = self._relief_reassignment_rank(current_metrics)
            audit["accepted"] = int(audit.get("accepted", 0)) + 1
            if len(audit["accepted_moves"]) < sample_limit:
                audit["accepted_moves"].append(best_candidate["details"])

        audit["final_metrics"] = current_metrics
        baseline_metrics = audit["baseline_metrics"] or current_metrics
        baseline_rank = self._relief_reassignment_rank(baseline_metrics)
        final_rank = self._relief_reassignment_rank(current_metrics)
        audit["improved"] = bool(
            self._soft_issue_candidate_accepted(
                baseline_metrics,
                current_metrics,
                baseline_rank,
                final_rank,
            )
            and current_metrics != baseline_metrics
        )
        if not audit["improved"] and audit.get("accepted") == 0:
            audit["result"] = "no_accepted_improvement"
        elif audit["improved"]:
            audit["result"] = "accepted_improvement"
        else:
            audit["result"] = "accepted_without_rank_gain"
        return current_duties, audit

    def _split_group_ids(self, duties: Sequence[Duty]) -> set[int]:
        group_to_duties: Dict[int, set[int]] = defaultdict(set)
        for duty in duties:
            for group_id in (duty.meta.get("covered_trip_group_ids") or []):
                group_to_duties[int(group_id)].add(int(duty.id))
        return {
            group_id
            for group_id, assigned_duties in group_to_duties.items()
            if len(assigned_duties) > 1
        }

    def _soft_issue_candidate_sources(self, duties: Sequence[Duty]) -> List[Dict[str, Any]]:
        split_group_ids = self._split_group_ids(duties)
        candidates: List[Dict[str, Any]] = []
        seen: set[Tuple[int, int]] = set()

        for duty in sorted((item for item in duties if item.tasks), key=lambda item: (item.start_time, item.id)):
            mandatory_rest_repair_indexes = self._mandatory_rest_repairable_task_indexes(duty)
            needs_meal_fix = self._duty_needs_meal_break(
                duty,
                projected_spread=int(duty.spread_time),
                projected_has_break=bool(duty.meta.get("meal_break_found", False)),
            )
            quality_metrics = duty.meta.get("quality_metrics") or self._build_duty_quality_metrics(
                duty.tasks,
                projected_work=int(duty.work_time),
                projected_spread=int(duty.spread_time),
            )
            extreme_duty = self._is_extreme_duty(duty, quality_metrics)
            bad_utilization = float(quality_metrics.get("utilization", 1.0) or 1.0) < self.utilization_target
            bad_spread = self.max_spread_soft > 0 and int(quality_metrics.get("spread_time", duty.spread_time) or duty.spread_time) > self.max_spread_soft
            bad_fragmentation = int(quality_metrics.get("break_count", 0) or 0) > self.fragmentation_soft_limit
            for task_index, task in enumerate(duty.tasks):
                reasons: List[str] = []
                task_group_ids = self._task_group_ids(task)
                if task_group_ids & split_group_ids:
                    reasons.append("trip_group_split")
                if task_index in mandatory_rest_repair_indexes:
                    reasons.append("mandatory_rest_missing_repair")
                if needs_meal_fix and len(duty.tasks) > 1 and task_index in (0, len(duty.tasks) - 1):
                    reasons.append("meal_break_missing")
                if len(duty.tasks) > 1 and task_index in (0, len(duty.tasks) - 1):
                    if bad_utilization:
                        reasons.append("low_utilization")
                    if bad_spread:
                        reasons.append("high_spread")
                    if bad_fragmentation:
                        reasons.append("fragmentation")
                    if extreme_duty:
                        reasons.append("extreme_low_utilization_spread")
                if not reasons:
                    continue
                signature = (int(duty.id), int(task_index))
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append(
                    {
                        "source_duty": duty,
                        "task_index": task_index,
                        "task": task,
                        "task_group_ids": task_group_ids,
                        "reasons": reasons,
                        "priority": (
                            0 if "trip_group_split" in reasons else 1,
                            0 if "mandatory_rest_missing_repair" in reasons else 1,
                            0 if "meal_break_missing" in reasons else 1,
                            0 if "low_utilization" in reasons else 1,
                            0 if "high_spread" in reasons else 1,
                            0 if "fragmentation" in reasons else 1,
                            0 if "extreme_low_utilization_spread" in reasons else 1,
                            -len(task_group_ids & split_group_ids),
                            int(task.total_drive_minutes),
                            int(task.start_time),
                            int(duty.id),
                        ),
                    }
                )

        candidates.sort(key=lambda item: item["priority"])
        return candidates

    def _mandatory_rest_repairable_task_indexes(self, duty: Duty) -> set[int]:
        if len(duty.tasks) < 3:
            return set()

        semantic_metrics = self._build_operational_semantic_metrics(
            duty.tasks,
            projected_work=int(duty.work_time),
            projected_spread=int(duty.spread_time),
            duty_id=int(duty.id),
        )
        if not bool(semantic_metrics.get("mandatory_rest_missing")):
            return set()

        repairable: set[int] = set()
        for task_index in range(1, len(duty.tasks) - 1):
            source_remaining = [
                candidate_task
                for index, candidate_task in enumerate(duty.tasks)
                if index != task_index
            ]
            source_rebuilt, _ = self._rebuild_duty_from_tasks(source_remaining, int(duty.id))
            if source_rebuilt is None:
                continue

            source_metrics = self._build_operational_semantic_metrics(
                source_rebuilt.tasks,
                projected_work=int(source_rebuilt.work_time),
                projected_spread=int(source_rebuilt.spread_time),
                duty_id=int(source_rebuilt.id),
            )
            if bool(source_metrics.get("mandatory_rest_missing")):
                continue

            extracted_duty, _ = self._rebuild_duty_from_tasks([duty.tasks[task_index]], -10_000 - int(task_index))
            if extracted_duty is None:
                continue
            extracted_metrics = self._build_operational_semantic_metrics(
                extracted_duty.tasks,
                projected_work=int(extracted_duty.work_time),
                projected_spread=int(extracted_duty.spread_time),
                duty_id=int(extracted_duty.id),
            )
            if bool(extracted_metrics.get("mandatory_rest_missing")):
                continue

            repairable.add(task_index)

        return repairable

    def _soft_issue_target_duties(
        self,
        current_duties: Sequence[Duty],
        source_duty: Duty,
        task: Block,
        task_group_ids: set[int],
    ) -> List[Duty]:
        candidate_targets = [
            duty
            for duty in current_duties
            if duty.id != source_duty.id and duty.tasks
        ]
        candidate_targets.sort(
            key=lambda duty: (
                0 if task_group_ids & {int(item) for item in duty.meta.get("covered_trip_group_ids", [])} else 1,
                min(
                    abs(int(task.start_time) - int(duty.tasks[-1].end_time)),
                    abs(int(duty.tasks[0].start_time) - int(task.end_time)),
                ),
                duty.id,
            )
        )
        return candidate_targets

    def _soft_issue_reconstruction_focus_duty_ids(self) -> set[int]:
        raw_ids = self.params.get("soft_issue_reconstruction_focus_duty_ids") or []
        if isinstance(raw_ids, (int, str)):
            raw_ids = [raw_ids]

        focus_ids: set[int] = set()
        for raw_id in raw_ids:
            try:
                focus_ids.add(int(raw_id))
            except (TypeError, ValueError):
                continue
        return focus_ids

    def _soft_issue_reconstruction_bundles(self, duty: Duty) -> List[List[Block]]:
        ordered_tasks = list(duty.tasks)
        if len(ordered_tasks) <= 1:
            return [[task] for task in ordered_tasks]

        group_to_indices: dict[int, list[int]] = defaultdict(list)
        for index, task in enumerate(ordered_tasks):
            for group_id in self._task_group_ids(task):
                group_to_indices[int(group_id)].append(index)

        adjacency: dict[int, set[int]] = {index: set() for index in range(len(ordered_tasks))}
        for indices in group_to_indices.values():
            if len(indices) <= 1:
                continue
            for left in indices:
                adjacency[left].update(indices)
                adjacency[left].discard(left)

        components: List[List[int]] = []
        visited: set[int] = set()
        for index in range(len(ordered_tasks)):
            if index in visited:
                continue
            stack = [index]
            component: List[int] = []
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)
                stack.extend(sorted(adjacency[current] - visited, reverse=True))
            components.append(sorted(component))

        components.sort(key=lambda item: item[0] if item else 0)
        if int(duty.id) in self._soft_issue_reconstruction_focus_duty_ids():
            return [[ordered_tasks[index] for index in component] for component in components if component]

        if len(ordered_tasks) <= 2:
            return [[ordered_tasks[index] for index in component] for component in components if component]

        component_by_index: dict[int, list[int]] = {}
        for component in components:
            for index in component:
                component_by_index[index] = component

        first_component = component_by_index.get(0, [0])
        last_component = component_by_index.get(len(ordered_tasks) - 1, [len(ordered_tasks) - 1])
        if first_component == last_component:
            return [[ordered_tasks[index] for index in first_component]]

        first_indices = set(first_component)
        last_indices = set(last_component)
        middle_indices = [
            index for index in range(len(ordered_tasks))
            if index not in first_indices and index not in last_indices
        ]

        bundles: List[List[Block]] = []
        bundles.append([ordered_tasks[index] for index in sorted(first_indices)])
        if middle_indices:
            bundles.append([ordered_tasks[index] for index in middle_indices])
        bundles.append([ordered_tasks[index] for index in sorted(last_indices)])
        return [bundle for bundle in bundles if bundle]

    def _soft_issue_rebuild_bundle_into_duty(
        self,
        duty: Duty,
        bundle: Sequence[Block],
        mode: str,
    ) -> Tuple[Optional[Duty], str]:
        if mode == "append":
            task_sequence = [*duty.tasks, *bundle]
        elif mode == "prepend":
            task_sequence = [*bundle, *duty.tasks]
        else:
            return None, "unsupported_mode"
        return self._rebuild_duty_from_tasks(task_sequence, duty.id)

    def _soft_issue_build_compact_dedicated_duties(
        self,
        bundles: Sequence[Sequence[Block]],
        next_duty_id: int,
    ) -> Tuple[List[Duty], List[Dict[str, Any]], int]:
        dedicated_duties: List[Duty] = []
        allocation_details: List[Dict[str, Any]] = []
        next_id = next_duty_id

        for bundle in bundles:
            ordered_bundle = sorted((task for task in bundle if task.trips), key=lambda item: (item.start_time, item.id))
            if not ordered_bundle:
                continue

            best_choice: Optional[Tuple[float, int, int, str, Optional[int], Duty]] = None
            for duty_index, dedicated in enumerate(dedicated_duties):
                rebuilt, reason = self._rebuild_duty_from_tasks([*dedicated.tasks, *ordered_bundle], dedicated.id)
                if rebuilt is None:
                    continue
                semantic_metrics = self._build_operational_semantic_metrics(
                    rebuilt.tasks,
                    projected_work=int(rebuilt.work_time),
                    projected_spread=int(rebuilt.spread_time),
                    duty_id=int(rebuilt.id),
                )
                semantic_score = self._operational_semantic_score(semantic_metrics)
                choice = (
                    semantic_score,
                    int(semantic_metrics["mandatory_rest_missing"]),
                    int(semantic_metrics["max_idle_time"]),
                    "merge",
                    duty_index,
                    rebuilt,
                )
                if best_choice is None or choice < best_choice:
                    best_choice = choice

            rebuilt, reason = self._rebuild_duty_from_tasks(ordered_bundle, next_id)
            if rebuilt is None:
                raise ValueError(f"bundle_dedicated_rebuild_failed:{reason}")
            semantic_metrics = self._build_operational_semantic_metrics(
                rebuilt.tasks,
                projected_work=int(rebuilt.work_time),
                projected_spread=int(rebuilt.spread_time),
                duty_id=int(rebuilt.id),
            )
            semantic_score = self._operational_semantic_score(semantic_metrics)
            new_choice = (
                semantic_score,
                int(semantic_metrics["mandatory_rest_missing"]),
                int(semantic_metrics["max_idle_time"]),
                "new",
                None,
                rebuilt,
            )
            if best_choice is None or new_choice < best_choice:
                best_choice = new_choice

            if best_choice is None:
                raise ValueError("bundle_dedicated_choice_missing")

            _, _, _, choice_mode, duty_index, chosen_duty = best_choice
            if choice_mode == "merge" and duty_index is not None:
                dedicated_duties[duty_index] = chosen_duty
                allocation_details.append(
                    {
                        "mode": "dedicated_merge",
                        "target_duty_id": int(chosen_duty.id),
                        "task_ids": [int(task.meta.get("task_id", task.id)) for task in ordered_bundle],
                        "trip_ids": [
                            int(getattr(trip, "public_id", trip.id))
                            for task in ordered_bundle
                            for trip in task.trips
                        ],
                    }
                )
                continue

            dedicated_duties.append(chosen_duty)
            allocation_details.append(
                {
                    "mode": "dedicated_new",
                    "target_duty_id": int(chosen_duty.id),
                    "task_ids": [int(task.meta.get("task_id", task.id)) for task in ordered_bundle],
                    "trip_ids": [
                        int(getattr(trip, "public_id", trip.id))
                        for task in ordered_bundle
                        for trip in task.trips
                    ],
                }
            )
            next_id += 1

        return dedicated_duties, allocation_details, next_id

    def _soft_issue_allocate_reconstruction_bundles(
        self,
        *,
        bundles: Sequence[Sequence[Block]],
        working_duties: Sequence[Duty],
        source_duty: Duty,
    ) -> Tuple[List[Duty], List[Dict[str, Any]], List[List[Block]]]:
        candidate_duties = [copy.deepcopy(duty) for duty in working_duties]
        bundle_allocations: List[Dict[str, Any]] = []
        deferred_bundles: List[List[Block]] = []

        for bundle in bundles:
            ordered_bundle = sorted((task for task in bundle if task.trips), key=lambda item: (item.start_time, item.id))
            if not ordered_bundle:
                continue
            bundle_group_ids = self._tasks_group_ids(ordered_bundle)
            target_seed = ordered_bundle[0]
            candidates: List[Tuple[float, int, int, int, str, Duty]] = []
            for target_duty in self._soft_issue_target_duties(candidate_duties, source_duty, target_seed, bundle_group_ids):
                for mode in ("append", "prepend"):
                    rebuilt, reason = self._soft_issue_rebuild_bundle_into_duty(target_duty, ordered_bundle, mode)
                    if rebuilt is None:
                        continue
                    semantic_metrics = self._build_operational_semantic_metrics(
                        rebuilt.tasks,
                        projected_work=int(rebuilt.work_time),
                        projected_spread=int(rebuilt.spread_time),
                        duty_id=int(rebuilt.id),
                    )
                    semantic_score = self._operational_semantic_score(semantic_metrics)
                    candidates.append(
                        (
                            semantic_score,
                            int(semantic_metrics["mandatory_rest_missing"]),
                            int(semantic_metrics["max_idle_time"]),
                            int(target_duty.id),
                            mode,
                            rebuilt,
                        )
                    )

            if not candidates:
                deferred_bundles.append(ordered_bundle)
                continue

            candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
            _, _, _, chosen_target_id, chosen_mode, rebuilt_target = candidates[0]
            updated_duties: List[Duty] = []
            for existing_duty in candidate_duties:
                if int(existing_duty.id) == chosen_target_id:
                    updated_duties.append(rebuilt_target)
                else:
                    updated_duties.append(existing_duty)
            candidate_duties = updated_duties
            bundle_allocations.append(
                {
                    "mode": chosen_mode,
                    "target_duty_id": int(chosen_target_id),
                    "task_ids": [int(task.meta.get("task_id", task.id)) for task in ordered_bundle],
                    "trip_ids": [
                        int(getattr(trip, "public_id", trip.id))
                        for task in ordered_bundle
                        for trip in task.trips
                    ],
                }
            )

        return candidate_duties, bundle_allocations, deferred_bundles

    def _soft_issue_trimmed_reconstruction_candidate(
        self,
        *,
        current_duties: Sequence[Duty],
        source_duty: Duty,
        current_metrics: Dict[str, Any],
        current_rank: Tuple[int, ...],
        original_blocks: Optional[List[Block]],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Tuple[int, ...]]]:
        if int(source_duty.id) not in self._soft_issue_reconstruction_focus_duty_ids():
            return None, None, None

        bundles = self._soft_issue_reconstruction_bundles(source_duty)
        bundle_count = len(bundles)
        if bundle_count < 3:
            return None, None, None

        quality_metrics = source_duty.meta.get("quality_metrics") or self._build_duty_quality_metrics(
            source_duty.tasks,
            projected_work=int(source_duty.work_time),
            projected_spread=int(source_duty.spread_time),
        )

        best_candidate: Optional[Dict[str, Any]] = None
        best_metrics: Optional[Dict[str, Any]] = None
        best_rank: Optional[Tuple[int, ...]] = None

        for left_trim in range(bundle_count):
            for right_trim in range(bundle_count - left_trim):
                removed_count = left_trim + right_trim
                if removed_count < 2 or removed_count >= bundle_count:
                    continue

                keep_start = left_trim
                keep_end = bundle_count - right_trim
                kept_bundles = bundles[keep_start:keep_end]
                removed_bundles = [*bundles[:keep_start], *bundles[keep_end:]]
                if not kept_bundles or not removed_bundles:
                    continue

                kept_tasks = [task for bundle in kept_bundles for task in bundle if task.trips]
                source_rebuilt, source_reason = self._rebuild_duty_from_tasks(kept_tasks, source_duty.id)
                if source_rebuilt is None:
                    continue

                seeded_duties = []
                for duty in current_duties:
                    if int(duty.id) == int(source_duty.id):
                        seeded_duties.append(source_rebuilt)
                    else:
                        seeded_duties.append(copy.deepcopy(duty))

                allocated_duties, bundle_allocations, deferred_bundles = self._soft_issue_allocate_reconstruction_bundles(
                    bundles=removed_bundles,
                    working_duties=seeded_duties,
                    source_duty=source_duty,
                )

                next_duty_id = max((int(duty.id) for duty in current_duties), default=0) + 1
                try:
                    dedicated_duties, dedicated_allocations, _ = self._soft_issue_build_compact_dedicated_duties(
                        deferred_bundles,
                        next_duty_id,
                    )
                except ValueError:
                    continue

                candidate_sample = {
                    "source_duty_id": int(source_duty.id),
                    "target_duty_id": int(source_duty.id),
                    "mode": "edge_trim_reconstruction",
                    "reasons": ["extreme_low_utilization_spread"],
                    "source_before": {
                        "task_ids": [int(task.meta.get("task_id", task.id)) for task in source_duty.tasks],
                        "trip_ids": [int(getattr(trip, "public_id", trip.id)) for trip in source_duty.all_trips],
                        "quality_metrics": quality_metrics,
                    },
                    "reconstruction": {
                        "trim_plan": {
                            "left_trim": left_trim,
                            "right_trim": right_trim,
                            "kept_bundle_count": len(kept_bundles),
                            "removed_bundle_count": len(removed_bundles),
                            "source_rebuild_reason": source_reason,
                        },
                        "bundle_count": bundle_count,
                        "allocated_to_existing": bundle_allocations,
                        "allocated_to_dedicated": dedicated_allocations,
                        "source_after_trip_ids": [
                            int(getattr(trip, "public_id", trip.id))
                            for trip in source_rebuilt.all_trips
                        ],
                    },
                }

                candidate, candidate_metrics, candidate_rank = self._evaluate_soft_issue_candidate(
                    candidate_duties=[*allocated_duties, *dedicated_duties],
                    current_metrics=current_metrics,
                    current_rank=current_rank,
                    original_blocks=original_blocks,
                    candidate_sample=candidate_sample,
                )
                if candidate is None or candidate_rank is None:
                    continue
                if best_candidate is None or candidate_rank < (best_rank or candidate_rank):
                    best_candidate = candidate
                    best_metrics = candidate_metrics
                    best_rank = candidate_rank

        return best_candidate, best_metrics, best_rank

    def _soft_issue_extreme_reconstruction_candidate(
        self,
        *,
        current_duties: Sequence[Duty],
        source_duty: Duty,
        current_metrics: Dict[str, Any],
        current_rank: Tuple[int, ...],
        original_blocks: Optional[List[Block]],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Tuple[int, ...]]]:
        quality_metrics = source_duty.meta.get("quality_metrics") or self._build_duty_quality_metrics(
            source_duty.tasks,
            projected_work=int(source_duty.work_time),
            projected_spread=int(source_duty.spread_time),
        )
        if not self._is_extreme_duty(source_duty, quality_metrics):
            return None, None, None

        bundles = self._soft_issue_reconstruction_bundles(source_duty)
        if not bundles:
            return None, None, None

        working_duties, bundle_allocations, deferred_bundles = self._soft_issue_allocate_reconstruction_bundles(
            bundles=bundles,
            working_duties=[duty for duty in current_duties if duty.id != source_duty.id],
            source_duty=source_duty,
        )

        next_duty_id = max((int(duty.id) for duty in current_duties), default=0) + 1
        try:
            dedicated_duties, dedicated_allocations, _ = self._soft_issue_build_compact_dedicated_duties(
                deferred_bundles,
                next_duty_id,
            )
        except ValueError:
            return None, None, None

        candidate_duties = [*working_duties, *dedicated_duties]
        candidate_sample = {
            "source_duty_id": int(source_duty.id),
            "target_duty_id": None,
            "mode": "local_reconstruction",
            "reasons": ["extreme_low_utilization_spread"],
            "source_before": {
                "task_ids": [int(task.meta.get("task_id", task.id)) for task in source_duty.tasks],
                "trip_ids": [int(getattr(trip, "public_id", trip.id)) for trip in source_duty.all_trips],
                "quality_metrics": quality_metrics,
            },
            "reconstruction": {
                "bundle_count": len(bundles),
                "allocated_to_existing": bundle_allocations,
                "allocated_to_dedicated": dedicated_allocations,
            },
        }
        return self._evaluate_soft_issue_candidate(
            candidate_duties=candidate_duties,
            current_metrics=current_metrics,
            current_rank=current_rank,
            original_blocks=original_blocks,
            candidate_sample=candidate_sample,
        )

    def _soft_issue_improved(self, current_metrics: Dict[str, Any], candidate_metrics: Dict[str, Any]) -> bool:
        improvement_keys = (
            "uncovered_blocks",
            "mandatory_rest_missing",
            "meal_break_missing",
            "duty_group_splits",
            "roster_group_splits",
            "extreme_duties",
            "low_utilization_duties",
            "high_spread_duties",
            "fragmented_duties",
            "short_connection_total",
        )
        if any(
            int(candidate_metrics.get(key, 0)) < int(current_metrics.get(key, 0))
            for key in improvement_keys
        ):
            return True
        return float(candidate_metrics.get("operational_semantic_score", 0.0) or 0.0) < float(
            current_metrics.get("operational_semantic_score", 0.0) or 0.0
        )

    def _soft_issue_reassignment_postopt(
        self,
        duties: List[Duty],
        original_blocks: Optional[List[Block]],
    ) -> Tuple[List[Duty], Dict[str, Any]]:
        enabled = bool(self.params.get("enable_soft_issue_reassignment_postopt", True))
        max_passes = max(1, int(self.params.get("soft_issue_reassignment_max_passes", 5) or 5))
        target_limit = max(1, int(self.params.get("soft_issue_reassignment_target_limit", 12) or 12))
        candidate_limit = max(8, int(self.params.get("soft_issue_reassignment_candidate_limit", 48) or 48))
        sample_limit = max(10, int(self.params.get("soft_issue_reassignment_sample_limit", 48) or 48))
        audit: Dict[str, Any] = {
            "enabled": enabled,
            "passes": 0,
            "considered": 0,
            "evaluated": 0,
            "feasible_targets": 0,
            "accepted": 0,
            "accepted_moves": [],
            "rejection_reasons": {},
            "samples": [],
            "baseline_metrics": None,
            "final_metrics": None,
            "candidate_count": 0,
            "improved": False,
        }

        if not enabled:
            audit["skipped"] = "disabled"
            return duties, audit

        seeded_duties = [duty for duty in duties if duty.tasks]
        if not seeded_duties:
            audit["skipped"] = "no_duties"
            return duties, audit

        current_duties, _, current_metrics = self._evaluate_relief_candidate_duties(seeded_duties, original_blocks)
        audit["baseline_metrics"] = current_metrics
        audit["final_metrics"] = current_metrics
        current_rank = self._relief_reassignment_rank(current_metrics)

        def record_rejection(reason: str, sample: Dict[str, Any]) -> None:
            reason_key = reason or "unknown"
            audit["rejection_reasons"][reason_key] = int(audit["rejection_reasons"].get(reason_key, 0)) + 1
            if len(audit["samples"]) < sample_limit:
                audit["samples"].append(sample)

        for pass_index in range(max_passes):
            audit["passes"] = pass_index + 1
            candidate_sources = self._soft_issue_candidate_sources(current_duties)
            audit["candidate_count"] = len(candidate_sources)
            if not candidate_sources:
                audit["skipped"] = "no_soft_issue_candidates"
                break

            best_candidate: Optional[Dict[str, Any]] = None
            best_rank: Optional[Tuple[int, ...]] = None
            reconstructed_source_ids: set[int] = set()

            for source in candidate_sources[:candidate_limit]:
                source_duty = source["source_duty"]
                task_index = int(source["task_index"])
                task = source["task"]
                task_group_ids = set(source["task_group_ids"])
                reasons = list(source["reasons"])

                source_remaining = [
                    candidate_task
                    for idx, candidate_task in enumerate(source_duty.tasks)
                    if idx != task_index
                ]
                source_rebuilt: Optional[Duty] = None
                source_remaining_group_ids = self._tasks_group_ids(source_remaining)
                if source_remaining:
                    source_rebuilt, source_reason = self._rebuild_duty_from_tasks(source_remaining, source_duty.id)
                    if source_rebuilt is None:
                        record_rejection(
                            f"source_rebuild_{source_reason}",
                            {
                                "reason": f"source_rebuild_{source_reason}",
                                "source_duty_id": int(source_duty.id),
                                "target_duty_id": None,
                                "mode": None,
                                "reasons": reasons,
                                "task": self._task_summary(task),
                            },
                        )
                        continue
                if task_group_ids & source_remaining_group_ids:
                    record_rejection(
                        "trip_group_split_source",
                        {
                            "reason": "trip_group_split_source",
                            "source_duty_id": int(source_duty.id),
                            "target_duty_id": None,
                            "mode": None,
                            "reasons": reasons,
                            "task": self._task_summary(task),
                        },
                    )
                    continue

                candidate_targets = self._soft_issue_target_duties(
                    current_duties,
                    source_duty,
                    task,
                    task_group_ids,
                )

                for target_duty in candidate_targets[:target_limit]:
                    for mode in ("append", "prepend"):
                        audit["considered"] = int(audit.get("considered", 0)) + 1
                        if mode == "append":
                            if int(target_duty.tasks[-1].end_time) > int(task.start_time):
                                record_rejection(
                                    "append_target_overlap",
                                    {
                                        "reason": "append_target_overlap",
                                        "source_duty_id": int(source_duty.id),
                                        "target_duty_id": int(target_duty.id),
                                        "mode": mode,
                                        "reasons": reasons,
                                        "task": self._task_summary(task),
                                    },
                                )
                                continue
                            target_task_sequence = [*target_duty.tasks, task]
                        else:
                            if int(task.end_time) > int(target_duty.tasks[0].start_time):
                                record_rejection(
                                    "prepend_target_overlap",
                                    {
                                        "reason": "prepend_target_overlap",
                                        "source_duty_id": int(source_duty.id),
                                        "target_duty_id": int(target_duty.id),
                                        "mode": mode,
                                        "reasons": reasons,
                                        "task": self._task_summary(task),
                                    },
                                )
                                continue
                            target_task_sequence = [task, *target_duty.tasks]

                        target_rebuilt, target_reason = self._rebuild_duty_from_tasks(
                            target_task_sequence,
                            target_duty.id,
                        )
                        if target_rebuilt is None:
                            record_rejection(
                                f"{mode}_target_{target_reason}",
                                {
                                    "reason": f"{mode}_target_{target_reason}",
                                    "source_duty_id": int(source_duty.id),
                                    "target_duty_id": int(target_duty.id),
                                    "mode": mode,
                                    "reasons": reasons,
                                    "task": self._task_summary(task),
                                },
                            )
                            continue

                        audit["feasible_targets"] = int(audit.get("feasible_targets", 0)) + 1

                        candidate_duties: List[Duty] = []
                        for existing_duty in current_duties:
                            if existing_duty.id == source_duty.id:
                                if source_rebuilt is not None:
                                    candidate_duties.append(source_rebuilt)
                                continue
                            if existing_duty.id == target_duty.id:
                                candidate_duties.append(target_rebuilt)
                                continue
                            candidate_duties.append(existing_duty)

                        normalized_candidate, _, candidate_metrics = self._evaluate_relief_candidate_duties(
                            candidate_duties,
                            original_blocks,
                        )
                        audit["evaluated"] = int(audit.get("evaluated", 0)) + 1
                        candidate_sample = {
                            "source_duty_id": int(source_duty.id),
                            "target_duty_id": int(target_duty.id),
                            "mode": mode,
                            "reasons": reasons,
                            "task": self._task_summary(task),
                        }
                        candidate_rank = self._relief_reassignment_rank(candidate_metrics)
                        evaluated_sample = {
                            **candidate_sample,
                            "metrics_before": current_metrics,
                            "metrics_after": candidate_metrics,
                        }

                        if self._soft_issue_candidate_accepted(
                            current_metrics,
                            candidate_metrics,
                            current_rank,
                            candidate_rank,
                        ):
                            if best_candidate is None or candidate_rank < (best_rank or candidate_rank):
                                best_candidate = {
                                    "duties": normalized_candidate,
                                    "metrics": candidate_metrics,
                                    "details": evaluated_sample,
                                }
                                best_rank = candidate_rank
                            continue

                        record_rejection(
                            "not_better",
                        {
                            **evaluated_sample,
                            "reason": "not_better",
                        },
                    )

                if "extreme_low_utilization_spread" in reasons and int(source_duty.id) not in reconstructed_source_ids:
                    reconstructed_source_ids.add(int(source_duty.id))
                    audit["considered"] = int(audit.get("considered", 0)) + 1
                    audit["evaluated"] = int(audit.get("evaluated", 0)) + 1
                    reconstruction_candidate, candidate_metrics, candidate_rank = self._soft_issue_extreme_reconstruction_candidate(
                        current_duties=current_duties,
                        source_duty=source_duty,
                        current_metrics=current_metrics,
                        current_rank=current_rank,
                        original_blocks=original_blocks,
                    )
                    if reconstruction_candidate is not None:
                        audit["feasible_targets"] = int(audit.get("feasible_targets", 0)) + 1
                        if best_candidate is None or (candidate_rank is not None and candidate_rank < (best_rank or candidate_rank)):
                            best_candidate = reconstruction_candidate
                            best_rank = candidate_rank
                        continue

                    trimmed_candidate, trimmed_metrics, trimmed_rank = self._soft_issue_trimmed_reconstruction_candidate(
                        current_duties=current_duties,
                        source_duty=source_duty,
                        current_metrics=current_metrics,
                        current_rank=current_rank,
                        original_blocks=original_blocks,
                    )
                    if trimmed_candidate is not None:
                        audit["feasible_targets"] = int(audit.get("feasible_targets", 0)) + 1
                        if best_candidate is None or (trimmed_rank is not None and trimmed_rank < (best_rank or trimmed_rank)):
                            best_candidate = trimmed_candidate
                            best_rank = trimmed_rank
                        continue

                    record_rejection(
                        "reconstruction_not_better",
                        {
                            "reason": "reconstruction_not_better",
                            "source_duty_id": int(source_duty.id),
                            "target_duty_id": None,
                            "mode": "local_reconstruction",
                            "reasons": reasons,
                            "task": self._task_summary(task),
                            "metrics_before": current_metrics,
                            "metrics_after": trimmed_metrics or candidate_metrics,
                        },
                    )

                if (
                    "extreme_low_utilization_spread" not in reasons
                    and "mandatory_rest_missing_repair" not in reasons
                ) or source_rebuilt is None:
                    continue

                dedicated_duty_id = max(int(duty.id) for duty in current_duties) + 1
                dedicated_duty = self._seed_duty_with_task(dedicated_duty_id, task)
                candidate_duties = []
                for existing_duty in current_duties:
                    if existing_duty.id == source_duty.id:
                        candidate_duties.append(source_rebuilt)
                        continue
                    candidate_duties.append(existing_duty)
                candidate_duties.append(dedicated_duty)

                audit["considered"] = int(audit.get("considered", 0)) + 1
                audit["feasible_targets"] = int(audit.get("feasible_targets", 0)) + 1
                audit["evaluated"] = int(audit.get("evaluated", 0)) + 1
                candidate_sample = {
                    "source_duty_id": int(source_duty.id),
                    "target_duty_id": int(dedicated_duty_id),
                    "mode": "dedicated",
                    "reasons": reasons,
                    "task": self._task_summary(task),
                }
                dedicated_ranked = self._evaluate_soft_issue_candidate(
                    candidate_duties=candidate_duties,
                    current_metrics=current_metrics,
                    current_rank=current_rank,
                    original_blocks=original_blocks,
                    candidate_sample=candidate_sample,
                )
                dedicated_candidate, candidate_metrics, candidate_rank = dedicated_ranked

                if dedicated_candidate is not None:
                    if best_candidate is None or (candidate_rank is not None and candidate_rank < (best_rank or candidate_rank)):
                        best_candidate = dedicated_candidate
                        best_rank = candidate_rank
                    continue

                record_rejection(
                    "not_better",
                    {
                        **candidate_sample,
                        "metrics_before": current_metrics,
                        "metrics_after": candidate_metrics,
                        "reason": "not_better",
                    },
                )

            if best_candidate is None:
                break

            current_duties = best_candidate["duties"]
            current_metrics = best_candidate["metrics"]
            current_rank = self._relief_reassignment_rank(current_metrics)
            audit["accepted"] = int(audit.get("accepted", 0)) + 1
            if len(audit["accepted_moves"]) < sample_limit:
                audit["accepted_moves"].append(best_candidate["details"])

        audit["final_metrics"] = current_metrics
        baseline_metrics = audit["baseline_metrics"] or current_metrics
        baseline_rank = self._relief_reassignment_rank(baseline_metrics)
        final_rank = self._relief_reassignment_rank(current_metrics)
        audit["improved"] = bool(
            self._soft_issue_candidate_accepted(
                baseline_metrics,
                current_metrics,
                baseline_rank,
                final_rank,
            )
            and current_metrics != baseline_metrics
        )
        if not audit["improved"] and audit.get("accepted") == 0:
            audit["result"] = "no_accepted_improvement"
        elif audit["improved"]:
            audit["result"] = "accepted_improvement"
        else:
            audit["result"] = "accepted_without_rank_gain"
        return current_duties, audit
