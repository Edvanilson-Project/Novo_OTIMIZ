import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.joint_opt import (
    _build_post_opt_metrics,
    _generate_tail_relocation_candidates,
    _generate_split_pair_repair_candidates,
    _is_better_post_opt_candidate,
    joint_duty_vehicle_swap,
)
from src.domain.models import Block, CSPSolution, Duty, Trip, VSPSolution


def _trip(
    trip_id: int,
    start_time: int,
    duration: int,
    *,
    line_id: int = 16,
    origin: int = 1,
    dest: int = 2,
    depot_id: int = 1,
    trip_group_id: int | None = None,
    extra_deadheads: dict[int, int] | None = None,
) -> Trip:
    deadheads = {origin: 8, dest: 8, 1: 8, 2: 8, 3: 8}
    if extra_deadheads:
        deadheads.update(extra_deadheads)
    return Trip(
        id=trip_id,
        line_id=line_id,
        start_time=start_time,
        end_time=start_time + duration,
        origin_id=origin,
        destination_id=dest,
        duration=duration,
        distance_km=max(1.0, duration / 3.0),
        deadhead_times=deadheads,
        depot_id=depot_id,
        trip_group_id=trip_group_id,
    )


def _block(block_id: int, trips: list[Trip]) -> Block:
    return Block(id=block_id, trips=trips)


def _seed_duty(solver: GreedyCSP, block: Block) -> Duty:
    duty = Duty(id=1)
    solver._apply_block(
        duty,
        block,
        {
            "new_work": sum(trip.duration for trip in block.trips),
            "new_spread": block.end_time - block.start_time,
            "new_cont": sum(trip.duration for trip in block.trips),
            "daily_drive": sum(trip.duration for trip in block.trips),
            "extended_days_used": 0,
        },
    )
    return duty


def test_greedy_csp_allows_continuous_midnight_extension():
    blocks = [
        _block(1, [_trip(1, 1380, 50, origin=1, dest=2)]),
        _block(2, [_trip(2, 1455, 45, origin=2, dest=1)]),
    ]

    solution = GreedyCSP(max_shift_minutes=480, max_work_minutes=480, min_break_minutes=30).solve(blocks, [])

    assert len(solution.duties) == 1
    duty = solution.duties[0]
    assert duty.meta.get("crosses_service_day") is True
    assert solution.meta["duty_merge_diagnostics"]["duty_build"]["cross_day_extensions"] >= 1


def test_extension_diagnostics_record_service_day_vehicle_and_terminal_rejections():
    solver = GreedyCSP(operator_single_vehicle_only=True, operator_change_terminals_only=True)
    solver._extension_diagnostics = solver._empty_extension_diagnostics()

    base_block = _block(1, [_trip(1, 360, 60, origin=1, dest=2, extra_deadheads={3: 8})])
    vehicle_only_block = _block(2, [_trip(2, 430, 60, origin=2, dest=1)])
    terminal_block = _block(1, [_trip(3, 500, 60, origin=3, dest=1, depot_id=2)])
    service_day_block = _block(1, [_trip(4, 2 * 1440 + 430, 60, origin=2, dest=1)])

    duty = _seed_duty(solver, base_block)

    for candidate_block, expected_reason in [
        (vehicle_only_block, "operator_single_vehicle_only"),
        (terminal_block, "operator_change_non_terminal"),
        (service_day_block, "different_service_day"),
    ]:
        ok, reason, data = solver._can_extend(duty, candidate_block)
        solver._record_extension_attempt("duty_build", duty, candidate_block, ok, reason, data)
        assert ok is False
        assert reason == expected_reason

    diagnostics = solver._extension_diagnostics_snapshot()["duty_build"]
    assert diagnostics["reasons"]["operator_single_vehicle_only"] == 1
    assert diagnostics["reasons"]["operator_change_non_terminal"] == 1
    assert diagnostics["reasons"]["different_service_day"] == 1
    assert len(diagnostics["samples"]) == 3


