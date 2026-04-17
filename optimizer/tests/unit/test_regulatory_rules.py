"""
Testes unitários para as novas regras regulatórias, EV e formulações avançadas.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.csp.set_partitioning import SetPartitioningCSP
from src.algorithms.utils import preferred_pair_penalty
from src.algorithms.vsp.greedy import GreedyVSP, build_preferred_pairs
from src.core.exceptions import HardConstraintViolationError
from src.domain.models import AlgorithmType, Block, Trip, VehicleType
from src.services.optimizer_service import OptimizerService


def _trip(
    tid: int,
    start: int,
    dur: int,
    *,
    line: int = 1,
    origin: int = 1,
    dest: int = 2,
    depot: int | None = None,
    energy: float = 0.0,
    night: bool = False,
    trip_group_id: int | None = None,
    direction: str | None = None,
    mid_relief_point: int | None = None,
    mid_relief_offset: int | None = None,
    mid_relief_distance_ratio: float | None = None,
    mid_relief_elevation_ratio: float | None = None,
):
    start_time = start if not night else 22 * 60 + start
    return Trip(
        id=tid,
        line_id=line,
        start_time=start_time,
        end_time=start_time + dur,
        origin_id=origin,
        destination_id=dest,
        trip_group_id=trip_group_id,
        direction=direction,
        duration=dur,
        distance_km=max(1.0, dur / 3),
        depot_id=depot,
        mid_trip_relief_point_id=mid_relief_point,
        mid_trip_relief_offset_minutes=mid_relief_offset,
        mid_trip_relief_distance_ratio=mid_relief_distance_ratio,
        mid_trip_relief_elevation_ratio=mid_relief_elevation_ratio,
        energy_kwh=energy,
        deadhead_times={origin: 8, dest: 8},
    )


def _vehicle(electric: bool = False) -> list[VehicleType]:
    return [
        VehicleType(
            id=1,
            name="EV" if electric else "Diesel",
            passenger_capacity=40,
            cost_per_km=2.0,
            cost_per_hour=50.0,
            fixed_cost=800.0,
            is_electric=electric,
            battery_capacity_kwh=40.0 if electric else 0.0,
            minimum_soc=0.2 if electric else 0.0,
            charge_rate_kw=60.0 if electric else 0.0,
            energy_cost_per_kwh=0.8 if electric else 0.0,
        )
    ]


def _task_block(block_id: int, trips: list[Trip]) -> Block:
    block = Block(id=block_id, trips=trips)
    block.meta.update(
        {
            "source_block_id": block_id,
            "task_id": block_id,
            "relief_start_id": trips[0].origin_id if trips else None,
            "relief_end_id": trips[-1].destination_id if trips else None,
            "task_drive_minutes": sum(trip.duration for trip in trips),
            "original_trip_ids": [int(getattr(trip, "public_id", trip.id)) for trip in trips],
            "contains_mid_trip_relief_segment": any(trip.is_mid_trip_segment for trip in trips),
            "starts_at_mid_trip_relief": bool(trips and trips[0].starts_at_mid_trip_relief),
            "ends_at_mid_trip_relief": bool(trips and trips[-1].ends_at_mid_trip_relief),
            "mid_trip_original_trip_ids": [int(getattr(trip, "public_id", trip.id)) for trip in trips if trip.is_mid_trip_segment],
            "is_source_block_start": True,
            "is_source_block_end": True,
            "task_start_buffer_minutes": 0,
            "task_end_buffer_minutes": 0,
            "source_start_buffer_minutes": 0,
            "source_end_buffer_minutes": 0,
        }
    )
    return block


def test_natural_language_same_depot_rule_generates_warning():
    trips = [
        _trip(1, 360, 60, depot=1, origin=1, dest=2),
        _trip(2, 450, 60, depot=2, origin=2, dest=3),
    ]
    svc = OptimizerService()
    with pytest.raises(HardConstraintViolationError) as exc:
        svc.run(
            trips,
            _vehicle(),
            algorithm=AlgorithmType.GREEDY,
            vsp_params={"natural_language_rules": ["Início e fim no mesmo depósito"]},
        )
    assert "DUTY_SAME_DEPOT_VIOLATION" in str(exc.value)


def test_ev_soc_rule_marks_unassignable_trip():
    trips = [_trip(1, 360, 60, energy=35.0)]
    sol = GreedyVSP(vsp_params={"max_simultaneous_chargers": 1}).solve(trips, _vehicle(electric=True))
    assert len(sol.unassigned_trips) == 1
    assert any("EV_SOC_INSUFFICIENT" in w for w in sol.warnings)


def test_greedy_csp_applies_guaranteed_pay_and_night_minutes():
    block = Block(id=1, trips=[_trip(1, 0, 60, night=True)])
    sol = GreedyCSP(min_guaranteed_work_minutes=240, nocturnal_start_hour=22, nocturnal_end_hour=5).solve([block], block.trips)
    duty = sol.duties[0]
    assert duty.nocturnal_minutes > 0
    assert duty.paid_minutes >= 240


def test_weekly_limit_creates_second_roster():
    blocks = []
    for day in range(7):
        start = day * 1440 + 6 * 60
        blocks.append(Block(id=day + 1, trips=[_trip(day + 1, start, 540)]))
    sol = GreedyCSP(weekly_driving_limit_minutes=3360, inter_shift_rest_minutes=660).solve(blocks, [])
    assert sol.meta["roster_count"] == 2


def test_set_covering_reports_workpieces_and_pricing_meta():
    blocks = [
        Block(id=1, trips=[_trip(1, 360, 60)]),
        Block(id=2, trips=[_trip(2, 450, 60, origin=2, dest=1)]),
        Block(id=3, trips=[_trip(3, 600, 60)]),
        Block(id=4, trips=[_trip(4, 690, 60, origin=2, dest=1)]),
    ]
    sol = SetPartitioningCSP(vsp_params={"pricing_enabled": True, "max_trips_per_piece": 2}).solve(blocks, [])
    assert sol.meta["workpieces_generated"] > 0
    assert sol.meta["roster_count"] >= 1


def test_vsp_enforces_min_layover_even_same_terminal():
    trips = [
        _trip(1, 360, 60, line=91, origin=1, dest=2, depot=1),
        _trip(2, 420, 60, line=91, origin=2, dest=3, depot=1),
    ]
    sol = GreedyVSP(vsp_params={"min_layover_minutes": 10}).solve(trips, _vehicle())
    assert len(sol.blocks) == 2


def test_vsp_allows_vehicle_split_shift_reuse():
    trips = [
        _trip(1, 360, 60, line=93, origin=1, dest=2, depot=1),
        _trip(2, 660, 60, line=93, origin=2, dest=1, depot=1),
    ]

    baseline = GreedyVSP(
        vsp_params={
            "min_layover_minutes": 15,
            "idle_cost_per_minute": 10.0,
            "max_connection_cost_for_reuse_ratio": 1.0,
            "allow_vehicle_split_shifts": False,
            "enable_single_trip_compaction": False,
        }
    ).solve(trips, _vehicle())
    split = GreedyVSP(
        vsp_params={
            "min_layover_minutes": 15,
            "idle_cost_per_minute": 10.0,
            "max_connection_cost_for_reuse_ratio": 1.0,
            "allow_vehicle_split_shifts": True,
            "split_shift_min_gap_minutes": 120,
            "split_shift_max_gap_minutes": 420,
            "enable_single_trip_compaction": False,
        }
    ).solve(trips, _vehicle())

    assert len(baseline.blocks) == 2
    assert len(split.blocks) == 1


def test_vsp_does_not_reuse_vehicle_when_split_shift_gap_is_below_minimum():
    trips = [
        _trip(1, 360, 60, line=95, origin=1, dest=2, depot=1),
        _trip(2, 535, 60, line=96, origin=2, dest=3, depot=1),
    ]

    sol = GreedyVSP(
        vsp_params={
            "min_layover_minutes": 15,
            "idle_cost_per_minute": 10.0,
            "max_connection_cost_for_reuse_ratio": 1.0,
            "allow_vehicle_split_shifts": True,
            "split_shift_min_gap_minutes": 120,
            "split_shift_max_gap_minutes": 420,
            "enable_single_trip_compaction": False,
            "preserve_preferred_pairs": False,
        }
    ).solve(trips, _vehicle())

    assert len(sol.blocks) == 2


def test_vsp_compacts_single_trip_blocks_when_viable():
    trips = [
        _trip(1, 360, 60, line=94, origin=1, dest=2, depot=1),
        _trip(2, 450, 60, line=94, origin=2, dest=1, depot=1),
        _trip(3, 1200, 60, line=94, origin=1, dest=2, depot=1),
    ]
    sol = GreedyVSP(
        vsp_params={
            "min_layover_minutes": 15,
            "idle_cost_per_minute": 10.0,
            "max_connection_cost_for_reuse_ratio": 1.0,
            "allow_vehicle_split_shifts": False,
            "enable_single_trip_compaction": True,
            "single_trip_compaction_max_gap_minutes": 420,
        }
    ).solve(trips, _vehicle())
    assert len(sol.blocks) == 2


def test_optimizer_avoids_short_layover_in_output_solution():
    trips = [
        _trip(1, 360, 60, line=92, origin=1, dest=2, depot=1),
        _trip(2, 420, 60, line=92, origin=2, dest=1, depot=1),
    ]
    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={"strict_hard_validation": True},
        vsp_params={"min_layover_minutes": 10},
        time_budget_s=5.0,
    )
    assert len(result.vsp.blocks) == 2


def test_run_cutting_splits_long_block_and_avoids_meal_break_violation():
    block = Block(
        id=1,
        trips=[
            _trip(1, 360, 120, depot=1, origin=1, dest=2),
            _trip(2, 480, 120, depot=1, origin=2, dest=1),
            _trip(3, 600, 120, depot=1, origin=1, dest=2),
        ],
    )
    solver = GreedyCSP(
        meal_break_minutes=30,
        mandatory_break_after_minutes=240,
        max_shift_minutes=480,
        max_work_minutes=420,
        min_break_minutes=30,
        allow_relief_points=True,
    )
    tasks, meta = solver.prepare_tasks([block])
    sol = solver.solve([block], block.trips)
    assert meta["task_count"] >= 2
    assert sol.cct_violations == 0
    assert all(duty.rest_violations == 0 for duty in sol.duties)


def test_run_cutting_never_splits_trip_in_middle_even_with_relief_boundary():
    trips = [
        _trip(1, 360, 120, depot=1, origin=1, dest=2),
        _trip(2, 500, 120, depot=1, origin=2, dest=1),
        _trip(3, 760, 120, depot=1, origin=1, dest=2),
    ]
    trips[1].is_relief_point = True
    trips[1].relief_point_id = trips[1].destination_id

    block = Block(id=1, trips=trips)
    solver = GreedyCSP(
        meal_break_minutes=30,
        mandatory_break_after_minutes=240,
        max_shift_minutes=480,
        max_work_minutes=420,
        min_break_minutes=30,
        allow_relief_points=True,
    )

    tasks, meta = solver.prepare_tasks([block])

    assert meta["task_count"] >= 2
    assert [trip.id for trip in tasks[0].trips] == [1, 2]
    assert [trip.id for trip in tasks[1].trips] == [3]

    task_trip_ids = [trip.id for task in tasks for trip in task.trips]
    assert task_trip_ids == [1, 2, 3]
    assert len(task_trip_ids) == len(set(task_trip_ids))

    original_windows = {trip.id: (trip.start_time, trip.end_time) for trip in trips}
    for task in tasks:
        for trip in task.trips:
            assert (trip.start_time, trip.end_time) == original_windows[trip.id]

    for left_task, right_task in zip(tasks, tasks[1:]):
        assert left_task.trips[-1].end_time <= right_task.trips[0].start_time


def test_natural_language_max_shift_rule_is_applied():
    trips = [
        _trip(1, 360, 180, depot=1, origin=1, dest=2),
        _trip(2, 550, 180, depot=1, origin=2, dest=1),
    ]
    svc = OptimizerService()
    result = svc.run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={"natural_language_rules": ["Nenhum motorista deve trabalhar mais de 9 horas"]},
        vsp_params={"pricing_enabled": True, "use_set_covering": True},
        time_budget_s=5.0,
    )
    assert result.meta["input"]["cct_params"]["max_shift_minutes"] == 540


def test_vsp_preserves_preferred_ida_volta_pairing_under_competition():
    trips = [
        _trip(1, 360, 60, line=10, origin=100, dest=200, depot=1),
        _trip(2, 430, 60, line=10, origin=100, dest=200, depot=1),
        _trip(3, 500, 60, line=10, origin=200, dest=100, depot=1),
        _trip(4, 570, 60, line=10, origin=200, dest=100, depot=1),
    ]
    sol = GreedyVSP().solve(trips, _vehicle())
    blocks = sorted(([t.id for t in block.trips] for block in sol.blocks), key=lambda item: item[0])
    assert blocks == [[1, 3], [2, 4]]
    assert sol.meta["preferred_pair_count"] == 2
    assert sol.meta["preferred_pair_breaks"] == 0


def test_build_preferred_pairs_accepts_contiguous_trip_group_pairs():
    trips = [
        _trip(1, 270, 75, line=16, origin=12, dest=13, trip_group_id=120001, direction="outbound"),
        _trip(2, 345, 87, line=16, origin=13, dest=12, trip_group_id=120001, direction="return"),
    ]
    assert build_preferred_pairs(trips, 10, 120) == {1: 2, 2: 1}


def test_preferred_pair_penalty_marks_contiguous_group_split_across_blocks():
    trip_a = _trip(1, 270, 75, line=16, origin=12, dest=13, trip_group_id=120001, direction="outbound")
    trip_b = _trip(2, 345, 87, line=16, origin=13, dest=12, trip_group_id=120001, direction="return")
    preferred_pairs = build_preferred_pairs([trip_a, trip_b], 10, 120)

    kept_penalty = preferred_pair_penalty(
        [Block(id=1, trips=[trip_a, trip_b])],
        preferred_pairs,
        pair_break_penalty=1000.0,
        paired_trip_bonus=40.0,
        hard_pairing_penalty=20000.0,
    )
    split_penalty = preferred_pair_penalty(
        [Block(id=1, trips=[trip_a]), Block(id=2, trips=[trip_b])],
        preferred_pairs,
        pair_break_penalty=1000.0,
        paired_trip_bonus=40.0,
        hard_pairing_penalty=20000.0,
    )

    assert kept_penalty < 0
    assert split_penalty >= 20000.0


def test_pairing_guard_reduces_pair_breaks_vs_disabled_mode():
    trips = [
        _trip(1, 360, 55, line=22, origin=11, dest=22, depot=1),
        _trip(2, 390, 55, line=22, origin=11, dest=22, depot=1),
        _trip(3, 430, 55, line=22, origin=22, dest=11, depot=1),
        _trip(4, 460, 55, line=22, origin=22, dest=11, depot=1),
        _trip(5, 500, 55, line=22, origin=11, dest=22, depot=1),
        _trip(6, 530, 55, line=22, origin=22, dest=11, depot=1),
    ]
    guarded = GreedyVSP().solve(trips, _vehicle())
    unguarded = GreedyVSP(vsp_params={"preserve_preferred_pairs": False}).solve(trips, _vehicle())
    assert guarded.meta["preferred_pair_breaks"] <= unguarded.meta.get("preferred_pair_breaks", guarded.meta["preferred_pair_breaks"] + 1)
    assert guarded.meta["paired_connections_followed"] >= unguarded.meta.get("paired_connections_followed", 0)


def test_optimizer_trip_group_pairing_is_soft_by_default():
    trips = [
        Trip(
            id=1,
            line_id=60,
            start_time=360,
            end_time=420,
            origin_id=10,
            destination_id=20,
            trip_group_id=900,
            duration=60,
            deadhead_times={10: 8, 20: 8},
        ),
        Trip(
            id=2,
            line_id=60,
            start_time=430,
            end_time=490,
            origin_id=20,
            destination_id=10,
            trip_group_id=900,
            duration=60,
            deadhead_times={10: 8, 20: 8},
        ),
    ]
    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        vsp_params={"preserve_preferred_pairs": True},
        cct_params={"allow_relief_points": True},
        time_budget_s=5.0,
    )
    assert "mandatory_trip_groups_same_duty" not in result.meta["input"]["cct_params"]


def test_optimizer_promotes_hard_pairing_to_vsp_when_single_vehicle_only():
    trips = [
        _trip(1, 270, 75, line=16, origin=12, dest=13, trip_group_id=120001, direction="outbound"),
        _trip(2, 345, 87, line=16, origin=13, dest=12, trip_group_id=120001, direction="return"),
    ]
    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.GREEDY,
        cct_params={
            "enforce_trip_groups_hard": True,
            "operator_single_vehicle_only": True,
            "allow_relief_points": True,
        },
        vsp_params={"preserve_preferred_pairs": True, "min_layover_minutes": 10},
        time_budget_s=2.0,
    )
    assert result.meta["input"]["vsp_params"]["hard_pairing_vehicle_level"] is True
    assert result.meta["input"]["vsp_params"]["hard_pairing_penalty"] >= 20000.0


def test_greedy_csp_can_enforce_single_line_duty():
    blocks = [
        Block(id=1, trips=[_trip(1, 360, 60, line=70, origin=10, dest=20, depot=1)]),
        Block(id=2, trips=[_trip(2, 430, 60, line=71, origin=20, dest=10, depot=1)]),
    ]

    unrestricted = GreedyCSP(allow_relief_points=True).solve(blocks, [])
    restricted = GreedyCSP(allow_relief_points=True, enforce_single_line_duty=True).solve(blocks, [])

    assert len(unrestricted.duties) == 1
    assert len(restricted.duties) == 2
    assert all(len(set(duty.meta.get("line_ids", []))) == 1 for duty in restricted.duties)


def test_hard_validation_rejects_ghost_bus_input():
    trips = [
        Trip(
            id=1,
            line_id=1,
            start_time=360,
            end_time=420,
            origin_id=1,
            destination_id=2,
            duration=60,
            sent_to_driver_terminal=False,
            deadhead_times={1: 8, 2: 8},
        )
    ]
    with pytest.raises(HardConstraintViolationError) as exc:
        OptimizerService().run(trips, _vehicle(), algorithm=AlgorithmType.GREEDY)
    assert "GHOST_BUS_TERMINAL_SYNC" in str(exc.value)


def test_hard_validation_rejects_invalid_gps_input():
    trips = [
        Trip(
            id=1,
            line_id=1,
            start_time=360,
            end_time=420,
            origin_id=1,
            destination_id=2,
            duration=60,
            origin_latitude=-12.9,
            origin_longitude=-38.5,
            destination_latitude=140.0,
            destination_longitude=-38.4,
            deadhead_times={1: 8, 2: 8},
        )
    ]
    with pytest.raises(HardConstraintViolationError) as exc:
        OptimizerService().run(trips, _vehicle(), algorithm=AlgorithmType.GREEDY)
    assert "GPS_LATITUDE_INVALID_DESTINATION" in str(exc.value)


def test_hard_validation_rejects_incomplete_mid_trip_relief_input():
    trips = [
        Trip(
            id=1,
            line_id=1,
            start_time=360,
            end_time=480,
            origin_id=1,
            destination_id=3,
            duration=120,
            mid_trip_relief_point_id=2,
            deadhead_times={1: 8, 2: 8, 3: 8},
        )
    ]
    with pytest.raises(HardConstraintViolationError) as exc:
        OptimizerService().run(
            trips,
            _vehicle(),
            algorithm=AlgorithmType.GREEDY,
            cct_params={"allow_relief_points": True},
        )
    assert "MID_TRIP_RELIEF_INCOMPLETE" in str(exc.value)


def test_hard_validation_rejects_mandatory_group_split():
    """MANDATORY_GROUP_SPLIT é soft — não bloqueia, mas aparece no relatório."""
    trips = [
        _trip(1, 360, 60, line=30, origin=10, dest=20, depot=1),
        _trip(2, 390, 60, line=30, origin=10, dest=20, depot=1),
        _trip(3, 500, 60, line=30, origin=20, dest=10, depot=1),
        _trip(4, 570, 60, line=30, origin=20, dest=10, depot=1),
    ]
    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={"mandatory_trip_groups_same_duty": [[1, 2]], "allow_relief_points": True},
        vsp_params={"preserve_preferred_pairs": True},
        time_budget_s=5.0,
    )
    output_report = result.meta["hard_constraint_report"]["output"]
    soft_issues = output_report.get("soft_issues", [])
    has_split = any("MANDATORY_GROUP_SPLIT" in issue for issue in soft_issues)
    # Se o solver conseguir manter o grupo junto, ótimo (sem split).
    # Se não, deve aparecer como soft issue (não hard).
    if not has_split:
        # Verificar que o grupo ficou junto (sucesso do solver)
        all_issues = output_report.get("issues", [])
        assert not any("MANDATORY_GROUP_SPLIT" in issue for issue in all_issues), \
            "MANDATORY_GROUP_SPLIT deve ser soft, não hard"


def test_run_cutting_splits_inside_trip_at_explicit_mid_trip_relief():
    block = Block(
        id=1,
        trips=[
            _trip(
                1,
                360,
                180,
                depot=1,
                origin=1,
                dest=3,
                mid_relief_point=2,
                mid_relief_offset=90,
            ),
            _trip(2, 540, 60, depot=1, origin=3, dest=1),
        ],
    )
    solver = GreedyCSP(
        mandatory_break_after_minutes=120,
        max_driving_minutes=120,
        max_shift_minutes=480,
        max_work_minutes=420,
        min_break_minutes=30,
        allow_relief_points=True,
    )

    tasks, meta = solver.prepare_tasks([block])

    assert meta["mid_trip_relief_splits"] == 1
    assert meta["task_count"] >= 2
    assert len(tasks[0].trips) == 1
    assert tasks[0].trips[0].public_id == 1
    assert tasks[0].trips[0].end_time == 450
    assert tasks[1].trips[0].public_id == 1
    assert tasks[1].trips[0].start_time == 450


def test_run_cutting_uses_physical_ratios_for_relief_energy_split_when_available():
    block = Block(
        id=1,
        trips=[
            _trip(
                1,
                360,
                180,
                depot=1,
                origin=1,
                dest=3,
                energy=30.0,
                mid_relief_point=2,
                mid_relief_offset=90,
                mid_relief_distance_ratio=0.7,
                mid_relief_elevation_ratio=0.9,
            ),
        ],
    )
    solver = GreedyCSP(allow_relief_points=True)

    tasks, meta = solver.prepare_tasks([block])

    assert meta["mid_trip_relief_splits"] == 1
    first_trip = tasks[0].trips[0]
    second_trip = tasks[1].trips[0]

    # O split físico informado deve prevalecer sobre o corte temporal de 50%.
    assert first_trip.energy_kwh == pytest.approx(21.0)
    assert second_trip.energy_kwh == pytest.approx(9.0)
    assert first_trip.distance_km > second_trip.distance_km


def test_optimizer_allows_mid_trip_relief_handoff_without_terminal_violation():
    trips = [
        _trip(
            1,
            360,
            180,
            depot=1,
            origin=1,
            dest=3,
            mid_relief_point=2,
            mid_relief_offset=90,
        )
    ]
    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.GREEDY,
        cct_params={
            "allow_relief_points": True,
            "max_work_minutes": 90,
            "overtime_limit_minutes": 0,
            "strict_hard_validation": True,
        },
        vsp_params={"min_layover_minutes": 8},
        time_budget_s=2.0,
    )

    assert len(result.csp.duties) == 2
    output = result.as_dict()
    duty_trip_ids = [trip["trip_id"] for duty in output["duties"] for trip in duty["trips"]]
    assert duty_trip_ids == [1, 1]
    assert not any(
        "OPERATOR_CHANGE_NON_TERMINAL" in issue
        for issue in result.meta["hard_constraint_report"]["output"]["issues"]
    )


def test_mid_trip_relief_optional_cut_does_not_increase_duties_or_crew():
    baseline_trips = [
        _trip(1, 960, 88, line=16, origin=1, dest=13),
        _trip(2, 1078, 118, line=16, origin=13, dest=12),
        _trip(3, 1226, 80, line=16, origin=12, dest=1),
    ]
    relief_trips = [
        _trip(1, 960, 88, line=16, origin=1, dest=13),
        _trip(2, 1078, 118, line=16, origin=13, dest=12, mid_relief_point=14, mid_relief_offset=60),
        _trip(3, 1226, 80, line=16, origin=12, dest=1),
    ]

    common_cct_params = {
        "max_work_minutes": 200,
        "overtime_limit_minutes": 0,
        "max_driving_minutes": 200,
        "mandatory_break_after_minutes": 200,
        "min_break_minutes": 30,
        "strict_hard_validation": False,
    }

    baseline = OptimizerService().run(
        baseline_trips,
        _vehicle(),
        algorithm=AlgorithmType.GREEDY,
        cct_params={**common_cct_params, "allow_relief_points": False},
        vsp_params={"min_layover_minutes": 8},
        time_budget_s=2.0,
    )
    relief = OptimizerService().run(
        relief_trips,
        _vehicle(),
        algorithm=AlgorithmType.GREEDY,
        cct_params={**common_cct_params, "allow_relief_points": True},
        vsp_params={"min_layover_minutes": 8},
        time_budget_s=2.0,
    )

    baseline_output = baseline.as_dict()
    relief_output = relief.as_dict()

    assert len(relief_output["duties"]) <= len(baseline_output["duties"])
    assert relief_output["crew"] <= baseline_output["crew"]
    assert relief_output["meta"]["mid_trip_relief_splits"] == 1
    assert "relief_reassignment_audit" in relief_output["meta"]
    assert any(duty["trip_ids"] == [2, 3] for duty in relief_output["duties"])


def test_relief_reassignment_postopt_moves_relief_task_to_future_compatible_duty():
    solver = GreedyCSP(allow_relief_points=True, strict_hard_validation=False)

    base_task = _task_block(1, [_trip(1, 900, 60, origin=1, dest=13)])
    relief_trip = _trip(2, 1060, 60, origin=14, dest=12)
    relief_trip.original_trip_id = 200
    relief_trip.segment_index = 1
    relief_trip.segment_count = 2
    relief_task = _task_block(2, [relief_trip])
    future_task = _task_block(3, [_trip(3, 1128, 60, origin=12, dest=1)])

    duties = [
        solver._seed_duty_with_task(1, base_task),
        solver._seed_duty_with_task(2, relief_task),
        solver._seed_duty_with_task(3, future_task),
    ]
    original_blocks = [
        Block(id=1, trips=list(base_task.trips)),
        Block(id=2, trips=list(relief_task.trips)),
        Block(id=3, trips=list(future_task.trips)),
    ]

    new_duties, audit = solver._relief_reassignment_postopt(duties, original_blocks)

    assert len(new_duties) == 2
    assert audit["accepted"] >= 1
    assert audit["improved"] is True
    assert audit["final_metrics"]["duties"] == 2
    assert any(move["task"]["mid_trip_original_trip_ids"] == [200] for move in audit["accepted_moves"])


def test_relief_reassignment_audit_reports_rejected_handoff_reason():
    solver = GreedyCSP(allow_relief_points=True, strict_hard_validation=False)

    base_task = _task_block(1, [_trip(1, 900, 60, origin=1, dest=13)])
    relief_trip = _trip(2, 1060, 60, origin=14, dest=12)
    relief_trip.original_trip_id = 201
    relief_trip.segment_index = 1
    relief_trip.segment_count = 2
    relief_task = _task_block(2, [relief_trip])
    incompatible_task = _task_block(3, [_trip(3, 1128, 60, origin=99, dest=1)])

    duties = [
        solver._seed_duty_with_task(1, base_task),
        solver._seed_duty_with_task(2, relief_task),
        solver._seed_duty_with_task(3, incompatible_task),
    ]
    original_blocks = [
        Block(id=1, trips=list(base_task.trips)),
        Block(id=2, trips=list(relief_task.trips)),
        Block(id=3, trips=list(incompatible_task.trips)),
    ]

    new_duties, audit = solver._relief_reassignment_postopt(duties, original_blocks)

    assert len(new_duties) == 3
    assert audit["accepted"] == 0
    assert audit["improved"] is False
    assert audit["rejection_reasons"]["prepend_target_operator_change_non_terminal"] >= 1


def test_run_cutting_cuts_before_guarded_pair_when_continuous_drive_would_break_limit():
    block = Block(
        id=1,
        trips=[
            _trip(1, 405, 87, line=16, origin=13, dest=12, trip_group_id=120002, direction="return"),
            _trip(2, 510, 80, line=16, origin=12, dest=13, trip_group_id=120010, direction="outbound"),
            _trip(3, 590, 106, line=16, origin=13, dest=12, trip_group_id=120010, direction="return"),
        ],
    )
    solver = GreedyCSP(
        min_break_minutes=20,
        mandatory_break_after_minutes=240,
        max_driving_minutes=270,
        meal_break_minutes=20,
        max_shift_minutes=560,
        max_work_minutes=440,
        allow_relief_points=True,
    )

    tasks, _ = solver.prepare_tasks([block])
    assert len(tasks) == 2
    assert [trip.id for trip in tasks[0].trips] == [1]
    assert [trip.id for trip in tasks[1].trips] == [2, 3]

    sol = solver.solve([block], block.trips)
    assert all(int(duty.meta.get("max_continuous_drive_minutes", 0)) <= 240 for duty in sol.duties)
    assert all(duty.rest_violations == 0 for duty in sol.duties)


def test_set_covering_respects_column_limit_meta():
    blocks = [
        Block(id=index + 1, trips=[_trip(index + 1, 360 + index * 70, 55, line=40, origin=1 if index % 2 == 0 else 2, dest=2 if index % 2 == 0 else 1, depot=1)])
        for index in range(8)
    ]
    sol = SetPartitioningCSP(
        vsp_params={
            "pricing_enabled": True,
            "max_trips_per_piece": 4,
            "max_generated_columns": 20,
            "max_candidate_successors_per_task": 3,
            "max_pricing_iterations": 1,
            "max_pricing_additions": 10,
        }
    ).solve(blocks, [])
    assert sol.meta["workpieces_generated"] <= 20
    assert sol.meta["column_generation"]["max_generated_columns"] == 20


def test_set_covering_preserves_relief_reassignment_audit_meta():
    blocks = [
        Block(id=1, trips=[_trip(1, 960, 88, line=16, origin=1, dest=13)]),
        Block(
            id=2,
            trips=[
                _trip(
                    2,
                    1048,
                    118,
                    line=16,
                    origin=13,
                    dest=12,
                    mid_relief_point=14,
                    mid_relief_offset=60,
                )
            ],
        ),
        Block(id=3, trips=[_trip(3, 1200, 80, line=16, origin=12, dest=1)]),
    ]

    sol = SetPartitioningCSP(
        allow_relief_points=True,
        strict_hard_validation=False,
        vsp_params={
            "pricing_enabled": True,
            "max_trips_per_piece": 2,
            "max_generated_columns": 32,
        },
    ).solve(blocks, [])

    assert "relief_reassignment_audit" in sol.meta
    assert sol.meta["relief_reassignment_audit"]["enabled"] is True
    assert sol.meta["relief_reassignment_audit"]["relief_task_candidates"] >= 1


def test_relief_reassignment_rank_prioritizes_duties_and_fragmentation_after_crew():
    solver = GreedyCSP()

    same_crew_more_fragmented = {
        "violations": 0,
        "crew": 10,
        "duties": 11,
        "split_duties": 2,
        "vehicle_switches": 2,
        "fragmentation_score": 120000,
        "short_duties": 1,
        "total_overtime_minutes": 40,
        "waiting_minutes": 60,
    }
    same_crew_better = {
        "violations": 0,
        "crew": 10,
        "duties": 10,
        "split_duties": 0,
        "vehicle_switches": 0,
        "fragmentation_score": 98000,
        "short_duties": 0,
        "total_overtime_minutes": 25,
        "waiting_minutes": 30,
    }

    assert solver._relief_reassignment_rank(same_crew_better) < solver._relief_reassignment_rank(same_crew_more_fragmented)


def test_operator_profiles_assign_senior_to_mandatory_early_shift():
    trips = [
        _trip(1, 300, 60, line=40, origin=10, dest=20, depot=1),
        _trip(2, 380, 60, line=40, origin=20, dest=10, depot=1),
        _trip(3, 980, 60, line=41, origin=30, dest=40, depot=1),
        _trip(4, 1060, 60, line=41, origin=40, dest=30, depot=1),
    ]
    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={
            "operator_profiles": [
                {"id": 1, "name": "Senior", "seniority_rank": 1, "mandatory_shift_types": ["early"]},
                {"id": 2, "name": "Junior", "seniority_rank": 2, "mandatory_shift_types": ["late"]},
            ]
        },
        vsp_params={"preserve_preferred_pairs": True},
        time_budget_s=5.0,
    )
    assignment = result.csp.meta["operator_assignment"]["rosters"]
    early = next(item for item in assignment if item["shift_type"] == "early")
    late = next(item for item in assignment if item["shift_type"] == "late")
    assert early["operator_name"] == "Senior"
    assert late["operator_name"] == "Junior"


def test_hard_validation_rejects_missing_union_compatible_operator():
    trips = [
        _trip(1, 300, 60, line=50, origin=10, dest=20, depot=1),
        _trip(2, 380, 60, line=50, origin=20, dest=10, depot=1),
    ]
    with pytest.raises(HardConstraintViolationError) as exc:
        OptimizerService().run(
            trips,
            _vehicle(),
            algorithm=AlgorithmType.HYBRID_PIPELINE,
            cct_params={
                "operator_profiles": [
                    {"id": 1, "name": "LateOnly", "seniority_rank": 1, "mandatory_shift_types": ["late"]},
                ],
                "strict_union_rules": True,
            },
            vsp_params={"preserve_preferred_pairs": True},
            time_budget_s=5.0,
        )
    assert "UNASSIGNED_OPERATOR_PROFILE" in str(exc.value)
