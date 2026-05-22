"""
FASE 5.3 — Testes para select_vehicle_type e integração com algoritmos VSP.

Verifica que greedy/mcnf/genetic/assignment escolhem o tipo correto
por depot e custo, em vez de hardcodar vehicle_types[0].
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from src.domain.models import Trip, VehicleType
from src.algorithms.utils import select_vehicle_type
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.mcnf import MCNFVSP


# ─── fixtures ────────────────────────────────────────────────────────────────

def make_vt(id, fixed_cost=800.0, depot_id=None):
    return VehicleType(
        id=id,
        name=f"Type-{id}",
        passenger_capacity=60,
        fixed_cost=fixed_cost,
        depot_id=depot_id,
    )


def make_trip(id, start, end, origin=1, dest=2, depot_id=None, line_id=1):
    t = Trip(
        id=id,
        line_id=line_id,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        distance_km=10.0,
        depot_id=depot_id,
    )
    t.deadhead_times = {}
    return t


# ─── select_vehicle_type unit tests ──────────────────────────────────────────

class TestSelectVehicleType:
    def test_empty_returns_none(self):
        assert select_vehicle_type([]) is None

    def test_single_returns_it(self):
        vt = make_vt(1)
        assert select_vehicle_type([vt]) is vt

    def test_no_depot_picks_cheapest_fixed_cost(self):
        expensive = make_vt(1, fixed_cost=1200.0)
        cheap = make_vt(2, fixed_cost=500.0)
        assert select_vehicle_type([expensive, cheap]) is cheap

    def test_with_depot_prefers_depot_match(self):
        global_vt = make_vt(1, fixed_cost=100.0, depot_id=None)   # sem depot — elegível sempre
        depot1_vt = make_vt(2, fixed_cost=800.0, depot_id=1)       # específico depot 1
        depot2_vt = make_vt(3, fixed_cost=800.0, depot_id=2)       # específico depot 2

        result = select_vehicle_type([global_vt, depot1_vt, depot2_vt], depot_id=1)
        # depot_id=1 → candidatos: global_vt (None) e depot1_vt (1). global é mais barato.
        assert result is global_vt

    def test_with_depot_excludes_other_depot_type(self):
        depot1_vt = make_vt(1, fixed_cost=500.0, depot_id=1)
        depot2_vt = make_vt(2, fixed_cost=300.0, depot_id=2)
        # depot_id=1 → só depot1_vt é compatível (depot2 excluído)
        result = select_vehicle_type([depot1_vt, depot2_vt], depot_id=1)
        assert result is depot1_vt

    def test_no_compatible_depot_falls_back_to_cheapest(self):
        depot1_vt = make_vt(1, fixed_cost=500.0, depot_id=1)
        depot2_vt = make_vt(2, fixed_cost=300.0, depot_id=2)
        # depot_id=3 → nenhum match → retorna o mais barato de todos
        result = select_vehicle_type([depot1_vt, depot2_vt], depot_id=3)
        assert result is depot2_vt

    def test_depot_none_does_not_filter(self):
        a = make_vt(1, fixed_cost=900.0, depot_id=5)
        b = make_vt(2, fixed_cost=400.0, depot_id=7)
        # sem depot_id no argumento → não filtra, retorna mais barato
        assert select_vehicle_type([a, b]) is b


# ─── integração com GreedyVSP ────────────────────────────────────────────────

class TestGreedyVSPVehicleTypeSelection:
    def test_single_type_assigned_to_block(self):
        trips = [make_trip(1, 0, 60), make_trip(2, 120, 180)]
        vts = [make_vt(1)]
        sol = GreedyVSP().solve(trips, vts)
        for blk in sol.blocks:
            assert blk.vehicle_type_id == 1

    def test_multi_type_no_depot_picks_cheapest(self):
        trips = [make_trip(1, 0, 60), make_trip(2, 120, 180)]
        cheap = make_vt(10, fixed_cost=300.0)
        expensive = make_vt(20, fixed_cost=900.0)
        sol = GreedyVSP().solve(trips, [expensive, cheap])
        for blk in sol.blocks:
            assert blk.vehicle_type_id == cheap.id, (
                f"Esperado {cheap.id} (barato), obtido {blk.vehicle_type_id}"
            )

    def test_multi_type_different_depots_assigned_correctly(self):
        # Trip depot=1 deve receber vt_d1, trip depot=2 deve receber vt_d2
        trip_d1 = make_trip(1, 0, 60, depot_id=1)
        trip_d2 = make_trip(2, 0, 60, origin=3, dest=4, depot_id=2)

        vt_d1 = make_vt(1, fixed_cost=800.0, depot_id=1)
        vt_d2 = make_vt(2, fixed_cost=800.0, depot_id=2)

        sol = GreedyVSP({"same_depot_required": True}).solve(
            [trip_d1, trip_d2], [vt_d1, vt_d2]
        )
        vt_map = {blk.trips[0].depot_id: blk.vehicle_type_id for blk in sol.blocks if blk.trips}
        if 1 in vt_map:
            assert vt_map[1] == vt_d1.id, f"depot=1 deveria usar vt_d1, obteve {vt_map[1]}"
        if 2 in vt_map:
            assert vt_map[2] == vt_d2.id, f"depot=2 deveria usar vt_d2, obteve {vt_map[2]}"


# ─── integração com MCNFVSP ──────────────────────────────────────────────────

class TestMCNFVSPVehicleTypeSelection:
    def test_single_type_assigned(self):
        trips = [
            make_trip(1, 0, 60),
            make_trip(2, 90, 150),
            make_trip(3, 180, 240),
        ]
        vts = [make_vt(5)]
        sol = MCNFVSP().solve(trips, vts)
        for blk in sol.blocks:
            assert blk.vehicle_type_id == 5

    def test_multi_type_picks_cheapest(self):
        trips = [
            make_trip(1, 0, 60),
            make_trip(2, 90, 150),
        ]
        cheap = make_vt(10, fixed_cost=200.0)
        expensive = make_vt(20, fixed_cost=1000.0)
        sol = MCNFVSP().solve(trips, [expensive, cheap])
        for blk in sol.blocks:
            assert blk.vehicle_type_id == cheap.id, (
                f"MCNF deveria usar tipo barato (id={cheap.id}), obteve {blk.vehicle_type_id}"
            )
