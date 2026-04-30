from __future__ import annotations

import pytest

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.csp.set_partitioning import SetPartitioningCSP
from src.algorithms.evaluator import CostEvaluator
from src.algorithms.vsp.greedy import GreedyVSP
from src.api.schemas import CctParamsInput, VspParamsInput
from src.core.exceptions import OptimizerError
from src.domain.models import Block, CSPSolution, Duty, OptimizationResult, Trip, VehicleType, VSPSolution
from src.services.optimizer_service import OptimizerService
from src.services.hard_constraint_validator import HardConstraintValidator
from src.domain.models import AlgorithmType


def trip(
    trip_id: int,
    start: int,
    end: int,
    *,
    origin: int = 1,
    destination: int = 2,
    line: int = 10,
    service_day: int | None = None,
) -> Trip:
    return Trip(
        id=trip_id,
        line_id=line,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=destination,
        duration=end - start,
        distance_km=10.0,
        service_day=service_day,
    )


def test_hybrid_pipeline_accepts_effective_optimization_params_without_type_error():
    trips = [
        trip(1, 0, 30, origin=1, destination=2),
        trip(2, 45, 75, origin=2, destination=1),
    ]
    vehicle_types = [VehicleType(id=1, name="Bus", passenger_capacity=40, fixed_cost=100.0)]

    result = OptimizerService().run(
        trips=trips,
        vehicle_types=vehicle_types,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={"apply_cct": False, "strict_hard_validation": False},
        vsp_params={"time_budget_s": 1, "min_layover_minutes": 0},
        optimization_params={"driver_cost_per_minute": 1.0, "ilp_timeout_seconds": 7},
    )

    assert result.total_cost > 0
    assert result.meta["ilp_timeout_seconds"] == 7


def test_driver_cost_parameter_changes_optimizer_final_cost():
    trips = [trip(1, 0, 60), trip(2, 90, 150, origin=2, destination=1)]
    vehicle_types = [VehicleType(id=1, name="Bus", passenger_capacity=40, fixed_cost=100.0)]
    common = {
        "trips": trips,
        "vehicle_types": vehicle_types,
        "algorithm": AlgorithmType.GREEDY,
        "cct_params": {"apply_cct": False, "strict_hard_validation": False},
        "vsp_params": {"min_layover_minutes": 0, "fixed_vehicle_activation_cost": 100.0},
    }

    cheap = OptimizerService().run(**common, optimization_params={"driver_cost_per_minute": 0.5})
    expensive = OptimizerService().run(**common, optimization_params={"driver_cost_per_minute": 2.0})

    assert expensive.total_cost > cheap.total_cost


def test_meal_break_parameter_changes_break_reset_threshold():
    duty = Duty(id=1)
    duty.add_task(Block(id=1, trips=[trip(1, 0, 30)]))
    candidate = Block(id=2, trips=[trip(2, 75, 105)])

    assert GreedyCSP(min_break_minutes=30, meal_break_minutes=60)._would_have_meal_break(duty, candidate) is False
    assert GreedyCSP(min_break_minutes=30, meal_break_minutes=30)._would_have_meal_break(duty, candidate) is True


def test_vehicle_idle_gap_return_to_garage_threshold_splits_blocks():
    trips = [
        trip(1, 0, 30, origin=1, destination=2),
        trip(2, 300, 330, origin=2, destination=1),
    ]
    vehicle_types = [VehicleType(id=1, name="Bus", passenger_capacity=40, fixed_cost=500.0)]

    stay = GreedyVSP(
        {
            "min_layover_minutes": 0,
            "fixed_vehicle_activation_cost": 500.0,
            "idle_cost_per_minute": 0.01,
            "enable_single_trip_compaction": False,
        }
    ).solve(trips, vehicle_types)
    return_to_garage = GreedyVSP(
        {
            "min_layover_minutes": 0,
            "fixed_vehicle_activation_cost": 500.0,
            "idle_cost_per_minute": 0.01,
            "vehicle_idle_gap_behavior": "return_to_garage",
            "vehicle_idle_gap_threshold_minutes": 120,
            "enable_single_trip_compaction": False,
        }
    ).solve(trips, vehicle_types)

    assert len(stay.blocks) == 1
    assert len(return_to_garage.blocks) == 2


