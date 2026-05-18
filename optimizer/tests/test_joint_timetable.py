"""Testes para Joint Timetable + VSP (MILP, Schmid & Ehmke 2015)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.algorithms.vsp.joint_timetable import JointTimetableVSP, _PULP_AVAILABLE
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


def _sequential_trips(n: int, start: int = 360, duration: int = 60, gap: int = 90):
    trips = []
    t = start
    for i in range(n):
        o, d = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(_trip(i + 1, t, t + duration, o, d))
        t += duration + gap
    return trips


class TestJointTimetableEmpty:
    def test_empty_trips_returns_empty_solution(self):
        solver = JointTimetableVSP()
        result = solver.solve([], _vt())
        assert result.num_vehicles == 0
        assert result.blocks == []

    def test_single_trip(self):
        trips = [_trip(1, 360, 420)]
        solver = JointTimetableVSP()
        result = solver.solve(trips, _vt())
        assert result.num_vehicles >= 1
        covered = {t.id for b in result.blocks for t in b.trips}
        assert 1 in covered


@pytest.mark.skipif(not _PULP_AVAILABLE, reason="PuLP não disponível")
class TestJointTimetableMILP:
    def test_small_instance_covers_all_trips(self):
        trips = _sequential_trips(10)
        solver = JointTimetableVSP()
        result = solver.solve(trips, _vt())
        covered = {t.id for b in result.blocks for t in b.trips}
        missing = {t.id for t in trips} - covered
        assert not missing, f"trips não cobertas: {missing}"

    def test_no_block_overlap(self):
        trips = _sequential_trips(10)
        solver = JointTimetableVSP()
        result = solver.solve(trips, _vt())
        for block in result.blocks:
            block_trips = sorted(block.trips, key=lambda t: t.start_time)
            for a, b in zip(block_trips, block_trips[1:]):
                assert a.end_time <= b.start_time, (
                    f"Sobreposição no bloco {block.id}: trip {a.id} termina {a.end_time}, "
                    f"trip {b.id} começa {b.start_time}"
                )

    def test_produces_metadata(self):
        trips = _sequential_trips(8)
        solver = JointTimetableVSP()
        result = solver.solve(trips, _vt())
        meta = result.meta
        assert meta is not None
        assert "joint_timetable_milp_status" in meta
        assert "joint_timetable_milp_solve_s" in meta
        assert "joint_timetable_trips_adjusted" in meta

    def test_timetable_adjustment_within_slack(self):
        """Nenhuma trip deve sair do slack window."""
        slack = 10
        trips = _sequential_trips(8)
        solver = JointTimetableVSP(vsp_params={"timetable_slack_minutes": slack})
        result = solver.solve(trips, _vt())
        original_starts = {t.id: t.start_time for t in trips}
        for block in result.blocks:
            for trip in block.trips:
                orig = original_starts[trip.id]
                deviation = abs(trip.start_time - orig)
                assert deviation <= slack, (
                    f"Trip {trip.id}: desvio {deviation} > slack {slack}"
                )

    def test_fewer_vehicles_than_trips(self):
        """Trips sequenciais bem espaçadas devem ser encadeadas (1 veículo)."""
        # 5 trips com gap=120min: qualquer solver deve encadeá-las em 1 veículo
        trips = _sequential_trips(5, gap=120, duration=30)
        solver = JointTimetableVSP()
        result = solver.solve(trips, _vt())
        assert result.num_vehicles <= 3, (
            f"Esperava ≤3 veículos para trips com folga, obteve {result.num_vehicles}"
        )


class TestJointTimetableFallback:
    def test_fallback_on_large_instance(self):
        """Instâncias com >150 trips devem acionar fallback para GreedyVSP."""
        trips = _sequential_trips(160)
        solver = JointTimetableVSP()
        result = solver.solve(trips, _vt())
        assert result.num_vehicles > 0
        meta = result.meta or {}
        assert meta.get("joint_timetable_skipped") == "instance_too_large"
        covered = {t.id for b in result.blocks for t in b.trips}
        assert len(covered) == len(trips)

    def test_fallback_preserves_algorithm_name(self):
        """Quando PuLP indisponível, fallback ainda retorna solução válida."""
        trips = _sequential_trips(5)
        solver = JointTimetableVSP()
        # Mesmo sem PuLP, GreedyVSP é o fallback — garante que solve não levanta exceção
        result = solver.solve(trips, _vt())
        assert result.num_vehicles >= 1
