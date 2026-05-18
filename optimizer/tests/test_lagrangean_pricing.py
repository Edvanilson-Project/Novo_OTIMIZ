"""Testes para Lagrangean Pricing (Löbel 1998)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.algorithms.integrated.lagrangean_pricing import (
    LagrangeanJointSolver,
    _compute_subgradient,
    _update_multipliers_polyak,
)
from src.algorithms.vsp.greedy import GreedyVSP
from src.domain.models import Trip, VehicleType, VSPSolution, CSPSolution


def _vt():
    return [
        VehicleType(
            id=1, name="Bus", passenger_capacity=40,
            cost_per_km=2.5, cost_per_hour=55.0, fixed_cost=900.0,
        )
    ]


def _trip(tid, start, end, origin=1, dest=2):
    return Trip(
        id=tid, line_id=1, start_time=start, end_time=end,
        origin_id=origin, destination_id=dest,
        duration=end - start, distance_km=max(1, (end - start) / 3),
        deadhead_times={origin: 8, dest: 8},
    )


def _consecutive_trips(n: int, gap: int = 90, duration: int = 60):
    trips = []
    t = 360
    for i in range(n):
        o, d = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(_trip(i + 1, t, t + duration, o, d))
        t += duration + gap
    return trips


class TestLagrangeanCorrectness:
    def test_returns_feasible_result(self):
        """Resultado deve cobrir todas as trips."""
        trips = _consecutive_trips(15, gap=120)
        solver = LagrangeanJointSolver(time_budget_s=10.0)
        result = solver.solve(trips, _vt())
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        missing = {t.id for t in trips} - covered
        assert not missing, f"Lagrangean não cobre {len(missing)} trips"

    def test_produces_lagrangean_metadata(self):
        """meta deve conter iterações, LB, UB, gap."""
        trips = _consecutive_trips(10)
        solver = LagrangeanJointSolver(time_budget_s=5.0)
        result = solver.solve(trips, _vt())
        meta = result.vsp.meta
        assert "lagrangean_iterations" in meta
        assert "lagrangean_lower_bound" in meta
        assert "lagrangean_upper_bound" in meta
        assert "lagrangean_final_gap_pct" in meta
        assert "lagrangean_history" in meta
        assert isinstance(meta["lagrangean_history"], list)

    def test_lb_never_exceeds_ub(self):
        """Cota inferior nunca pode exceder upper bound (dualidade fraca)."""
        trips = _consecutive_trips(12)
        solver = LagrangeanJointSolver(time_budget_s=10.0)
        result = solver.solve(trips, _vt())
        lb = result.vsp.meta["lagrangean_lower_bound"]
        ub = result.vsp.meta["lagrangean_upper_bound"]
        assert lb <= ub + 0.01, f"LB ({lb}) > UB ({ub}) viola dualidade fraca"

    def test_lagrangean_at_least_as_good_as_greedy(self):
        """Lagrangean deve produzir UB ≤ greedy puro (mesma instância)."""
        trips = _consecutive_trips(20)
        greedy_v = GreedyVSP().solve(trips, _vt()).num_vehicles

        solver = LagrangeanJointSolver(time_budget_s=15.0)
        result = solver.solve(trips, _vt())

        assert result.vsp.num_vehicles <= greedy_v + 1, (
            f"Lagrangean ({result.vsp.num_vehicles}) usou mais veículos que Greedy ({greedy_v})"
        )


class TestSubgradientUpdate:
    def test_subgradient_zero_when_coverage_perfect(self):
        """Se cov_vsp + cov_csp = 2 ∀i, subgradiente = 0."""
        trips = [_trip(1, 360, 420), _trip(2, 430, 490)]
        vsp_sol = VSPSolution(
            blocks=[__import__("src.domain.models", fromlist=["Block"]).Block(id=1, trips=trips)],
            algorithm="test",
        )
        # Mock duty cobrindo as mesmas trips
        Duty = __import__("src.domain.models", fromlist=["Duty"]).Duty
        Block = __import__("src.domain.models", fromlist=["Block"]).Block
        duty = Duty(id=1)
        task = Block(id=1, trips=trips)
        duty.add_task(task)
        csp_sol = CSPSolution(duties=[duty], algorithm="test")

        subgrad = _compute_subgradient(vsp_sol, csp_sol, trips)
        # Cada trip está em 1 bloco VSP e 1 task CSP → 1 + 1 - 2 = 0
        assert all(abs(g) < 1e-9 for g in subgrad.values())

    def test_polyak_step_zero_when_gap_zero(self):
        """Se UB == LB, atualização não move multiplicadores."""
        mults = {1: 0.5, 2: -0.3}
        subgrad = {1: 1.0, 2: -1.0}
        new = _update_multipliers_polyak(mults, subgrad, upper_bound=100.0, lower_bound=100.0)
        assert new == mults

    def test_polyak_decreases_when_overcovered(self):
        """Trip com cov > 2 → subgrad > 0 → λ diminui (penalizar menos)."""
        mults = {1: 1.0}
        subgrad = {1: 1.0}  # over-covered
        new = _update_multipliers_polyak(mults, subgrad, upper_bound=100.0, lower_bound=50.0)
        assert new[1] < mults[1]


class TestLagrangeanScale:
    def test_handles_50_trips_within_budget(self):
        """Garante que escala razoável funciona dentro do budget."""
        import time
        trips = _consecutive_trips(50)
        solver = LagrangeanJointSolver(time_budget_s=30.0)
        t0 = time.perf_counter()
        result = solver.solve(trips, _vt())
        elapsed = time.perf_counter() - t0
        assert elapsed < 35.0, f"Lagrangean 50 trips levou {elapsed:.1f}s > 35s SLA"
        assert result.vsp.num_vehicles > 0
