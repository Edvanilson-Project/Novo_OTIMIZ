import json
from pathlib import Path

import pytest

from src.algorithms.csp.greedy import GreedyCSP, _nocturnal_overlap
from src.algorithms.vsp import simulated_annealing as sa_module
from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.algorithms.vsp.greedy import GreedyVSP
from src.core.exceptions import OptimizerError
from src.domain.models import AlgorithmType, Block, CSPSolution, Duty, OptimizationResult, Trip, VSPSolution
from src.services.optimizer_service import OptimizerService


def _make_trip(
    trip_id: int,
    start: int,
    end: int,
    origin: int = 1,
    destination: int = 2,
    line_id: int = 1,
) -> Trip:
    return Trip(
        id=trip_id,
        line_id=line_id,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=destination,
        duration=end - start,
        deadhead_times={origin: 0, destination: 0},
    )


def _load_chunk_fixture(name: str) -> tuple[list[Trip], dict]:
    payload = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / name).read_text())
    trips = [
        Trip(
            id=int(row["id"]),
            line_id=int(row["line_id"]),
            start_time=int(row["start_time"]),
            end_time=int(row["end_time"]),
            origin_id=int(row["origin_id"]),
            destination_id=int(row["destination_id"]),
            trip_group_id=row.get("trip_group_id"),
            direction=row.get("direction"),
            duration=int(row.get("duration") or (int(row["end_time"]) - int(row["start_time"]))),
            distance_km=float(row.get("distance_km") or 0.0),
            original_trip_id=row.get("original_trip_id"),
        )
        for row in payload["trips"]
    ]
    return trips, dict(payload["params"])


def test_wrap_around_midnight_nocturnal_and_service_day_is_stable():
    trip_night = _make_trip(1, 23 * 60, 26 * 60)
    block_night = Block(id=10, trips=[trip_night], vehicle_type_id=1)

    # 23:00 -> 02:00 = 180 min dentro da janela noturna 22:00-05:00.
    nocturnal_minutes = _nocturnal_overlap(
        trip_night.start_time,
        trip_night.end_time,
        22,
        5,
    )

    solver = GreedyCSP(nocturnal_start_hour=22, nocturnal_end_hour=5)
    next_block = Block(id=11, trips=[_make_trip(2, 26 * 60, 27 * 60)], vehicle_type_id=1)

    assert nocturnal_minutes == 180
    assert nocturnal_minutes >= 0
    assert solver._service_day(block_night) == 0
    assert solver._service_day(next_block) == 1


def test_split_shift_spread_12h_work_8h_has_zero_overtime():
    duty = Duty(id=101, work_time=8 * 60, spread_time=12 * 60)

    solution = GreedyCSP(
        max_shift_minutes=12 * 60,
        max_work_minutes=8 * 60,
        overtime_limit_minutes=120,
    ).finalize_selected_duties([duty])

    assert solution.duties[0].overtime_minutes == 0
    assert solution.cct_violations == 0


def test_big_m_one_million_and_graceful_fallback_on_impossible_case(monkeypatch):
    try:
        import pulp  # noqa: F401
    except Exception:
        pytest.skip("PuLP/CBC indisponível no ambiente")

    import src.algorithms.csp.set_partitioning_optimized as sp_opt

    if not sp_opt._PULP_AVAILABLE:
        pytest.skip("set_partitioning_optimized sem PuLP no ambiente")

    captured_slack_coeffs = []

    def _fake_solve(lp_problem, *args, **kwargs):
        # Captura coeficientes da função objetivo para variáveis slack.
        for var, coef in lp_problem.objective.items():
            if var.name.startswith("s_") or var.name.startswith("s_int_"):
                captured_slack_coeffs.append(float(coef))

        # Simula solução "ótima" porém com uso de slack > 0 para acionar fallback gracioso.
        lp_problem.status = sp_opt.pulp.constants.LpStatusOptimal
        for var in lp_problem.variables():
            if var.name.startswith("s_int_"):
                var.varValue = 1.0
            else:
                var.varValue = 0.0
        return lp_problem.status

    monkeypatch.setattr(sp_opt.pulp.LpProblem, "solve", _fake_solve)

    long_trip = _make_trip(99, 6 * 60, 26 * 60)  # 20h contínuas
    block = Block(id=99, trips=[long_trip], vehicle_type_id=1)

    solver = SetPartitioningOptimizedCSP(
        vsp_params={
            "pricing_enabled": False,
            "max_generated_columns": 64,
            "max_candidate_successors_per_task": 4,
        },
        max_shift_minutes=8 * 60,
        max_work_minutes=8 * 60,
        overtime_limit_minutes=0,
    )

    solution = solver.solve([block], [long_trip])

    assert isinstance(solution, CSPSolution)
    assert solution.meta.get("column_generation", {}).get("fallback") is True
    assert captured_slack_coeffs, "Nenhum coeficiente de slack foi capturado"
    # Big-M agora é dinâmico: max(max_col_cost * |tasks| + 1, 1000.0).
    # Validamos que a penalidade de slack está em escala "alta o suficiente"
    # (>= 1000 para garantir desincentivo) e que todos os coefs são iguais
    # entre si (uniformidade da Big-M dentro de uma mesma rodada).
    assert all(coef >= 1000.0 for coef in captured_slack_coeffs), (
        f"Big-M abaixo do piso 1000: {captured_slack_coeffs}"
    )
    first = captured_slack_coeffs[0]
    assert all(coef == pytest.approx(first) for coef in captured_slack_coeffs), (
        "Big-M não é uniforme entre slacks da mesma rodada"
    )


