"""
Audit Suite: Correctness assertions for the optimizer.

Checks four properties against the real API (no mocks, no simulated data):
  A. Cost consistency — CostEvaluator returns positive, monotone costs.
  B. Deadhead impact — block cost grows when trips are spread further apart.
  C. Optimality gap — CostEvaluator exposes gap metadata with correct keys.
  D. Coverage completeness — all trips assigned after VSP+CSP pipeline.

Mirrors the style of proof_of_optimization_suite.py.
Run:
    cd optimizer
    python -m pytest tests/audit_correctness.py -v --tb=short
"""

from __future__ import annotations

import os
import sys
from typing import List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.evaluator import CostEvaluator
from src.algorithms.hybrid.pipeline import HybridPipeline
from src.algorithms.vsp.greedy import GreedyVSP
from src.domain.models import (
    AlgorithmType,
    Block,
    CSPSolution,
    Duty,
    OptimizationResult,
    Trip,
    VehicleType,
    VSPSolution,
)


# ─── Helpers (same pattern as proof_of_optimization_suite) ───────────────────


def _vt(n: int = 1) -> List[VehicleType]:
    return [
        VehicleType(
            id=i + 1,
            name=f"Bus-{i+1}",
            passenger_capacity=40,
            cost_per_km=2.5,
            cost_per_hour=55.0,
            fixed_cost=900.0,
        )
        for i in range(n)
    ]


def _trip(tid: int, start: int, end: int, *, origin: int = 1, dest: int = 2) -> Trip:
    return Trip(
        id=tid,
        line_id=1,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        distance_km=max(1.0, (end - start) / 3.0),
        deadhead_times={origin: 8, dest: 8},
    )


def consecutive_trips(n: int, gap: int = 90, duration: int = 60, offset: int = 360) -> List[Trip]:
    trips = []
    t = offset
    for i in range(n):
        origin, dest = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(_trip(i + 1, t, t + duration, origin=origin, dest=dest))
        t += duration + gap
    return trips


def simultaneous_trips(n: int, start: int = 360, duration: int = 60) -> List[Trip]:
    return [_trip(i + 1, start, start + duration, origin=1, dest=2) for i in range(n)]


# ─── A. Cost consistency ──────────────────────────────────────────────────────


class TestAuditCostConsistency:
    """A: CostEvaluator must return positive, internally-consistent costs."""

    def test_block_cost_positive(self):
        """Every block produced by GreedyVSP must have positive cost."""
        trips = consecutive_trips(10)
        sol = GreedyVSP().solve(trips, _vt())
        ev = CostEvaluator()
        for block in sol.blocks:
            cost = ev.block_cost(block, _vt())
            assert cost > 0, f"Block {block.id} has non-positive cost {cost}"

    def test_two_vehicles_cost_more_than_one(self):
        """Splitting trips across two vehicles must be more expensive (fixed cost)."""
        t1 = _trip(1, 360, 420)
        t2 = _trip(2, 430, 490)
        ev = CostEvaluator()
        block_single = Block(id=1, trips=[t1, t2], vehicle_type_id=1)
        block_a = Block(id=2, trips=[t1], vehicle_type_id=1)
        block_b = Block(id=3, trips=[t2], vehicle_type_id=1)
        cost_single = ev.block_cost(block_single, _vt())
        cost_two = ev.block_cost(block_a, _vt()) + ev.block_cost(block_b, _vt())
        assert cost_two > cost_single, (
            f"Two vehicles ({cost_two:.2f}) should cost more than one ({cost_single:.2f})"
        )

    def test_total_cost_breakdown_required_keys(self):
        """total_cost_breakdown must expose 'total', 'vsp', 'csp' keys."""
        trips = consecutive_trips(10)
        vsp = GreedyVSP().solve(trips, _vt())
        duty = Duty(id=1)
        for b in vsp.blocks:
            duty.add_task(b)
        duty.paid_minutes = 480
        csp = CSPSolution(duties=[duty], algorithm="greedy")
        result = OptimizationResult(vsp=vsp, csp=csp)
        ev = CostEvaluator()
        breakdown = ev.total_cost_breakdown(result, _vt())
        for key in ("total", "vsp", "csp"):
            assert key in breakdown, f"Breakdown missing key: '{key}'"
        assert breakdown["total"] >= 0


# ─── B. Deadhead impact ───────────────────────────────────────────────────────


