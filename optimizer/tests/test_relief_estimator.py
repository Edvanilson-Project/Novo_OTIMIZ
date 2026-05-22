"""
ReliefVehicleEstimator — testes unitários.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.algorithms.relief.estimator import ReliefVehicleEstimator
from src.domain.models import Block, CSPSolution, Duty, DutySegment, Trip


def make_trip(id_, start, end, origin_id=1, destination_id=2):
    t = Trip(
        id=id_, line_id=1, start_time=start, end_time=end,
        origin_id=origin_id, destination_id=destination_id,
        duration=end - start,
    )
    t.deadhead_times = {}
    return t


def make_segment(block_id, trips):
    seg = DutySegment(block_id=block_id, trips=trips)
    return seg


def make_duty(id_, segments):
    d = Duty(id=id_)
    d.segments = segments
    return d


def make_csp(duties):
    return CSPSolution(duties=duties)


class TestReliefEstimator:

    def test_no_duties_returns_zero(self):
        """CSP vazio → estimativa zerada."""
        est = ReliefVehicleEstimator()
        report = est.estimate(make_csp([]))
        assert report.total_events == 0
        assert report.min_vehicles == 0
        assert report.total_cost == 0.0

    def test_single_duty_no_relief(self):
        """Um único motorista cobre o bloco inteiro — sem rendição."""
        trips = [make_trip(1, 300, 360), make_trip(2, 380, 440)]
        seg = make_segment(block_id=1, trips=trips)
        duty = make_duty(1, [seg])
        report = ReliefVehicleEstimator().estimate(make_csp([duty]))
        assert report.total_events == 0
        assert report.min_vehicles == 0

    def test_two_duties_same_block_one_relief(self):
        """Dois motoristas cobrem partes distintas do mesmo bloco → 1 rendição."""
        t1 = make_trip(1, 300, 360)
        t2 = make_trip(2, 380, 440, origin_id=3)
        seg1 = make_segment(block_id=1, trips=[t1])
        seg2 = make_segment(block_id=1, trips=[t2])
        d1 = make_duty(1, [seg1])
        d2 = make_duty(2, [seg2])
        est = ReliefVehicleEstimator(travel_minutes=10, cost_per_event=50.0)
        report = est.estimate(make_csp([d1, d2]))
        assert report.total_events == 1
        assert report.total_cost == pytest.approx(50.0)
        ev = report.events[0]
        assert ev.block_id == 1
        assert ev.from_duty_id == 1
        assert ev.to_duty_id == 2
        assert ev.handoff_time == 380
        assert ev.location_id == 3

    def test_same_driver_both_segments_no_relief(self):
        """Mesmo duty cobrindo dois segmentos do mesmo bloco → sem rendição."""
        t1 = make_trip(1, 300, 360)
        t2 = make_trip(2, 380, 440)
        seg1 = make_segment(block_id=1, trips=[t1])
        seg2 = make_segment(block_id=1, trips=[t2])
        d1 = make_duty(1, [seg1, seg2])
        report = ReliefVehicleEstimator().estimate(make_csp([d1]))
        assert report.total_events == 0

    def test_min_vehicles_sequential_one_enough(self):
        """Duas rendições bem espaçadas → 1 veículo de apoio basta."""
        # Rendição 1 às 300, rendição 2 às 400, travel=10 → veículo livre às 310
        t1a = make_trip(1, 240, 300)
        t1b = make_trip(2, 300, 360)
        t2a = make_trip(3, 360, 400)
        t2b = make_trip(4, 400, 460)
        seg1a = make_segment(block_id=1, trips=[t1a])
        seg1b = make_segment(block_id=1, trips=[t1b])
        seg2a = make_segment(block_id=2, trips=[t2a])
        seg2b = make_segment(block_id=2, trips=[t2b])
        d1 = make_duty(1, [seg1a, seg2a])
        d2 = make_duty(2, [seg1b, seg2b])
        est = ReliefVehicleEstimator(travel_minutes=10)
        report = est.estimate(make_csp([d1, d2]))
        assert report.total_events == 2
        assert report.min_vehicles == 1  # 1 veículo cobre ambas (300→310, então livre para 400)

    def test_min_vehicles_concurrent_two_needed(self):
        """Duas rendições simultâneas → 2 veículos."""
        t1a = make_trip(1, 240, 300)
        t1b = make_trip(2, 300, 360)
        t2a = make_trip(3, 240, 300)
        t2b = make_trip(4, 300, 360)
        seg1a = make_segment(block_id=1, trips=[t1a])
        seg1b = make_segment(block_id=1, trips=[t1b])
        seg2a = make_segment(block_id=2, trips=[t2a])
        seg2b = make_segment(block_id=2, trips=[t2b])
        d1 = make_duty(1, [seg1a, seg2a])
        d2 = make_duty(2, [seg1b, seg2b])
        est = ReliefVehicleEstimator(travel_minutes=30)  # longo → não reutiliza
        report = est.estimate(make_csp([d1, d2]))
        assert report.total_events == 2
        assert report.min_vehicles == 2

    def test_peak_hour_detected(self):
        """Peak hour é a hora com mais rendições."""
        # 2 rendições às 7h (420 min), 1 às 8h (480 min)
        def make_handoff_duties(block_id, handoff_time):
            ta = make_trip(block_id * 10 + 1, handoff_time - 60, handoff_time)
            tb = make_trip(block_id * 10 + 2, handoff_time, handoff_time + 60)
            da = make_duty(block_id * 10 + 1, [make_segment(block_id, [ta])])
            db = make_duty(block_id * 10 + 2, [make_segment(block_id, [tb])])
            return da, db

        d1a, d1b = make_handoff_duties(1, 420)
        d2a, d2b = make_handoff_duties(2, 425)
        d3a, d3b = make_handoff_duties(3, 480)
        csp = make_csp([d1a, d1b, d2a, d2b, d3a, d3b])
        report = ReliefVehicleEstimator().estimate(csp)
        assert report.peak_hour == 7  # 420//60 == 7

    def test_to_dict_structure(self):
        """to_dict deve incluir campos esperados."""
        t1 = make_trip(1, 300, 360)
        t2 = make_trip(2, 360, 420)
        seg1 = make_segment(block_id=1, trips=[t1])
        seg2 = make_segment(block_id=1, trips=[t2])
        d1 = make_duty(1, [seg1])
        d2 = make_duty(2, [seg2])
        report = ReliefVehicleEstimator().estimate(make_csp([d1, d2]))
        d = report.to_dict()
        assert "total_events" in d
        assert "min_vehicles" in d
        assert "peak_hour" in d
        assert "total_cost" in d
        assert "hourly_distribution" in d
        assert "events" in d
        assert len(d["events"]) == 1
        ev = d["events"][0]
        assert "block_id" in ev
        assert "handoff_time" in ev
        assert "from_duty_id" in ev
        assert "to_duty_id" in ev