def test_greedy_single_trip_compaction_prepend_has_needed_defined():
    trips = [
        _make_trip(1, 0, 10, origin=1, destination=2),
        _make_trip(2, 500, 510, origin=2, destination=1),
    ]

    solution = GreedyVSP(
        vsp_params={
            "fixed_vehicle_activation_cost": 1,
            "max_connection_cost_for_reuse_ratio": 1.0,
            "idle_cost_per_minute": 1.0,
            "min_layover_minutes": 5,
            "enable_single_trip_compaction": True,
        }
    ).solve(trips, [])

    assert solution.blocks
    assert sum(len(block.trips) for block in solution.blocks) == 2


def test_group_repair_rejects_overlapping_mandatory_group():
    first = _make_trip(1, 100, 150, origin=1, destination=2)
    second = _make_trip(2, 140, 180, origin=2, destination=1)
    first.trip_group_id = 10
    second.trip_group_id = 10

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[Block(id=1, trips=[first]), Block(id=2, trips=[second])]),
        csp=CSPSolution(duties=[]),
    )

    with pytest.raises(OptimizerError) as exc:
        OptimizerService()._repair_split_trip_groups_with_dedicated_blocks(
            result,
            [first, second],
            {"strict_hard_constraints": True},
            {"strict_hard_constraints": True, "min_layover_minutes": 5},
            {},
        )

    assert exc.value.code == "GROUP_INFEASIBLE"
    assert exc.value.details["reason_code"] == "GROUP_OVERLAP_INFEASIBLE"


def test_sa_merge_handles_index_shift_when_right_block_removed_first(monkeypatch):
    trip_map = {
        1: _make_trip(1, 0, 10),
        2: _make_trip(2, 20, 30),
        3: _make_trip(3, 40, 50),
    }
    state = [[1], [2], [3]]

    monkeypatch.setattr(sa_module.random, "sample", lambda population, k: [2, 0])

    merged = sa_module._merge(state, trip_map, min_gap=0, min_break=0)

    assert merged is not None
    assert sorted(len(block) for block in merged) == [1, 2]
    assert sorted(trip.id for block in merged for trip in [trip_map[tid] for tid in block]) == [1, 2, 3]


def test_chunk_2000_index3_primary_hybrid_no_longer_raises_list_index_error():
    trips, params = _load_chunk_fixture("chunk_2000_index3.json")
    service = OptimizerService()

    try:
        result = service.run(
            trips=trips,
            vehicle_types=[],
            algorithm=AlgorithmType.HYBRID_PIPELINE,
            cct_params=dict(params),
            vsp_params={**dict(params), "disable_scale_decomposition": True},
            optimization_params=dict(params),
            time_budget_s=30.0,
        )
        assert result is not None
    except OptimizerError as exc:
        assert exc.code == "GROUP_INFEASIBLE"
        assert "list index out of range" not in str(exc)


def test_group_repair_surfaces_group_infeasible_for_connection_break():
    first = _make_trip(1, 100, 130, origin=1, destination=2)
    second = _make_trip(2, 132, 160, origin=3, destination=4)
    first.trip_group_id = 77
    second.trip_group_id = 77
    first.deadhead_times = {3: 15}

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[Block(id=1, trips=[first]), Block(id=2, trips=[second])]),
        csp=CSPSolution(duties=[]),
    )

    with pytest.raises(OptimizerError) as exc:
        OptimizerService()._repair_split_trip_groups_with_dedicated_blocks(
            result,
            [first, second],
            {"strict_hard_constraints": True, "min_break_minutes": 0},
            {"strict_hard_constraints": True, "min_layover_minutes": 5, "min_break_minutes": 0},
            {},
        )

    assert exc.value.code == "GROUP_INFEASIBLE"
    assert exc.value.details["reason_code"] == "GROUP_CONNECTION_INFEASIBLE"
    assert exc.value.details["trip_ids"] == [1, 2]


