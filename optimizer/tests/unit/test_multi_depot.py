"""
Testes de multi-depósito no VSP Greedy, SA e Tabu.

Valida que `same_depot_required=True` impede que viagens de depósitos diferentes
fiquem no mesmo bloco (veículo) em todos os algoritmos.
"""
from __future__ import annotations

import pytest
from src.domain.models import Trip, VehicleType, VSPSolution
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from src.algorithms.vsp.tabu_search import TabuSearchVSP
from src.algorithms.vsp.genetic import GeneticVSP


def _vt() -> VehicleType:
    return VehicleType(id=1, name="Bus", passenger_capacity=60, fixed_cost=800.0)


def _trip(
    id: int,
    start: int,
    end: int,
    origin: int = 1,
    dest: int = 2,
    depot_id: int | None = None,
) -> Trip:
    return Trip(
        id=id,
        line_id=1,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        depot_id=depot_id,
    )


class TestSingleDepot:
    """Comportamento padrão (same_depot_required=False): sem restrição de depósito."""

    def test_trips_same_depot_grouped(self):
        trips = [
            _trip(1, 360, 480, depot_id=1),
            _trip(2, 500, 620, depot_id=1),
        ]
        sol = GreedyVSP({"min_layover_minutes": 5}).solve(trips, [_vt()])
        assert len(sol.blocks) == 1, "Viagens do mesmo depósito devem ir ao mesmo bloco"

    def test_no_depot_no_restriction(self):
        trips = [
            _trip(1, 360, 480, depot_id=None),
            _trip(2, 500, 620, depot_id=None),
        ]
        sol = GreedyVSP({"min_layover_minutes": 5}).solve(trips, [_vt()])
        assert len(sol.blocks) == 1


class TestMultiDepotRestriction:
    """same_depot_required=True: viagens de depósitos diferentes devem ficar em blocos separados."""

    def test_different_depots_separate_blocks(self):
        trips = [
            _trip(1, 360, 480, depot_id=1),
            _trip(2, 500, 620, depot_id=2),  # depot diferente
        ]
        sol = GreedyVSP({
            "min_layover_minutes": 5,
            "same_depot_required": True,
        }).solve(trips, [_vt()])
        assert len(sol.blocks) == 2, (
            "Viagens de depósitos diferentes devem usar veículos diferentes"
        )

    def test_same_depot_still_grouped(self):
        trips = [
            _trip(1, 360, 480, depot_id=3),
            _trip(2, 500, 620, depot_id=3),
        ]
        sol = GreedyVSP({
            "min_layover_minutes": 5,
            "same_depot_required": True,
        }).solve(trips, [_vt()])
        assert len(sol.blocks) == 1, (
            "Viagens do mesmo depósito devem continuar agrupadas"
        )

    def test_mixed_none_and_depot(self):
        """Trips sem depot_id (None) não devem ser bloqueadas por same_depot_required."""
        trips = [
            _trip(1, 360, 480, depot_id=None),
            _trip(2, 500, 620, depot_id=None),
        ]
        sol = GreedyVSP({
            "min_layover_minutes": 5,
            "same_depot_required": True,
        }).solve(trips, [_vt()])
        # Com depot_id=None, a restrição não deve ser aplicada
        assert len(sol.blocks) == 1

    def test_three_depots(self):
        """3 depósitos → 3 blocos mínimos (um veículo por depósito)."""
        trips = [
            _trip(1, 360, 480, depot_id=1),
            _trip(2, 360, 480, depot_id=2),
            _trip(3, 360, 480, depot_id=3),
        ]
        sol = GreedyVSP({
            "min_layover_minutes": 5,
            "same_depot_required": True,
        }).solve(trips, [_vt()])
        assert len(sol.blocks) == 3

    def test_depot_ids_filter_in_optimizer(self):
        """
        O optimizer_service filtra trips por depot_ids antes de chamar o solver.
        Aqui simulamos esse filtro manualmente.
        """
        all_trips = [
            _trip(1, 360, 480, depot_id=1),
            _trip(2, 500, 620, depot_id=1),
            _trip(3, 360, 480, depot_id=2),
        ]
        # Filtrar apenas depot 1
        depot_trips = [t for t in all_trips if t.depot_id is None or t.depot_id == 1]
        sol = GreedyVSP({"min_layover_minutes": 5}).solve(depot_trips, [_vt()])
        assert len(sol.blocks) == 1
        assigned_ids = {t.id for b in sol.blocks for t in b.trips}
        assert 3 not in assigned_ids, "Viagem de depot 2 não deve aparecer no resultado"


