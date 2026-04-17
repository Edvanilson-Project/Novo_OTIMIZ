import logging
from typing import List, Dict, Any, Optional, Tuple
import copy
from .evaluator import CostEvaluator
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
                meta=dict(vsp_sol.meta or {}),
            )
            candidates.append(refined_vsp)

    return candidates


def _vsp_signature(vsp_sol: VSPSolution) -> Tuple[Tuple[int, ...], ...]:
    ordered_blocks = sorted(vsp_sol.blocks, key=lambda block: (block.start_time, block.id))
    return tuple(tuple(int(trip.id) for trip in block.trips) for block in ordered_blocks)


def _build_post_opt_metrics(csp_sol: CSPSolution, vsp_sol: VSPSolution, min_work: int) -> Dict[str, Any]:
    duties = csp_sol.duties or []
    short_duties = sum(1 for duty in duties if min_work > 0 and duty.work_time < min_work)
    split_duties = 0
    vehicle_switches = 0
    waiting_minutes = 0
    unpaid_break_minutes = 0
    cross_day_duties = 0

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
    }


def _is_better_post_opt_candidate(current: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    if candidate["unassigned_trips"] > current["unassigned_trips"]:
        return False
    if candidate["uncovered_blocks"] > current["uncovered_blocks"]:
        return False
    if candidate["violations"] > current["violations"]:
        return False
    if candidate["vehicles"] > current["vehicles"]:
        return False
    if candidate["crew"] > current["crew"]:
        return False

    current_rank = (
        current["violations"],
        current["vehicles"],
        current["crew"],
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
    last_trip = recipient.trips[-1]
    first_suffix_trip = suffix[0]
    gap = first_suffix_trip.start_time - last_trip.end_time

    if gap < 0:
        return False, "overlap", {"gap": gap}

    deadhead = int(last_trip.deadhead_times.get(first_suffix_trip.origin_id, 0))
    transfer_needed = max(min_layover, deadhead)
    if gap < transfer_needed:
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
            baseline_metrics = _build_post_opt_metrics(csp_sol, vsp_sol, 0)
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

        vsp_params = dict(kwargs.get("vsp_params", {})) if kwargs.get("vsp_params") else (dict(vsp_sol.meta) if vsp_sol.meta else {})
        solver_kwargs = {key: value for key, value in kwargs.items() if key != "vsp_params"}
        min_work = int(solver_kwargs.get("min_work_minutes", cct_params.get("min_work_minutes", 0)) or 0)
        original_vehicles = len(vsp_sol.blocks)
        original_crew = csp_sol.num_crew
        baseline_metrics = _build_post_opt_metrics(csp_sol, vsp_sol, min_work)

        # ── Fase 1: Merge de blocos VSP ──────────────────────────────────────
        merged_vsp = _try_merge_vsp_blocks(vsp_sol, vsp_params)
        vsp_changed = len(merged_vsp.blocks) < original_vehicles

        # ── Fase 2: Swap de trips entre blocos (multi-pass) ──────────────────
        max_unpaid_break = int(cct_params.get("max_unpaid_break_minutes", cct_params.get("max_unpaid_break", 180)))
        max_vehicle_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960))

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

        best_csp = csp_sol
        best_vsp = vsp_sol
        best_metrics = baseline_metrics
        best_candidate: Optional[Dict[str, Any]] = None
        evaluated_signatures = {_vsp_signature(vsp_sol)}

        for candidate in candidate_vsps:
            candidate_vsp = candidate["vsp"]
            signature = _vsp_signature(candidate_vsp)
            if signature in evaluated_signatures:
                continue
            evaluated_signatures.add(signature)

            csp_candidate = GreedyCSP(vsp_params=vsp_params, **solver_kwargs).solve(candidate_vsp.blocks, trips)
            candidate_metrics = _build_post_opt_metrics(csp_candidate, candidate_vsp, min_work)
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
                fb_metrics = _build_post_opt_metrics(fb_csp, fb_vsp, min_work)
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
