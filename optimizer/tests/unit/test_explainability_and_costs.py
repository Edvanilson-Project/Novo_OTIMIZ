import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.api.routes.optimize import _build_optimize_response, router as optimize_router
from fastapi import FastAPI
from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.evaluator import CostEvaluator
from src.algorithms.hybrid.pipeline import HybridPipeline
from src.core.exceptions import HardConstraintViolationError
from src.domain.models import AlgorithmType, Block, Duty, OptimizationResult, Trip, VehicleType, VSPSolution, CSPSolution
from src.services.optimizer_service import OptimizerService
from src.services.optimizer_tasks import run_optimization_task


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
    # cost_duty default = 500.0 → overhead fixo por jornada (1 duty * 500 = 500)
    assert breakdown["duty_overhead_cost"] == pytest.approx(500.0)
    assert breakdown["total"] == pytest.approx(131.25 + 500.0)


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
    # Per-duty total inclui cost_duty (500.0) por design — total = 131.25 + 500 = 631.25
    assert payload["duties"][0]["total_cost"] == pytest.approx(631.25)


def test_optimizer_result_compact_payload_avoids_trip_object_duplication():
    trip = _trip(1, 360, 60, trip_group_id=77, direction="outbound")
    block = Block(id=1, trips=[trip], vehicle_type_id=1)
    duty = Duty(id=1)
    duty.add_task(block)
    duty.meta["covered_original_trip_ids"] = [77]

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block], meta={"input": {"min_layover_minutes": 8}}),
        csp=CSPSolution(duties=[duty], meta={"input": {"meal_break_minutes": 60}}),
        meta={
            "solver_version": "test",
            "performance": {"solver_ms": 12},
            "solver_explanation": {
                "status": "soft_violation",
                "issues": {
                    "hard": [],
                    "soft": [{"raw": "MANDATORY_GROUP_SPLIT [1,2]", "code": "MANDATORY_GROUP_SPLIT"} for _ in range(12)],
                },
            },
            "trip_group_audit": {
                "groups_total": 20,
                "split_groups": 3,
                "sample_splits": [{"trip_group_id": idx} for idx in range(12)],
            },
        },
    )
    breakdown = CostEvaluator().total_cost_breakdown(result, _vehicle())
    breakdown["vsp"]["blocks"] = [{"block_id": 1, "total": 123.0}]
    breakdown["csp"]["duties"] = [{"duty_id": 1, "total": 456.0}]
    result.total_cost = breakdown["total"]
    result.meta["cost_breakdown"] = breakdown
    result.meta["hard_constraint_report"] = {"strict": True, "input": {"ok": True}}
    result.meta["operational_kpis"] = {"vehicles": 1}

    payload = result.as_compact_dict()

    assert payload["blocks"][0]["trips"] == [1]
    assert payload["blocks"][0]["trip_ids"] == [1]
    assert payload["duties"][0]["trips"] == [77]
    assert payload["duties"][0]["trip_ids"] == [77]
    assert "segments" not in payload["duties"][0]
    assert payload["meta"]["solver_version"] == "test"
    assert payload["meta"]["performance"] == {"solver_ms": 12}
    assert "blocks" not in payload["cost_breakdown"]["vsp"]
    assert "duties" not in payload["cost_breakdown"]["csp"]
    assert payload["solver_explanation"]["issues"]["soft_count"] == 12
    assert len(payload["solver_explanation"]["issues"]["soft"]) == 10
    assert len(payload["trip_group_audit"]["sample_splits"]) == 5


