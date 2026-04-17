import pytest

from src.algorithms.csp.greedy import GreedyCSP, _nocturnal_overlap
from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.domain.models import Block, CSPSolution, Duty, Trip


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
    assert all(coef == pytest.approx(1_000_000.0) for coef in captured_slack_coeffs)