def test_terminal_location_ids_restrict_operator_change_boundaries():
    block_a = Block(id=1, trips=[trip(1, 0, 30, origin=1, destination=2)])
    block_b = Block(id=2, trips=[trip(2, 60, 90, origin=2, destination=3)])
    params = {
        "apply_cct": False,
        "operator_change_terminals_only": True,
        "min_layover_minutes": 0,
    }

    disallowed = GreedyCSP(**params, terminal_location_ids=[99]).solve([block_a, block_b])
    allowed = GreedyCSP(**params, terminal_location_ids=[2]).solve([block_a, block_b])

    assert len(disallowed.duties) == 2
    assert len(allowed.duties) == 1


def test_min_guaranteed_work_minutes_changes_paid_minutes():
    block = Block(id=1, trips=[trip(1, 0, 60)])

    result = GreedyCSP(
        apply_cct=False,
        min_guaranteed_work_minutes=300,
        idle_time_is_paid=False,
    ).solve([block])

    assert result.duties[0].paid_minutes == 300


def test_enable_column_generation_false_disables_pricing_when_pricing_not_explicit():
    csp = SetPartitioningCSP(
        vsp_params={"enable_column_generation": False},
        max_shift_minutes=720,
        max_work_minutes=480,
    )

    assert csp.pricing_enabled is False


def test_sunday_off_weight_is_applied_without_unbound_error():
    duty = Duty(id=1)
    duty.add_task(Block(id=1, trips=[trip(1, 0, 60, service_day=0)]))
    duty.meta["is_sunday"] = True
    solution = CSPSolution(duties=[duty])

    evaluator = CostEvaluator()
    evaluator.set_costs(
        {
            "driver_cost_per_minute": 1.0,
            "holiday_extra_pct": 0.0,
            "sunday_off_weight": 123.0,
        }
    )
    breakdown = evaluator.csp_cost_breakdown(solution)

    assert breakdown["cct_penalties"] == pytest.approx(123.0)


def test_min_break_blocks_short_positive_interval_between_driver_tasks():
    block_a = Block(id=1, trips=[trip(1, 0, 30, origin=1, destination=2)])
    block_b = Block(id=2, trips=[trip(2, 36, 66, origin=2, destination=1)])

    result = GreedyCSP(
        apply_cct=True,
        enforce_min_interval=True,
        min_break_minutes=30,
        min_layover_minutes=0,
        max_shift_minutes=720,
        max_work_minutes=480,
        mandatory_break_after_minutes=480,
    ).solve([block_a, block_b])

    assert len(result.duties) == 2
    assert result.meta["duty_merge_diagnostics"]["duty_build"]["reasons"]["min_interval_violation"] >= 1


def test_min_break_splits_short_positive_interval_hidden_inside_source_block():
    source_block = Block(
        id=1,
        trips=[
            trip(1, 0, 30, origin=1, destination=2),
            trip(2, 36, 66, origin=2, destination=1),
        ],
    )

    result = GreedyCSP(
        apply_cct=True,
        enforce_min_interval=True,
        min_break_minutes=30,
        min_layover_minutes=0,
        max_shift_minutes=720,
        max_work_minutes=480,
        mandatory_break_after_minutes=480,
    ).solve([source_block])

    assert len(result.duties) == 2
    assert result.meta["relief_cuts"] == 1
    assert {task.meta.get("split_reason") for duty in result.duties for task in duty.tasks} >= {"short_interval"}