def test_optimizer_result_compact_payload_keeps_operational_quality_decision_in_root_and_meta():
    trip = _trip(1, 360, 60, trip_group_id=77, direction="outbound")
    block = Block(id=1, trips=[trip], vehicle_type_id=1)
    duty = Duty(id=1)
    duty.add_task(block)

    decision = {
        "mode": "balanced",
        "chosen_scenario": "plus_one_duty",
        "chosen_title": "Plano mais equilibrado",
        "justification": ["Melhor equilibrio operacional."],
        "trade_offs": ["Exige +1 duty."],
        "rejected_scenarios": [{"scenario_id": "current_plan", "reason": "Mantem mais excecoes."}],
    }
    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[duty]),
        meta={
            "chosen_scenario": "plus_one_duty",
            "rejected_scenarios": decision["rejected_scenarios"],
            "justification": decision["justification"],
            "trade_offs": decision["trade_offs"],
            "operational_quality_decision": decision,
        },
    )

    payload = result.as_compact_dict()

    assert payload["chosen_scenario"] == "plus_one_duty"
    assert payload["operational_quality_decision"]["chosen_scenario"] == "plus_one_duty"
    assert payload["meta"]["chosen_scenario"] == "plus_one_duty"
    assert payload["meta"]["justification"] == ["Melhor equilibrio operacional."]
    assert payload["meta"]["trade_offs"] == ["Exige +1 duty."]
    assert payload["meta"]["operational_quality_decision"]["chosen_scenario"] == "plus_one_duty"


def test_run_optimization_task_returns_compact_payload(monkeypatch):
    trip = _trip(1, 360, 60)
    block = Block(id=1, trips=[trip], vehicle_type_id=1)
    duty = Duty(id=1)
    duty.add_task(block)

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block], meta={"input": {"min_layover_minutes": 8}}),
        csp=CSPSolution(duties=[duty], meta={"input": {"meal_break_minutes": 60}}),
        meta={"solver_version": "test"},
    )
    breakdown = CostEvaluator().total_cost_breakdown(result, _vehicle())
    result.total_cost = breakdown["total"]
    result.meta["cost_breakdown"] = breakdown

    class DummyService:
        def run(self, *args, **kwargs):
            return result

    monkeypatch.setattr("src.services.optimizer_tasks.OptimizerService", lambda: DummyService())

    response = run_optimization_task(
        {
            "trips": [trip.__dict__],
            "vehicle_types": [VehicleType(
                id=1,
                name="Standard",
                passenger_capacity=40,
            ).__dict__],
            "algorithm": "greedy",
            "run_id": 99,
            "line_id": 1,
            "company_id": 1,
        }
    )

    assert response["_is_error"] is False
    compact = response["result"]
    assert compact["blocks"][0]["trips"] == [1]
    assert compact["duties"][0]["trips"] == [1]
    assert compact["meta"]["run_id"] == 99


def test_build_optimize_response_recovers_operational_quality_fields_from_meta():
    raw = {
        "vehicles": 1,
        "crew": 1,
        "total_trips": 1,
        "total_cost": 10.0,
        "cct_violations": 0,
        "unassigned_trips": 0,
        "uncovered_blocks": 0,
        "vsp_algorithm": "greedy",
        "csp_algorithm": "greedy",
        "elapsed_ms": 1.0,
        "blocks": [{"block_id": 1, "trips": [1], "num_trips": 1, "start_time": 360, "end_time": 420}],
        "duties": [{"duty_id": 1, "blocks": [1], "trip_ids": [1], "work_time": 60, "spread_time": 60, "rest_violations": 0}],
        "meta": {
            "chosen_scenario": "current_plan",
            "rejected_scenarios": [{"scenario_id": "plus_one_duty"}],
            "justification": ["Plano atual atende ao criterio."],
            "trade_offs": ["Nao adiciona duty extra."],
            "operational_quality_decision": {"chosen_scenario": "current_plan"},
        },
    }

    response = _build_optimize_response(raw, 1)

    assert response.chosen_scenario == "current_plan"
    assert response.rejected_scenarios == [{"scenario_id": "plus_one_duty"}]
    assert response.justification == ["Plano atual atende ao criterio."]
    assert response.trade_offs == ["Nao adiciona duty extra."]
    assert response.operational_quality_decision["chosen_scenario"] == "current_plan"


