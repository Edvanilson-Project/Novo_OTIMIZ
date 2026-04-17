"""
Validador bruto de hard constraints fatais.

Objetivo:
- bloquear entrada inconsistente ou insegura
- auditar a solução VSP/CSP final
- transformar erros críticos em relatório estruturado
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from ..domain.models import OptimizationResult, Trip


class HardConstraintValidator:
    def audit_input(
        self,
        trips: Sequence[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        issues: List[str] = []
        seen_ids: set[int] = set()
        strict_gps = bool(cct_params.get("strict_gps_validation", True))
        strict_sync = bool(cct_params.get("strict_terminal_sync_validation", True))
        allow_relief_points = bool(cct_params.get("allow_relief_points", False))

        for trip in trips:
            if trip.id in seen_ids:
                issues.append(f"DUPLICATE_TRIP_ID T{trip.id}")
            seen_ids.add(trip.id)

            if trip.end_time <= trip.start_time:
                issues.append(f"INVALID_TIME_WINDOW T{trip.id}")
            if trip.duration <= 0:
                issues.append(f"INVALID_DURATION T{trip.id}")
            if trip.origin_id == trip.destination_id:
                issues.append(f"INVALID_TERMINAL_LOOP T{trip.id}")

            if strict_sync and trip.sent_to_driver_terminal is False:
                issues.append(f"GHOST_BUS_TERMINAL_SYNC T{trip.id}")

            if strict_gps:
                gps_issue = self._validate_trip_gps(trip)
                if gps_issue:
                    issues.append(gps_issue)
                if trip.gps_valid is False:
                    issues.append(f"GPS_FLAG_INVALID T{trip.id}")

            issues.extend(self._validate_mid_trip_relief(trip, allow_relief_points))

        max_shift = int(cct_params.get("max_shift_minutes", 480) or 480)
        max_driving = int(cct_params.get("max_driving_minutes", 270) or 270)
        inter_shift = int(cct_params.get("inter_shift_rest_minutes", 660) or 660)
        if max_shift > 1440:
            issues.append(f"LEGAL_MAX_SHIFT_EXCEEDED config={max_shift}")
        if max_driving > 600:
            issues.append(f"LEGAL_CONTINUOUS_DRIVING_EXCEEDED config={max_driving}")
        if inter_shift < 660:
            issues.append(f"LEGAL_INTERSHIFT_REST_TOO_LOW config={inter_shift}")

        return {
            "ok": not issues,
            "issues": issues,
            "counts": {
                "input_issues": len(issues),
            },
        }

    def audit_result(
        self,
        result: OptimizationResult,
        trips: Sequence[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        issues: List[str] = []
        max_shift = min(int(cct_params.get("max_shift_minutes", 480) or 480), 720)
        max_driving = int(cct_params.get("max_driving_minutes", 270) or 270)
        min_break = int(cct_params.get("min_break_minutes", 30) or 30)
        min_layover = int(cct_params.get("min_layover_minutes", vsp_params.get("min_layover_minutes", 8)) or 8)
        inter_shift = max(int(cct_params.get("inter_shift_rest_minutes", 660) or 660), 660)
        enforce_same_depot = bool(cct_params.get("enforce_same_depot_start_end", False) or vsp_params.get("same_depot_required", False))
        enforce_single_line_duty = bool(cct_params.get("enforce_single_line_duty", False))
        operator_change_terminals_only = bool(cct_params.get("operator_change_terminals_only", True))
        allow_relief_points = bool(cct_params.get("allow_relief_points", False))

        allow_multi_line_block = bool(vsp_params.get("allow_multi_line_block", True))

        if result.vsp.unassigned_trips:
            issues.extend(f"UNCOVERED_TRIP T{trip.id}" for trip in result.vsp.unassigned_trips)
        if result.csp.uncovered_blocks:
            issues.extend(f"UNCOVERED_BLOCK B{block.id}" for block in result.csp.uncovered_blocks)

        warning_pool = [*getattr(result.vsp, "warnings", []), *getattr(result.csp, "warnings", [])]
        if any("CHARGER_CAPACITY_EXCEEDED" in warning for warning in warning_pool):
            issues.append("EV_CHARGER_CAPACITY_EXCEEDED")
        if any("EV_SOC_INSUFFICIENT" in warning for warning in warning_pool):
            issues.append("EV_SOC_INSUFFICIENT")

        for block in result.vsp.blocks:
            issues.extend(self._audit_block(block, min_layover, enforce_same_depot, allow_multi_line_block))

        roster_windows: Dict[int, List[Tuple[int, int, int]]] = {}
        for duty in result.csp.duties:
            issues.extend(
                self._audit_duty(
                    duty,
                    max_shift,
                    max_driving,
                    min_break,
                    enforce_same_depot,
                    enforce_single_line_duty,
                    operator_change_terminals_only,
                    allow_relief_points,
                )
            )
            roster_id = int(duty.meta.get("roster_id", 0) or 0)
            if roster_id > 0 and duty.tasks:
                roster_windows.setdefault(roster_id, []).append((duty.tasks[0].start_time, duty.tasks[-1].end_time, duty.id))

        for roster_id, windows in roster_windows.items():
            ordered = sorted(windows)
            for index in range(len(ordered) - 1):
                _, current_end, duty_id = ordered[index]
                next_start, _, next_duty_id = ordered[index + 1]
                if next_start - current_end < inter_shift:
                    issues.append(f"INTERSHIFT_REST_VIOLATION R{roster_id} D{duty_id}->{next_duty_id}")

        mandatory_groups = cct_params.get("mandatory_trip_groups_same_duty") or []
        if mandatory_groups:
            roster_by_trip: Dict[int, Optional[int]] = {}
            for duty in result.csp.duties:
                rid = duty.meta.get("roster_id")
                for task in duty.tasks:
                    for trip in task.trips:
                        roster_by_trip[trip.id] = rid
            for group in mandatory_groups:
                group_ids = [int(item) for item in group]
                assigned = {roster_by_trip.get(trip_id) for trip_id in group_ids}
                if None in assigned or len(assigned) > 1:
                    issues.append(f"MANDATORY_GROUP_SPLIT {group_ids}")

        issues.extend(self._audit_operator_assignment(result, cct_params))
        issues.extend(
            self._audit_source_block_handoffs(
                result.csp.duties,
                operator_change_terminals_only,
                allow_relief_points,
            )
        )

        # Separar violações hard (bloqueantes) de soft (avisos)
        _SOFT_PREFIXES = ("MEAL_BREAK_MISSING", "CONTINUOUS_DRIVING_EXCEEDED", "MANDATORY_GROUP_SPLIT")
        hard_issues = [i for i in issues if not any(i.startswith(p) for p in _SOFT_PREFIXES)]
        soft_issues = [i for i in issues if any(i.startswith(p) for p in _SOFT_PREFIXES)]

        return {
            "ok": not hard_issues,
            "issues": issues,
            "hard_issues": hard_issues,
            "soft_issues": soft_issues,
            "counts": {
                "result_issues": len(issues),
                "hard_issues": len(hard_issues),
                "soft_issues": len(soft_issues),
                "unassigned_trips": len(result.vsp.unassigned_trips),
                "uncovered_blocks": len(result.csp.uncovered_blocks),
            },
        }

    def _audit_operator_assignment(self, result: OptimizationResult, cct_params: Dict[str, Any]) -> List[str]:
        operator_profiles = list(cct_params.get("operator_profiles") or [])
        if not operator_profiles:
            return []

        strict_union = bool(cct_params.get("strict_union_rules", True))
        operator_meta = ((result.csp.meta or {}).get("operator_assignment") or {})
        rosters = list(operator_meta.get("rosters") or [])
        issues: List[str] = []
        profile_map = {int(profile.get("id")): profile for profile in operator_profiles if profile.get("id") is not None}

        for roster in rosters:
            operator_id = roster.get("operator_id")
            shift_type = roster.get("shift_type")
            line_ids = set(int(item) for item in (roster.get("line_ids") or []))
            if operator_id is None:
                if strict_union:
                    issues.append(f"UNASSIGNED_OPERATOR_PROFILE R{roster.get('roster_id')}")
                continue
            profile = profile_map.get(int(operator_id))
            if not profile:
                issues.append(f"UNKNOWN_OPERATOR_PROFILE R{roster.get('roster_id')} O{operator_id}")
                continue
            mandatory_shift_types = set(profile.get("mandatory_shift_types") or [])
            mandatory_line_ids = set(int(item) for item in (profile.get("mandatory_line_ids") or []))
            if mandatory_shift_types and shift_type not in mandatory_shift_types:
                issues.append(f"MANDATORY_SHIFT_PREFERENCE_VIOLATION O{operator_id} R{roster.get('roster_id')}")
            if mandatory_line_ids and not line_ids.issubset(mandatory_line_ids):
                issues.append(f"MANDATORY_LINE_PREFERENCE_VIOLATION O{operator_id} R{roster.get('roster_id')}")

        def priority(profile: Dict[str, Any]) -> float:
            if profile.get("seniority_score") is not None:
                return float(profile["seniority_score"])
            if profile.get("seniority_rank") is not None:
                return -float(profile["seniority_rank"])
            return 0.0

        assigned_by_shift: Dict[str, List[Tuple[float, int]]] = {}
        for roster in rosters:
            operator_id = roster.get("operator_id")
            if operator_id is None:
                continue
            profile = profile_map.get(int(operator_id))
            if profile is None:
                continue
            assigned_by_shift.setdefault(str(roster.get("shift_type")), []).append((priority(profile), int(operator_id)))

        for profile in operator_profiles:
            preferred_shifts = set(profile.get("mandatory_shift_types") or profile.get("preferred_shift_types") or [])
            operator_id = int(profile.get("id")) if profile.get("id") is not None else None
            if operator_id is None or not preferred_shifts:
                continue
            current_shift = next((str(roster.get("shift_type")) for roster in rosters if roster.get("operator_id") == operator_id), None)
            if current_shift in preferred_shifts:
                continue
            for shift in preferred_shifts:
                for assigned_priority, assigned_operator_id in assigned_by_shift.get(shift, []):
                    if assigned_operator_id == operator_id:
                        continue
                    other_profile = profile_map.get(assigned_operator_id)
                    if other_profile and priority(profile) > assigned_priority:
                        issues.append(f"SENIORITY_PRIORITY_VIOLATION O{operator_id}>{assigned_operator_id} shift={shift}")
                        break

        return sorted(set(issues))

    def _validate_trip_gps(self, trip: Trip) -> str | None:
        coords = [
            (trip.origin_latitude, trip.origin_longitude, "ORIGIN"),
            (trip.destination_latitude, trip.destination_longitude, "DESTINATION"),
        ]
        for lat, lon, label in coords:
            if lat is None and lon is None:
                continue
            if lat is None or lon is None:
                return f"GPS_COORDINATE_INCOMPLETE_{label} T{trip.id}"
            if not (-90.0 <= float(lat) <= 90.0):
                return f"GPS_LATITUDE_INVALID_{label} T{trip.id}"
            if not (-180.0 <= float(lon) <= 180.0):
                return f"GPS_LONGITUDE_INVALID_{label} T{trip.id}"
        return None

    def _validate_mid_trip_relief(self, trip: Trip, allow_relief_points: bool) -> List[str]:
        issues: List[str] = []
        has_point = trip.mid_trip_relief_point_id is not None
        has_offset = trip.mid_trip_relief_offset_minutes is not None
        if not has_point and not has_offset:
            return issues
        if has_point != has_offset:
            issues.append(f"MID_TRIP_RELIEF_INCOMPLETE T{trip.id}")
            return issues
        if not allow_relief_points:
            issues.append(f"MID_TRIP_RELIEF_DISABLED T{trip.id}")
        split_offset = int(trip.mid_trip_relief_offset_minutes or 0)
        trip_duration = int(trip.duration or max(0, trip.end_time - trip.start_time))
        if split_offset <= 0 or (trip_duration > 0 and split_offset >= trip_duration):
            issues.append(f"MID_TRIP_RELIEF_OFFSET_INVALID T{trip.id}")
        relief_point_id = int(trip.mid_trip_relief_point_id or 0)
        if relief_point_id <= 0:
            issues.append(f"MID_TRIP_RELIEF_POINT_INVALID T{trip.id}")
        if relief_point_id in {int(trip.origin_id), int(trip.destination_id)}:
            issues.append(f"MID_TRIP_RELIEF_ENDPOINT_DUPLICATE T{trip.id}")
        return issues

    def _operator_change_boundary_ok(
        self,
        end_trip: Trip,
        start_trip: Trip,
        allow_relief_points: bool,
    ) -> bool:
        same_terminal = end_trip.destination_id == start_trip.origin_id
        same_depot = (
            end_trip.depot_id is not None
            and start_trip.depot_id is not None
            and end_trip.depot_id == start_trip.depot_id
        )
        relief_ok = False
        if allow_relief_points:
            relief_ok = bool(
                end_trip.is_relief_point
                or start_trip.is_relief_point
                or (
                    end_trip.relief_point_id is not None
                    and end_trip.relief_point_id in {end_trip.destination_id, start_trip.origin_id}
                )
                or (
                    start_trip.relief_point_id is not None
                    and start_trip.relief_point_id in {end_trip.destination_id, start_trip.origin_id}
                )
            )
        return same_terminal or same_depot or relief_ok

    def _audit_block(self, block, min_layover: int, enforce_same_depot: bool, allow_multi_line: bool = True) -> List[str]:
        issues: List[str] = []
        trips = list(getattr(block, "trips", []))
        line_ids = {int(trip.line_id) for trip in trips}
        if len(line_ids) > 1 and not allow_multi_line:
            issues.append(f"BLOCK_MULTI_LINE B{block.id}")
        for index in range(len(trips) - 1):
            current = trips[index]
            nxt = trips[index + 1]
            gap = nxt.start_time - current.end_time
            # Contiguous trip_group pair (ida/volta): no layover needed
            if (
                gap == 0
                and getattr(current, "trip_group_id", None) is not None
                and current.trip_group_id == getattr(nxt, "trip_group_id", None)
            ):
                continue
            deadhead_need = int(
                current.deadhead_times.get(
                    nxt.origin_id,
                    0 if current.destination_id == nxt.origin_id else min_layover,
                )
            )
            need = max(min_layover, deadhead_need)
            if gap < 0:
                issues.append(f"VEHICLE_OVERLAP B{block.id} T{current.id}->{nxt.id}")
            elif gap < need:
                issues.append(f"DEADHEAD_INFEASIBLE B{block.id} T{current.id}->{nxt.id}")
        if enforce_same_depot and trips:
            start_depot = trips[0].depot_id
            end_depot = trips[-1].depot_id
            if start_depot is not None and end_depot is not None and start_depot != end_depot:
                issues.append(f"BLOCK_SAME_DEPOT_VIOLATION B{block.id}")
        return issues

    def _audit_duty(
        self,
        duty,
        max_shift: int,
        max_driving: int,
        min_break: int,
        enforce_same_depot: bool,
        enforce_single_line_duty: bool,
        operator_change_terminals_only: bool,
        allow_relief_points: bool,
    ) -> List[str]:
        issues: List[str] = []
        if duty.spread_time > max_shift:
            issues.append(f"SPREAD_EXCEEDED D{duty.id}")
        if int(duty.meta.get("max_continuous_drive_minutes", 0)) > max_driving:
            issues.append(f"CONTINUOUS_DRIVING_EXCEEDED D{duty.id}")
        if any("Intervalo de refeição insuficiente" in warning for warning in duty.warnings):
            issues.append(f"MEAL_BREAK_MISSING D{duty.id}")
        if enforce_same_depot and duty.meta.get("start_depot_id") is not None and duty.meta.get("end_depot_id") is not None:
            if duty.meta.get("start_depot_id") != duty.meta.get("end_depot_id"):
                issues.append(f"DUTY_SAME_DEPOT_VIOLATION D{duty.id}")
        if enforce_single_line_duty:
            line_ids = {int(line_id) for line_id in duty.meta.get("line_ids", [])}
            if len(line_ids) > 1:
                issues.append(f"DUTY_MULTI_LINE D{duty.id}")

        tasks = list(getattr(duty, "tasks", []))
        for index in range(len(tasks) - 1):
            current = tasks[index]
            nxt = tasks[index + 1]
            gap = nxt.start_time - current.end_time
            if gap < 0:
                issues.append(f"DUTY_OVERLAP D{duty.id} B{current.id}->{nxt.id}")
            if operator_change_terminals_only and current.trips and nxt.trips:
                end_trip = current.trips[-1]
                start_trip = nxt.trips[0]
                if not self._operator_change_boundary_ok(end_trip, start_trip, allow_relief_points):
                    issues.append(f"OPERATOR_CHANGE_NON_TERMINAL D{duty.id} B{current.id}->{nxt.id}")
        return issues

    def _audit_source_block_handoffs(
        self,
        duties,
        operator_change_terminals_only: bool,
        allow_relief_points: bool,
    ) -> List[str]:
        if not operator_change_terminals_only:
            return []

        grouped: Dict[int, List[Tuple[int, Any]]] = {}
        for duty in duties:
            for task in getattr(duty, "tasks", []):
                source_block_id = int(task.meta.get("source_block_id", task.id))
                grouped.setdefault(source_block_id, []).append((int(duty.id), task))

        issues: List[str] = []
        for source_block_id, entries in grouped.items():
            ordered = sorted(entries, key=lambda item: (item[1].start_time, item[1].id, item[0]))
            for index in range(len(ordered) - 1):
                current_duty_id, current_task = ordered[index]
                next_duty_id, next_task = ordered[index + 1]
                if current_duty_id == next_duty_id:
                    continue
                gap = next_task.start_time - current_task.end_time
                if gap < 0:
                    issues.append(
                        f"SOURCE_BLOCK_DUTY_OVERLAP SB{source_block_id} D{current_duty_id}->{next_duty_id}"
                    )
                    continue
                if not current_task.trips or not next_task.trips:
                    continue
                if not self._operator_change_boundary_ok(
                    current_task.trips[-1],
                    next_task.trips[0],
                    allow_relief_points,
                ):
                    issues.append(
                        f"OPERATOR_CHANGE_NON_TERMINAL SB{source_block_id} D{current_duty_id}->{next_duty_id}"
                    )
        return issues
