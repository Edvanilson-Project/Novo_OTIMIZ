import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.api.routes.optimize import router as optimize_router
from fastapi import FastAPI
from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.evaluator import CostEvaluator
from src.core.exceptions import HardConstraintViolationError
from src.domain.models import AlgorithmType, Block, Duty, OptimizationResult, Trip, VehicleType, VSPSolution, CSPSolution
from src.services.optimizer_service import OptimizerService


def _trip(
    tid: int,
    start: int,
    dur: int,
    *,
    line: int = 1,
    origin: int = 1,
    dest: int = 2,
    trip_group_id: int | None = None,
    direction: str | None = None,
    distance: float = 20.0,
):
    return Trip(
        id=tid,
        line_id=line,
        start_time=start,
        end_time=start + dur,
        origin_id=origin,
        destination_id=dest,
        trip_group_id=trip_group_id,
        direction=direction,
        duration=dur,
        distance_km=distance,
        deadhead_times={1: 8, 2: 8, 3: 8, 4: 8, 9: 8},
    )


def _vehicle() -> list[VehicleType]:
    return [
        VehicleType(
            id=1,
            name="Standard",
            passenger_capacity=40,
            cost_per_km=3.0,
            cost_per_hour=60.0,
            fixed_cost=1000.0,
        )
    ]


def test_block_cost_counts_vehicle_fixed_once_when_vehicle_type_exists():
    trip = _trip(1, 360, 60)
    trip.idle_before_minutes = 10
    trip.idle_after_minutes = 5
    block = Block(id=1, trips=[trip], vehicle_type_id=1)

    evaluator = CostEvaluator(idle_cost_per_minute=0.5)
    cost = evaluator.block_cost(block, _vehicle())

    expected = 1000.0 + (3.0 * trip.distance_km) + 60.0 + ((10 + 5) * 0.5)
    assert cost == pytest.approx(expected)


def test_total_cost_breakdown_separates_vsp_and_csp_components():
    trip = _trip(1, 360, 60)
    block = Block(id=1, trips=[trip], vehicle_type_id=1)
    duty = Duty(id=1)
    duty.add_task(block)
    duty.paid_minutes = 90

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[duty]),
    )
    evaluator = CostEvaluator()

    breakdown = evaluator.total_cost_breakdown(result, _vehicle())

    assert breakdown["vsp"]["activation"] == pytest.approx(1000.0)
    assert breakdown["vsp"]["distance"] == pytest.approx(60.0)
    assert breakdown["vsp"]["time"] == pytest.approx(60.0)
    assert breakdown["csp"]["work_cost"] == pytest.approx(25.0)
    assert breakdown["csp"]["waiting_cost"] == pytest.approx(12.5)
    assert breakdown["total"] == pytest.approx(
        breakdown["vsp"]["total"] + breakdown["csp"]["total"]
    )


def test_vsp_total_cost_breakdown_includes_idle_cost_in_total():
    trip = _trip(1, 360, 60)
    trip.idle_before_minutes = 12
    trip.idle_after_minutes = 18
    block = Block(id=1, trips=[trip], vehicle_type_id=1)
    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[]),
    )

    breakdown = CostEvaluator(idle_cost_per_minute=0.5).total_cost_breakdown(result, _vehicle())

    assert breakdown["vsp"]["idle_cost"] == pytest.approx(15.0)
    assert breakdown["vsp"]["blocks"][0]["idle_cost"] == pytest.approx(15.0)
    assert breakdown["vsp"]["total"] == pytest.approx(1000.0 + 60.0 + 60.0 + 15.0)
    assert breakdown["total"] == pytest.approx(breakdown["vsp"]["total"])


def test_csp_cost_breakdown_includes_guaranteed_waiting_and_overtime_components():
    block = Block(id=1, trips=[_trip(1, 360, 60)])
    duty = Duty(id=1)
    duty.add_task(block)
    duty.paid_minutes = 300
    duty.overtime_minutes = 30
    duty.meta["guaranteed_minutes"] = 240
    duty.meta["overtime_extra_pct"] = 0.5

    breakdown = CostEvaluator().csp_cost_breakdown(CSPSolution(duties=[duty]))
    duty_breakdown = breakdown["duties"][0]

    assert duty_breakdown["work_cost"] == pytest.approx(25.0)
    assert duty_breakdown["guaranteed_cost"] == pytest.approx(75.0)
    assert duty_breakdown["waiting_cost"] == pytest.approx(25.0)
    assert duty_breakdown["overtime_cost"] == pytest.approx(6.25)
    assert breakdown["total"] == pytest.approx(131.25)