def test_hybrid_group_audit_fallback_is_skipped_for_large_instances(monkeypatch):
    trips = [_trip(tid, 300 + (tid * 10), 8) for tid in range(1, 222)]
    blocks = [Block(id=idx, trips=[trip]) for idx, trip in enumerate(trips, start=1)]
    result = OptimizationResult(
        vsp=VSPSolution(blocks=blocks, algorithm="hybrid_pipeline"),
        csp=CSPSolution(duties=[]),
    )

    service = OptimizerService()
    dispatch_calls: list[AlgorithmType] = []

    def fake_dispatch(algorithm, *args, **kwargs):
        dispatch_calls.append(algorithm)
        return result

    monkeypatch.setattr(service, "_dispatch", fake_dispatch)
    monkeypatch.setattr(service, "_build_trip_group_audit", lambda *args, **kwargs: {"split_groups": 5, "same_roster_ratio": 0.4})
    monkeypatch.setattr(service, "_ensure_deadhead_coverage", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_inject_trip_group_constraints", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_ensure_vsp_operational_warnings", lambda *args, **kwargs: None)
    monkeypatch.setattr(service.validator, "audit_input", lambda *args, **kwargs: {"ok": True, "issues": []})
    monkeypatch.setattr(service.validator, "audit_result", lambda *args, **kwargs: {"ok": True, "issues": []})
    monkeypatch.setattr(service.evaluator, "total_cost_breakdown", lambda *args, **kwargs: {"total": 0.0, "vsp": {"total": 0.0}, "csp": {"total": 0.0}})
    monkeypatch.setattr(service, "_build_operational_kpis", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_build_phase_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_build_reproducibility_snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_build_solver_explanation", lambda *args, **kwargs: {})

    service.run(
        trips,
        _vehicle(),
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        cct_params={"strict_hard_validation": False},
        vsp_params={},
        time_budget_s=30.0,
    )

    assert dispatch_calls == [AlgorithmType.HYBRID_PIPELINE]
    assert result.meta["performance"]["group_audit_fallback_skipped"]["reason"] == "instance_scale_guard"


def test_hybrid_pipeline_skips_vsp_metaheuristics_for_scaled_instances(monkeypatch):
    trips = [_trip(tid, 300 + (tid * 10), 8) for tid in range(1, 510)]
    baseline_blocks = [Block(id=idx, trips=[trip]) for idx, trip in enumerate(trips, start=1)]
    baseline_vsp = VSPSolution(blocks=baseline_blocks, algorithm="mcnf_vsp")

    monkeypatch.setattr("src.algorithms.hybrid.pipeline.MCNFVSP.solve", lambda self, *args, **kwargs: baseline_vsp)
    # For n≥500, pipeline also runs GreedyVSP to pick the best VSP baseline.
    # n=229 is below that threshold so GreedyVSP won't be called, but mock it
    # defensively to prevent accidental real-execution if the threshold changes.
    monkeypatch.setattr("src.algorithms.hybrid.pipeline.GreedyVSP.solve", lambda self, *args, **kwargs: baseline_vsp)
    monkeypatch.setattr("src.algorithms.hybrid.pipeline._vsp_cost", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("src.algorithms.hybrid.pipeline._vsp_hard_issue_count", lambda *args, **kwargs: 0)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("metaheuristic should have been skipped")

    monkeypatch.setattr("src.algorithms.hybrid.pipeline.SimulatedAnnealingVSP.solve", _should_not_run)
    monkeypatch.setattr("src.algorithms.hybrid.pipeline.TabuSearchVSP.solve", _should_not_run)
    monkeypatch.setattr("src.algorithms.hybrid.pipeline.GeneticVSP.solve", _should_not_run)
    monkeypatch.setattr(
        "src.algorithms.hybrid.pipeline.HybridPipeline._finalize",
        lambda self, vsp_sol, trips, vehicle_types, phase_timings_ms=None: OptimizationResult(
            vsp=vsp_sol,
            csp=CSPSolution(duties=[]),
            total_elapsed_ms=1.0,
            meta={"phase_timings_ms": phase_timings_ms or {}},
        ),
    )

    result = HybridPipeline(time_budget_s=30.0, cct_params={}, vsp_params={}).solve(trips, _vehicle())

    # Both MCNF and Greedy return the same mock (equal blocks/cost) — MCNF kept (no strict improvement).
    assert result.vsp.algorithm == "mcnf_vsp"
    assert baseline_vsp.meta["performance"]["vsp_metaheuristics_skipped"]["reason"] == "instance_scale_guard"


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
    # Duty overhead: 2 duties * 500.0 = 1000.0; total = 16.67 + 1000.0
    assert breakdown["duty_overhead_cost"] == pytest.approx(1000.0)
    assert breakdown["total"] == pytest.approx(1016.67)


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
    assert result.meta["run_snapshot"]["trips_hash"] == result.meta["reproducibility"]["input_hash"]
    assert result.meta["run_snapshot"]["resolved_params"]["cct_params"]["strict_hard_validation"] is True
    assert result.meta["performance"]["phase_timings_ms"]["input_validation_ms"] >= 0
    assert result.meta["performance"]["phase_timings_ms"]["solver_ms"] >= 0
    assert result.meta["performance"]["phase_timings_ms"]["output_validation_ms"] >= 0
    assert result.meta["performance"]["phase_timings_ms"]["audit_enrichment_ms"] >= 0


def test_operational_quality_defaults_to_balanced_and_sets_current_plan_when_missing():
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
        optimization_params={},
    )

    payload = result.as_compact_dict()

    assert result.meta["chosen_scenario"] == "current_plan"
    assert result.meta["operational_quality_decision"]["mode"] == "balanced"
    assert result.meta["operational_quality_decision"]["chosen_scenario"] == "current_plan"
    assert payload["chosen_scenario"] == "current_plan"
    assert payload["operational_quality_decision"]["chosen_scenario"] == "current_plan"
    assert payload["meta"]["chosen_scenario"] == "current_plan"


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
        _vehicle(),
        AlgorithmType.HYBRID_PIPELINE,
        {"max_shift_minutes": 480},
        {"random_seed": 7, "time_budget_s": 9},
        {},
        stage="output_validation",
    )

    assert payload["phase"] == "csp"
    assert payload["infeasibility_explanation"]["reason"] == "spread_limit"
    assert payload["issue_count"] == 2
    assert payload["input_snapshot"]["trip_count"] == 2
    assert payload["input_snapshot"]["input_hash"]
    assert payload["input_snapshot"]["params_hash"]
    assert payload["input_snapshot"]["time_budget_s"] == pytest.approx(9.0)
    assert payload["run_snapshot"]["seed"] == 7


