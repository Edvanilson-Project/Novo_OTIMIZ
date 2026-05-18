"""Testes para DisruptionRecoverySolver."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.algorithms.integrated.disruption_recovery import DisruptionRecoverySolver
from src.domain.models import Trip, VehicleType


def _vt():
    return [VehicleType(id=1, name="Bus", passenger_capacity=40,
                        cost_per_km=2.5, cost_per_hour=55.0, fixed_cost=900.0)]


def _trip(tid, start, end, origin=1, dest=2):
    return Trip(id=tid, line_id=1, start_time=start, end_time=end,
                origin_id=origin, destination_id=dest, duration=end - start,
                distance_km=10.0, deadhead_times={1: 8, 2: 8})


class TestDisruptionRecoveryEmpty:
    def test_empty_trips(self):
        s = DisruptionRecoverySolver()
        result = s.solve([], _vt(), disrupted_trip_ids=set(), current_blocks=[])
        assert result.vsp.num_vehicles == 0

    def test_no_disruption_returns_frozen_blocks(self):
        trips = [_trip(1, 360, 420), _trip(2, 500, 560)]
        current_blocks = [[trips[0]], [trips[1]]]
        s = DisruptionRecoverySolver()
        result = s.solve(trips, _vt(), disrupted_trip_ids=set(), current_blocks=current_blocks)
        # Sem perturbação → todos os blocos congelados, mantém cobertura
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        assert covered == {1, 2}
        meta = result.vsp.meta or {}
        assert meta.get("disruption_frozen_blocks") == 2


class TestDisruptionRecoveryIncremental:
    def test_only_affected_block_reoptimized(self):
        """Bloco 1 afetado → bloco 2 deve permanecer congelado."""
        t1 = _trip(1, 360, 420)
        t2 = _trip(2, 440, 500)
        t3 = _trip(3, 600, 660)
        current_blocks = [[t1, t2], [t3]]
        trips_all = [t1, t2, t3]

        s = DisruptionRecoverySolver()
        result = s.solve(trips_all, _vt(), disrupted_trip_ids={1}, current_blocks=current_blocks)

        meta = result.vsp.meta or {}
        assert meta.get("disruption_frozen_blocks") == 1, "Bloco 2 deve estar congelado"
        assert meta.get("disruption_affected_blocks") == 1
        assert meta.get("disruption_strategy") == "incremental"
        # Todas as trips devem estar cobertas
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        assert {1, 2, 3}.issubset(covered)

    def test_full_reoptimize_when_ratio_exceeded(self):
        """Quando >50% dos blocos são afetados, deve fazer re-otimização total."""
        trips = [_trip(i, 360 + i * 120, 420 + i * 120) for i in range(6)]
        # 4 blocos de 1 trip cada
        current_blocks = [[t] for t in trips[:4]]
        # Perturba 3 dos 4 blocos → 75% > 50%
        disrupted = {trips[0].id, trips[1].id, trips[2].id}

        s = DisruptionRecoverySolver()
        result = s.solve(trips, _vt(), disrupted_trip_ids=disrupted, current_blocks=current_blocks)
        meta = result.vsp.meta or {}
        assert meta.get("disruption_strategy") == "full_reoptimize"

    def test_new_trips_included_in_reoptimization(self):
        """Trip nova (não estava em nenhum bloco) deve ser incluída na re-otimização."""
        t1 = _trip(1, 360, 420)
        t2 = _trip(2, 440, 500)
        t_new = _trip(99, 520, 580)  # trip nova perturbada
        current_blocks = [[t1], [t2]]
        trips_all = [t1, t2, t_new]

        s = DisruptionRecoverySolver()
        result = s.solve(trips_all, _vt(), disrupted_trip_ids={99}, current_blocks=current_blocks)
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        # Trip nova deve estar coberta (foi re-otimizada)
        assert 99 in covered

    def test_freeze_unaffected_false_forces_full_reopt(self):
        trips = [_trip(i, 360 + i * 120, 420 + i * 120) for i in range(4)]
        current_blocks = [[t] for t in trips]

        s = DisruptionRecoverySolver(vsp_params={"disruption_freeze_unaffected": False})
        result = s.solve(trips, _vt(), disrupted_trip_ids={trips[0].id}, current_blocks=current_blocks)
        meta = result.vsp.meta or {}
        assert meta.get("disruption_strategy") == "full_reoptimize"


class TestDisruptionRecoveryMetrics:
    def test_meta_contains_all_fields(self):
        trips = [_trip(1, 360, 420), _trip(2, 500, 560)]
        current_blocks = [[trips[0]], [trips[1]]]
        s = DisruptionRecoverySolver()
        result = s.solve(trips, _vt(), disrupted_trip_ids={1}, current_blocks=current_blocks)
        meta = result.vsp.meta or {}
        for key in [
            "disruption_trip_ids",
            "disruption_affected_blocks",
            "disruption_frozen_blocks",
            "disruption_reoptimized_blocks",
            "disruption_trips_reassigned",
            "disruption_affected_ratio",
            "disruption_strategy",
        ]:
            assert key in meta, f"Campo ausente no meta: {key}"

    def test_algorithm_name(self):
        trips = [_trip(1, 360, 420)]
        s = DisruptionRecoverySolver()
        result = s.solve(trips, _vt(), disrupted_trip_ids={1}, current_blocks=[[trips[0]]])
        assert result.vsp.algorithm == "disruption_recovery"