def test_hard_validator_rejects_short_positive_vehicle_and_driver_intervals():
    trips = [
        trip(1, 0, 30, origin=1, destination=2),
        trip(2, 36, 66, origin=2, destination=1),
    ]
    block = Block(id=1, trips=trips)
    duty = Duty(id=1)
    duty.add_task(block)
    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[duty]),
    )

    report = HardConstraintValidator().audit_result(
        result,
        trips,
        cct_params={"apply_cct": True, "enforce_min_interval": True, "min_break_minutes": 30},
        vsp_params={"min_layover_minutes": 0},
    )

    assert report["ok"] is False
    assert any(issue.startswith("VEHICLE_MIN_INTERVAL_VIOLATION") for issue in report["issues"])
    assert any(issue.startswith("DUTY_MIN_INTERVAL_VIOLATION") for issue in report["issues"])


def test_service_min_break_parameter_becomes_hard_min_interval():
    trips = [
        trip(1, 0, 30, origin=1, destination=2),
        trip(2, 36, 66, origin=2, destination=1),
    ]
    vehicle_types = [VehicleType(id=1, name="Bus", passenger_capacity=40, fixed_cost=100.0)]

    result = OptimizerService().run(
        trips=trips,
        vehicle_types=vehicle_types,
        algorithm=AlgorithmType.GREEDY,
        cct_params={
            "apply_cct": True,
            "strict_hard_validation": True,
            "min_break_minutes": 30,
            "max_shift_minutes": 720,
            "max_work_minutes": 480,
            "mandatory_break_after_minutes": 480,
        },
        vsp_params={"min_layover_minutes": 0},
    )

    assert len(result.vsp.blocks) == 2
    assert len(result.csp.duties) == 2
    assert result.meta["hard_constraint_report"]["output"]["ok"] is True


def test_optimizer_api_schemas_accept_validation_and_ilp_parameters():
    cct = CctParamsInput(
        enforce_min_interval=True,
        strict_zero_gap_validation=True,
        strict_operational_mode=True,
        strict_hard_constraints=True,
        strict_gps_validation=False,
        strict_terminal_sync_validation=False,
    )
    vsp = VspParamsInput(
        enforce_min_interval=True,
        ilp_timeout_seconds=45,
        strict_zero_gap_validation=True,
        strict_operational_mode=True,
        strict_hard_constraints=True,
    )

    assert cct.enforce_min_interval is True
    assert cct.strict_zero_gap_validation is True
    assert cct.strict_operational_mode is True
    assert cct.strict_hard_constraints is True
    assert cct.strict_gps_validation is False
    assert cct.strict_terminal_sync_validation is False
    assert vsp.enforce_min_interval is True
    assert vsp.ilp_timeout_seconds == 45
    assert vsp.strict_zero_gap_validation is True
    assert vsp.strict_operational_mode is True
    assert vsp.strict_hard_constraints is True


def test_strict_input_validation_flags_are_effective():
    bad_trip = trip(1, 0, 30, origin=1, destination=2)
    bad_trip.gps_valid = False
    bad_trip.sent_to_driver_terminal = False
    validator = HardConstraintValidator()

    strict = validator.audit_input(
        [bad_trip],
        cct_params={"strict_gps_validation": True, "strict_terminal_sync_validation": True},
        vsp_params={},
    )
    relaxed = validator.audit_input(
        [bad_trip],
        cct_params={"strict_gps_validation": False, "strict_terminal_sync_validation": False},
        vsp_params={},
    )

    assert "GPS_FLAG_INVALID T1" in strict["issues"]
    assert "GHOST_BUS_TERMINAL_SYNC T1" in strict["issues"]
    assert relaxed["ok"] is True


