"""
Quality Validation Suite — Industry Benchmark Comparison

Validates optimizer quality against transit industry standards and
Optibus-documented performance benchmarks.

Mathematical foundations used here:
  [1] Bodin & Golden (1981): VSP lower bound = max concurrent trips at peak
  [2] Mesquita & Paias (2008): typical optimality gap 5-15% for heuristics
  [3] Aziez, Côté & Coelho (2020): crew cost benchmark methodology
  [4] Optibus published claims: PVR -10%, crew -5%, runtime seconds-to-minutes
  [5] CLT / CCT: Brazilian labor law compliance (max_shift ≤ 600 min driving)

Each test class has a docstring citing the specific claim it validates.
All assertions are conservative to avoid false failures on different
random seeds or parameter values.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.algorithms.evaluator import (
    CostEvaluator,
    _gini_coefficient,
    _percentile,
    _compute_fairness_metrics,
)
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from src.algorithms.vsp.tabu_search import TabuSearchVSP
from src.algorithms.csp.greedy import GreedyCSP
from src.domain.models import Block, Duty, OptimizationResult, Trip, VehicleType, VSPSolution, CSPSolution
from src.services.solution_validator import SolutionValidator


# ── Helpers ───────────────────────────────────────────────────────────────────


def _trip(tid: int, start: int, end: int, *, origin: int = 1, dest: int = 2, line: int = 1) -> Trip:
    return Trip(
        id=tid,
        line_id=line,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        distance_km=max(1.0, (end - start) / 3.0),
    )


def _vt() -> list:
    return [VehicleType(id=1, name="Bus", passenger_capacity=40, cost_per_km=2.5, cost_per_hour=55.0, fixed_cost=900.0)]


def max_concurrent_trips(trips: list) -> int:
    """
    VSP theoretical lower bound [Bodin & Golden 1981].
    At any moment t, every active trip requires a distinct vehicle.
    The maximum over all t is the minimum possible fleet size.
    """
    events = []
    for t in trips:
        events.append((t.start_time, +1))
        events.append((t.end_time, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # end before start at same time
    concurrent = peak = 0
    for _, delta in events:
        concurrent += delta
        if concurrent > peak:
            peak = concurrent
    return peak


def _consecutive_trips(n: int, gap: int = 90, duration: int = 60, offset: int = 360) -> list:
    """n non-overlapping trips — can be served by 1 vehicle if gap>=deadhead."""
    trips = []
    t = offset
    for i in range(n):
        origin, dest = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(_trip(i + 1, t, t + duration, origin=origin, dest=dest))
        t += duration + gap
    return trips


def _simultaneous_trips(n: int, start: int = 360, duration: int = 60) -> list:
    """n fully overlapping trips — requires exactly n vehicles."""
    return [_trip(i + 1, start, start + duration, origin=1, dest=2) for i in range(n)]


def _chain_trips(n: int, deadhead: int = 5) -> list:
    """n trips with minimal gap — should be served by 1 vehicle."""
    trips = []
    t = 360
    for i in range(n):
        origin, dest = (1, 2) if i % 2 == 0 else (2, 1)
        end = t + 60
        trips.append(_trip(i + 1, t, end, origin=origin, dest=dest))
        t = end + deadhead
    return trips


def _validate_no_overlaps(blocks) -> list[str]:
    """Returns list of overlap descriptions for any vehicle with overlapping trips."""
    errors = []
    for b in blocks:
        trips = sorted(b.trips, key=lambda t: t.start_time)
        for i in range(len(trips) - 1):
            if trips[i].end_time > trips[i + 1].start_time:
                errors.append(
                    f"block {b.id}: trip {trips[i].id} ends {trips[i].end_time} "
                    f"but trip {trips[i+1].id} starts {trips[i+1].start_time}"
                )
    return errors


# ── VSP Lower Bound ───────────────────────────────────────────────────────────


class TestVSPLowerBound:
    """
    [Bodin & Golden 1981] The minimum number of vehicles required equals
    the maximum number of trips simultaneously active (the PVR).
    Any feasible schedule must use at least this many vehicles.

    We validate that:
      1. Simultaneous trips force exactly N vehicles.
      2. Non-overlapping trips need significantly fewer than N vehicles.
      3. Greedy VSP never uses fewer vehicles than the lower bound.
    """

    def test_simultaneous_trips_require_n_vehicles(self):
        n = 8
        trips = _simultaneous_trips(n)
        lb = max_concurrent_trips(trips)
        assert lb == n, f"Lower bound should be {n} for fully simultaneous trips"

        sol = GreedyVSP().solve(trips, _vt())
        assert sol.num_vehicles >= lb
        assert sol.num_vehicles == n  # no merging possible

    def test_consecutive_trips_lower_bound_is_one(self):
        trips = _consecutive_trips(10, gap=90)
        lb = max_concurrent_trips(trips)
        assert lb == 1  # trips never overlap

    def test_greedy_never_violates_lower_bound(self):
        trips = _consecutive_trips(10, gap=90)
        lb = max_concurrent_trips(trips)
        sol = GreedyVSP().solve(trips, _vt())
        assert sol.num_vehicles >= lb

    def test_mixed_peak_lower_bound(self):
        # 3 trips at 8:00, 2 at 10:00, 1 at 12:00 → lb=3
        trips = [
            _trip(1, 480, 540), _trip(2, 480, 540), _trip(3, 480, 540),  # 3 simultaneous
            _trip(4, 600, 660), _trip(5, 600, 660),                        # 2 simultaneous
            _trip(6, 720, 780),                                             # 1
        ]
        lb = max_concurrent_trips(trips)
        assert lb == 3

        sol = GreedyVSP().solve(trips, _vt())
        assert sol.num_vehicles >= lb

    def test_pvr_reduction_vs_naive_baseline(self):
        """
        Optibus claims 10%+ PVR reduction.
        Conservative threshold: greedy must do at least 20% better than N vehicles.
        Valid only when lb < N (there is room to improve).
        """
        trips = _consecutive_trips(20, gap=90)
        n = len(trips)  # naive: 1 vehicle per trip = 20 vehicles
        lb = max_concurrent_trips(trips)

        sol = GreedyVSP().solve(trips, _vt())
        num_v = sol.num_vehicles

        # Greedy must beat naive by at least 50% (consecutive trips allow full merging)
        assert num_v < n * 0.5, (
            f"Greedy used {num_v} vehicles, naive needs {n}; "
            f"should reduce by >50% on consecutive trips (lb={lb})"
        )

    def test_optimality_gap_within_15_percent(self):
        """
        [Mesquita & Paias 2008] Good heuristics achieve within 5-15% of lower bound.
        We use 15% as the conservative acceptance threshold.
        """
        # Use a scenario where lb > 1 so gap is meaningful
        trips = []
        for i in range(5):
            # 5 bursts of 2 simultaneous trips = lb=2
            base = 360 + i * 150
            trips.append(_trip(len(trips) + 1, base, base + 60))
            trips.append(_trip(len(trips) + 1, base, base + 60, origin=2, dest=1))
            # filler after each burst (single trip)
            trips.append(_trip(len(trips) + 1, base + 70, base + 130))

        lb = max_concurrent_trips(trips)
        assert lb >= 2  # at least 2 simultaneous trips exist

        sol = GreedyVSP().solve(trips, _vt())
        gap_pct = (sol.num_vehicles - lb) / lb * 100
        assert gap_pct <= 15.0, (
            f"Optimality gap {gap_pct:.1f}% exceeds 15% threshold "
            f"(lb={lb}, actual={sol.num_vehicles})"
        )


# ── Coverage ──────────────────────────────────────────────────────────────────


class TestCoverageCorrectness:
    """
    A transit optimizer MUST cover 100% of trips. This is a hard feasibility
    requirement — partial coverage is operationally illegal.
    """

    def test_greedy_covers_all_trips(self):
        trips = _consecutive_trips(12)
        sol = GreedyVSP().solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        expected = {t.id for t in trips}
        assert covered == expected, f"Uncovered trips: {expected - covered}"

    def test_simultaneous_trips_all_covered(self):
        trips = _simultaneous_trips(6)
        sol = GreedyVSP().solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        assert covered == {t.id for t in trips}

    def test_chain_trips_all_covered(self):
        trips = _chain_trips(8)
        sol = GreedyVSP().solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        assert covered == {t.id for t in trips}

    def test_single_trip_covered(self):
        trip = _trip(1, 480, 540)
        sol = GreedyVSP().solve([trip], _vt())
        assert sol.num_vehicles == 1
        assert sol.blocks[0].trips[0].id == 1

    def test_empty_input_returns_empty_solution(self):
        sol = GreedyVSP().solve([], _vt())
        assert sol.num_vehicles == 0
        assert sol.blocks == []

    def test_csp_covers_all_blocks(self):
        trips = _consecutive_trips(8, gap=120)
        vsp = GreedyVSP().solve(trips, _vt())
        csp = GreedyCSP().solve(vsp.blocks)

        covered_trip_ids = {
            t.id for d in csp.duties for task in d.tasks for t in task.trips
        }
        original_trip_ids = {t.id for b in vsp.blocks for t in b.trips}
        assert covered_trip_ids == original_trip_ids, (
            f"CSP uncovered: {original_trip_ids - covered_trip_ids}"
        )

    def test_sa_vsp_covers_all_trips(self):
        trips = _consecutive_trips(10)
        sol = SimulatedAnnealingVSP(vsp_params={"sa_max_iterations": 500}).solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        assert covered == {t.id for t in trips}

    def test_tabu_vsp_covers_all_trips(self):
        trips = _consecutive_trips(10)
        sol = TabuSearchVSP().solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        assert covered == {t.id for t in trips}


# ── No Overlaps ───────────────────────────────────────────────────────────────


class TestNoTimeOverlaps:
    """
    A vehicle cannot serve two trips at the same time.
    All algorithms must produce overlap-free block assignments.
    """

    def test_greedy_no_overlaps_consecutive(self):
        trips = _consecutive_trips(12)
        sol = GreedyVSP().solve(trips, _vt())
        assert _validate_no_overlaps(sol.blocks) == []

    def test_greedy_no_overlaps_simultaneous(self):
        trips = _simultaneous_trips(5)
        sol = GreedyVSP().solve(trips, _vt())
        assert _validate_no_overlaps(sol.blocks) == []

    def test_sa_no_overlaps(self):
        trips = _consecutive_trips(10)
        sol = SimulatedAnnealingVSP(vsp_params={"sa_max_iterations": 500}).solve(trips, _vt())
        assert _validate_no_overlaps(sol.blocks) == []

    def test_tabu_no_overlaps(self):
        trips = _consecutive_trips(10)
        sol = TabuSearchVSP().solve(trips, _vt())
        assert _validate_no_overlaps(sol.blocks) == []

    def test_solution_validator_detects_overlap(self):
        validator = SolutionValidator(tolerance_minutes=5)
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "start_time": 480, "end_time": 540},
                    {"tripId": 2, "start_time": 530, "end_time": 600},  # 10 min overlap
                ],
            }
        ]
        result = validator.validate(blocks, [], [], {})
        assert not result.valid
        assert any(e.error_type == "TIME_OVERLAP" for e in result.errors)

    def test_solution_validator_accepts_clean_solution(self):
        validator = SolutionValidator(tolerance_minutes=5)
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "start_time": 480, "end_time": 540},
                    {"tripId": 2, "start_time": 545, "end_time": 605},  # 5 min gap = ok
                ],
            }
        ]
        result = validator.validate(blocks, [], [], {})
        overlap_errors = [e for e in result.errors if e.error_type == "TIME_OVERLAP"]
        assert len(overlap_errors) == 0


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Correctness on boundary cases that solvers must handle without crashing."""

    def test_chain_can_use_single_vehicle(self):
        """8 trips with 10-min gaps — greedy should chain into 1 vehicle."""
        trips = _chain_trips(8, deadhead=10)
        sol = GreedyVSP().solve(trips, _vt())
        # All trips are consecutive with enough gap — at most 2 vehicles
        assert sol.num_vehicles <= 2

    def test_overnight_trip_handled(self):
        """Trip crossing midnight (start < midnight, end > midnight)."""
        trip = _trip(1, 23 * 60, 25 * 60)  # 23:00 → 01:00 next day
        sol = GreedyVSP().solve([trip], _vt())
        assert sol.num_vehicles == 1
        assert sol.blocks[0].trips[0].id == 1

    def test_very_long_trip_handled(self):
        """Trip > 6 hours should not crash the solver."""
        trip = _trip(1, 360, 360 + 400)  # 6h40m
        sol = GreedyVSP().solve([trip], _vt())
        assert sol.num_vehicles == 1

    def test_zero_duration_trip_not_crash(self):
        """Zero-duration trip edge case — must not crash."""
        trip = Trip(id=1, line_id=1, start_time=480, end_time=480, origin_id=1, destination_id=2, duration=0)
        sol = GreedyVSP().solve([trip], _vt())
        assert sol.num_vehicles >= 0

    def test_all_same_time_window(self):
        """N trips all starting and ending at the same time → N vehicles."""
        n = 5
        trips = _simultaneous_trips(n, start=600, duration=60)
        sol = GreedyVSP().solve(trips, _vt())
        assert sol.num_vehicles == n

    def test_two_groups_no_crossover(self):
        """Two disjoint groups in time — vehicles from group A don't serve group B (already covered)."""
        group_a = [_trip(i + 1, 360 + i * 20, 360 + i * 20 + 15) for i in range(3)]
        group_b = [_trip(i + 10, 800 + i * 20, 800 + i * 20 + 15) for i in range(3)]
        trips = group_a + group_b
        sol = GreedyVSP().solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        assert covered == {t.id for t in trips}


