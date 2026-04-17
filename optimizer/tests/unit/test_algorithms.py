"""
Testes unitários dos algoritmos VSP e CSP.
Execute com: pytest tests/unit/test_algorithms.py -v
"""
from collections import Counter
import sys
import os

# Garante que o package raiz seja encontrado
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.domain.models import Block, Trip, VehicleType
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from src.algorithms.vsp.tabu_search import TabuSearchVSP
from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.integrated.joint_solver import JointSolver
from src.algorithms.evaluator import CostEvaluator
from src.services.optimizer_service import OptimizerService
from src.services import optimizer_service as optimizer_service_module
from src.domain.models import AlgorithmType, CSPSolution, OptimizationResult, VSPSolution


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_trips(n: int = 6) -> list:
    """Gera n viagens simples consecutivas (ida/volta alternadas)."""
    trips = []
    start = 360  # 06:00
    for i in range(n):
        origin = 1 if i % 2 == 0 else 2
        destination = 2 if i % 2 == 0 else 1
        t = Trip(
            id=i + 1,
            line_id=1,
            start_time=start,
            end_time=start + 60,
            origin_id=origin,
            destination_id=destination,
            duration=60,
            distance_km=20.0,
        )
        trips.append(t)
        start += 90  # 1h30 de intervalo
    return trips


def make_vehicle_types() -> list:
    return [
        VehicleType(
            id=1,
            name="Bus Standard",
            passenger_capacity=40,
            cost_per_km=2.0,
            cost_per_hour=50.0,
            fixed_cost=800.0,
        )
    ]


# ── VSP Greedy ────────────────────────────────────────────────────────────────

class TestGreedyVSP:
    def test_returns_solution(self):
        trips = make_trips(4)
        vt = make_vehicle_types()
        sol = GreedyVSP().solve(trips, vt)
        assert sol is not None
        assert sol.num_vehicles > 0

    def test_all_trips_covered(self):
        trips = make_trips(6)
        vt = make_vehicle_types()
        sol = GreedyVSP().solve(trips, vt)
        covered = {t.id for b in sol.blocks for t in b.trips}
        trip_ids = {t.id for t in trips}
        assert covered == trip_ids

    def test_empty_input(self):
        sol = GreedyVSP().solve([], [])
        assert sol.num_vehicles == 0

    def test_single_trip(self):
        trip = Trip(id=1, line_id=1, start_time=360, end_time=420, origin_id=1, destination_id=2)
        sol = GreedyVSP().solve([trip], make_vehicle_types())
        assert sol.num_vehicles == 1
        assert sol.blocks[0].trips[0].id == 1


# ── CSP Greedy ────────────────────────────────────────────────────────────────

class TestGreedyCSP:
    def test_covers_all_blocks(self):
        trips = make_trips(4)
        vsp = GreedyVSP().solve(trips, make_vehicle_types())
        csp = GreedyCSP().solve(vsp.blocks)
        # CSP run-cutting may split blocks into sub-tasks; verify all trip_ids are covered
        covered_trip_ids = {t.id for d in csp.duties for task in d.tasks for t in task.trips}
        original_trip_ids = {t.id for b in vsp.blocks for t in b.trips}
        assert covered_trip_ids == original_trip_ids

    def test_empty_blocks(self):
        csp = GreedyCSP().solve([])
        assert csp.num_crew == 0

    def test_skips_duplicate_tasks_with_same_trip_ids(self, monkeypatch):
        trips = make_trips(2)
        source_block = Block(id=1, trips=list(trips), meta={"source_block_id": 1})
        duplicated_tasks = [
            Block(id=101, trips=[trips[0]], meta={"source_block_id": 1}),
            Block(id=102, trips=[trips[0]], meta={"source_block_id": 1}),
            Block(id=103, trips=[trips[1]], meta={"source_block_id": 1}),
        ]

        def fake_prepare_tasks(_blocks):
            return duplicated_tasks, {
                "task_count": len(duplicated_tasks),
                "source_block_count": 1,
                "relief_cuts": 0,
                "run_cutting": "test_duplicate_tasks",
            }

        monkeypatch.setattr(GreedyCSP, "prepare_tasks", lambda self, blocks: fake_prepare_tasks(blocks))
        csp = GreedyCSP().solve([source_block])
        trip_id_counts = Counter(
            trip.id
            for duty in csp.duties
            for task in duty.tasks
            for trip in task.trips
        )

        assert trip_id_counts[trips[0].id] == 1
        assert trip_id_counts[trips[1].id] == 1
        assert csp.meta["duplicate_task_skips"] == 1

    def test_uses_real_pullout_and_pullback_only_on_boundary_trips(self):
        start_trip = Trip(
            id=1,
            line_id=1,
            start_time=360,
            end_time=420,
            origin_id=1,
            destination_id=2,
            duration=60,
            depot_id=1,
            is_pull_out=True,
            idle_before_minutes=18,
        )
        end_trip = Trip(
            id=2,
            line_id=1,
            start_time=450,
            end_time=510,
            origin_id=2,
            destination_id=1,
            duration=60,
            depot_id=1,
            is_pull_back=True,
            idle_after_minutes=12,
        )

        solution = GreedyCSP(
            min_break_minutes=30,
            max_shift_minutes=720,
            max_work_minutes=720,
            pullout_minutes=10,
            pullback_minutes=10,
        ).solve([
            Block(id=1, trips=[start_trip]),
            Block(id=2, trips=[end_trip]),
        ])

        assert len(solution.duties) == 1
        duty = solution.duties[0]
        assert duty.spread_time == (end_trip.end_time - start_trip.start_time) + 18 + 12
        assert duty.meta["start_buffer_minutes"] == 18
        assert duty.meta["end_buffer_minutes"] == 12
        assert duty.meta["duty_start_minutes"] == 342
        assert duty.meta["duty_end_minutes"] == 522
        assert solution.duties[0].tasks[0].meta["task_start_buffer_minutes"] == 18
        assert solution.duties[0].tasks[-1].meta["task_end_buffer_minutes"] == 12


