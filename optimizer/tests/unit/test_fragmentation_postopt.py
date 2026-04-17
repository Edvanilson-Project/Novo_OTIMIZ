import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.joint_opt import (
    _build_post_opt_metrics,
    _generate_tail_relocation_candidates,
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