def test_optimize_route_returns_structured_diagnostics_on_failure():
    service = OptimizerService()
    trips = [
        _trip(1, 360, 420, origin=1, dest=1, distance=10.0),  # origin == dest triggers INVALID_TERMINAL_LOOP
    ]
    
    with pytest.raises(HardConstraintViolationError) as excinfo:
        service.run(
            trips,
            [],
            algorithm=AlgorithmType.HYBRID_PIPELINE,
            cct_params={"strict_hard_validation": True},
            vsp_params={"min_layover_minutes": 30, "random_seed": 11},
        )
    
    payload = excinfo.value.details
    assert payload["code"] == "HARD_CONSTRAINT_VIOLATION"
    assert payload["kind"] == "hard_constraint_violation"
    assert payload["stage"] == "input_validation"
    assert payload["issue_count"] > 0
    assert payload["infeasibility_explanation"]["reason"] == "hard_constraints"


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


def test_missing_random_seed_is_derived_deterministically_from_input_and_params():
    trips = [
        _trip(1, 360, 60, origin=1, dest=2),
        _trip(2, 450, 60, origin=2, dest=1),
        _trip(3, 570, 60, origin=1, dest=2),
        _trip(4, 660, 60, origin=2, dest=1),
    ]
    service = OptimizerService()
    params = {"preserve_preferred_pairs": True, "min_layover_minutes": 30}

    result_a = service.run(trips, _vehicle(), algorithm=AlgorithmType.HYBRID_PIPELINE, vsp_params=params, time_budget_s=4.0)
    result_b = service.run(trips, _vehicle(), algorithm=AlgorithmType.HYBRID_PIPELINE, vsp_params=params, time_budget_s=4.0)

    signature_a = [[trip.id for trip in block.trips] for block in result_a.vsp.blocks]
    signature_b = [[trip.id for trip in block.trips] for block in result_b.vsp.blocks]
    seed_a = result_a.meta["run_snapshot"]["seed"]
    seed_b = result_b.meta["run_snapshot"]["seed"]

    assert seed_a == seed_b
    assert seed_a is not None
    assert result_a.meta["run_snapshot"]["resolved_params"]["vsp_params"]["random_seed"] == seed_a
    assert result_b.meta["run_snapshot"]["resolved_params"]["vsp_params"]["random_seed"] == seed_b
    assert signature_a == signature_b
