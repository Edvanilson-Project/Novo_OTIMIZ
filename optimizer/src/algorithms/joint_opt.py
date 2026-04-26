import logging
import math
import random
from typing import List, Dict, Any, Optional, Tuple, Set
import copy
from .evaluator import CostEvaluator
from .vsp.greedy import build_preferred_pairs
from ..domain.models import CSPSolution, VSPSolution, Trip, Block, Duty

logger = logging.getLogger(__name__)
evaluator = CostEvaluator()

def _try_merge_vsp_blocks(vsp_sol: VSPSolution, vsp_params: Dict[str, Any]) -> VSPSolution:
    """
    Tenta fundir blocos VSP adjacentes para reduzir veículos.
    Percorre APENAS pares adjacentes (por start_time) — O(B²) no pior caso
    vs O(B³) antigo que escaneava todos os j > i.
    """
    min_layover = int(vsp_params.get("min_layover_minutes", 8))
    max_vehicle_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960))
    allow_multi_line = bool(vsp_params.get("allow_multi_line_block", True))
    connection_tolerance = int(vsp_params.get("connection_tolerance_minutes", 0))

    # Shallow copy: new Block objects with new trips lists, independent meta dicts
    blocks = [Block(id=b.id, trips=list(b.trips), vehicle_type_id=b.vehicle_type_id,
                    warnings=b.warnings, meta=dict(b.meta)) for b in vsp_sol.blocks]
    changed = True
    total_merges = 0

    while changed:
        changed = False
        blocks.sort(key=lambda b: b.start_time)

        i = 0
        while i < len(blocks) - 1:
            b1 = blocks[i]
            b2 = blocks[i + 1]
            if not b1.trips or not b2.trips:
                i += 1
                continue

            last_t = b1.trips[-1]
            first_t = b2.trips[0]
            gap = first_t.start_time - last_t.end_time
            if gap < 0:
                i += 1
                continue

            # Verificar deadhead — respeita connection_tolerance_minutes
            deadhead = int(last_t.deadhead_times.get(first_t.origin_id, 0))
            needed = max(min_layover, deadhead)
            if gap + connection_tolerance < needed:
                i += 1
                continue

            # Verificar duração total do bloco consolidado
            total_duration = b2.trips[-1].end_time - b1.trips[0].start_time
            if total_duration > max_vehicle_shift:
                i += 1
                continue

            # Verificar multi-linha
            if not allow_multi_line:
                lines_b1 = {t.line_id for t in b1.trips}
                lines_b2 = {t.line_id for t in b2.trips}
                if lines_b1 != lines_b2:
                    i += 1
                    continue

            # Merge b2 into b1
            b1.trips.extend(b2.trips)
            b1.trips.sort(key=lambda t: t.start_time)
            blocks.pop(i + 1)
            changed = True
            total_merges += 1
            # Não incrementa i — tenta fundir mais blocos neste

    # Filtrar blocos vazios independente de merge
    blocks = [b for b in blocks if b.trips]

    if total_merges > 0 or len(blocks) < len(vsp_sol.blocks):
        logger.info(f"[VSP-MERGE] Fundiu {total_merges} blocos: {len(vsp_sol.blocks)} → {len(blocks)}")
        for idx, b in enumerate(blocks):
            b.id = idx + 1
        result = copy.deepcopy(vsp_sol)
        result.blocks = blocks
        return result

    return vsp_sol


def _renumber_blocks(blocks: List[Block]) -> List[Block]:
    ordered = [block for block in blocks if block.trips]
    ordered.sort(key=lambda block: (block.start_time, block.id))
    for idx, block in enumerate(ordered, start=1):
        block.id = idx
    return ordered


def _csp_feedback_candidates(
    csp_sol: CSPSolution,
    vsp_sol: VSPSolution,
    vsp_params: Dict[str, Any],
) -> List[VSPSolution]:
    """Generate VSP refinements guided by CSP evaluation results (O-C5 feedback).

    Identifies blocks involved in CSP violations/overtime and creates VSP
    candidates that split those blocks, giving CSP shorter blocks to work with.
    """
    # Identify blocks contributing to duties with violations or overtime
    problem_block_ids: set = set()
    for duty in (csp_sol.duties or []):
        has_issue = (
            duty.rest_violations > 0
            or duty.shift_violations > 0
            or duty.overtime_minutes > 0
            or duty.continuous_driving_violation
        )
        if has_issue:
            for seg in duty.segments:
                problem_block_ids.add(seg.block_id)

    if not problem_block_ids:
        return []

    candidates: List[VSPSolution] = []
    max_id = max((b.id for b in vsp_sol.blocks), default=0)

    for target_id in problem_block_ids:
        new_blocks: List[Block] = []
        split_done = False
        next_id = max_id + 1
        for b in vsp_sol.blocks:
            if b.id == target_id and len(b.trips) >= 4:
                # Split at midpoint — creates two smaller blocks for CSP
                mid = len(b.trips) // 2
                b1 = Block(id=b.id, trips=list(b.trips[:mid]),
                           vehicle_type_id=b.vehicle_type_id,
                           warnings=b.warnings, meta=dict(b.meta))
                b2 = Block(id=next_id, trips=list(b.trips[mid:]),
                           vehicle_type_id=b.vehicle_type_id,
                           warnings=b.warnings, meta=dict(b.meta))
                new_blocks.extend([b1, b2])
                next_id += 1
                split_done = True
            else:
                new_blocks.append(b)

        if split_done:
            refined_blocks = _renumber_blocks(new_blocks)
            refined_vsp = VSPSolution(
                blocks=refined_blocks,
                algorithm=vsp_sol.algorithm,
                warnings=list(vsp_sol.warnings or []),
                unassigned_trips=list(vsp_sol.unassigned_trips or []),
                meta=dict(vsp_sol.meta or {}),
            )
            candidates.append(refined_vsp)

    return candidates


def _vsp_signature(vsp_sol: VSPSolution) -> Tuple[Tuple[int, ...], ...]:
    ordered_blocks = sorted(vsp_sol.blocks, key=lambda block: (block.start_time, block.id))
    return tuple(tuple(int(trip.id) for trip in block.trips) for block in ordered_blocks)