def test_tail_relocation_candidate_moves_suffix_between_blocks():
    blocks = [
        _block(
            1,
            [
                _trip(1, 360, 60, origin=1, dest=2),
                _trip(2, 430, 60, origin=2, dest=1),
                _trip(3, 1320, 60, origin=1, dest=2),
                _trip(4, 1390, 60, origin=2, dest=1),
            ],
        ),
        _block(
            2,
            [
                _trip(5, 600, 60, origin=1, dest=2),
                _trip(6, 670, 60, origin=2, dest=1),
                _trip(7, 1465, 60, origin=1, dest=2),
                _trip(8, 1535, 60, origin=2, dest=1),
            ],
        ),
    ]
    vsp = VSPSolution(blocks=copy.deepcopy(blocks), algorithm="test")

    candidates, stats = _generate_tail_relocation_candidates(
        vsp,
        {"min_layover_minutes": 8, "max_vehicle_shift_minutes": 1500},
        limit=10,
        max_tail_trips=3,
    )

    assert stats["generated"] > 0
    assert any(candidate["details"]["tail_trip_ids"] == [7, 8] for candidate in candidates)


def test_split_pair_repair_candidate_reunites_boundary_pair():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 430, 60, origin=2, dest=1),
        _trip(3, 520, 60, origin=1, dest=2),
        _trip(4, 590, 60, origin=2, dest=1),
        _trip(5, 1200, 60, origin=1, dest=2, trip_group_id=700),
        _trip(6, 1260, 60, origin=2, dest=1, trip_group_id=700),
        _trip(7, 1350, 60, origin=1, dest=2),
    ]
    vsp = VSPSolution(
        blocks=[
            _block(1, [trips[0], trips[1], trips[2], trips[3], trips[4]]),
            _block(2, [trips[5], trips[6]]),
        ],
        algorithm="test",
    )

    candidates, stats = _generate_split_pair_repair_candidates(
        vsp,
        trips,
        {
            "min_layover_minutes": 0,
            "max_vehicle_shift_minutes": 960,
            "preserve_preferred_pairs": True,
            "preferred_pair_window_minutes": 120,
        },
        limit=10,
    )

    assert stats["generated"] > 0
    candidate = next(item for item in candidates if item["details"]["pair_trip_ids"] == [5, 6])
    block_trip_ids = [[trip.id for trip in block.trips] for block in candidate["vsp"].blocks]

    assert [5, 6] in block_trip_ids
    assert len(candidate["vsp"].blocks) == 3
    assert [1, 2, 3, 4] in block_trip_ids


def test_post_opt_comparator_accepts_fragmentation_gain_with_same_crew():
    vsp = VSPSolution(
        blocks=[
            _block(1, [_trip(1, 360, 60)]),
            _block(2, [_trip(2, 480, 60, origin=2, dest=1)]),
        ],
        algorithm="test",
    )
    old_csp = CSPSolution(
        duties=[
            Duty(id=1, work_time=120, spread_time=140, paid_minutes=120, meta={"source_block_ids": [1], "waiting_minutes": 20}),
            Duty(id=2, work_time=110, spread_time=130, paid_minutes=110, meta={"source_block_ids": [1], "waiting_minutes": 20}),
            Duty(id=3, work_time=100, spread_time=120, paid_minutes=100, meta={"source_block_ids": [2], "waiting_minutes": 20}),
        ],
        meta={"roster_count": 2},
    )
    new_csp = CSPSolution(
        duties=[
            Duty(id=10, work_time=230, spread_time=250, paid_minutes=230, meta={"source_block_ids": [1], "waiting_minutes": 20}),
            Duty(id=11, work_time=100, spread_time=120, paid_minutes=100, meta={"source_block_ids": [2], "waiting_minutes": 20}),
        ],
        meta={"roster_count": 2},
    )

    baseline = _build_post_opt_metrics(old_csp, vsp, min_work=240)
    candidate = _build_post_opt_metrics(new_csp, vsp, min_work=240)

    assert baseline["crew"] == candidate["crew"] == 2
    assert baseline["duties"] == 3
    assert candidate["duties"] == 2
    assert _is_better_post_opt_candidate(baseline, candidate) is True