def test_joint_solver_propagates_remaining_budget_to_subsolvers(monkeypatch):
    trips = make_trips(2)
    vehicle_types = make_vehicle_types()
    captured: dict[str, float] = {}

    class FakeVspSolver:
        def __init__(self):
            self.time_budget_s = 999.0

        def solve(self, trips, vehicle_types, depot_id=None):
            captured["vsp_budget"] = self.time_budget_s
            return VSPSolution(blocks=[Block(id=1, trips=list(trips))], algorithm="fake_vsp")

    class FakeCspSolver:
        def __init__(self):
            self.time_budget_s = 999.0
            self.greedy = type("GreedyBudgetHolder", (), {"time_budget_s": 999.0})()

        def solve(self, blocks, trips=None):
            captured["csp_budget"] = self.time_budget_s
            captured["csp_greedy_budget"] = self.greedy.time_budget_s
            return CSPSolution(duties=[], cct_violations=0)

    joint = JointSolver(time_budget_s=12.0, max_rounds=2, cct_params={}, vsp_params={})
    monkeypatch.setattr(joint, "_vsp_solver", lambda: FakeVspSolver())
    monkeypatch.setattr(joint, "_csp_solver", lambda: FakeCspSolver())

    joint.solve(trips, vehicle_types)

    assert captured["vsp_budget"] <= 12.0
    assert captured["csp_budget"] <= 12.0
    assert captured["csp_greedy_budget"] == captured["csp_budget"]


def test_optimizer_service_passes_time_budget_to_joint_solver(monkeypatch):
    trips = make_trips(2)
    vehicle_types = make_vehicle_types()
    captured: dict[str, float | None] = {"budget": None}

    class FakeJointSolver:
        def __init__(self, time_budget_s=None, cct_params=None, vsp_params=None, **kwargs):
            captured["budget"] = time_budget_s

        def solve(self, trips, vehicle_types, depot_id=None):
            return OptimizationResult(vsp=VSPSolution(blocks=[]), csp=CSPSolution())

    monkeypatch.setattr(optimizer_service_module, "JointSolver", FakeJointSolver)

    OptimizerService().run(
        trips,
        vehicle_types,
        algorithm=AlgorithmType.JOINT_SOLVER,
        time_budget_s=12.0,
    )

    assert captured["budget"] == 12.0

def test_falls_back_to_configured_pullout_and_pullback_without_flags():
    trip = Trip(
        id=1,
        line_id=1,
        start_time=360,
        end_time=420,
        origin_id=1,
        destination_id=2,
        duration=60,
    )

    solution = GreedyCSP(
        max_shift_minutes=720,
        max_work_minutes=720,
        pullout_minutes=11,
        pullback_minutes=13,
    ).solve([Block(id=1, trips=[trip])])

    assert len(solution.duties) == 1
    assert solution.duties[0].spread_time == 60 + 11 + 13