def test_group_infeasibility_modes_are_explicit_and_controlled():
    service = OptimizerService()
    first = trip(1, 100, 130, origin=1, destination=2)
    second = trip(2, 132, 160, origin=3, destination=4)
    first.trip_group_id = 77
    second.trip_group_id = 77
    result = OptimizationResult(
        vsp=VSPSolution(blocks=[Block(id=1, trips=[first]), Block(id=2, trips=[second])]),
        csp=CSPSolution(duties=[]),
    )
    audit = {
        "split_groups": 1,
        "sample_splits": [{"trip_group_id": 77, "trip_ids": [1, 2], "block_ids": [1, 2]}],
    }
    exc = OptimizerError(
        "group cannot be preserved",
        code="GROUP_INFEASIBLE",
        details={"group_id": 77, "trip_ids": [1, 2], "reason_code": "GROUP_CONNECTION_INFEASIBLE"},
    )

    production = service._apply_group_infeasibility_policy(result, audit, exc, "production", [first, second], "test")
    handling = production.meta["group_infeasibility_handling"]
    assert handling["status"] == "relaxed"
    assert production.meta["relaxed_constraints"][0]["constraint"] == "mandatory_trip_group_same_roster"
    assert production.meta["affected_groups"][0]["trip_group_id"] == 77

    with pytest.raises(OptimizerError) as assisted:
        service._apply_group_infeasibility_policy(result, audit, exc, "assisted", [first, second], "test")
    assert assisted.value.code == "GROUP_INFEASIBLE"
    assert assisted.value.details["group_infeasibility_handling"]["status"] == "manual_intervention_required"

    with pytest.raises(OptimizerError) as strict:
        service._apply_group_infeasibility_policy(result, audit, exc, "strict", [first, second], "test")
    assert strict.value.code == "GROUP_INFEASIBLE"


def test_production_group_infeasibility_mode_returns_audited_relaxation(monkeypatch):
    service = OptimizerService()
    first = trip(1, 100, 130, origin=1, destination=2)
    second = trip(2, 132, 160, origin=3, destination=4)
    first.trip_group_id = 77
    second.trip_group_id = 77
    split_result = OptimizationResult(
        vsp=VSPSolution(blocks=[Block(id=1, trips=[first]), Block(id=2, trips=[second])], algorithm="hybrid_pipeline"),
        csp=CSPSolution(duties=[]),
    )
    audit = {
        "groups_total": 1,
        "same_roster_groups": 0,
        "split_groups": 1,
        "same_roster_ratio": 0.0,
        "sample_splits": [{"trip_group_id": 77, "trip_ids": [1, 2], "block_ids": [1, 2]}],
    }

    monkeypatch.setattr(service, "_dispatch", lambda *args, **kwargs: split_result)
    monkeypatch.setattr(service, "_ensure_deadhead_coverage", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_inject_trip_group_constraints", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_build_trip_group_audit", lambda *args, **kwargs: dict(audit))
    monkeypatch.setattr(
        service,
        "_repair_split_trip_groups_with_dedicated_blocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OptimizerError(
                "cannot preserve group",
                code="GROUP_INFEASIBLE",
                details={"group_id": 77, "trip_ids": [1, 2], "reason_code": "GROUP_CONNECTION_INFEASIBLE"},
            )
        ),
    )
    monkeypatch.setattr(service.validator, "audit_input", lambda *args, **kwargs: {"ok": True, "issues": []})
    monkeypatch.setattr(
        service.validator,
        "audit_result",
        lambda *args, **kwargs: {
            "ok": False,
            "issues": ["MANDATORY_GROUP_SPLIT [1, 2]"],
            "hard_issues": ["MANDATORY_GROUP_SPLIT [1, 2]"],
            "soft_issues": [],
        },
    )
    monkeypatch.setattr(service.evaluator, "total_cost_breakdown", lambda *args, **kwargs: {"total": 0.0, "vsp": {"total": 0.0}, "csp": {"total": 0.0}})

    result = service.run(
        [first, second],
        [VehicleType(id=1, name="Bus", passenger_capacity=40)],
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={
            "strict_hard_validation": True,
            "strict_hard_constraints": True,
            "group_infeasibility_mode": "production",
        },
        vsp_params={"strict_hard_constraints": True},
        time_budget_s=30.0,
    )

    handling = result.meta["group_infeasibility_handling"]
    assert handling["status"] == "relaxed"
    assert result.meta["hard_constraint_report"]["strict_relaxation_override"]["mode"] == "production"
    assert result.meta["affected_groups"][0]["trip_group_id"] == 77