def test_optimizer_result_payload_serializes_block_and_duty_cost_fields():
    trip = _trip(1, 360, 60)
    trip.idle_before_minutes = 12
    trip.idle_after_minutes = 18
    block = Block(id=1, trips=[trip], vehicle_type_id=1)
    duty = Duty(id=1)
    duty.add_task(block)
    duty.paid_minutes = 300
    duty.overtime_minutes = 30
    duty.meta["guaranteed_minutes"] = 240
    duty.meta["covered_trip_ids"] = [trip.id]
    duty.meta["overtime_extra_pct"] = 0.5

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[duty]),
    )
    breakdown = CostEvaluator(idle_cost_per_minute=0.5).total_cost_breakdown(result, _vehicle())
    result.total_cost = breakdown["total"]
    result.meta["cost_breakdown"] = breakdown

    payload = result.as_dict()

    assert payload["blocks"][0]["idle_cost"] == pytest.approx(15.0)
    assert payload["blocks"][0]["total_cost"] == pytest.approx(1135.0)
    assert payload["duties"][0]["guaranteed_cost"] == pytest.approx(75.0)
    assert payload["duties"][0]["waiting_cost"] == pytest.approx(25.0)
    assert payload["duties"][0]["overtime_cost"] == pytest.approx(6.25)
    assert payload["duties"][0]["total_cost"] == pytest.approx(131.25)


def test_greedy_csp_computes_overtime_from_work_time_not_spread_time():
    duty = Duty(id=165, work_time=484, spread_time=560)

    solution = GreedyCSP(
        max_shift_minutes=560,
        max_work_minutes=480,
        overtime_limit_minutes=120,
    ).finalize_selected_duties([duty])

    assert solution.duties[0].overtime_minutes == 4
    assert solution.cct_violations == 0


def test_csp_cost_breakdown_preserves_raw_precision_until_final_rounding():
    duty_a = Duty(id=1, work_time=20, paid_minutes=20)
    duty_b = Duty(id=2, work_time=20, paid_minutes=20)

    breakdown = CostEvaluator().csp_cost_breakdown(CSPSolution(duties=[duty_a, duty_b]))

    # 20 min at 25/h = 8.333..., twice = 16.666... -> 16.67.
    # If each duty were rounded first, the result would drift to 16.66.
    assert breakdown["work_cost"] == pytest.approx(16.67)
    assert breakdown["total"] == pytest.approx(16.67)


def test_csp_cost_breakdown_uses_piecewise_long_unpaid_break_penalty():
    duty = Duty(id=10, work_time=60, spread_time=240, paid_minutes=60)
    duty.meta["unpaid_break_total_minutes"] = 180

    breakdown = CostEvaluator(
        long_unpaid_break_limit_minutes=90,
        long_unpaid_break_penalty_weight=0.05,
    ).csp_cost_breakdown(CSPSolution(duties=[duty]))

    # Excess = 90 min -> 30*1 + 60*3 = 210 weight-units -> 10.5 monetary units.
    assert breakdown["long_unpaid_break_penalty"] == pytest.approx(10.5)
    assert breakdown["duties"][0]["long_unpaid_break_penalty"] == pytest.approx(10.5)


def test_optimizer_result_exposes_solver_explanation_and_trip_group_audit():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2, trip_group_id=77, direction="outbound"),
        _trip(2, 430, 60, origin=2, dest=1, trip_group_id=77, direction="return"),
    ]

    result = OptimizerService().run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.GREEDY,
        cct_params={"strict_hard_validation": True},
        vsp_params={"preserve_preferred_pairs": True},
    )
    payload = result.as_dict()

    assert payload["cost_breakdown"]["total"] == pytest.approx(result.total_cost)
    assert payload["solver_explanation"]["status"] == "feasible"
    assert payload["trip_group_audit"]["groups_total"] == 1
    assert payload["trip_group_audit"]["same_roster_groups"] == 1
    assert payload["phase_summary"]["vsp"]["vehicles"] >= 1
    assert payload["phase_summary"]["csp"]["crew"] >= 1
    assert result.meta["reproducibility"]["input_hash"]
    assert result.meta["reproducibility"]["params_hash"]
    assert result.meta["performance"]["phase_timings_ms"]["input_validation_ms"] >= 0
    assert result.meta["performance"]["phase_timings_ms"]["solver_ms"] >= 0
    assert result.meta["performance"]["phase_timings_ms"]["output_validation_ms"] >= 0
    assert result.meta["performance"]["phase_timings_ms"]["audit_enrichment_ms"] >= 0