def test_operator_only_gets_boundary_ociosa_when_duty_touches_vehicle_edge():
    first = Trip(
        id=1,
        line_id=1,
        start_time=360,
        end_time=420,
        origin_id=1,
        destination_id=2,
        duration=60,
        idle_before_minutes=18,
    )
    last = Trip(
        id=2,
        line_id=1,
        start_time=540,
        end_time=600,
        origin_id=2,
        destination_id=3,
        duration=60,
        idle_after_minutes=12,
    )
    source_block = Block(id=1, trips=[first, last])

    solution = GreedyCSP(
        min_break_minutes=30,
        max_shift_minutes=180,
        max_work_minutes=180,
        pullout_minutes=10,
        pullback_minutes=10,
    ).solve([source_block])

    assert len(solution.duties) == 2
    duties = sorted(solution.duties, key=lambda duty: duty.meta["duty_start_minutes"])
    first_duty, last_duty = duties

    assert source_block.meta["start_buffer_minutes"] == 18
    assert source_block.meta["end_buffer_minutes"] == 12
    assert first_duty.meta["start_buffer_minutes"] == 18
    assert first_duty.meta["end_buffer_minutes"] == 0
    assert last_duty.meta["start_buffer_minutes"] == 0
    assert last_duty.meta["end_buffer_minutes"] == 12
    assert first_duty.spread_time == 78
    assert last_duty.spread_time == 72


