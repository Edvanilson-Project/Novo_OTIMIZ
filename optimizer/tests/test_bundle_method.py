"""Testes para Bundle Method (Borndörfer et al. 2008 adaptation)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.algorithms.large_scale.bundle_method import (
    BundleMethodSolver,
    decompose_by_depot,
    decompose_by_line,
    decompose_temporal,
)
from src.domain.models import Trip, VehicleType


def _vt():
    return [
        VehicleType(
            id=1, name="Bus", passenger_capacity=40,
            cost_per_km=2.5, cost_per_hour=55.0, fixed_cost=900.0,
        )
    ]


def _trip(tid, start, end, origin=1, dest=2, line=1, depot=None):
    return Trip(
        id=tid, line_id=line, start_time=start, end_time=end,
        origin_id=origin, destination_id=dest,
        duration=end - start, distance_km=max(1, (end - start) / 3),
        depot_id=depot,
        deadhead_times={origin: 8, dest: 8},
    )


def _make_trips(n: int, gap: int = 90, duration: int = 60):
    trips = []
    t = 360
    for i in range(n):
        o, d = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(_trip(i + 1, t, t + duration, o, d))
        t += duration + gap
    return trips


class TestDecomposition:
    def test_decompose_by_line(self):
        trips = [
            _trip(1, 360, 420, line=1),
            _trip(2, 430, 490, line=1),
            _trip(3, 500, 560, line=2),
        ]
        result = decompose_by_line(trips)
        assert len(result) == 2
        assert len(result[1]) == 2
        assert len(result[2]) == 1

    def test_decompose_by_depot(self):
        trips = [
            _trip(1, 360, 420, depot=10),
            _trip(2, 430, 490, depot=10),
            _trip(3, 500, 560, depot=20),
        ]
        result = decompose_by_depot(trips)
        assert len(result) == 2

    def test_decompose_temporal_no_chunking_small(self):
        trips = _make_trips(50)
        chunks = decompose_temporal(trips, chunk_size=800)
        assert len(chunks) == 1
        assert len(chunks[0]) == 50

    def test_decompose_temporal_chunks_large(self):
        trips = _make_trips(200)
        chunks = decompose_temporal(trips, chunk_size=80)
        assert len(chunks) > 1
        total = sum(len(c) for c in chunks)
        # Total >= 200 (overlap pode duplicar)
        assert total >= 200


class TestBundleCorrectness:
    def test_solves_small_instance(self):
        trips = _make_trips(20)
        solver = BundleMethodSolver(
            time_budget_s=10.0,
            decomposition="none",
            max_iterations=5,
        )
        result = solver.solve(trips, _vt())
        assert result.vsp.num_vehicles > 0
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        missing = {t.id for t in trips} - covered
        assert not missing, f"Bundle não cobre {len(missing)} trips"

    def test_produces_bundle_metadata(self):
        trips = _make_trips(15)
        solver = BundleMethodSolver(
            time_budget_s=5.0,
            decomposition="none",
            max_iterations=3,
        )
        result = solver.solve(trips, _vt())
        meta = result.vsp.meta
        assert "bundle_iterations" in meta
        assert "bundle_upper_bound" in meta
        assert "bundle_elapsed_ms" in meta

    def test_temporal_decomposition_large_instance(self):
        """Para n>800, usa temporal decomposition."""
        # Reduzimos para 100 trips com chunks pequenos para testar o caminho
        trips = _make_trips(100, gap=30, duration=20)
        solver = BundleMethodSolver(
            time_budget_s=20.0,
            decomposition="temporal",
            max_iterations=3,
        )
        # Força decomposition path
        result = solver._solve_decomposed(trips, _vt(), None)
        meta = result.vsp.meta
        assert "bundle_decomposition" in meta
        assert meta["bundle_decomposition"] == "temporal"
        assert "bundle_subproblems" in meta


class TestBundleScale:
    def test_handles_300_trips(self):
        """Garante que escala razoável funciona."""
        import time
        trips = _make_trips(300, gap=20, duration=30)
        solver = BundleMethodSolver(
            time_budget_s=60.0,
            decomposition="temporal",
            max_iterations=3,
        )
        t0 = time.perf_counter()
        result = solver.solve(trips, _vt())
        elapsed = time.perf_counter() - t0
        assert elapsed < 90.0, f"Bundle 300 trips: {elapsed:.1f}s > 90s SLA"
        # Garante que cobriu maioria das trips (decomposition pode deixar fronteira)
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        assert len(covered) >= len(trips) * 0.95
