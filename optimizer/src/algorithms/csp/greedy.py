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
from ..base import BaseAlgorithm

settings = get_settings()

_DEF_MAX_SHIFT = getattr(settings, "cct_max_shift_minutes", 560)
_DEF_MAX_WORK = getattr(settings, "cct_max_work_minutes", 480)
_DEF_MAX_DRIVING = getattr(settings, "cct_max_driving_minutes", 270)
_DEF_MIN_BREAK = getattr(settings, "cct_min_break_minutes", 30)


def _nocturnal_overlap(start: int, end: int, noct_start_h: int, noct_end_h: int) -> int:
    """Calcula minutos noturnos entre start e end (minutos absolutos).
    Suporta janela noturna com wrap de meia-noite (ex: 22h-5h) e sem wrap (ex: 1h-6h)."""
    if start >= end:
        return 0
    start_noct = noct_start_h * 60
    end_noct = noct_end_h * 60
    wraps_midnight = noct_start_h > noct_end_h  # e.g. 22h-5h

    total = 0
    # Iterar dia a dia coberto pelo intervalo
    day_start = (start // 1440) * 1440
    day_end = ((end - 1) // 1440) * 1440

    for day_base in range(day_start, day_end + 1440, 1440):
        if wraps_midnight:
            # Janela noturna: [day_base+start_noct, day_base+1440) + [day_base+1440, day_base+1440+end_noct)
            win_a_start = day_base + start_noct
            win_a_end = day_base + 1440
            win_b_start = day_base + 1440
            win_b_end = day_base + 1440 + end_noct
            for ws, we in [(win_a_start, win_a_end), (win_b_start, win_b_end)]:
                ov_start = max(start, ws)
                ov_end = min(end, we)
                if ov_end > ov_start:
                    total += ov_end - ov_start
        else:
            # Janela contígua: [day_base+start_noct, day_base+end_noct)
            ws = day_base + start_noct
            we = day_base + end_noct
            ov_start = max(start, ws)
            ov_end = min(end, we)
            if ov_end > ov_start:
                total += ov_end - ov_start

    return total


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
        self.legal_max_shift = int(params.get("legal_max_shift_minutes", 720))
        self.legal_max_continuous_driving = 600
        self.max_shift = min(int(params.get("max_shift_minutes", _DEF_MAX_SHIFT)), self.legal_max_shift)
        self.max_work = int(params.get("max_work_minutes", _DEF_MAX_WORK))
        self.min_work = int(params.get("min_work_minutes", 0))
        self.min_shift = int(params.get("min_shift_minutes", 0))
        self.overtime_limit = int(params.get("overtime_limit_minutes", 120))
        self.max_driving = min(int(params.get("max_driving_minutes", _DEF_MAX_DRIVING)), self.legal_max_continuous_driving)
        self.min_break = int(params.get("min_break_minutes", _DEF_MIN_BREAK))
        self.connection_tolerance = max(0, int(params.get("connection_tolerance_minutes", 0)))
        self.mandatory_break_after = min(int(params.get("mandatory_break_after_minutes", self.max_driving)), self.legal_max_continuous_driving)
        self.split_break_first = int(params.get("split_break_first_minutes", 15))
        self.split_break_second = int(params.get("split_break_second_minutes", max(self.min_break, 30)))
        self.meal_break_minutes = int(params.get("meal_break_minutes", 0))
        self.inter_shift_rest = max(int(params.get("inter_shift_rest_minutes", 660)), 660)
        self.weekly_rest = int(params.get("weekly_rest_minutes", 1440))
        self.daily_driving_limit = int(params.get("daily_driving_limit_minutes", 540))
        self.extended_daily_driving_limit = int(params.get("extended_daily_driving_limit_minutes", 600))
        self.max_extended_days = int(params.get("max_extended_driving_days_per_week", 2))
        self.weekly_driving_limit = int(params.get("weekly_driving_limit_minutes", 3360))
        self.fortnight_driving_limit = int(params.get("fortnight_driving_limit_minutes", 5400))
        self.min_layover = int(params.get("min_layover_minutes", self.vsp_params.get("min_layover_minutes", 8)))
        self.pullout = int(params.get("pullout_minutes", 10))
        self.pullback = int(params.get("pullback_minutes", 10))
        self.idle_time_is_paid = bool(params.get("idle_time_is_paid", True))
        self.waiting_time_pay_pct = float(params.get("waiting_time_pay_pct", 0.30))
        max_unpaid_break = params.get("max_unpaid_break_minutes", None)
        self.max_unpaid_break = None if max_unpaid_break is None else max(0, int(max_unpaid_break))
        self.long_unpaid_break_limit = int(params.get("long_unpaid_break_limit_minutes", 180))
        self.long_unpaid_break_penalty_weight = float(params.get("long_unpaid_break_penalty_weight", 4.0))
        max_total_unpaid_break = params.get("max_total_unpaid_break_minutes", None)
        self.max_total_unpaid_break = None if max_total_unpaid_break is None else max(0, int(max_total_unpaid_break))
        self.min_guaranteed_work = int(params.get("min_guaranteed_work_minutes", 0))
        self.allow_relief_points = bool(params.get("allow_relief_points", False))
        self.enforce_same_depot = bool(params.get("enforce_same_depot_start_end", False))
        self.enforce_single_line_duty = bool(params.get("enforce_single_line_duty", False))
        self.operator_single_vehicle_only = bool(params.get("operator_single_vehicle_only", False))
        self.nocturnal_start_hour = int(params.get("nocturnal_start_hour", 22))
        self.nocturnal_end_hour = int(params.get("nocturnal_end_hour", 5))
        self.nocturnal_extra_pct = float(params.get("nocturnal_extra_pct", 0.20))
        self.holiday_extra_pct = float(params.get("holiday_extra_pct", 1.0))
        self.goal_weights = dict(params.get("goal_weights") or self.vsp_params.get("goal_weights") or {})
        fairness_weight = params.get("fairness_weight", self.goal_weights.get("fairness", 0.0))
        try:
            fairness_weight = float(fairness_weight)
        except (TypeError, ValueError):
            fairness_weight = 0.0
        if fairness_weight > 1.0:
            fairness_weight = fairness_weight / 100.0
        self.fairness_weight = max(0.0, fairness_weight)
        self.fairness_target_work = int(params.get("fairness_target_work_minutes", self.goal_weights.get("target_work_minutes", 420)))
        self.fairness_tolerance = int(params.get("fairness_tolerance_minutes", 30))
        self.operator_change_terminals_only = bool(params.get("operator_change_terminals_only", True))
        self.strict_union_rules = bool(params.get("strict_union_rules", True))
        self.operator_profiles = list(params.get("operator_profiles") or [])
        self.trip_group_keep_bonus = float(params.get("trip_group_keep_bonus", 180.0))
        self.trip_group_split_penalty = float(
            params.get("trip_group_split_penalty", max(self.trip_group_keep_bonus * 1.5, 240.0))
        )
        self._extension_diagnostics = self._empty_extension_diagnostics()

    def _block_drive(self, block: Block) -> int:
        return sum(t.duration for t in block.trips)

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
        if effective_gap >= self.min_break:
            state["credit"] = 0
            state["has_long"] = False
            return True, state, self._adjustment_needed(gap, self.min_break)

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
        if current.destination_id == nxt.origin_id:
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
        if current.destination_id == nxt.origin_id:
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

    def _make_task(self, source_block: Block, trips: Sequence[Trip], task_id: int) -> Block:
        source_start_buffer = max(0, int(source_block.meta.get("start_buffer_minutes", 0) or 0))
        source_end_buffer = max(0, int(source_block.meta.get("end_buffer_minutes", 0) or 0))
        first_trip_id = int(source_block.meta.get("vehicle_first_trip_id", trips[0].id if trips else 0))
        last_trip_id = int(source_block.meta.get("vehicle_last_trip_id", trips[-1].id if trips else 0))
        is_source_block_start = bool(trips) and int(trips[0].id) == first_trip_id
        is_source_block_end = bool(trips) and int(trips[-1].id) == last_trip_id
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
        max_chunk_drive = max(60, min(self.max_work, self.mandatory_break_after, self.daily_driving_limit))
        meal_trigger = max(240, self.mandatory_break_after - max(0, self.meal_break_minutes)) if self.meal_break_minutes > 0 else self.mandatory_break_after

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

                if gap >= self.min_break:
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

                if pair_guard:
                    should_cut = False

                if should_cut:
                    task = self._make_task(block, current, self._next_block_id())
                    task.meta["relief_cut"] = True
                    task.meta["split_reason"] = (
                        "explicit_mid_trip_relief" if explicit_mid_trip_relief_boundary else
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

        if self.max_unpaid_break is not None and gap > self.max_unpaid_break:
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

        new_spread = self._duty_spread_minutes([*duty.tasks, block])
        if new_spread > self.max_shift:
            return False, "spread_exceeded", {"new_spread": new_spread}

        projected_work = duty.work_time + self._block_drive(block)
        overtime_minutes = self._regular_overtime_minutes(projected_work)
        if overtime_minutes > self.overtime_limit:
            return False, "overtime_hard", {"new_spread": new_spread, "new_work": projected_work, "overtime_minutes": overtime_minutes}

        start_depot = duty.meta.get("start_depot_id")
        candidate_end_depot = block.trips[-1].depot_id
        if self.enforce_same_depot and start_depot is not None and candidate_end_depot is not None and candidate_end_depot != start_depot:
            return False, "same_depot_required", {}

        had_break, break_state, break_adjustment = self._break_resets(duty.meta.get("break_state", {}), gap)
        current_cont = int(duty.meta.get("continuous_drive", 0))
        block_drive = self._block_drive(block)
        new_cont = block_drive if had_break else current_cont + block_drive
        if new_cont > self.max_driving or new_cont > self.mandatory_break_after:
            return False, "continuous_drive_exceeded", {"continuous_drive": new_cont}

        daily_drive = int(duty.meta.get("daily_driving", 0)) + block_drive
        extended_days_used = int(duty.meta.get("extended_days_used", 0))
        if daily_drive > self.extended_daily_driving_limit:
            return False, "daily_driving_exceeded", {"daily_drive": daily_drive}
        if daily_drive > self.daily_driving_limit and extended_days_used >= self.max_extended_days:
            return False, "daily_extension_quota_exceeded", {"daily_drive": daily_drive}

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
        duty.work_time = int(data.get("new_work", self._block_drive(block)))
        duty.spread_time = max(0, duty_end - duty_start)
        gap = int(data.get("gap", 0))
        duty.meta["continuous_drive"] = int(data.get("new_cont", self._block_drive(block)))
        duty.meta["daily_driving"] = int(data.get("daily_drive", self._block_drive(block)))
        duty.meta["extended_days_used"] = int(data.get("extended_days_used", 0))
        duty.meta["break_state"] = dict(data.get("break_state", duty.meta.get("break_state", {"credit": 0, "has_long": False})))
        duty.meta["duty_start_minutes"] = duty_start
        duty.meta["duty_end_minutes"] = duty_end
        duty.meta["start_buffer_minutes"] = start_buffer
        duty.meta["end_buffer_minutes"] = end_buffer
        duty.meta["waiting_minutes"] = int(duty.meta.get("waiting_minutes", 0)) + max(0, gap - int(data.get("transfer_needed", 0)))
        duty.meta["passive_transfer_minutes"] = int(duty.meta.get("passive_transfer_minutes", 0)) + int(data.get("passive_transfer", 0))
        duty.meta["connection_tolerance_minutes"] = self.connection_tolerance
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
        for trip in block.trips:
            group_id = getattr(trip, "trip_group_id", None)
            if group_id is None:
                continue
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

            max_continuous_drive, meal_break_found = self._continuous_drive_stats(duty)
            duty.meta["max_continuous_drive_minutes"] = max_continuous_drive
            duty.meta["meal_break_found"] = meal_break_found

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
            if self.meal_break_minutes > 0 and duty.spread_time >= 360 and not meal_break_found:
                duty.rest_violations += 1
                duty.warnings.append(f"Intervalo de refeição insuficiente: 0min < {self.meal_break_minutes}min")
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
            # First pass: try preferred roster only
            if preferred_roster is not None:
                for roster in sorted_rosters:
                    if roster["id"] != preferred_roster:
                        continue
                    if roster["last_end"] + self.inter_shift_rest > duty_start:
                        continue
                    week = duty_start // (7 * 1440)
                    fortnight = duty_start // (14 * 1440)
                    month = duty_start // (30 * 1440)
                    week_drive = roster["week_drive"].get(week, 0) + daily_drive
                    fortnight_drive = roster["fortnight_drive"].get(fortnight, 0) + daily_drive
                    month_drive = roster["month_drive"].get(month, 0) + daily_drive
                    if week_drive > self.weekly_driving_limit or fortnight_drive > self.fortnight_driving_limit:
                        continue
                    assigned_roster = roster
                    break
            # Second pass: try any compatible roster
            if assigned_roster is None:
                if preferred_roster is not None:
                    warnings.append(f"PAIR_GROUP_ROSTER_SPLIT D{duty.id} expected_roster={preferred_roster}")
                for roster in sorted_rosters:
                    if roster["last_end"] + self.inter_shift_rest > duty_start:
                        continue
                    week = duty_start // (7 * 1440)
                    fortnight = duty_start // (14 * 1440)
                    month = duty_start // (30 * 1440)
                    week_drive = roster["week_drive"].get(week, 0) + daily_drive
                    fortnight_drive = roster["fortnight_drive"].get(fortnight, 0) + daily_drive
                    month_drive = roster["month_drive"].get(month, 0) + daily_drive
                    if week_drive > self.weekly_driving_limit or fortnight_drive > self.fortnight_driving_limit:
                        continue
                    assigned_roster = roster
                    break
            if assigned_roster is not None:
                roster = assigned_roster
                week = duty_start // (7 * 1440)
                fortnight = duty_start // (14 * 1440)
                month = duty_start // (30 * 1440)
                roster["last_end"] = duty_end
                roster["week_drive"][week] = roster["week_drive"].get(week, 0) + daily_drive
                roster["fortnight_drive"][fortnight] = roster["fortnight_drive"].get(fortnight, 0) + daily_drive
                roster["month_drive"][month] = roster["month_drive"].get(month, 0) + daily_drive
                roster["duties"].append(duty.id)
            if assigned_roster is None:
                roster_id = len(roster_state) + 1
                assigned_roster = {
                    "id": roster_id,
                    "last_end": duty_end,
                    "week_drive": defaultdict(int),
                    "fortnight_drive": defaultdict(int),
                    "month_drive": defaultdict(int),
                    "duties": [duty.id],
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
            feasible_candidates: List[Tuple[float, Duty, Dict[str, Any]]] = []
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
                projected_work = int(data.get("new_work", duty.work_time + self._block_drive(task)))
                fairness_penalty = self._fairness_penalty(projected_work)
                gap = float(data.get("gap", 0))
                long_gap_penalty = self._long_unpaid_break_penalty(gap)
                meal_penalty = 0.0
                if self.meal_break_minutes > 0:
                    new_spread = float(data.get("new_spread", 0))
                    if new_spread >= 360 and not self._would_have_meal_break(duty, task):
                        meal_penalty = 200.0
                trip_group_score = self._trip_group_score(duty, task_group_ids, duties)
                candidate_score = (
                    gap
                    + float(data.get("passive_transfer", 0))
                    + fairness_penalty
                    + long_gap_penalty
                    + meal_penalty
                    + trip_group_score
                )
                feasible_candidates.append((candidate_score, duty, data))
            if feasible_candidates:
                _, duty, data = min(feasible_candidates, key=lambda item: (item[0], item[1].id))
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
                    "new_work": self._block_drive(task),
                    "new_spread": self._duty_spread_minutes([task]),
                    "new_cont": self._block_drive(task),
                    "daily_drive": self._block_drive(task),
                    "extended_days_used": 1 if self._block_drive(task) > self.daily_driving_limit else 0,
                },
            )
            covered_trip_ids.update(task_trip_ids)
            duties.append(duty)

        duties = self._merge_small_duties(duties)
        duties, relief_reassignment_audit = self._relief_reassignment_postopt(duties, blocks)
        if relief_reassignment_audit.get("accepted_moves"):
            duties = self._merge_small_duties(duties)

        sol = self.finalize_selected_duties(duties, original_blocks=blocks)
        run_cut_meta["duplicate_task_skips"] = duplicate_task_skips
        sol.meta.update(run_cut_meta)
        sol.meta["duty_merge_diagnostics"] = self._extension_diagnostics_snapshot()
        sol.meta["relief_reassignment_audit"] = relief_reassignment_audit
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
                    self._block_drive(t) for t in b.tasks
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
        relief_handoff_map: Dict[int, set[int]] = defaultdict(set)
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

            for trip in duty.all_trips:
                if trip.is_mid_trip_segment:
                    relief_handoff_map[int(trip.public_id)].add(int(duty.id))

        relief_handoffs = sum(1 for assigned_duties in relief_handoff_map.values() if len(assigned_duties) > 1)
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
            "relief_handoffs": relief_handoffs,
            "uncovered_blocks": len(solution.uncovered_blocks or []),
            "fragmentation_score": fragmentation_score,
        }

    def _relief_reassignment_rank(self, metrics: Dict[str, Any]) -> Tuple[int, int, int, int, int, int, int, int, int]:
        return (
            int(metrics.get("violations", 0)),
            int(metrics.get("crew", 0)),
            int(metrics.get("duties", 0)),
            int(metrics.get("split_duties", 0)),
            int(metrics.get("vehicle_switches", 0)),
            int(metrics.get("fragmentation_score", 0)),
            int(metrics.get("short_duties", 0)),
            int(metrics.get("total_overtime_minutes", 0)),
            int(metrics.get("waiting_minutes", 0)),
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
            best_rank: Optional[Tuple[int, int, int, int, int, int, int]] = None

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
        audit["improved"] = bool(
            self._relief_reassignment_rank(current_metrics)
            < self._relief_reassignment_rank(audit["baseline_metrics"] or current_metrics)
        )
        if not audit["improved"] and audit.get("accepted") == 0:
            audit["result"] = "no_accepted_improvement"
        elif audit["improved"]:
            audit["result"] = "accepted_improvement"
        else:
            audit["result"] = "accepted_without_rank_gain"
        return current_duties, audit
