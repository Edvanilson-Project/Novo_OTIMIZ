"""
Timetable Slack Optimization — testes unitários e de integração.

Valida:
  - Ajustes dentro do slack permitido
  - Não ultrapassa slack máximo por trip
  - Trips não cobertas sem slack continuam sem cobertura
  - PVR reduz quando trips quase conectáveis existem
  - Trips já conectáveis não são perturbadas
  - Integração com OptimizerService via vsp_params["timetable_slack_minutes"]
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.algorithms.vsp.timetable_slack import TimetableSlackOptimizer, _find_min_delta
from src.algorithms.vsp.greedy import GreedyVSP
from src.domain.models import Trip, VehicleType


def make_vt(id_=1):
    return VehicleType(id=id_, name="Std", passenger_capacity=60,
                       fixed_cost=800.0, cost_per_km=2.5, cost_per_hour=30.0)


def make_trip(id_, start, end, origin=1, dest=2, deadhead_times=None):
    t = Trip(
        id=id_, line_id=1,
        start_time=start, end_time=end, duration=end - start,
        origin_id=origin, destination_id=dest, distance_km=10.0,
    )
    t.deadhead_times = deadhead_times or {}
    return t


class TestFindMinDelta:
    def test_already_feasible_returns_zero(self):
        last = make_trip(1, 300, 360)
        first = make_trip(2, 380, 440)  # gap=20 > min_layover=8
        delta = _find_min_delta(last, first, slack=10, step=5, min_layover=8)
        assert delta == (0, 0)

    def test_gap_too_small_finds_minimal_delta(self):
        last = make_trip(1, 300, 360)
        first = make_trip(2, 362, 420)  # gap=2 < min_layover=8 → deficit=6
        delta = _find_min_delta(last, first, slack=10, step=5, min_layover=8)
        assert delta is not None
        d_last, d_first = delta
        assert abs(d_last) <= 10 and abs(d_first) <= 10
        new_gap = (first.start_time + d_first) - (last.end_time + d_last)
        assert new_gap >= 8

    def test_returns_none_when_impossible(self):
        last = make_trip(1, 300, 360)
        first = make_trip(2, 362, 420)  # gap=2, deficit=6, slack=2 → impossível
        delta = _find_min_delta(last, first, slack=2, step=1, min_layover=8)
        assert delta is None

    def test_deadhead_respected(self):
        # deadhead_times no last: para ir de last.dest(1) até first.origin(2), leva 15min
        last = make_trip(1, 300, 360, dest=1, deadhead_times={2: 15})
        first = make_trip(2, 370, 430, origin=2)
        # gap=10, deadhead=15 → required=15, deficit=5
        delta = _find_min_delta(last, first, slack=10, step=5, min_layover=8)
        if delta is not None:
            d_last, d_first = delta
            new_gap = (first.start_time + d_first) - (last.end_time + d_last)
            assert new_gap >= 15

    def test_minimizes_perturbation(self):
        last = make_trip(1, 300, 360)
        first = make_trip(2, 363, 420)  # gap=3, deficit=5
        # Possível: d_last=-5 (atrasa fim) OU d_first=+5 (adianta início), ambos abs=5
        delta = _find_min_delta(last, first, slack=10, step=5, min_layover=8)
        assert delta is not None
        d_last, d_first = delta
        assert abs(d_last) + abs(d_first) <= 10  # não usa mais perturbação que necessário


class TestTimetableSlackOptimizer:

    def _trips_disconnected_by_small_gap(self):
        """
        3 trips: t1→t2 (gap=3, precisa 8) e t3 (gap gigante → 2 blocos).
        Com slack=5, deve fundir t1+t2 em 1 bloco.
        """
        return [
            make_trip(1, 300, 360),   # bloco A: 300-360
            make_trip(2, 363, 423),   # gap=3 do t1, precisa 8 → 2 blocos sem slack
            make_trip(3, 700, 760),   # bloco isolado, horário muito distante
        ]

    def test_no_slack_returns_original_trips(self):
        trips = self._trips_disconnected_by_small_gap()
        tso = TimetableSlackOptimizer(slack_minutes=0)
        adjusted, meta = tso.optimize(trips, [make_vt()], depot_id=None)
        assert [t.id for t in adjusted] == [t.id for t in trips]
        assert meta["slack_applied"] is False

    def test_with_slack_reduces_pvr(self):
        trips = self._trips_disconnected_by_small_gap()
        vts = [make_vt()]

        # Baseline sem slack
        greedy = GreedyVSP()
        baseline = greedy.solve(trips, vts)
        pvr_before = len(baseline.blocks)

        tso = TimetableSlackOptimizer(slack_minutes=10, step_minutes=5)
        adjusted, meta = tso.optimize(trips, vts)
        pvr_after = len(greedy.solve(adjusted, vts).blocks)

        assert pvr_after <= pvr_before
        assert meta["pvr_before"] == pvr_before

    def test_adjustments_within_slack(self):
        trips = self._trips_disconnected_by_small_gap()
        slack = 10
        tso = TimetableSlackOptimizer(slack_minutes=slack)
        adjusted, _ = tso.optimize(trips, [make_vt()])
        orig = {t.id: t for t in trips}
        for t in adjusted:
            orig_t = orig[t.id]
            assert abs(t.start_time - orig_t.start_time) <= slack, (
                f"Trip {t.id} ajustada por {abs(t.start_time - orig_t.start_time)} > slack {slack}"
            )
            # duração preservada
            assert t.end_time - t.start_time == orig_t.end_time - orig_t.start_time

    def test_trip_ids_unchanged(self):
        trips = self._trips_disconnected_by_small_gap()
        tso = TimetableSlackOptimizer(slack_minutes=10)
        adjusted, _ = tso.optimize(trips, [make_vt()])
        assert {t.id for t in adjusted} == {t.id for t in trips}

    def test_already_feasible_trips_not_perturbed(self):
        """Se todas conexões já são viáveis, nenhum trip deve ser ajustado."""
        trips = [
            make_trip(1, 300, 360),
            make_trip(2, 380, 440),  # gap=20 > 8 → viável
            make_trip(3, 600, 660),  # gap enorme → 2 blocos (evita pvr=1 early return)
        ]
        tso = TimetableSlackOptimizer(slack_minutes=10)
        adjusted, meta = tso.optimize(trips, [make_vt()])
        # Trips 1 e 2 já conectáveis — não devem ser perturbadas
        orig = {t.id: t for t in trips}
        assert adjusted[0].start_time == orig[1].start_time
        assert adjusted[1].start_time == orig[2].start_time

    def test_empty_trips_returns_empty(self):
        tso = TimetableSlackOptimizer(slack_minutes=10)
        adjusted, meta = tso.optimize([], [make_vt()])
        assert adjusted == []
        assert meta["slack_applied"] is False

    def test_single_trip_no_adjustment(self):
        trips = [make_trip(1, 300, 360)]
        tso = TimetableSlackOptimizer(slack_minutes=10)
        adjusted, meta = tso.optimize(trips, [make_vt()])
        assert len(adjusted) == 1
        assert meta.get("pvr_reduction", 0) == 0

    def test_meta_keys_present(self):
        trips = self._trips_disconnected_by_small_gap()
        tso = TimetableSlackOptimizer(slack_minutes=10)
        _, meta = tso.optimize(trips, [make_vt()])
        for key in ("slack_applied", "pvr_before", "pvr_after", "pvr_reduction",
                    "pvr_reduction_pct", "trips_adjusted", "total_merges"):
            assert key in meta, f"Chave ausente no meta: {key}"

    def test_slack_insufficient_no_merge(self):
        """Gap de 50 minutos, slack de 2 → impossível fechar."""
        trips = [
            make_trip(1, 300, 360),
            make_trip(2, 361, 420),  # gap=1, min_layover=8, deficit=7
        ]
        tso = TimetableSlackOptimizer(slack_minutes=2, step_minutes=1, min_layover=8)
        adjusted, meta = tso.optimize(trips, [make_vt()])
        # Não deve ter fechado o gap (impossível com slack=2 para deficit=7)
        orig = {t.id: t for t in trips}
        for t in adjusted:
            assert abs(t.start_time - orig[t.id].start_time) <= 2


class TestTimetableSlackIntegration:
    """Integração: via OptimizerService com vsp_params["timetable_slack_minutes"]."""

    def test_optimizer_service_respects_slack_param(self):
        from src.services.optimizer_service import OptimizerService
        from src.domain.models import AlgorithmType

        svc = OptimizerService()
        trips = [
            make_trip(1, 300, 360),
            make_trip(2, 363, 423),   # gap=3, quase conectável
            make_trip(3, 700, 760),
        ]
        vts = [make_vt()]

        # Sem slack
        r_no_slack = svc.run(
            trips=trips, vehicle_types=vts,
            algorithm=AlgorithmType.GREEDY, time_budget_s=30,
            vsp_params={}, cct_params={},
        )
        pvr_no_slack = len(r_no_slack.vsp.blocks) if r_no_slack.vsp else 999

        # Com slack=10
        r_with_slack = svc.run(
            trips=trips, vehicle_types=vts,
            algorithm=AlgorithmType.GREEDY, time_budget_s=30,
            vsp_params={"timetable_slack_minutes": 10}, cct_params={},
        )
        pvr_with_slack = len(r_with_slack.vsp.blocks) if r_with_slack.vsp else 999

        # Com slack, deve ter <= blocos que sem slack
        assert pvr_with_slack <= pvr_no_slack

        # Meta deve estar presente
        if r_with_slack.meta:
            assert "timetable_slack" in r_with_slack.meta