def test_scale_decomposition_thresholds_route_large_hybrid_only():
    service = OptimizerService()
    trips = [_make_trip(i, i * 10, i * 10 + 5) for i in range(1, 2001)]
    cct = {"strict_hard_constraints": True}
    vsp = {"strict_hard_constraints": True}
    profile = service._build_scale_profile(trips, cct, vsp)

    assert profile["mode"] == "decomposed_required"
    assert service._should_use_scale_decomposition(AlgorithmType.HYBRID_PIPELINE, trips, cct, vsp, profile)
    assert not service._should_use_scale_decomposition(AlgorithmType.GREEDY, trips, cct, vsp, profile)


def test_trip_group_payload_divergence_is_rejected():
    service = OptimizerService()
    first = _make_trip(1, 100, 150, origin=1, destination=2)
    second = _make_trip(2, 160, 210, origin=2, destination=1)
    first.trip_group_id = 44
    second.trip_group_id = 44

    with pytest.raises(OptimizerError) as exc:
        service._build_group_inference_report(
            [first, second],
            {
                "trip_group_inference_mode": "optimizer_only",
                "backend_trip_group_stats": {
                    "group_count": 0,
                    "grouped_trip_count": 0,
                    "max_group_size": 0,
                },
            },
        )

    assert exc.value.code == "TRIP_GROUP_PAYLOAD_DIVERGENCE"
    assert exc.value.details["backend_trip_group_stats"]["group_count"] == 0
    assert exc.value.details["optimizer_input_stats"]["group_count"] == 1


def test_scale_failure_hard_constraint_report_extracts_problem_groups():
    report = OptimizerService()._build_scale_failure_hard_constraint_report(
        [
            {
                "chunk_index": 3,
                "error": "Hard constraints violated: MANDATORY_GROUP_SPLIT [25043, 25047]; MANDATORY_GROUP_SPLIT [25045, 25054]",
            }
        ]
    )

    assert report["ok"] is False
    assert report["problem_trip_groups"] == [[25043, 25047], [25045, 25054]]
    assert any("25043" in issue for issue in report["issues"])


def test_scale_partition_never_splits_trip_group():
    service = OptimizerService()
    trips = []
    for i in range(1, 41):
        trip = _make_trip(i, i * 20, i * 20 + 10, line_id=1 + (i % 3))
        if i in {3, 17, 31}:
            trip.trip_group_id = 900
        elif i in {8, 9}:
            trip.trip_group_id = 901
        trips.append(trip)

    cct = {"strict_hard_constraints": True}
    vsp = {
        "strict_hard_constraints": True,
        "scale_chunk_target_trips": 6,
        "scale_chunk_max_trips": 8,
    }
    chunks = service._partition_scale_chunks(trips, cct, vsp)
    group_locations = {}
    for chunk in chunks:
        for trip in chunk["trips"]:
            if trip.trip_group_id is None:
                continue
            group_locations.setdefault(trip.trip_group_id, set()).add(chunk["index"])

    assert chunks
    assert all(len(locations) == 1 for locations in group_locations.values())
    assert all(chunk["trip_count"] <= 8 or len(chunk["trip_group_ids"]) == 1 for chunk in chunks)


def test_scale_stitching_keeps_blocks_separate_when_connection_invalid():
    service = OptimizerService()
    first = _make_trip(1, 100, 150, origin=1, destination=2)
    second = _make_trip(2, 155, 180, origin=3, destination=4)
    first.deadhead_times = {3: 30}
    blocks = [Block(id=1, trips=[first]), Block(id=2, trips=[second])]

    stitched, remap, meta = service._stitch_scale_blocks(
        blocks,
        {"strict_hard_constraints": True, "min_break_minutes": 5},
        {
            "strict_hard_constraints": True,
            "min_layover_minutes": 5,
            "scale_stitch_max_gap_minutes": 60,
        },
    )

    assert len(stitched) == 2
    assert remap == {1: 1, 2: 2}
    assert meta["accepted"] == 0