def test_min_connection_time_alias_affects_vsp_and_parameter_report():
    trips = [
        trip(1, 0, 30, origin=1, destination=2),
        trip(2, 35, 65, origin=2, destination=1),
    ]
    vehicle_types = [VehicleType(id=1, name="Bus", passenger_capacity=40, fixed_cost=100.0)]

    result = OptimizerService().run(
        trips=trips,
        vehicle_types=vehicle_types,
        algorithm=AlgorithmType.GREEDY,
        cct_params={"apply_cct": False, "strict_hard_validation": False, "min_connection_time": 10},
        vsp_params={},
    )

    assert len(result.vsp.blocks) == 2
    report = result.meta["parameter_effect_report"]
    assert report["active_constraints"]["min_connection_time"]["value_minutes"] == 10
    assert report["blocked_connections"]["by_constraint"]["min_connection_time"] >= 1
    assert {"vsp", "csp", "fallback", "stitching"} <= set(report["impact"])


def test_parameter_effect_report_covers_csp_fallback_stitching_zero_gap_and_vehicle_swap():
    first = trip(1, 0, 120, origin=1, destination=2)
    second = trip(2, 120, 260, origin=3, destination=4)
    duty = Duty(id=1)
    duty.add_task(Block(id=1, trips=[first, second]))
    duty.spread_time = 260
    duty.continuous_driving_violation = True
    duty.meta["max_continuous_drive_minutes"] = 260
    result = OptimizationResult(
        vsp=VSPSolution(blocks=[Block(id=1, trips=[first, second])]),
        csp=CSPSolution(duties=[duty]),
        meta={
            "hard_constraint_report": {
                "output": {
                    "issues": ["OPERATOR_MULTIPLE_VEHICLES O1 count=2"],
                    "hard_issues": ["OPERATOR_MULTIPLE_VEHICLES O1 count=2"],
                }
            },
            "performance": {
                "group_audit_fallback": {"algorithm": "greedy"},
                "scale_decomposition": {
                    "fallback_chunk_count": 1,
                    "stitching": {"attempted": 2, "accepted": 1, "rejected": 1},
                },
            },
        },
    )

    report = OptimizerService()._build_parameter_effect_report(
        result,
        [first, second],
        {
            "max_shift_minutes": 200,
            "max_driving_minutes": 240,
            "strict_zero_gap_validation": True,
            "operator_single_vehicle_only": True,
        },
        {"allow_vehicle_swap": False, "min_layover_minutes": 5},
    )

    assert report["active_constraints"]["zero_gap"]["active"] is True
    assert report["active_constraints"]["allow_vehicle_swap"]["active"] is True
    assert report["blocked_connections"]["by_constraint"]["zero_gap"] >= 1
    assert report["blocked_connections"]["by_constraint"]["max_shift_minutes"] >= 1
    assert report["blocked_connections"]["by_constraint"]["max_driving_minutes"] >= 1
    assert report["blocked_connections"]["by_constraint"]["allow_vehicle_swap"] >= 1
    assert report["impact"]["fallback"]["scale_fallback_chunk_count"] == 1
    assert report["impact"]["stitching"]["rejected"] == 1


def test_optimizer_api_schemas_accept_product_infeasibility_and_connection_parameters():
    cct = CctParamsInput(min_connection_time=12, group_infeasibility_mode="assisted")
    vsp = VspParamsInput(min_connection_time=12, group_infeasibility_mode="production")

    assert cct.min_connection_time == 12
    assert cct.group_infeasibility_mode == "assisted"
    assert vsp.min_connection_time == 12
    assert vsp.group_infeasibility_mode == "production"