class TestSAMultiDepot:
    """SA deve respeitar same_depot_required durante perturbações."""

    def test_sa_does_not_mix_depots(self):
        params = {
            "min_layover_minutes": 5,
            "same_depot_required": True,
            "random_seed": 42,
        }
        trips = [
            _trip(1, 360, 470, depot_id=1),
            _trip(2, 480, 590, depot_id=1),
            _trip(3, 360, 470, depot_id=2),
            _trip(4, 480, 590, depot_id=2),
        ]
        sol = SimulatedAnnealingVSP(vsp_params=params).solve(trips, [_vt()])
        for block in sol.blocks:
            depots = {t.depot_id for t in block.trips if t.depot_id is not None}
            assert len(depots) <= 1, f"SA misturou depósitos no bloco: {depots}"

    def test_sa_groups_same_depot(self):
        params = {
            "min_layover_minutes": 5,
            "same_depot_required": True,
            "random_seed": 42,
        }
        trips = [
            _trip(1, 360, 470, depot_id=1),
            _trip(2, 480, 590, depot_id=1),
        ]
        sol = SimulatedAnnealingVSP(vsp_params=params).solve(trips, [_vt()])
        assert len(sol.blocks) == 1


class TestTabuMultiDepot:
    """Tabu Search deve respeitar same_depot_required durante moves."""

    def test_tabu_does_not_mix_depots(self):
        params = {
            "min_layover_minutes": 5,
            "same_depot_required": True,
            "random_seed": 42,
        }
        trips = [
            _trip(1, 360, 470, depot_id=1),
            _trip(2, 480, 590, depot_id=1),
            _trip(3, 360, 470, depot_id=2),
            _trip(4, 480, 590, depot_id=2),
        ]
        sol = TabuSearchVSP(vsp_params=params).solve(trips, [_vt()])
        for block in sol.blocks:
            depots = {t.depot_id for t in block.trips if t.depot_id is not None}
            assert len(depots) <= 1, f"Tabu misturou depósitos no bloco: {depots}"

    def test_tabu_groups_same_depot(self):
        params = {
            "min_layover_minutes": 5,
            "same_depot_required": True,
            "random_seed": 42,
        }
        trips = [
            _trip(1, 360, 470, depot_id=1),
            _trip(2, 480, 590, depot_id=1),
        ]
        sol = TabuSearchVSP(vsp_params=params).solve(trips, [_vt()])
        assert len(sol.blocks) == 1


class TestGeneticMultiDepot:
    """Genetic VSP deve respeitar same_depot_required no repair/crossover/mutate."""

    def test_genetic_does_not_mix_depots(self):
        params = {
            "min_layover_minutes": 5,
            "same_depot_required": True,
            "random_seed": 42,
        }
        trips = [
            _trip(1, 360, 470, depot_id=1),
            _trip(2, 480, 590, depot_id=1),
            _trip(3, 360, 470, depot_id=2),
            _trip(4, 480, 590, depot_id=2),
        ]
        sol = GeneticVSP(vsp_params=params).solve(trips, [_vt()])
        for block in sol.blocks:
            depots = {t.depot_id for t in block.trips if t.depot_id is not None}
            assert len(depots) <= 1, f"Genetic misturou depósitos no bloco: {depots}"


class TestMultiDepotMeta:
    """Metadados de depósito devem ser preservados no bloco."""

    def test_block_carries_depot_meta(self):
        trips = [_trip(1, 360, 480, depot_id=5)]
        sol = GreedyVSP({"min_layover_minutes": 5}).solve(trips, [_vt()])
        assert len(sol.blocks) == 1
        blk = sol.blocks[0]
        assert blk.meta.get("start_depot_id") == 5

    def test_block_end_depot_updated(self):
        trips = [
            _trip(1, 360, 480, depot_id=5),
            _trip(2, 500, 620, depot_id=5),
        ]
        sol = GreedyVSP({"min_layover_minutes": 5}).solve(trips, [_vt()])
        blk = sol.blocks[0]
        assert blk.meta.get("end_depot_id") == 5