def test_greedy_csp_prefers_existing_trip_group_duty_when_feasible():
    blocks = [
        Block(id=1, trips=[_trip(1, 360, 60, origin=1, dest=2, trip_group_id=42)]),
        Block(id=2, trips=[_trip(2, 425, 40, origin=9, dest=2)]),
        Block(id=3, trips=[_trip(3, 600, 60, origin=2, dest=1, trip_group_id=42)]),
    ]

    solution = GreedyCSP(
        min_break_minutes=30,
        max_shift_minutes=720,
        max_work_minutes=720,
        trip_group_keep_bonus=220.0,
        trip_group_split_penalty=320.0,
    ).solve(blocks, [])

    duty_by_trip: dict[int, int] = {}
    for duty in solution.duties:
        for task in duty.tasks:
            for trip in task.trips:
                duty_by_trip[trip.id] = duty.id

    assert duty_by_trip[1] == duty_by_trip[3]


def test_build_failure_payload_exposes_infeasibility_explanation():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 400, 60, origin=2, dest=1),
    ]
    service = OptimizerService()

    payload = service.build_failure_payload(
        HardConstraintViolationError(["SPREAD_EXCEEDED D5", "CONTINUOUS_DRIVING_EXCEEDED D6"]),
        trips,
        AlgorithmType.HYBRID_PIPELINE,
        {"max_shift_minutes": 480},
        {"random_seed": 7, "time_budget_s": 9},
        stage="output_validation",
    )

    assert payload["phase"] == "csp"
    assert payload["infeasibility_explanation"]["reason"] == "spread_limit"
    assert payload["issue_count"] == 2
    assert payload["input_snapshot"]["trip_count"] == 2
    assert payload["input_snapshot"]["input_hash"]
    assert payload["input_snapshot"]["params_hash"]
    assert payload["input_snapshot"]["time_budget_s"] == pytest.approx(9.0)


def test_optimize_route_returns_structured_diagnostics_on_failure():
    app = FastAPI()
    app.include_router(optimize_router, prefix="/optimize")
    client = TestClient(app)

    response = client.post(
        "/optimize/",
        json={
            "algorithm": "hybrid_pipeline",
            "trips": [
                {
                    "id": 1,
                    "line_id": 1,
                    "start_time": 360,
                    "end_time": 420,
                    "origin_id": 1,
                    "destination_id": 1,
                    "duration": 60,
                    "distance_km": 10,
                },
            ],
            "vehicle_types": [],
            "cct_params": {"strict_hard_validation": True},
            "vsp_params": {"min_layover_minutes": 30, "random_seed": 11},
        },
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["code"] == "HARD_CONSTRAINT_VIOLATION"
    assert payload["diagnostics"]["stage"] in {"input_validation", "output_validation", "api"}
    assert payload["diagnostics"]["issues"]
    assert payload["diagnostics"]["infeasibility_explanation"]["reason"] is not None


def test_same_random_seed_produces_same_hybrid_solution_signature():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 450, 60, origin=2, dest=1),
        _trip(3, 570, 60, origin=1, dest=2),
        _trip(4, 660, 60, origin=2, dest=1),
        _trip(5, 780, 60, origin=1, dest=2),
        _trip(6, 870, 60, origin=2, dest=1),
    ]
    service = OptimizerService()
    params = {"random_seed": 123, "preserve_preferred_pairs": True}

    result_a = service.run(trips, _vehicle(), algorithm=AlgorithmType.HYBRID_PIPELINE, vsp_params=params, time_budget_s=4.0)
    result_b = service.run(trips, _vehicle(), algorithm=AlgorithmType.HYBRID_PIPELINE, vsp_params=params, time_budget_s=4.0)

    signature_a = [[trip.id for trip in block.trips] for block in result_a.vsp.blocks]
    signature_b = [[trip.id for trip in block.trips] for block in result_b.vsp.blocks]
    assert signature_a == signature_b
    assert result_a.meta["reproducibility"]["deterministic_replay_possible"] is False
    assert "budget por tempo" in result_a.meta["reproducibility"]["note"]
    assert result_a.meta["reproducibility"]["input_hash"] == result_b.meta["reproducibility"]["input_hash"]
    assert result_a.meta["reproducibility"]["params_hash"] == result_b.meta["reproducibility"]["params_hash"]
    assert result_a.meta["reproducibility"]["time_budget_s"] == pytest.approx(4.0)
    assert result_a.meta["solver_version"]
    assert "phase_timings_ms" in result_a.meta.get("performance", {})
    assert result_a.meta["performance"]["phase_timings_ms"].get("vsp_mcnf_ms") is not None
    assert result_a.meta["performance"]["phase_timings_ms"].get("solver_ms") is not None