def test_post_opt_comparator_accepts_pair_repair_with_one_extra_vehicle():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 430, 60, origin=2, dest=1),
        _trip(3, 520, 60, origin=1, dest=2),
        _trip(4, 590, 60, origin=2, dest=1),
        _trip(5, 1200, 60, origin=1, dest=2, trip_group_id=700),
        _trip(6, 1260, 60, origin=2, dest=1, trip_group_id=700),
        _trip(7, 1350, 60, origin=1, dest=2),
    ]
    current_vsp = VSPSolution(
        blocks=[
            _block(1, [trips[0], trips[1], trips[2], trips[3], trips[4]]),
            _block(2, [trips[5], trips[6]]),
        ],
        algorithm="test",
    )
    candidate_vsp = VSPSolution(
        blocks=[
            _block(1, [trips[0], trips[1], trips[2], trips[3]]),
            _block(2, [trips[4], trips[5]]),
            _block(3, [trips[6]]),
        ],
        algorithm="test",
    )

    base_csp = CSPSolution()
    baseline = _build_post_opt_metrics(
        base_csp,
        current_vsp,
        min_work=0,
        trips=trips,
        vsp_params={
            "preserve_preferred_pairs": True,
            "min_layover_minutes": 0,
            "preferred_pair_window_minutes": 120,
        },
    )
    candidate = _build_post_opt_metrics(
        base_csp,
        candidate_vsp,
        min_work=0,
        trips=trips,
        vsp_params={
            "preserve_preferred_pairs": True,
            "min_layover_minutes": 0,
            "preferred_pair_window_minutes": 120,
        },
    )

    assert baseline["vehicles"] == 2
    assert candidate["vehicles"] == 3
    assert baseline["preferred_pair_breaks"] == 1
    assert candidate["preferred_pair_breaks"] == 0
    assert _is_better_post_opt_candidate(baseline, candidate) is True


def test_post_opt_comparator_prefers_lower_trip_group_split_groups():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2, trip_group_id=701),
        _trip(2, 430, 60, origin=2, dest=1, trip_group_id=701),
    ]
    vsp = VSPSolution(
        blocks=[
            _block(1, [trips[0]]),
            _block(2, [trips[1]]),
        ],
        algorithm="test",
    )

    baseline_csp = CSPSolution(
        duties=[
            Duty(id=1, meta={"roster_id": 1, "source_block_ids": [1]}),
            Duty(id=2, meta={"roster_id": 2, "source_block_ids": [2]}),
        ],
    )
    baseline_csp.duties[0].add_task(_block(1, [trips[0]]))
    baseline_csp.duties[1].add_task(_block(2, [trips[1]]))

    candidate_csp = CSPSolution(
        duties=[
            Duty(id=10, meta={"roster_id": 1, "source_block_ids": [1]}),
            Duty(id=11, meta={"roster_id": 1, "source_block_ids": [2]}),
        ],
    )
    candidate_csp.duties[0].add_task(_block(1, [trips[0]]))
    candidate_csp.duties[1].add_task(_block(2, [trips[1]]))

    baseline = _build_post_opt_metrics(
        baseline_csp,
        vsp,
        min_work=0,
        trips=trips,
        vsp_params={
            "preserve_preferred_pairs": True,
            "min_layover_minutes": 0,
            "preferred_pair_window_minutes": 120,
        },
    )
    candidate = _build_post_opt_metrics(
        candidate_csp,
        vsp,
        min_work=0,
        trips=trips,
        vsp_params={
            "preserve_preferred_pairs": True,
            "min_layover_minutes": 0,
            "preferred_pair_window_minutes": 120,
        },
    )

    assert baseline["trip_group_split_groups"] == 1
    assert candidate["trip_group_split_groups"] == 0
    assert _is_better_post_opt_candidate(baseline, candidate) is True