def _build_post_opt_metrics(
    csp_sol: CSPSolution,
    vsp_sol: VSPSolution,
    min_work: int,
    trips: Optional[List[Trip]] = None,
    vsp_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    duties = csp_sol.duties or []
    short_duties = sum(1 for duty in duties if min_work > 0 and duty.work_time < min_work)
    split_duties = 0
    vehicle_switches = 0
    waiting_minutes = 0
    unpaid_break_minutes = 0
    cross_day_duties = 0
    preferred_pair_count = 0
    preferred_pair_breaks = 0
    boundary_preferred_pair_breaks = 0
    duty_pair_splits = 0
    trip_group_total = 0
    trip_group_same_roster = 0
    trip_group_same_duty = 0
    trip_group_same_block = 0
    trip_group_split_groups = 0

    for duty in duties:
        unique_sources: List[int] = []
        for source_block_id in duty.meta.get("source_block_ids", []):
            if source_block_id is None:
                continue
            parsed_source = int(source_block_id)
            if parsed_source not in unique_sources:
                unique_sources.append(parsed_source)
        switches = max(0, len(unique_sources) - 1)
        vehicle_switches += switches
        if switches > 0:
            split_duties += 1

        waiting_minutes += int(duty.meta.get("waiting_minutes", 0) or 0)
        unpaid_break_minutes += int(
            duty.meta.get("unpaid_break_total_minutes", max(0, duty.spread_time - duty.work_time)) or 0
        )
        if int(duty.meta.get("last_service_day", duty.meta.get("service_day", 0)) or 0) > int(
            duty.meta.get("service_day", 0) or 0
        ):
            cross_day_duties += 1

    if trips and bool((vsp_params or {}).get("preserve_preferred_pairs", True)):
        min_layover = int((vsp_params or {}).get("min_layover_minutes", 8) or 8)
        pair_window = int((vsp_params or {}).get("preferred_pair_window_minutes", 120) or 120)
        preferred_pairs = build_preferred_pairs(list(trips), min_layover, pair_window)
        unique_pairs = {
            tuple(sorted((trip_id, pair_id)))
            for trip_id, pair_id in preferred_pairs.items()
            if trip_id < pair_id
        }
        consecutive_pairs = {
            tuple(sorted((block.trips[index].id, block.trips[index + 1].id)))
            for block in (vsp_sol.blocks or [])
            for index in range(len(block.trips) - 1)
            if preferred_pairs.get(block.trips[index].id) == block.trips[index + 1].id
        }
        preferred_pair_count = len(unique_pairs)
        preferred_pair_breaks = len(unique_pairs - consecutive_pairs)

        duty_by_trip: Dict[int, int] = {}
        trip_positions: Dict[int, Tuple[int, int, int]] = {}
        for duty in duties:
            for task in getattr(duty, "tasks", []):
                for trip in task.trips:
                    duty_by_trip[int(trip.id)] = int(duty.id)
        for block in (vsp_sol.blocks or []):
            for index, trip in enumerate(block.trips):
                trip_positions[int(trip.id)] = (int(block.id), int(index), int(len(block.trips)))
        seen_pairs: Set[Tuple[int, int]] = set()
        for trip_id, pair_id in preferred_pairs.items():
            signature = tuple(sorted((int(trip_id), int(pair_id))))
            if signature in seen_pairs:
                continue
            seen_pairs.add(signature)
            if duty_by_trip.get(signature[0]) != duty_by_trip.get(signature[1]):
                duty_pair_splits += 1
            pos_a = trip_positions.get(signature[0])
            pos_b = trip_positions.get(signature[1])
            if pos_a is not None and pos_b is not None:
                same_block = pos_a[0] == pos_b[0]
                boundary_a = pos_a[1] == 0 or pos_a[1] == pos_a[2] - 1
                boundary_b = pos_b[1] == 0 or pos_b[1] == pos_b[2] - 1
                if not same_block and (boundary_a or boundary_b):
                    boundary_preferred_pair_breaks += 1

        group_map: Dict[int, Dict[str, set[int]]] = {}
        for trip in trips:
            group_id = getattr(trip, "trip_group_id", None)
            if group_id is None:
                continue
            parsed_group_id = int(group_id)
            entry = group_map.setdefault(
                parsed_group_id,
                {"blocks": set(), "duties": set(), "rosters": set()},
            )
            trip_block = trip_positions.get(int(trip.id))
            if trip_block is not None:
                entry["blocks"].add(int(trip_block[0]))
            duty_id = duty_by_trip.get(int(trip.id))
            if duty_id is not None:
                entry["duties"].add(int(duty_id))
                for duty in duties:
                    if int(duty.id) == int(duty_id):
                        roster_id = duty.meta.get("roster_id")
                        if roster_id is not None:
                            entry["rosters"].add(int(roster_id))
                        break

        trip_group_total = len(group_map)
        for entry in group_map.values():
            same_block = len(entry["blocks"]) <= 1
            same_duty = len(entry["duties"]) <= 1
            same_roster = len(entry["rosters"]) <= 1 if entry["rosters"] else False
            if same_block:
                trip_group_same_block += 1
            if same_duty:
                trip_group_same_duty += 1
            if same_roster:
                trip_group_same_roster += 1
            if not same_roster and trip_group_total > 0:
                trip_group_split_groups += 1

    preferred_pair_pressure = (
        preferred_pair_breaks * 1000
        + boundary_preferred_pair_breaks * 3000
    )

    fragmentation_score = (
        len(duties) * 10000
        + short_duties * 1000
        + split_duties * 400
        + vehicle_switches * 150
        + waiting_minutes
        + max(0, unpaid_break_minutes - waiting_minutes)
    )

    return {
        "vehicles": len(vsp_sol.blocks),
        "crew": csp_sol.num_crew,
        "duties": len(duties),
        "violations": int(csp_sol.cct_violations or 0),
        "short_duties": short_duties,
        "split_duties": split_duties,
        "vehicle_switches": vehicle_switches,
        "waiting_minutes": waiting_minutes,
        "unpaid_break_minutes": unpaid_break_minutes,
        "cross_day_duties": cross_day_duties,
        "fragmentation_score": fragmentation_score,
        "uncovered_blocks": len(csp_sol.uncovered_blocks or []),
        "unassigned_trips": len(vsp_sol.unassigned_trips or []),
        "csp_cost": round(evaluator.csp_cost(csp_sol), 2),
        "preferred_pair_count": preferred_pair_count,
        "preferred_pair_breaks": preferred_pair_breaks,
        "boundary_preferred_pair_breaks": boundary_preferred_pair_breaks,
        "preferred_pair_pressure": preferred_pair_pressure,
        "duty_pair_splits": duty_pair_splits,
        "trip_group_total": trip_group_total,
        "trip_group_same_block": trip_group_same_block,
        "trip_group_same_duty": trip_group_same_duty,
        "trip_group_same_roster": trip_group_same_roster,
        "trip_group_split_groups": trip_group_split_groups,
    }


def _is_better_post_opt_candidate(current: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    current_pair_pressure = int(
        current.get(
            "preferred_pair_pressure",
            current.get("preferred_pair_breaks", 0) * 1000 + current.get("boundary_preferred_pair_breaks", 0) * 3000,
        )
    )
    candidate_pair_pressure = int(
        candidate.get(
            "preferred_pair_pressure",
            candidate.get("preferred_pair_breaks", 0) * 1000 + candidate.get("boundary_preferred_pair_breaks", 0) * 3000,
        )
    )

    if candidate["unassigned_trips"] > current["unassigned_trips"]:
        return False
    if candidate["uncovered_blocks"] > current["uncovered_blocks"]:
        return False
    if candidate["violations"] > current["violations"]:
        return False
    if candidate.get("trip_group_split_groups", 0) > current.get("trip_group_split_groups", 0):
        return False
    if candidate["vehicles"] > current["vehicles"] + 1:
        return False
    if candidate["crew"] > current["crew"] and candidate["vehicles"] <= current["vehicles"]:
        return False
    if candidate["vehicles"] > current["vehicles"] and candidate["crew"] > current["crew"] + 1:
        return False
    if candidate_pair_pressure > current_pair_pressure:
        return False
    if candidate.get("duty_pair_splits", 0) > current.get("duty_pair_splits", 0):
        return False

    if candidate["vehicles"] > current["vehicles"]:
        if candidate_pair_pressure >= current_pair_pressure:
            return False
        current_rank = (
            current["violations"],
            current.get("trip_group_split_groups", 0),
            current_pair_pressure,
            current.get("duty_pair_splits", 0),
            current["crew"],
            current["fragmentation_score"],
            current["vehicles"],
            current["short_duties"],
            current["split_duties"],
            current["vehicle_switches"],
            current["csp_cost"],
        )
        candidate_rank = (
            candidate["violations"],
            candidate.get("trip_group_split_groups", 0),
            candidate_pair_pressure,
            candidate.get("duty_pair_splits", 0),
            candidate["crew"],
            candidate["fragmentation_score"],
            candidate["vehicles"],
            candidate["short_duties"],
            candidate["split_duties"],
            candidate["vehicle_switches"],
            candidate["csp_cost"],
        )
        return candidate_rank < current_rank

    current_rank = (
        current["violations"],
        current["vehicles"],
        current["crew"],
        current.get("trip_group_split_groups", 0),
        current_pair_pressure,
        current.get("duty_pair_splits", 0),
        current["fragmentation_score"],
        current["short_duties"],
        current["split_duties"],
        current["vehicle_switches"],
        current["csp_cost"],
    )
    candidate_rank = (
        candidate["violations"],
        candidate["vehicles"],
        candidate["crew"],
        candidate.get("trip_group_split_groups", 0),
        candidate_pair_pressure,
        candidate.get("duty_pair_splits", 0),
        candidate["fragmentation_score"],
        candidate["short_duties"],
        candidate["split_duties"],
        candidate["vehicle_switches"],
        candidate["csp_cost"],
    )
    return candidate_rank < current_rank


def _can_append_suffix(recipient: Block, suffix: List[Trip], vsp_params: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    if not recipient.trips or not suffix:
        return False, "empty_block", {}

    min_layover = int(vsp_params.get("min_layover_minutes", 8) or 8)
    max_vehicle_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960) or 960)
    allow_multi_line = bool(vsp_params.get("allow_multi_line_block", True))
    connection_tolerance = int(vsp_params.get("connection_tolerance_minutes", 0) or 0)
    last_trip = recipient.trips[-1]
    first_suffix_trip = suffix[0]
    gap = first_suffix_trip.start_time - last_trip.end_time

    if gap < 0:
        return False, "overlap", {"gap": gap}

    deadhead = int(last_trip.deadhead_times.get(first_suffix_trip.origin_id, 0))
    transfer_needed = max(min_layover, deadhead)
    if gap + connection_tolerance < transfer_needed:
        return False, "transfer_insufficient", {"gap": gap, "transfer_needed": transfer_needed}

    if not allow_multi_line:
        recipient_lines = {int(trip.line_id) for trip in recipient.trips}
        suffix_lines = {int(trip.line_id) for trip in suffix}
        if recipient_lines and suffix_lines and recipient_lines != suffix_lines:
            return False, "multi_line_disabled", {}

    combined_duration = suffix[-1].end_time - recipient.trips[0].start_time
    if max_vehicle_shift > 0 and combined_duration > max_vehicle_shift:
        return False, "max_vehicle_shift_exceeded", {"combined_duration": combined_duration}

    return True, "", {"gap": gap, "transfer_needed": transfer_needed}


def _generate_tail_relocation_candidates(
    vsp_sol: VSPSolution,
    vsp_params: Dict[str, Any],
    *,
    limit: int = 16,
    max_tail_trips: int = 4,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if limit <= 0 or max_tail_trips <= 0:
        return [], {"considered": 0, "generated": 0, "reasons": {}}

    base_blocks = sorted(copy.deepcopy(vsp_sol.blocks), key=lambda block: (block.start_time, block.id))
    candidates: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {"considered": 0, "generated": 0, "reasons": {}}
    seen_signatures: set[Tuple[Tuple[int, ...], ...]] = set()

    for recipient_idx, recipient in enumerate(base_blocks):
        for donor_idx, donor in enumerate(base_blocks):
            if recipient_idx == donor_idx:
                continue

            donor_trips = sorted(donor.trips, key=lambda trip: (trip.start_time, trip.id))
            if len(donor_trips) < 2:
                continue

            tail_cap = min(max_tail_trips, len(donor_trips) - 1)
            for tail_size in range(1, tail_cap + 1):
                suffix = donor_trips[-tail_size:]
                stats["considered"] = int(stats.get("considered", 0)) + 1
                ok, reason, data = _can_append_suffix(recipient, suffix, vsp_params)
                if not ok:
                    reason_counts = stats.setdefault("reasons", {})
                    reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1
                    continue

                candidate_blocks = copy.deepcopy(base_blocks)
                candidate_recipient = candidate_blocks[recipient_idx]
                candidate_donor = candidate_blocks[donor_idx]
                suffix_trip_ids = {int(trip.id) for trip in suffix}
                candidate_tail = [copy.deepcopy(trip) for trip in suffix]
                candidate_recipient.trips.extend(candidate_tail)
                candidate_recipient.trips.sort(key=lambda trip: (trip.start_time, trip.id))
                candidate_donor.trips = [trip for trip in candidate_donor.trips if int(trip.id) not in suffix_trip_ids]
                candidate_blocks = _renumber_blocks(candidate_blocks)

                candidate_vsp = copy.deepcopy(vsp_sol)
                candidate_vsp.blocks = candidate_blocks
                signature = _vsp_signature(candidate_vsp)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)

                candidates.append(
                    {
                        "phase": "tail_relocation",
                        "vsp": candidate_vsp,
                        "details": {
                            "recipient_block_id": int(recipient.id),
                            "donor_block_id": int(donor.id),
                            "tail_trip_ids": [int(trip.id) for trip in suffix],
                            "tail_size": tail_size,
                            "gap": int(data.get("gap", 0)),
                        },
                    }
                )
                stats["generated"] = int(stats.get("generated", 0)) + 1

    candidates.sort(
        key=lambda item: (
            int(item["details"].get("gap", 0)),
            -int(item["details"].get("tail_size", 0)),
            int(item["details"].get("recipient_block_id", 0)),
            int(item["details"].get("donor_block_id", 0)),
        )
    )
    return candidates[:limit], stats


def _generate_split_pair_repair_candidates(
    vsp_sol: VSPSolution,
    trips: List[Trip],
    vsp_params: Dict[str, Any],
    *,
    limit: int = 16,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Gera reparos conservadores para pares preferenciais que ficaram em blocos distintos.

    A heurística só tenta o caso em que o trip inicial do par está no fim do bloco de origem
    e o parceiro começa o bloco destino. Nesse cenário, o prefixo anterior ao par é destacado
    como um novo bloco para encurtar a janela operacional e permitir que o par volte ao mesmo
    veículo sem violar `max_vehicle_shift`.
    """
    if limit <= 0 or not trips:
        return [], {"considered": 0, "generated": 0, "reasons": {}}
    if not bool(vsp_params.get("preserve_preferred_pairs", True)):
        return [], {"considered": 0, "generated": 0, "reasons": {}}

    min_layover = int(vsp_params.get("min_layover_minutes", 8) or 8)
    max_vehicle_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960) or 960)
    allow_multi_line = bool(vsp_params.get("allow_multi_line_block", True))
    connection_tolerance = int(vsp_params.get("connection_tolerance_minutes", 0) or 0)
    pair_window = int(vsp_params.get("preferred_pair_window_minutes", 120) or 120)
    preferred_pairs = build_preferred_pairs(list(trips), min_layover, pair_window)
    if not preferred_pairs:
        return [], {"considered": 0, "generated": 0, "reasons": {}}

    trip_map: Dict[int, Trip] = {int(trip.id): trip for trip in trips}
    base_blocks = sorted(copy.deepcopy(vsp_sol.blocks), key=lambda block: (block.start_time, block.id))
    trip_to_block: Dict[int, Block] = {}
    for block in base_blocks:
        for trip in block.trips:
            trip_to_block[int(trip.id)] = block

    def _block_is_feasible(trips_seq: List[Trip]) -> bool:
        if not trips_seq:
            return True
        if max_vehicle_shift > 0 and trips_seq[-1].end_time - trips_seq[0].start_time > max_vehicle_shift:
            return False
        if not allow_multi_line:
            lines = {int(trip.line_id) for trip in trips_seq}
            if len(lines) > 1:
                return False
        for index in range(len(trips_seq) - 1):
            current = trips_seq[index]
            nxt = trips_seq[index + 1]
            gap = int(nxt.start_time - current.end_time)
            if gap < 0:
                return False
            if (
                gap == 0
                and getattr(current, "trip_group_id", None) is not None
                and current.trip_group_id == getattr(nxt, "trip_group_id", None)
            ):
                continue
            needed = max(min_layover, int(current.deadhead_times.get(nxt.origin_id, 0)))
            if gap + connection_tolerance < needed:
                return False
        return True

    def _signature(blocks: List[Block]) -> Tuple[Tuple[int, ...], ...]:
        ordered = sorted((block for block in blocks if block.trips), key=lambda block: (block.start_time, block.id))
        return tuple(tuple(int(trip.id) for trip in block.trips) for block in ordered)

    stats: Dict[str, Any] = {"considered": 0, "generated": 0, "reasons": {}}
    candidates: List[Dict[str, Any]] = []
    seen_signatures: Set[Tuple[Tuple[int, ...], ...]] = set()
    seen_pairs: Set[Tuple[int, int]] = set()

    for trip_id, pair_id in preferred_pairs.items():
        if trip_id >= pair_id:
            continue
        pair_signature = (int(trip_id), int(pair_id))
        if pair_signature in seen_pairs:
            continue
        seen_pairs.add(pair_signature)
        stats["considered"] = int(stats.get("considered", 0)) + 1

        trip_a = trip_map.get(int(trip_id))
        trip_b = trip_map.get(int(pair_id))
        if trip_a is None or trip_b is None:
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["missing_trip"] = int(reason_counts.get("missing_trip", 0)) + 1
            continue

        if trip_a.start_time <= trip_b.start_time:
            first_id, second_id = int(trip_a.id), int(trip_b.id)
        else:
            first_id, second_id = int(trip_b.id), int(trip_a.id)

        src_block = trip_to_block.get(first_id)
        dst_block = trip_to_block.get(second_id)
        if src_block is None or dst_block is None or src_block.id == dst_block.id:
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["not_split"] = int(reason_counts.get("not_split", 0)) + 1
            continue
        if not src_block.trips or not dst_block.trips:
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["empty_block"] = int(reason_counts.get("empty_block", 0)) + 1
            continue
        if src_block.trips[-1].id != first_id:
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["source_not_boundary"] = int(reason_counts.get("source_not_boundary", 0)) + 1
            continue
        if dst_block.trips[0].id != second_id:
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["target_not_boundary"] = int(reason_counts.get("target_not_boundary", 0)) + 1
            continue

        src_idx = len(src_block.trips) - 1
        prefix = list(src_block.trips[:src_idx])
        source_suffix = list(src_block.trips[src_idx:])
        if not prefix or not source_suffix:
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["no_prefix"] = int(reason_counts.get("no_prefix", 0)) + 1
            continue

        candidate_prefix = Block(
            id=0,
            trips=list(prefix),
            vehicle_type_id=src_block.vehicle_type_id,
            warnings=list(src_block.warnings),
            meta=dict(src_block.meta),
        )
        candidate_source = Block(
            id=0,
            trips=[*source_suffix, copy.deepcopy(dst_block.trips[0])],
            vehicle_type_id=src_block.vehicle_type_id,
            warnings=list(src_block.warnings),
            meta=dict(src_block.meta),
        )
        candidate_target = Block(
            id=0,
            trips=list(dst_block.trips[1:]),
            vehicle_type_id=dst_block.vehicle_type_id,
            warnings=list(dst_block.warnings),
            meta=dict(dst_block.meta),
        )

        if not _block_is_feasible(candidate_prefix.trips):
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["prefix_infeasible"] = int(reason_counts.get("prefix_infeasible", 0)) + 1
            continue
        if not _block_is_feasible(candidate_source.trips):
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["source_infeasible"] = int(reason_counts.get("source_infeasible", 0)) + 1
            continue
        if candidate_target.trips and not _block_is_feasible(candidate_target.trips):
            reason_counts = stats.setdefault("reasons", {})
            reason_counts["target_infeasible"] = int(reason_counts.get("target_infeasible", 0)) + 1
            continue

        candidate_blocks: List[Block] = []
        for block in base_blocks:
            if block.id == src_block.id:
                candidate_blocks.append(copy.deepcopy(candidate_prefix))
                candidate_blocks.append(copy.deepcopy(candidate_source))
            elif block.id == dst_block.id:
                if candidate_target.trips:
                    candidate_blocks.append(copy.deepcopy(candidate_target))
            else:
                candidate_blocks.append(copy.deepcopy(block))

        candidate_vsp = copy.deepcopy(vsp_sol)
        candidate_vsp.blocks = _renumber_blocks(candidate_blocks)
        signature = _signature(candidate_vsp.blocks)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        candidates.append(
            {
                "phase": "pair_repair",
                "vsp": candidate_vsp,
                "details": {
                    "pair_trip_ids": [first_id, second_id],
                    "source_block_id": int(src_block.id),
                    "target_block_id": int(dst_block.id),
                    "prefix_trip_ids": [int(trip.id) for trip in prefix],
                    "source_trip_ids": [int(trip.id) for trip in candidate_source.trips],
                    "target_trip_ids": [int(trip.id) for trip in candidate_target.trips],
                    "prefix_size": len(prefix),
                },
            }
        )
        stats["generated"] = int(stats.get("generated", 0)) + 1
        if len(candidates) >= limit:
            break

    candidates.sort(
        key=lambda item: (
            -int(item["details"].get("prefix_size", 0)),
            int(item["details"].get("source_block_id", 0)),
            int(item["details"].get("target_block_id", 0)),
        )
    )
    return candidates[:limit], stats


def _enhanced_large_neighborhood_search(
    vsp_sol: VSPSolution,
    csp_sol: CSPSolution,
    vsp_params: Dict[str, Any],
    cct_params: Dict[str, Any],
    trips: List[Trip],
    evaluator: CostEvaluator,
    max_iterations: int = 10,
    destruction_rate: float = 0.3,
    temperature: float = 100.0,
    cooling_rate: float = 0.95
) -> Tuple[VSPSolution, CSPSolution, Dict[str, Any]]:
    """
    LNS aprimorada com:
    1. Destruição baseada em custo marginal
    2. Reparação com busca local
    3. Critério de aceitação por simulated annealing
    4. Foco em redução de custo total (frota + pessoal)
    """
    from .csp.greedy import GreedyCSP
    
    best_vsp = copy.deepcopy(vsp_sol)
    best_csp = copy.deepcopy(csp_sol)
    best_cost = evaluator.csp_cost(best_csp) + evaluator.vsp_cost(best_vsp, [])
    
    stats = {
        "iterations": 0,
        "accepted": 0,
        "improvements": 0,
        "temperature_history": [],
        "cost_history": []
    }
    
    current_temp = temperature
    
    for iteration in range(max_iterations):
        # 1. DESTRUIR: Selecionar blocos com maior custo marginal
        _duty_breakdown = evaluator.csp_cost_breakdown(best_csp)
        duty_cost_map: Dict[int, float] = {
            d["duty_id"]: d["total"] for d in _duty_breakdown.get("duties", [])
        }
        blocks_to_destroy = _select_blocks_by_marginal_cost(
            best_vsp, best_csp, duty_cost_map, destruction_rate
        )
        
        # Extrair trips dos blocos destruídos
        destroyed_trips = []
        remaining_blocks = []
        
        for block in best_vsp.blocks:
            if block.id in blocks_to_destroy:
                destroyed_trips.extend(block.trips)
            else:
                remaining_blocks.append(copy.deepcopy(block))
        
        # 2. REPARAR: Heurística GRASP com múltiplos critérios
        repaired_blocks = _grasp_repair(
            remaining_blocks, destroyed_trips, vsp_params, evaluator
        )
        
        # 3. AVALIAR: Resolver CSP para nova configuração
        candidate_vsp = VSPSolution(
            blocks=repaired_blocks,
            algorithm=f"{best_vsp.algorithm}_lns",
            meta=dict(best_vsp.meta or {})
        )
        
        csp_solver = GreedyCSP(vsp_params=vsp_params, **cct_params)
        candidate_csp = csp_solver.solve(candidate_vsp.blocks, trips)
        
        candidate_cost = evaluator.csp_cost(candidate_csp) + evaluator.vsp_cost(candidate_vsp, [])
        
        # 4. ACEITAR: Critério de simulated annealing
        cost_delta = candidate_cost - best_cost
        
        if cost_delta < 0 or random.random() < math.exp(-cost_delta / current_temp):
            best_vsp = candidate_vsp
            best_csp = candidate_csp
            best_cost = candidate_cost
            
            if cost_delta < 0:
                stats["improvements"] += 1
            stats["accepted"] += 1
        
        # Atualizar temperatura
        current_temp *= cooling_rate
        stats["temperature_history"].append(current_temp)
        stats["cost_history"].append(best_cost)
        stats["iterations"] += 1
        
        # Critério de parada prematura
        if current_temp < 1.0 and stats["improvements"] == 0:
            break
    
    return best_vsp, best_csp, stats

def _select_blocks_by_marginal_cost(
    vsp_sol: VSPSolution,
    csp_sol: CSPSolution,
    duty_cost_map: Dict[int, float],
    destruction_rate: float
) -> Set[int]:
    """Seleciona blocos com maior custo marginal para destruição."""
    block_costs = []

    for block in vsp_sol.blocks:
        fleet_cost = block.total_duration * 0.5  # R$/min

        personnel_cost = 0.0
        for duty in (csp_sol.duties or []):
            for seg in duty.segments:
                if seg.block_id == block.id:
                    block_work = sum(t.duration for t in block.trips)
                    duty_work = duty.work_time
                    if duty_work > 0:
                        personnel_cost = duty_cost_map.get(duty.id, 0.0) * (block_work / duty_work)
                    break

        block_costs.append((block.id, fleet_cost + personnel_cost))

    block_costs.sort(key=lambda x: x[1], reverse=True)
    n_destroy = max(2, int(len(vsp_sol.blocks) * destruction_rate))
    return {block_id for block_id, _ in block_costs[:n_destroy]}

def _feasible_insertion(block: Block, trip: Trip, vsp_params: Dict[str, Any]) -> Tuple[bool, int, float]:
    """Verifica viabilidade de inserção de uma trip no final de um bloco.

    Reutiliza _can_append_suffix para garantir que todas as hard constraints
    (deadhead, min_layover, max_vehicle_shift, multi_line) sejam respeitadas.
    Só considera inserção no final (append) para preservar a ordenação temporal.
    """
    if not block.trips:
        return True, 0, 0.0

    ok, _reason, data = _can_append_suffix(block, [trip], vsp_params)
    if not ok:
        return False, -1, 0.0

    position = len(block.trips)
    idle_cost = int(data.get("gap", 0)) * 0.25  # R$/min ocioso (alinhado ao CostEvaluator)
    return True, position, idle_cost

def _local_search_2opt(blocks: List[Block], vsp_params: Dict[str, Any]) -> List[Block]:
    """Busca local 2-opt inter-bloco: troca sufixos de tamanho variável para reduzir ociosidade.

    Para cada par de blocos (i, j), testa trocar sufixos de tamanho 'cut'.
    A troca só é efetivada se _can_append_suffix confirmar viabilidade em AMBOS os
    receptores E houver redução líquida do gap ocioso no ponto de corte.
    """
    blocks = copy.deepcopy(blocks)
    improved = True

    while improved:
        improved = False
        n = len(blocks)
        for i in range(n):
            for j in range(i + 1, n):
                b1, b2 = blocks[i], blocks[j]
                if len(b1.trips) < 2 or len(b2.trips) < 2:
                    continue

                for cut in range(1, min(len(b1.trips), len(b2.trips))):
                    head1 = b1.trips[:-cut]
                    tail1 = b1.trips[-cut:]
                    head2 = b2.trips[:-cut]
                    tail2 = b2.trips[-cut:]

                    if not head1 or not head2:
                        continue

                    temp_b1 = Block(id=b1.id, trips=list(head1),
                                    vehicle_type_id=b1.vehicle_type_id, warnings=[], meta=b1.meta)
                    temp_b2 = Block(id=b2.id, trips=list(head2),
                                    vehicle_type_id=b2.vehicle_type_id, warnings=[], meta=b2.meta)

                    ok1, _, data1 = _can_append_suffix(temp_b1, list(tail2), vsp_params)
                    ok2, _, data2 = _can_append_suffix(temp_b2, list(tail1), vsp_params)

                    if not (ok1 and ok2):
                        continue

                    cur_gap1 = tail1[0].start_time - head1[-1].end_time
                    cur_gap2 = tail2[0].start_time - head2[-1].end_time
                    new_gap1 = int(data1.get("gap", 0))
                    new_gap2 = int(data2.get("gap", 0))

                    if new_gap1 + new_gap2 < cur_gap1 + cur_gap2:
                        b1.trips = list(head1) + list(tail2)
                        b2.trips = list(head2) + list(tail1)
                        improved = True
                        break

                if improved:
                    break
            if improved:
                break

    return blocks

def _grasp_repair(
    base_blocks: List[Block],
    unassigned_trips: List[Trip],
    vsp_params: Dict[str, Any],
    evaluator: CostEvaluator,
    alpha: float = 0.3,
    local_search_iterations: int = 5
) -> List[Block]:
    """
    Reparação GRASP (Greedy Randomized Adaptive Search Procedure).
    """
    repaired_blocks = copy.deepcopy(base_blocks)
    unassigned = sorted(unassigned_trips, key=lambda t: t.start_time)
    
    while unassigned:
        # Lista de candidatos restritos (RCL)
        candidate_insertions = []
        
        for trip in unassigned[:10]:  # Limitar busca
            for block in repaired_blocks:
                # Verificar viabilidade de inserção
                feasible, position, cost = _feasible_insertion(
                    block, trip, vsp_params
                )
                if feasible:
                    candidate_insertions.append((trip, block, position, cost))
        
        if not candidate_insertions:
            # Criar novo bloco
            new_block = Block(
                id=len(repaired_blocks) + 1,
                trips=[unassigned[0]],
                vehicle_type_id=1
            )
            repaired_blocks.append(new_block)
            unassigned.pop(0)
            continue
        
        # Ordenar por custo
        candidate_insertions.sort(key=lambda x: x[3])
        
        # Criar RCL (Restricted Candidate List)
        min_cost = candidate_insertions[0][3]
        max_cost = candidate_insertions[-1][3]
        threshold = min_cost + alpha * (max_cost - min_cost)
        
        rcl = [c for c in candidate_insertions if c[3] <= threshold]
        
        # Seleção aleatória da RCL
        selected = random.choice(rcl)
        trip, block, position, _ = selected
        
        # Inserir trip
        block.trips.insert(position, trip)
        
        # Remover trip da lista não atribuída
        unassigned = [t for t in unassigned if t.id != trip.id]
    
    # Busca local nos blocos reparados
    for _ in range(local_search_iterations):
        repaired_blocks = _local_search_2opt(repaired_blocks, vsp_params)
    
    return repaired_blocks

def joint_duty_vehicle_swap(
    csp_sol: CSPSolution,
    vsp_sol: VSPSolution,
    trips: List[Trip],
    cct_params: Dict[str, Any],
    kwargs: Dict[str, Any]
) -> Tuple[CSPSolution, VSPSolution]:
    """
    Pós-otimização conjunta Veículo+Tripulante:
    1. Tenta fundir blocos VSP para reduzir veículos
    2. Tenta mover trips entre blocos para criar jornadas mais eficientes
    3. Recalcula CSP se houve mudanças
    """
    logger.info("Executando Post-Otimizacao (VSP merge + Joint swap)...")

    try:
        from .csp.greedy import GreedyCSP

        def _post_opt_meta(
            *,
            accepted: bool,
            baseline: Dict[str, Any],
            selected_phase: Optional[str],
            selected_candidate: Optional[Dict[str, Any]],
            selected_metrics: Optional[Dict[str, Any]],
            candidates_evaluated: int,
            merged_blocks: int,
            swaps: int,
            fragmentation_enabled: bool,
            candidate_limit: int,
            max_tail_trips: int,
            tail_stats: Dict[str, Any],
            outcome: str,
        ) -> Dict[str, Any]:
            return {
                "accepted": accepted,
                "outcome": outcome,
                "baseline": baseline,
                "selected_phase": selected_phase,
                "selected_candidate": selected_candidate,
                "selected_metrics": selected_metrics,
                "joint_swap": {
                    "merged_blocks": merged_blocks,
                    "swaps": swaps,
                },
                "tail_relocation": {
                    "enabled": fragmentation_enabled,
                    "candidate_limit": candidate_limit,
                    "max_tail_trips": max_tail_trips,
                    "considered": int(tail_stats.get("considered", 0)),
                    "generated": int(tail_stats.get("generated", 0)),
                    "reasons": dict(tail_stats.get("reasons", {})),
                },
                "candidates_evaluated": candidates_evaluated,
            }

        if len(vsp_sol.blocks) < 2:
            baseline_metrics = _build_post_opt_metrics(csp_sol, vsp_sol, 0, trips, {})
            post_opt_meta = _post_opt_meta(
                accepted=False,
                baseline=baseline_metrics,
                selected_phase=None,
                selected_candidate=None,
                selected_metrics=None,
                candidates_evaluated=0,
                merged_blocks=0,
                swaps=0,
                fragmentation_enabled=bool(vsp_sol.meta.get("enable_fragmentation_postopt", True)) if vsp_sol.meta else True,
                candidate_limit=int((vsp_sol.meta or {}).get("fragmentation_candidate_limit", 16) or 16),
                max_tail_trips=int((vsp_sol.meta or {}).get("fragmentation_max_tail_trips", 4) or 4),
                tail_stats={"considered": 0, "generated": 0, "reasons": {}},
                outcome="skipped_single_block",
            )
            csp_sol.meta = {**(csp_sol.meta or {}), "post_optimization": post_opt_meta}
            vsp_sol.meta = {**(vsp_sol.meta or {}), "post_optimization": post_opt_meta}
            return csp_sol, vsp_sol

        # ── Parâmetros globais ───────────────────────────────────────────────
        vsp_params = dict(kwargs.get("vsp_params", {})) if kwargs.get("vsp_params") else (dict(vsp_sol.meta) if vsp_sol.meta else {})
        solver_kwargs = {key: value for key, value in kwargs.items() if key != "vsp_params"}
        min_work = int(solver_kwargs.get("min_work_minutes", cct_params.get("min_work_minutes", 0)) or 0)
        min_layover = int(vsp_params.get("min_layover_minutes", 8))
        max_unpaid_break = int(cct_params.get("max_unpaid_break_minutes", cct_params.get("max_unpaid_break", 180)))
        max_vehicle_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960))

        original_vehicles = len(vsp_sol.blocks)
        original_crew = csp_sol.num_crew
        baseline_metrics = _build_post_opt_metrics(csp_sol, vsp_sol, min_work, trips, vsp_params)

        # ── Fase 1: Merge de blocos VSP ──────────────────────────────────────
        merged_vsp = _try_merge_vsp_blocks(vsp_sol, vsp_params)
        vsp_changed = len(merged_vsp.blocks) < original_vehicles

        # ── Fase 2: Swap de trips entre blocos (multi-pass) ──────────────────

        swap_vsp = copy.deepcopy(merged_vsp)
        blocks = swap_vsp.blocks
        blocks.sort(key=lambda b: b.start_time)
        total_swaps = 0

        # Multi-pass: continua tentando até não haver mais melhorias
        for _pass in range(5):
            pass_swaps = 0
            for i in range(len(blocks)):
                for j in range(i + 1, len(blocks)):
                    b1 = blocks[i]
                    b2 = blocks[j]
                    if not b1.trips or not b2.trips:
                        continue

                    last_b1 = b1.trips[-1]
                    first_b2 = b2.trips[0]
                    gap = first_b2.start_time - last_b1.end_time

                    if gap < 0 or gap > max_unpaid_break:
                        continue

                    deadhead = int(last_b1.deadhead_times.get(first_b2.origin_id, 0))
                    min_layover = int(vsp_params.get("min_layover_minutes", 8))
                    needed = max(min_layover, deadhead)
                    if gap < needed:
                        continue

                    # Verificar max_vehicle_shift após swap
                    combined_duration = first_b2.end_time - b1.trips[0].start_time
                    if max_vehicle_shift > 0 and combined_duration > max_vehicle_shift:
                        continue

                    # Mover primeira trip de b2 para b1
                    b1.trips.append(first_b2)
                    b2.trips.pop(0)
                    pass_swaps += 1
                    total_swaps += 1

            if pass_swaps == 0:
                break
            # Remover blocos vazios e re-numerar
            blocks = [b for b in blocks if b.trips]
            for idx, b in enumerate(blocks):
                b.id = idx + 1

        swap_changed = total_swaps > 0
        if swap_changed:
            swap_vsp.blocks = _renumber_blocks(blocks)

        base_candidate_vsp = swap_vsp if swap_changed else merged_vsp if vsp_changed else vsp_sol
        candidate_vsps: List[Dict[str, Any]] = []
        if vsp_changed or swap_changed:
            logger.info(
                f"[POST-OPT] Veículos: {original_vehicles} → {len(base_candidate_vsp.blocks)}, "
                f"merges={original_vehicles - len(merged_vsp.blocks)}, swaps={total_swaps}"
            )
            candidate_vsps.append(
                {
                    "phase": "joint_swap",
                    "vsp": base_candidate_vsp,
                    "details": {
                        "merged_blocks": original_vehicles - len(merged_vsp.blocks),
                        "swaps": total_swaps,
                    },
                }
            )

        fragmentation_enabled = bool(vsp_params.get("enable_fragmentation_postopt", True))
        tail_candidate_limit = int(vsp_params.get("fragmentation_candidate_limit", 16) or 16)
        max_tail_trips = int(vsp_params.get("fragmentation_max_tail_trips", 4) or 4)
        tail_candidates: List[Dict[str, Any]] = []
        tail_stats: Dict[str, Any] = {"considered": 0, "generated": 0, "reasons": {}}
        if fragmentation_enabled:
            tail_seed_vsps = [vsp_sol]
            if _vsp_signature(base_candidate_vsp) != _vsp_signature(vsp_sol):
                tail_seed_vsps.append(base_candidate_vsp)

            seen_tail_signatures: set[Tuple[Tuple[int, ...], ...]] = set()
            expanded_limit = max(64, tail_candidate_limit * len(tail_seed_vsps) * 2)
            for seed_index, seed_vsp in enumerate(tail_seed_vsps):
                seed_candidates, seed_stats = _generate_tail_relocation_candidates(
                    seed_vsp,
                    vsp_params,
                    limit=expanded_limit,
                    max_tail_trips=max_tail_trips,
                )
                tail_stats["considered"] = int(tail_stats.get("considered", 0)) + int(seed_stats.get("considered", 0))
                tail_stats["generated"] = int(tail_stats.get("generated", 0)) + int(seed_stats.get("generated", 0))
                tail_reasons = tail_stats.setdefault("reasons", {})
                for reason, count in (seed_stats.get("reasons") or {}).items():
                    tail_reasons[reason] = int(tail_reasons.get(reason, 0)) + int(count)

                for candidate in seed_candidates:
                    signature = _vsp_signature(candidate["vsp"])
                    if signature in seen_tail_signatures:
                        continue
                    seen_tail_signatures.add(signature)
                    candidate_details = dict(candidate.get("details") or {})
                    candidate_details["source_seed"] = "original_vsp" if seed_index == 0 else "joint_swap_seed"
                    tail_candidates.append(
                        {
                            **candidate,
                            "details": candidate_details,
                        }
                    )

            tail_candidates.sort(
                key=lambda item: (
                    int(item["details"].get("gap", 0)),
                    -int(item["details"].get("tail_size", 0)),
                    int(item["details"].get("recipient_block_id", 0)),
                    int(item["details"].get("donor_block_id", 0)),
                )
            )
            tail_candidates = tail_candidates[:tail_candidate_limit]
            candidate_vsps.extend(tail_candidates)

        pair_repair_enabled = bool(vsp_params.get("enable_pair_repair_postopt", True))
        pair_repair_candidates: List[Dict[str, Any]] = []
        if pair_repair_enabled and trips:
            pair_seed_vsps = [vsp_sol]
            if _vsp_signature(base_candidate_vsp) != _vsp_signature(vsp_sol):
                pair_seed_vsps.append(base_candidate_vsp)

            seen_pair_signatures: set[Tuple[Tuple[int, ...], ...]] = set()
            expanded_limit = max(32, tail_candidate_limit * len(pair_seed_vsps) * 2)
            for seed_index, seed_vsp in enumerate(pair_seed_vsps):
                seed_candidates, seed_stats = _generate_split_pair_repair_candidates(
                    seed_vsp,
                    trips,
                    vsp_params,
                    limit=expanded_limit,
                )
                for candidate in seed_candidates:
                    signature = _vsp_signature(candidate["vsp"])
                    if signature in seen_pair_signatures:
                        continue
                    seen_pair_signatures.add(signature)
                    candidate_details = dict(candidate.get("details") or {})
                    candidate_details["source_seed"] = "original_vsp" if seed_index == 0 else "joint_swap_seed"
                    pair_repair_candidates.append(
                        {
                            **candidate,
                            "details": candidate_details,
                        }
                    )

            pair_repair_candidates.sort(
                key=lambda item: (
                    -int(item["details"].get("prefix_size", 0)),
                    int(item["details"].get("source_block_id", 0)),
                    int(item["details"].get("target_block_id", 0)),
                )
            )
            pair_repair_candidates = pair_repair_candidates[:tail_candidate_limit]
            candidate_vsps.extend(pair_repair_candidates)

        best_csp = csp_sol
        best_vsp = vsp_sol
        best_metrics = baseline_metrics
        best_candidate: Optional[Dict[str, Any]] = None
        evaluated_signatures = {_vsp_signature(vsp_sol)}

        # ── Fase 3: Large Neighborhood Search (LNS) ──────────────────────────
        lns_enabled = bool(vsp_params.get("enable_lns_postopt", True))
        if lns_enabled and len(best_vsp.blocks) > 2:
            import random
            # RNG local determinístico: seed derivada da assinatura da VSP inicial.
            # Garante reprodutibilidade entre workers Celery distintos rodando o
            # mesmo run_id, sem mexer no estado global de `random`.
            lns_seed = vsp_params.get("lns_seed")
            if lns_seed is None:
                lns_seed = hash(_vsp_signature(best_vsp)) & 0xFFFFFFFF
            rng = random.Random(lns_seed)
            lns_vsp = copy.deepcopy(best_vsp)
            # 1. Destroy: Seleciona aleatoriamente 20% dos blocos para destruir
            num_destroy = max(2, int(len(lns_vsp.blocks) * 0.2))
            destroy_indices = rng.sample(range(len(lns_vsp.blocks)), num_destroy)

            unassigned = []
            for idx in sorted(destroy_indices, reverse=True):
                unassigned.extend(lns_vsp.blocks[idx].trips)
                lns_vsp.blocks.pop(idx)

            unassigned.sort(key=lambda t: t.start_time)

            # 2. Repair: Reinsere as viagens usando heurística gulosa com ruído
            new_blocks = []
            current_block = []
            for t in unassigned:
                if not current_block:
                    current_block.append(t)
                else:
                    last_t = current_block[-1]
                    gap = t.start_time - last_t.end_time
                    deadhead = int(last_t.deadhead_times.get(t.origin_id, 0))
                    needed = max(min_layover, deadhead)

                    if gap >= needed and gap < max_unpaid_break + rng.randint(0, 30):
                        current_block.append(t)
                    else:
                        new_blocks.append(Block(id=0, trips=current_block, vehicle_type_id=lns_vsp.blocks[0].vehicle_type_id if lns_vsp.blocks else 1))
                        current_block = [t]
            if current_block:
                new_blocks.append(Block(id=0, trips=current_block, vehicle_type_id=lns_vsp.blocks[0].vehicle_type_id if lns_vsp.blocks else 1))
                
            lns_vsp.blocks.extend(new_blocks)
            lns_vsp.blocks = _renumber_blocks(lns_vsp.blocks)
            
            candidate_vsps.append({
                "phase": "large_neighborhood_search",
                "vsp": lns_vsp,
                "details": {"destroyed_blocks": num_destroy}
            })

        for candidate in candidate_vsps:
            candidate_vsp = candidate["vsp"]
            signature = _vsp_signature(candidate_vsp)
            if signature in evaluated_signatures:
                continue
            evaluated_signatures.add(signature)

            csp_candidate = GreedyCSP(vsp_params=vsp_params, **solver_kwargs).solve(candidate_vsp.blocks, trips)
            candidate_metrics = _build_post_opt_metrics(csp_candidate, candidate_vsp, min_work, trips, vsp_params)
            if _is_better_post_opt_candidate(best_metrics, candidate_metrics):
                best_csp = csp_candidate
                best_vsp = candidate_vsp
                best_metrics = candidate_metrics
                best_candidate = {
                    "phase": candidate["phase"],
                    "details": dict(candidate.get("details") or {}),
                    "metrics": candidate_metrics,
                }

        # ── CSP Feedback Round (O-C5): use CSP results to refine VSP ─────
        if best_metrics["violations"] > 0:
            feedback_vsps = _csp_feedback_candidates(best_csp, best_vsp, vsp_params)
            for fb_vsp in feedback_vsps:
                fb_sig = _vsp_signature(fb_vsp)
                if fb_sig in evaluated_signatures:
                    continue
                evaluated_signatures.add(fb_sig)
                fb_csp = GreedyCSP(vsp_params=vsp_params, **solver_kwargs).solve(fb_vsp.blocks, trips)
                fb_metrics = _build_post_opt_metrics(fb_csp, fb_vsp, min_work, trips, vsp_params)
                if _is_better_post_opt_candidate(best_metrics, fb_metrics):
                    best_csp = fb_csp
                    best_vsp = fb_vsp
                    best_metrics = fb_metrics
                    best_candidate = {
                        "phase": "csp_feedback",
                        "details": {"split_violation_blocks": True},
                        "metrics": fb_metrics,
                    }

        if best_candidate is not None:
            post_opt_meta = _post_opt_meta(
                accepted=True,
                baseline=baseline_metrics,
                selected_phase=best_candidate["phase"],
                selected_candidate=best_candidate["details"],
                selected_metrics=best_candidate["metrics"],
                candidates_evaluated=len(evaluated_signatures) - 1,
                merged_blocks=original_vehicles - len(merged_vsp.blocks),
                swaps=total_swaps,
                fragmentation_enabled=fragmentation_enabled,
                candidate_limit=tail_candidate_limit,
                max_tail_trips=max_tail_trips,
                tail_stats=tail_stats,
                outcome="accepted_improvement",
            )
            best_csp.meta = {**(best_csp.meta or {}), "post_optimization": post_opt_meta}
            best_vsp.meta = {**(best_vsp.meta or {}), "post_optimization": post_opt_meta}
            logger.info(
                "[POST-OPT] Aceito via %s: Veículos %d→%d, Crew %d→%d, Duties %d→%d, Frag %d→%d",
                best_candidate["phase"],
                baseline_metrics["vehicles"],
                best_metrics["vehicles"],
                original_crew,
                best_metrics["crew"],
                baseline_metrics["duties"],
                best_metrics["duties"],
                baseline_metrics["fragmentation_score"],
                best_metrics["fragmentation_score"],
            )
            return best_csp, best_vsp

        post_opt_meta = _post_opt_meta(
            accepted=False,
            baseline=baseline_metrics,
            selected_phase=None,
            selected_candidate=None,
            selected_metrics=None,
            candidates_evaluated=len(evaluated_signatures) - 1,
            merged_blocks=original_vehicles - len(merged_vsp.blocks),
            swaps=total_swaps,
            fragmentation_enabled=fragmentation_enabled,
            candidate_limit=tail_candidate_limit,
            max_tail_trips=max_tail_trips,
            tail_stats=tail_stats,
            outcome="no_better_candidate" if candidate_vsps else "no_candidate_generated",
        )
        csp_sol.meta = {**(csp_sol.meta or {}), "post_optimization": post_opt_meta}
        vsp_sol.meta = {**(vsp_sol.meta or {}), "post_optimization": post_opt_meta}

        if candidate_vsps:
            logger.info(
                "[POST-OPT] Nenhuma melhoria aceita: Vehicles=%d Crew=%d Duties=%d Frag=%d",
                baseline_metrics["vehicles"],
                baseline_metrics["crew"],
                baseline_metrics["duties"],
                baseline_metrics["fragmentation_score"],
            )

        return csp_sol, vsp_sol

    except Exception as e:
        logger.error(f"Erro no post-optimization: {e}")
        return csp_sol, vsp_sol