def test_operator_change_requires_terminal_boundary():
    first = Trip(
        id=1,
        line_id=1,
        start_time=360,
        end_time=420,
        origin_id=1,
        destination_id=2,
        duration=60,
        depot_id=1,
    )
    second = Trip(
        id=2,
        line_id=1,
        start_time=450,
        end_time=510,
        origin_id=3,
        destination_id=4,
        duration=60,
        depot_id=2,
    )

    solution = GreedyCSP(
        min_break_minutes=30,
        max_shift_minutes=720,
        max_work_minutes=720,
        operator_change_terminals_only=True,
        allow_relief_points=False,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    assert len(solution.duties) == 2


def test_connection_tolerance_absorbs_small_transfer_deficit():
    first = Trip(
        id=1,
        line_id=1,
        start_time=360,
        end_time=420,
        origin_id=1,
        destination_id=2,
        duration=60,
        deadhead_times={2: 0},
    )
    second = Trip(
        id=2,
        line_id=1,
        start_time=428,
        end_time=488,
        origin_id=2,
        destination_id=3,
        duration=60,
    )

    without_tolerance = GreedyCSP(
        min_layover_minutes=10,
        min_break_minutes=0,
        max_shift_minutes=720,
        max_work_minutes=720,
        max_driving_minutes=240,
        connection_tolerance_minutes=0,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    with_tolerance = GreedyCSP(
        min_layover_minutes=10,
        min_break_minutes=0,
        max_shift_minutes=720,
        max_work_minutes=720,
        max_driving_minutes=240,
        connection_tolerance_minutes=2,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    assert len(without_tolerance.duties) == 2
    assert len(with_tolerance.duties) == 1
    duty = with_tolerance.duties[0]
    assert duty.meta["connection_tolerance_used_minutes"] == 2
    assert duty.meta["connection_tolerance_uses"] == 1
    assert duty.meta["adjusted_connections"][0]["adjustment_minutes"] == 2


def test_connection_tolerance_can_reset_break_for_small_gap_deficit():
    first = Trip(
        id=1,
        line_id=1,
        start_time=360,
        end_time=420,
        origin_id=1,
        destination_id=2,
        duration=60,
        deadhead_times={2: 0},
    )
    second = Trip(
        id=2,
        line_id=1,
        start_time=448,
        end_time=508,
        origin_id=2,
        destination_id=3,
        duration=60,
    )

    without_tolerance = GreedyCSP(
        min_layover_minutes=0,
        min_break_minutes=30,
        max_shift_minutes=720,
        max_work_minutes=720,
        max_driving_minutes=100,
        mandatory_break_after_minutes=100,
        connection_tolerance_minutes=0,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    with_tolerance = GreedyCSP(
        min_layover_minutes=0,
        min_break_minutes=30,
        max_shift_minutes=720,
        max_work_minutes=720,
        max_driving_minutes=100,
        mandatory_break_after_minutes=100,
        connection_tolerance_minutes=2,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    assert len(without_tolerance.duties) == 2
    assert len(with_tolerance.duties) == 1
    duty = with_tolerance.duties[0]
    assert duty.meta["max_continuous_drive_minutes"] == 60
    assert duty.meta["connection_tolerance_used_minutes"] == 2
    assert any("Ajuste fino de conexão aplicado" in warning for warning in duty.warnings)


def test_connection_tolerance_accepts_values_above_two_minutes():
    first = Trip(
        id=1,
        line_id=1,
        start_time=360,
        end_time=420,
        origin_id=1,
        destination_id=2,
        duration=60,
        deadhead_times={2: 0},
    )
    second = Trip(
        id=2,
        line_id=1,
        start_time=430,
        end_time=490,
        origin_id=2,
        destination_id=3,
        duration=60,
    )

    without_tolerance = GreedyCSP(
        min_layover_minutes=20,
        min_break_minutes=0,
        max_shift_minutes=720,
        max_work_minutes=720,
        max_driving_minutes=240,
        connection_tolerance_minutes=0,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    with_tolerance = GreedyCSP(
        min_layover_minutes=20,
        min_break_minutes=0,
        max_shift_minutes=720,
        max_work_minutes=720,
        max_driving_minutes=240,
        connection_tolerance_minutes=10,
    ).solve([
        Block(id=1, trips=[first]),
        Block(id=2, trips=[second]),
    ])

    assert len(without_tolerance.duties) == 2
    assert len(with_tolerance.duties) == 1
    duty = with_tolerance.duties[0]
    assert duty.meta["connection_tolerance_minutes"] == 10
    assert duty.meta["connection_tolerance_used_minutes"] == 10
    assert duty.meta["adjusted_connections"][0]["adjustment_minutes"] == 10


# ── SA VSP ────────────────────────────────────────────────────────────────────

class TestSimulatedAnnealingVSP:
    def test_returns_solution(self):
        trips = make_trips(5)
        sa = SimulatedAnnealingVSP()
        sa.time_budget_s = 2.0
        sol = sa.solve(trips, make_vehicle_types())
        assert sol.num_vehicles > 0


# ── Tabu VSP ──────────────────────────────────────────────────────────────────

class TestTabuSearchVSP:
    def test_returns_solution(self):
        trips = make_trips(5)
        ts = TabuSearchVSP()
        ts.time_budget_s = 2.0
        ts.max_iterations = 20
        sol = ts.solve(trips, make_vehicle_types())
        assert sol.num_vehicles > 0


# ── Evaluator ─────────────────────────────────────────────────────────────────

class TestCostEvaluator:
    def test_vsp_cost_positive(self):
        trips = make_trips(3)
        vt = make_vehicle_types()
        sol = GreedyVSP().solve(trips, vt)
        from src.domain.models import VSPSolution, CSPSolution, OptimizationResult
        csp = GreedyCSP().solve(sol.blocks)
        result = OptimizationResult(vsp=sol, csp=csp)
        ev = CostEvaluator()
        cost = ev.total_cost(result, vt)
        assert cost > 0

    def test_vsp_idle_proxy_prefers_block_boundary_buffers(self):
        block = Block(
            id=1,
            trips=[
                Trip(id=1, line_id=1, start_time=360, end_time=420, origin_id=1, destination_id=2, duration=60),
                Trip(id=2, line_id=1, start_time=430, end_time=490, origin_id=2, destination_id=3, duration=60),
            ],
            vehicle_type_id=1,
            meta={"start_buffer_minutes": 11, "end_buffer_minutes": 13},
        )
        sol = GreedyVSP().solve([], [])
        sol.blocks = [block]

        breakdown = CostEvaluator(idle_cost_per_minute=1.0).vsp_cost_breakdown(sol, make_vehicle_types())

        assert breakdown["advisory_idle_proxy_cost"] == 24.0
        assert breakdown["blocks"][0]["start_buffer_minutes"] == 11
        assert breakdown["blocks"][0]["end_buffer_minutes"] == 13


# ── OptimizerService ──────────────────────────────────────────────────────────

class TestOptimizerService:
    def test_greedy_pipeline(self):
        trips = make_trips(4)
        vt = make_vehicle_types()
        svc = OptimizerService()
        result = svc.run(trips, vt, algorithm=AlgorithmType.GREEDY)
        assert result.vsp.num_vehicles > 0
        assert result.csp.num_crew > 0
        assert result.total_cost > 0

    def test_hybrid_pipeline_small(self):
        trips = make_trips(6)
        vt = make_vehicle_types()
        svc = OptimizerService()
        result = svc.run(trips, vt, algorithm=AlgorithmType.HYBRID_PIPELINE, time_budget_s=5.0)
        assert result.vsp.num_vehicles > 0

    def test_empty_trips_raises(self):
        from src.core.exceptions import NoProblemDataError
        svc = OptimizerService()
        with pytest.raises(NoProblemDataError):
            svc.run([], [], algorithm=AlgorithmType.GREEDY)
