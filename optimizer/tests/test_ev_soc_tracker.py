"""
EV SoC Tracker — testes unitários.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.algorithms.ev.soc_tracker import EVSoCTracker
from src.domain.models import Block, Trip, VehicleType, VSPSolution


def make_ev_vt(battery_kwh=200.0, minimum_soc=0.1, charge_rate_kw=100.0,
               energy_cost_per_kwh=2.0):
    return VehicleType(
        id=1, name="EV", passenger_capacity=60, fixed_cost=1200.0,
        is_electric=True, battery_capacity_kwh=battery_kwh,
        minimum_soc=minimum_soc, charge_rate_kw=charge_rate_kw,
        energy_cost_per_kwh=energy_cost_per_kwh,
    )


def make_non_ev_vt():
    return VehicleType(id=1, name="Diesel", passenger_capacity=60, fixed_cost=800.0)


def make_trip(id_, start, end, dist_km=10.0):
    t = Trip(id=id_, line_id=1, start_time=start, end_time=end,
             origin_id=1, destination_id=2, duration=end - start,
             distance_km=dist_km)
    t.deadhead_times = {}
    return t


def make_block(id_, trips):
    return Block(id=id_, trips=trips)


def make_solution(blocks):
    sol = VSPSolution(blocks=blocks, algorithm="test")
    return sol


class TestEVSoCTracker:

    def test_non_ev_returns_empty_report(self):
        """Veículo não-EV deve retornar relatório vazio."""
        tracker = EVSoCTracker(make_non_ev_vt())
        trips = [make_trip(1, 300, 360, 10.0)]
        sol = make_solution([make_block(1, trips)])
        report = tracker.track(sol)
        assert report.is_ev is False
        assert report.blocks == []
        assert report.total_energy_kwh == 0.0

    def test_single_trip_soc_reduction(self):
        """Uma trip de 10km × 1.8 kWh/km consome 18 kWh."""
        vt = make_ev_vt(battery_kwh=200.0, energy_cost_per_kwh=2.0)
        tracker = EVSoCTracker(vt, kwh_per_km=1.8)
        trips = [make_trip(1, 300, 360, 10.0)]
        sol = make_solution([make_block(1, trips)])
        report = tracker.track(sol)

        assert report.is_ev is True
        assert len(report.blocks) == 1
        b = report.blocks[0]
        assert b.total_distance_km == pytest.approx(10.0)
        assert b.total_energy_kwh == pytest.approx(18.0)
        assert b.soc_start_kwh == pytest.approx(200.0)
        assert b.soc_end_kwh == pytest.approx(200.0 - 18.0)
        assert b.total_energy_cost == pytest.approx(36.0)  # 18 * 2.0

    def test_below_minimum_soc_flagged(self):
        """Trip que drena abaixo do SoC mínimo deve ser marcada."""
        # battery=100, min_soc=0.5 → min=50kWh; trip consome 60kWh → abaixo do mínimo
        vt = make_ev_vt(battery_kwh=100.0, minimum_soc=0.5, charge_rate_kw=0.0)
        tracker = EVSoCTracker(vt, kwh_per_km=1.0)
        trips = [make_trip(1, 300, 360, 60.0)]
        sol = make_solution([make_block(1, trips)])
        report = tracker.track(sol)

        b = report.blocks[0]
        assert b.trips[0].below_minimum is True
        assert b.needs_mid_block_charge is True
        assert report.blocks_needing_mid_charge == 1

    def test_recharge_during_gap(self):
        """Gap entre trips permite recarga parcial."""
        # battery=100, consumo=40kWh (40km), gap=60min, charge_rate=60kW → 60kWh disponíveis
        # mas recarga máxima = 100 - (100-40) = 40kWh (bateria cheia)
        vt = make_ev_vt(battery_kwh=100.0, minimum_soc=0.0, charge_rate_kw=60.0)
        tracker = EVSoCTracker(vt, kwh_per_km=1.0, charge_efficiency=1.0)
        trips = [
            make_trip(1, 0, 60, 40.0),   # consome 40kWh → soc=60
            make_trip(2, 120, 180, 10.0), # gap=60min → recarga disponível=60kWh, cap=40kWh → soc=100
        ]
        sol = make_solution([make_block(1, trips)])
        report = tracker.track(sol)

        b = report.blocks[0]
        # Após trip 1: soc=60; recarga no gap 60min@60kW=60kWh, mas cap=40 → soc=100
        assert b.trips[0].energy_recharged_kwh == pytest.approx(40.0, abs=1.0)
        # Após recarga, trip 2 consome 10kWh → soc_final=90
        assert b.soc_end_kwh == pytest.approx(90.0, abs=1.0)

    def test_multiple_blocks_aggregated(self):
        """Relatório agrega energia e custo de múltiplos blocos."""
        vt = make_ev_vt(battery_kwh=200.0, energy_cost_per_kwh=3.0, charge_rate_kw=0.0)
        tracker = EVSoCTracker(vt, kwh_per_km=1.0)
        b1 = make_block(1, [make_trip(1, 300, 360, 20.0)])  # 20kWh
        b2 = make_block(2, [make_trip(2, 300, 360, 30.0)])  # 30kWh
        sol = make_solution([b1, b2])
        report = tracker.track(sol)

        assert report.total_energy_kwh == pytest.approx(50.0)
        assert report.total_energy_cost == pytest.approx(150.0)
        assert len(report.blocks) == 2

    def test_to_dict_structure(self):
        """to_dict deve incluir todos os campos esperados."""
        vt = make_ev_vt(battery_kwh=100.0)
        tracker = EVSoCTracker(vt)
        trips = [make_trip(1, 300, 360, 5.0)]
        sol = make_solution([make_block(1, trips)])
        report = tracker.track(sol)
        d = report.to_dict()

        assert "is_ev" in d
        assert "battery_kwh" in d
        assert "total_energy_kwh" in d
        assert "total_energy_cost" in d
        assert "blocks_needing_mid_charge" in d
        assert "blocks" in d
        assert len(d["blocks"]) == 1
        assert "trips" in d["blocks"][0]
        assert "soc_before_kwh" in d["blocks"][0]["trips"][0]