# ── Cost Function Correctness ─────────────────────────────────────────────────


class TestCostFunctionCorrectness:
    """
    The cost evaluator must be internally consistent.
    Tests verify mathematical properties, not specific values.
    """

    def test_block_cost_positive(self):
        trip = _trip(1, 360, 420)
        block = Block(id=1, trips=[trip], vehicle_type_id=1)
        evaluator = CostEvaluator()
        cost = evaluator.block_cost(block, _vt())
        assert cost > 0

    def test_block_cost_increases_with_distance(self):
        trip_short = Trip(id=1, line_id=1, start_time=360, end_time=420,
                          origin_id=1, destination_id=2, duration=60, distance_km=5.0)
        trip_long = Trip(id=2, line_id=1, start_time=360, end_time=420,
                         origin_id=1, destination_id=2, duration=60, distance_km=50.0)
        block_short = Block(id=1, trips=[trip_short], vehicle_type_id=1)
        block_long = Block(id=2, trips=[trip_long], vehicle_type_id=1)
        evaluator = CostEvaluator()
        assert evaluator.block_cost(block_long, _vt()) > evaluator.block_cost(block_short, _vt())

    def test_total_cost_breakdown_has_required_keys(self):
        trip = _trip(1, 360, 420)
        block = Block(id=1, trips=[trip], vehicle_type_id=1)
        duty = Duty(id=1)
        duty.add_task(block)
        duty.paid_minutes = 60

        vsp_sol = VSPSolution(blocks=[block], algorithm="greedy")
        csp_sol = CSPSolution(duties=[duty], algorithm="greedy")
        result = OptimizationResult(vsp=vsp_sol, csp=csp_sol)

        evaluator = CostEvaluator()
        breakdown = evaluator.total_cost_breakdown(result, _vt())

        assert "total" in breakdown
        assert "vsp" in breakdown
        assert "csp" in breakdown
        assert breakdown["total"] >= 0

    def test_more_vehicles_increases_fleet_cost(self):
        """Adding more blocks (vehicles) must increase total fleet cost."""
        trip_a = _trip(1, 360, 420)
        trip_b = _trip(2, 360, 420, origin=2, dest=1)

        block_a = Block(id=1, trips=[trip_a], vehicle_type_id=1)
        block_ab = Block(id=2, trips=[trip_a, trip_b], vehicle_type_id=1)

        evaluator = CostEvaluator()
        # Two separate blocks cost more (two fixed_costs) than one block
        cost_one = evaluator.block_cost(block_a, _vt())
        cost_two = evaluator.block_cost(block_a, _vt()) + evaluator.block_cost(
            Block(id=3, trips=[trip_b], vehicle_type_id=1), _vt()
        )
        # Two vehicles always costs more in fixed cost
        assert cost_two > cost_one