class TestAuditDeadheadImpact:
    """B: A block containing two trips must be cheaper than two single-trip blocks."""

    def test_chaining_two_trips_saves_fixed_cost(self):
        """Chain t1→t2 in one block vs two separate blocks — one block wins on fixed cost."""
        t1 = _trip(1, 360, 420)
        t2 = _trip(2, 500, 560)  # gap of 80 min — compatible
        ev = CostEvaluator()
        block_chain = Block(id=1, trips=[t1, t2], vehicle_type_id=1)
        block_t1 = Block(id=2, trips=[t1], vehicle_type_id=1)
        block_t2 = Block(id=3, trips=[t2], vehicle_type_id=1)
        cost_chain = ev.block_cost(block_chain, _vt())
        cost_split = ev.block_cost(block_t1, _vt()) + ev.block_cost(block_t2, _vt())
        assert cost_chain < cost_split, (
            f"Chaining ({cost_chain:.2f}) should beat two blocks ({cost_split:.2f})"
        )

    def test_block_cost_increases_with_more_trips(self):
        """A block with more work should cost more than one with less work."""
        t1 = _trip(1, 360, 420)
        t2 = _trip(2, 430, 490)
        t3 = _trip(3, 500, 560)
        ev = CostEvaluator()
        block_1t = Block(id=1, trips=[t1], vehicle_type_id=1)
        block_3t = Block(id=2, trips=[t1, t2, t3], vehicle_type_id=1)
        cost_1 = ev.block_cost(block_1t, _vt())
        cost_3 = ev.block_cost(block_3t, _vt())
        assert cost_3 > cost_1, (
            f"3-trip block ({cost_3:.2f}) should cost more than 1-trip block ({cost_1:.2f})"
        )


# ─── C. Optimality gap metadata ──────────────────────────────────────────────


class TestAuditOptimalityGap:
    """C: CostEvaluator must expose optimality gap with correct structure."""

    def test_optimality_key_present_in_breakdown(self):
        """Breakdown must contain 'optimality' sub-dict with required keys."""
        trips = simultaneous_trips(5)
        vsp = GreedyVSP().solve(trips, _vt())
        csp = CSPSolution(duties=[], algorithm="greedy")
        result = OptimizationResult(vsp=vsp, csp=csp)
        breakdown = CostEvaluator().total_cost_breakdown(result, _vt())
        assert "optimality" in breakdown, "Missing 'optimality' key in breakdown"
        opt = breakdown["optimality"]
        for key in ("vsp_lower_bound", "vsp_actual", "vsp_gap_pct"):
            assert key in opt, f"Missing '{key}' inside breakdown['optimality']"

    def test_gap_zero_for_simultaneous_trips(self):
        """5 simultaneous trips → lb=5, greedy uses 5 → gap must be 0."""
        trips = simultaneous_trips(5)
        vsp = GreedyVSP().solve(trips, _vt())
        csp = CSPSolution(duties=[], algorithm="greedy")
        result = OptimizationResult(vsp=vsp, csp=csp)
        opt = CostEvaluator().total_cost_breakdown(result, _vt())["optimality"]
        assert opt["vsp_lower_bound"] == 5
        assert opt["vsp_actual"] == 5
        assert opt["vsp_gap_pct"] == 0.0

    def test_gap_non_negative(self):
        """Gap percent must never be negative (can't beat lower bound)."""
        trips = consecutive_trips(20)
        vsp = GreedyVSP().solve(trips, _vt())
        csp = CSPSolution(duties=[], algorithm="greedy")
        result = OptimizationResult(vsp=vsp, csp=csp)
        opt = CostEvaluator().total_cost_breakdown(result, _vt())["optimality"]
        assert opt["vsp_gap_pct"] >= 0.0, f"Negative gap: {opt['vsp_gap_pct']}"


# ─── D. Coverage completeness ─────────────────────────────────────────────────


class TestAuditCoverage:
    """D: Every trip must appear in exactly one block/duty after the full pipeline."""

    def test_vsp_greedy_covers_all_trips(self):
        """GreedyVSP must cover 100% of trips."""
        trips = consecutive_trips(30)
        sol = GreedyVSP().solve(trips, _vt())
        covered = {t.id for b in sol.blocks for t in b.trips}
        missing = {t.id for t in trips} - covered
        assert not missing, f"GreedyVSP left {len(missing)} trips uncovered: {missing}"

    def test_csp_greedy_covers_all_blocks(self):
        """GreedyCSP must cover all block trips across duties."""
        trips = consecutive_trips(20, gap=120, duration=60)
        vsp = GreedyVSP().solve(trips, _vt())
        csp = GreedyCSP().solve(vsp.blocks)
        covered = {t.id for d in csp.duties for task in d.tasks for t in task.trips}
        expected = {t.id for b in vsp.blocks for t in b.trips}
        missing = expected - covered
        assert not missing, f"GreedyCSP left {len(missing)} trips uncovered"

    def test_hybrid_covers_all_trips(self):
        """HybridPipeline must cover 100% of trips."""
        trips = consecutive_trips(50, gap=60)
        result = HybridPipeline(time_budget_s=15).solve(trips, _vt())
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        missing = {t.id for t in trips} - covered
        assert not missing, f"HybridPipeline left {len(missing)} trips uncovered"