def test_post_opt_comparator_rejects_trip_group_split_regression_when_integrity_is_hard():
    current = {
        "unassigned_trips": 0,
        "uncovered_blocks": 0,
        "vehicles": 2,
        "crew": 2,
        "violations": 0,
        "preferred_pair_breaks": 0,
        "fragmentation_score": 200,
        "low_utilization_duties": 0,
        "high_spread_duties": 0,
        "fragmented_duties": 0,
        "short_connection_total": 0,
        "max_idle_time": 0,
        "trip_group_split_groups": 0,
    }
    candidate = {
        "unassigned_trips": 0,
        "uncovered_blocks": 0,
        "vehicles": 2,
        "crew": 1,
        "violations": 0,
        "preferred_pair_breaks": 0,
        "fragmentation_score": 50,
        "low_utilization_duties": 0,
        "high_spread_duties": 0,
        "fragmented_duties": 0,
        "short_connection_total": 0,
        "max_idle_time": 0,
        "trip_group_split_groups": 1,
    }

    assert _is_better_post_opt_candidate(current, candidate) is True
    assert _is_better_post_opt_candidate(
        current,
        candidate,
        enforce_trip_group_integrity=True,
    ) is False


def test_joint_post_opt_prefers_pair_repair_when_tail_move_is_too_long():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 430, 60, origin=2, dest=1),
        _trip(3, 520, 60, origin=1, dest=2),
        _trip(4, 590, 60, origin=2, dest=1),
        _trip(5, 1200, 60, origin=1, dest=2, trip_group_id=700),
        _trip(6, 1260, 60, origin=2, dest=1, trip_group_id=700),
        _trip(7, 1350, 60, origin=1, dest=2),
    ]
    blocks = [
        _block(1, [trips[0], trips[1], trips[2], trips[3], trips[4]]),
        _block(2, [trips[5], trips[6]]),
    ]
    vsp = VSPSolution(blocks=copy.deepcopy(blocks), algorithm="test", meta={"max_vehicle_shift_minutes": 960, "min_layover_minutes": 0})
    csp = GreedyCSP(max_shift_minutes=560, max_work_minutes=480, min_break_minutes=30, inter_shift_rest_minutes=660).solve(copy.deepcopy(blocks), trips)

    new_csp, new_vsp = joint_duty_vehicle_swap(
        csp,
        vsp,
        trips,
        cct_params={"max_shift_minutes": 560, "max_work_minutes": 480, "min_break_minutes": 30, "inter_shift_rest_minutes": 660},
        kwargs={
            "vsp_params": {
                "min_layover_minutes": 0,
                "max_vehicle_shift_minutes": 960,
                "preserve_preferred_pairs": True,
                "preferred_pair_window_minutes": 120,
                "enable_pair_repair_postopt": True,
            },
        },
    )

    assert new_csp.meta["post_optimization"]["selected_phase"] in {"pair_repair", "joint_swap"}
    assert new_csp.meta["post_optimization"]["outcome"] == "accepted_improvement"
    assert new_csp.meta["post_optimization"]["selected_metrics"]["preferred_pair_breaks"] == 0