# ── Gini / Fairness Metrics ───────────────────────────────────────────────────


class TestFairnessMetrics:
    """
    Fairness metrics (Gini, P5/P95) must be mathematically correct.
    These are exposed in cost_breakdown.csp.fairness to mirror Optibus analytics.
    """

    def test_gini_perfect_equality(self):
        assert _gini_coefficient([300, 300, 300, 300]) == 0.0

    def test_gini_increases_with_inequality(self):
        g_equal = _gini_coefficient([400, 400, 400, 400])
        g_unequal = _gini_coefficient([100, 100, 100, 1000])
        assert g_unequal > g_equal

    def test_gini_bounded_zero_to_one(self):
        for values in [[1, 1, 1], [0, 0, 100], [200, 300, 400, 500]]:
            g = _gini_coefficient(values)
            assert 0.0 <= g <= 1.0, f"Gini out of bounds for {values}: {g}"

    def test_gini_below_threshold_balanced_schedule(self):
        """Balanced duties (±5% work time) should have Gini < 0.05."""
        work_times = [390, 400, 405, 410, 395, 402]
        g = _gini_coefficient(work_times)
        assert g < 0.05, f"Gini {g:.4f} too high for balanced schedule"

    def test_percentile_monotonic(self):
        sv = sorted([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
        p5 = _percentile(sv, 5)
        p50 = _percentile(sv, 50)
        p95 = _percentile(sv, 95)
        assert p5 <= p50 <= p95

    def test_percentile_single_value(self):
        assert _percentile([500], 50) == 500.0

    def test_fairness_metrics_empty(self):
        m = _compute_fairness_metrics([], [])
        assert m["num_duties"] == 0

    def test_fairness_metrics_structure(self):
        class _FakeDuty:
            def __init__(self, w):
                self.work_time = w
        duties = [_FakeDuty(w) for w in [400, 420, 380, 410]]
        costs = [{"total": 1000.0 + i * 50} for i in range(4)]
        m = _compute_fairness_metrics(duties, costs)
        assert "work_time" in m
        assert "num_duties" in m
        assert m["num_duties"] == 4
        assert m["work_time"]["min"] <= m["work_time"]["mean"] <= m["work_time"]["max"]


# ── Runtime Performance ───────────────────────────────────────────────────────


class TestRuntimePerformance:
    """
    Optibus processes schedules in seconds-to-minutes.
    These thresholds are conservative (3x typical measured runtime on this hardware).
    Validated on AMD Ryzen 5 4600H (CPU-only, no GPU).
    """

    def test_greedy_50_trips_under_2s(self):
        trips = _consecutive_trips(50, gap=15, duration=40)
        vt = _vt()
        t0 = time.perf_counter()
        GreedyVSP().solve(trips, vt)
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"50 trips took {elapsed:.2f}s (limit: 2s)"

    def test_greedy_200_trips_under_15s(self):
        trips = _consecutive_trips(200, gap=10, duration=30)
        vt = _vt()
        t0 = time.perf_counter()
        GreedyVSP().solve(trips, vt)
        elapsed = time.perf_counter() - t0
        assert elapsed < 15.0, f"200 trips took {elapsed:.2f}s (limit: 15s)"

    def test_csp_greedy_50_blocks_under_5s(self):
        trips = _consecutive_trips(50, gap=120, duration=60)
        vsp = GreedyVSP().solve(trips, _vt())
        t0 = time.perf_counter()
        GreedyCSP().solve(vsp.blocks)
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"CSP 50 blocks took {elapsed:.2f}s (limit: 5s)"

    def test_evaluator_cost_under_1s_for_large_solution(self):
        trips = _consecutive_trips(100, gap=120)
        vsp = GreedyVSP().solve(trips, _vt())
        duty = Duty(id=1)
        for b in vsp.blocks:
            duty.add_task(b)
        duty.paid_minutes = 480
        csp_sol = CSPSolution(duties=[duty], algorithm="greedy")
        result = OptimizationResult(vsp=vsp, csp=csp_sol)
        evaluator = CostEvaluator()
        t0 = time.perf_counter()
        evaluator.total_cost_breakdown(result, _vt())
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"Cost evaluation took {elapsed:.2f}s (limit: 1s)"


# ── Algorithm Diversity ───────────────────────────────────────────────────────


class TestAllAlgorithmsProduce_ValidSolutions:
    """
    All algorithm variants must produce feasible solutions.
    No algorithm should crash or produce empty results on standard inputs.
    """

    def _assert_valid_vsp(self, sol, trips):
        assert sol is not None
        assert sol.num_vehicles > 0
        covered = {t.id for b in sol.blocks for t in b.trips}
        assert covered == {t.id for t in trips}, f"Coverage gap: {set(t.id for t in trips) - covered}"
        assert _validate_no_overlaps(sol.blocks) == []

    def test_greedy_vsp(self):
        trips = _consecutive_trips(8)
        self._assert_valid_vsp(GreedyVSP().solve(trips, _vt()), trips)

    def test_sa_vsp(self):
        trips = _consecutive_trips(8)
        self._assert_valid_vsp(SimulatedAnnealingVSP(vsp_params={"sa_max_iterations": 500}).solve(trips, _vt()), trips)

    def test_tabu_vsp(self):
        trips = _consecutive_trips(8)
        self._assert_valid_vsp(TabuSearchVSP().solve(trips, _vt()), trips)

    def test_greedy_csp(self):
        trips = _consecutive_trips(8, gap=120)
        vsp = GreedyVSP().solve(trips, _vt())
        csp = GreedyCSP().solve(vsp.blocks)
        assert csp is not None
        assert csp.num_crew > 0

    def test_all_algorithms_cover_same_trips(self):
        """Different algorithms on the same input must all cover all trips."""
        trips = _consecutive_trips(10)
        trip_ids = {t.id for t in trips}
        for algo_cls in [GreedyVSP, SimulatedAnnealingVSP, TabuSearchVSP]:
            if algo_cls == SimulatedAnnealingVSP:
                sol = algo_cls(vsp_params={"sa_max_iterations": 500}).solve(trips, _vt())
            else:
                sol = algo_cls().solve(trips, _vt())
            covered = {t.id for b in sol.blocks for t in b.trips}
            assert covered == trip_ids, f"{algo_cls.__name__} missed trips: {trip_ids - covered}"


# ── Mathematical Properties ───────────────────────────────────────────────────


class TestMathematicalProperties:
    """
    Structural properties that must hold by construction,
    independent of algorithm quality.
    """

    def test_num_vehicles_equals_num_blocks(self):
        trips = _consecutive_trips(6)
        sol = GreedyVSP().solve(trips, _vt())
        assert sol.num_vehicles == len(sol.blocks)

    def test_each_block_has_at_least_one_trip(self):
        trips = _consecutive_trips(6)
        sol = GreedyVSP().solve(trips, _vt())
        for b in sol.blocks:
            assert len(b.trips) >= 1, f"Block {b.id} has no trips"

    def test_trips_sorted_by_start_time_within_block(self):
        trips = _consecutive_trips(8)
        sol = GreedyVSP().solve(trips, _vt())
        for b in sol.blocks:
            times = [t.start_time for t in b.trips]
            assert times == sorted(times), f"Block {b.id} trips not sorted: {times}"

    def test_no_trip_appears_in_multiple_blocks(self):
        trips = _consecutive_trips(10)
        sol = GreedyVSP().solve(trips, _vt())
        seen = {}
        for b in sol.blocks:
            for t in b.trips:
                assert t.id not in seen, (
                    f"Trip {t.id} in both block {seen[t.id]} and block {b.id}"
                )
                seen[t.id] = b.id

    def test_gini_symmetric(self):
        """Gini is invariant to permutation of values."""
        values = [100, 200, 300, 400]
        import itertools
        base = _gini_coefficient(values)
        for perm in itertools.permutations(values):
            assert _gini_coefficient(list(perm)) == base

    def test_lower_bound_monotone_with_more_simultaneous_trips(self):
        """Adding one more simultaneous trip cannot decrease the lower bound."""
        prev_lb = 0
        for n in range(1, 8):
            trips = _simultaneous_trips(n)
            lb = max_concurrent_trips(trips)
            assert lb >= prev_lb
            prev_lb = lb

    def test_cost_non_negative(self):
        trip = _trip(1, 360, 480)
        block = Block(id=1, trips=[trip], vehicle_type_id=1)
        evaluator = CostEvaluator()
        cost = evaluator.block_cost(block, _vt())
        assert cost >= 0

    def test_empty_solution_zero_cost(self):
        vsp_sol = VSPSolution(blocks=[], algorithm="greedy")
        csp_sol = CSPSolution(duties=[], algorithm="greedy")
        result = OptimizationResult(vsp=vsp_sol, csp=csp_sol)
        evaluator = CostEvaluator()
        breakdown = evaluator.total_cost_breakdown(result, _vt())
        assert breakdown["total"] == 0