def test_joint_post_opt_accepts_tail_relocation_that_reduces_fragmentation():
    params = {
        "max_shift_minutes": 560,
        "max_work_minutes": 480,
        "min_break_minutes": 30,
        "inter_shift_rest_minutes": 660,
        "operator_single_vehicle_only": True,
        "min_work_minutes": 240,
    }
    vsp_meta = {"max_vehicle_shift_minutes": 1500, "min_layover_minutes": 8}
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 430, 60, origin=2, dest=1),
        _trip(3, 1320, 60, origin=1, dest=2),
        _trip(4, 1390, 60, origin=2, dest=1),
        _trip(5, 600, 60, origin=1, dest=2),
        _trip(6, 670, 60, origin=2, dest=1),
        _trip(7, 1465, 60, origin=1, dest=2),
        _trip(8, 1535, 60, origin=2, dest=1),
    ]
    blocks = [
        _block(1, [trips[0], trips[1], trips[2], trips[3]]),
        _block(2, [trips[4], trips[5], trips[6], trips[7]]),
    ]
    vsp = VSPSolution(blocks=copy.deepcopy(blocks), algorithm="test", meta=dict(vsp_meta))
    csp = GreedyCSP(**params).solve(copy.deepcopy(blocks), trips)

    new_csp, new_vsp = joint_duty_vehicle_swap(
        csp,
        vsp,
        trips,
        cct_params=params,
        kwargs=params,
    )

    assert new_csp.num_crew == csp.num_crew
    assert len(new_csp.duties) < len(csp.duties)
    assert new_csp.meta["post_optimization"]["selected_phase"] == "tail_relocation"
    assert new_csp.meta["post_optimization"]["selected_candidate"]["tail_trip_ids"] == [7, 8]
    assert any([int(trip.id) for trip in block.trips] == [1, 2, 3, 4, 7, 8] for block in new_vsp.blocks)


def test_joint_post_opt_records_meta_when_skipped_for_single_block():
    block = _block(1, [_trip(1, 360, 60, origin=1, dest=2)])
    vsp = VSPSolution(blocks=[copy.deepcopy(block)], algorithm="test")
    csp = GreedyCSP().solve([copy.deepcopy(block)], block.trips)

    new_csp, new_vsp = joint_duty_vehicle_swap(
        csp,
        vsp,
        block.trips,
        cct_params={},
        kwargs={},
    )

    assert new_csp.meta["post_optimization"]["accepted"] is False
    assert new_csp.meta["post_optimization"]["outcome"] == "skipped_single_block"
    assert new_vsp.meta["post_optimization"]["outcome"] == "skipped_single_block"


def test_greedy_csp_quality_penalty_is_higher_for_low_utilization_duty():
    solver = GreedyCSP(
        duty_utilization_target=0.30,
        duty_max_spread_soft_minutes=720,
        duty_max_idle_soft_minutes=180,
        duty_fragmentation_soft_limit=2,
        short_connection_threshold_minutes=15,
    )

    compact_tasks = [
        _block(1, [_trip(1, 360, 60, origin=1, dest=2)]),
        _block(2, [_trip(2, 430, 60, origin=2, dest=1)]),
    ]
    stretched_tasks = [
        _block(3, [_trip(3, 360, 60, origin=1, dest=2)]),
        _block(4, [_trip(4, 900, 60, origin=2, dest=1)]),
    ]

    compact_metrics = solver._build_duty_quality_metrics(compact_tasks, projected_work=120)
    stretched_metrics = solver._build_duty_quality_metrics(stretched_tasks, projected_work=120)

    assert solver._operational_quality_penalty(stretched_metrics) > solver._operational_quality_penalty(compact_metrics)
    assert stretched_metrics["utilization"] < compact_metrics["utilization"]
    assert stretched_metrics["max_idle_time"] > compact_metrics["max_idle_time"]


def test_greedy_csp_exposes_quality_summary_and_per_duty_metrics():
    blocks = [
        _block(1, [_trip(1, 360, 60, origin=1, dest=2)]),
        _block(2, [_trip(2, 430, 60, origin=2, dest=1)]),
        _block(3, [_trip(3, 900, 60, origin=1, dest=2)]),
    ]

    solution = GreedyCSP(
        max_shift_minutes=960,
        duty_utilization_target=0.30,
        duty_max_spread_soft_minutes=720,
        duty_max_idle_soft_minutes=180,
    ).solve(blocks, [])

    quality_summary = solution.meta.get("quality_summary") or {}
    assert quality_summary.get("duties") == len(solution.duties)
    assert "avg_utilization" in quality_summary
    assert "low_utilization_duties" in quality_summary
    assert all("quality_metrics" in duty.meta for duty in solution.duties)


@pytest.mark.skip(reason=(
    "Sprint F (operational_time_service:248) corrigiu CCT: mandatory_rest_required agora "
    "exige max_continuous_drive > mandatory_break_after (não mais productive_minutes). "
    "Esta condição é HARD-REJEITADA pelo greedy._can_extend (greedy.py:1019), tornando "
    "este cenário não-construível via _rebuild_duty_from_tasks com os mesmos parâmetros. "
    "A feature `_soft_issue_reassignment_postopt` permanece útil em código defensivo "
    "(ex.: pós relief_reassignment que pode introduzir violações), mas não é mais "
    "alcançável via test fixture com greedy strict. Para reativar, precisaria mockear "
    "o solver ou construir duty diretamente bypass de finalize_selected_duties."
))
def test_soft_issue_postopt_can_move_internal_task_to_fix_mandatory_rest_missing():
    solver = GreedyCSP(
        apply_cct=True,
        operator_change_terminals_only=False,
        min_break_minutes=15,
        meal_break_minutes=30,
        mandatory_break_after_minutes=240,
        min_layover_minutes=0,
        max_shift_minutes=900,
        max_work_minutes=480,
        inter_shift_rest_minutes=660,
    )

    source_tasks = [
        _block(1, [_trip(1, 360, 60, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(2, [_trip(2, 440, 60, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(3, [_trip(3, 520, 60, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(4, [_trip(4, 600, 42, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(5, [_trip(5, 673, 22, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(6, [_trip(6, 708, 66, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(7, [_trip(7, 800, 60, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
    ]
    target_task = _block(8, [_trip(8, 790, 60, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})])
    source_duty, reason = solver._rebuild_duty_from_tasks(source_tasks, 1)
    target_duty, target_reason = solver._rebuild_duty_from_tasks([target_task], 2)

    assert reason == ""
    assert target_reason == ""

    baseline_solution = solver.finalize_selected_duties(
        [copy.deepcopy(source_duty), copy.deepcopy(target_duty)],
        original_blocks=[*source_tasks, target_task],
    )
    baseline_metrics = solver._build_relief_reassignment_metrics(baseline_solution)
    baseline_source_metrics = solver._build_operational_semantic_metrics(
        source_duty.tasks,
        projected_work=int(source_duty.work_time),
        projected_spread=int(source_duty.spread_time),
        duty_id=int(source_duty.id),
    )

    assert baseline_source_metrics["mandatory_rest_missing"] is True
    assert baseline_metrics["mandatory_rest_missing"] == 1
    assert baseline_metrics["crew"] == 2

    repaired_duties, audit = solver._soft_issue_reassignment_postopt(
        [source_duty, target_duty],
        original_blocks=[*source_tasks, target_task],
    )

    assert audit["improved"] is True
    assert audit["baseline_metrics"]["mandatory_rest_missing"] == 1
    assert audit["final_metrics"]["mandatory_rest_missing"] == 0
    assert audit["final_metrics"]["crew"] == 2
    assert audit["accepted"] == 1
    assert "mandatory_rest_missing_repair" in audit["accepted_moves"][0]["reasons"]

    repaired_by_id = {int(duty.id): duty for duty in repaired_duties}
    source_after = repaired_by_id[1]
    target_after = repaired_by_id[2]
    source_after_metrics = solver._build_operational_semantic_metrics(
        source_after.tasks,
        projected_work=int(source_after.work_time),
        projected_spread=int(source_after.spread_time),
        duty_id=int(source_after.id),
    )

    assert source_after_metrics["mandatory_rest_missing"] is False
    assert [trip.id for task in source_after.tasks for trip in task.trips] == [1, 2, 3, 4, 5, 7]
    assert [trip.id for task in target_after.tasks for trip in task.trips] == [6, 8]
    assert sorted(
        trip.id
        for duty in repaired_duties
        for task in duty.tasks
        for trip in task.trips
    ) == [1, 2, 3, 4, 5, 6, 7, 8]


@pytest.mark.skip(reason=(
    "Mesma raiz do test acima (Sprint F): mandatory_rest_required agora exige max_continuous_drive "
    "> mandatory_break_after, condição que o greedy._can_extend hard-rejeita. Setup viável "
    "exigiria mock ou construção bypass de finalize."
))
def test_soft_issue_postopt_can_create_dedicated_duty_to_fix_mandatory_rest_missing():
    solver = GreedyCSP(
        apply_cct=True,
        operator_change_terminals_only=False,
        min_break_minutes=15,
        meal_break_minutes=30,
        mandatory_break_after_minutes=240,
        min_layover_minutes=0,
        max_shift_minutes=900,
        max_work_minutes=480,
        inter_shift_rest_minutes=660,
        soft_issue_reassignment_max_passes=1,
    )

    source_tasks = [
        _block(1, [_trip(1, 360, 60, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(2, [_trip(2, 440, 60, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(3, [_trip(3, 520, 60, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(4, [_trip(4, 600, 42, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(5, [_trip(5, 673, 22, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(6, [_trip(6, 708, 66, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
        _block(7, [_trip(7, 800, 60, origin=2, dest=1, extra_deadheads={1: 0, 2: 0, 3: 0})]),
    ]
    blocking_target = _block(8, [_trip(8, 720, 60, origin=1, dest=2, extra_deadheads={1: 0, 2: 0, 3: 0})])
    source_duty, reason = solver._rebuild_duty_from_tasks(source_tasks, 1)
    target_duty, target_reason = solver._rebuild_duty_from_tasks([blocking_target], 2)

    assert reason == ""
    assert target_reason == ""

    repaired_duties, audit = solver._soft_issue_reassignment_postopt(
        [source_duty, target_duty],
        original_blocks=[*source_tasks, blocking_target],
    )

    assert audit["accepted"] == 1
    assert audit["improved"] is True
    assert audit["baseline_metrics"]["mandatory_rest_missing"] == 1
    assert audit["final_metrics"]["mandatory_rest_missing"] == 0
    assert audit["final_metrics"]["violations"] == 0
    assert audit["final_metrics"]["crew"] == 3
    assert audit["accepted_moves"][0]["mode"] == "dedicated"
    assert "mandatory_rest_missing_repair" in audit["accepted_moves"][0]["reasons"]

    repaired_by_id = {int(duty.id): duty for duty in repaired_duties}
    source_after = repaired_by_id[1]
    target_after = repaired_by_id[2]
    dedicated_after = next(duty for duty in repaired_duties if int(duty.id) not in (1, 2))
    source_after_metrics = solver._build_operational_semantic_metrics(
        source_after.tasks,
        projected_work=int(source_after.work_time),
        projected_spread=int(source_after.spread_time),
        duty_id=int(source_after.id),
    )

    assert source_after_metrics["mandatory_rest_missing"] is False
    assert [trip.id for task in source_after.tasks for trip in task.trips] == [1, 2, 3, 4, 5, 7]
    assert [trip.id for task in target_after.tasks for trip in task.trips] == [8]
    assert [trip.id for task in dedicated_after.tasks for trip in task.trips] == [6]
    assert sorted(
        trip.id
        for duty in repaired_duties
        for task in duty.tasks
        for trip in task.trips
    ) == [1, 2, 3, 4, 5, 6, 7, 8]
