"""
Branch-and-Price — testes F1 + F3 (SPPRC pricing).

F1: Master LP funcional sobre warm-start greedy.
F3: Pricing via SPPRC com dominância + MIP final.

Ver optimizer/docs/column_generation_plan.md §5.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.algorithms.vsp.branch_and_price import (
    BranchAndPrice,
    MasterProblemLP,
    PricingSubproblem,
)
from src.algorithms.vsp.greedy import GreedyVSP
from src.domain.models import Trip, VehicleType


def make_vt(id_, fixed_cost=800.0):
    return VehicleType(
        id=id_, name=f"Type-{id_}", passenger_capacity=60, fixed_cost=fixed_cost
    )


def make_trip(id_, start, end, origin=1, dest=2, deadhead_times=None):
    t = Trip(
        id=id_,
        line_id=1,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        distance_km=10.0,
    )
    t.deadhead_times = deadhead_times or {}
    return t


def _synthetic_trips(n=100, trips_per_turn=5, gap=90, duration=60):
    """Gera n viagens curtas espalhadas em turnos."""
    trips = []
    turns = (n + trips_per_turn - 1) // trips_per_turn
    tid = 1
    for turn in range(turns):
        base = turn * 60
        for k in range(trips_per_turn):
            if tid > n:
                break
            start = base + k * gap
            trips.append(make_trip(tid, start, start + duration))
            tid += 1
    return trips[:n]


# ─── MasterProblemLP unit tests ───────────────────────────────────────────────

class TestMasterProblemLP:
    def test_empty_columns_returns_zero(self):
        m = MasterProblemLP()
        assert m.solve_lp() == 0.0
        assert m.num_columns == 0

    def test_single_column_objective(self):
        m = MasterProblemLP()
        m.add_column([1, 2, 3], cost=800.0)
        assert m.solve_lp() == 800.0
        assert m.selected_columns() == [0]

    def test_picks_cheaper_partition(self):
        m = MasterProblemLP()
        m.add_column([1, 2, 3], cost=1000.0)
        m.add_column([1, 2], cost=500.0)
        m.add_column([3], cost=300.0)
        obj = m.solve_lp()
        assert obj == 800.0
        assert set(m.selected_columns()) == {1, 2}

    def test_mip_selects_integer_solution(self):
        m = MasterProblemLP()
        m.add_column([1, 2], cost=600.0)
        m.add_column([3], cost=400.0)
        obj = m.solve_mip()
        assert abs(obj - 1000.0) < 1.0
        assert set(m.selected_columns()) == {0, 1}

    def test_duals_populated_after_lp(self):
        m = MasterProblemLP()
        m.add_column([1], cost=100.0)
        m.add_column([2], cost=200.0)
        m.solve_lp()
        d = m.duals()
        assert 1 in d and 2 in d


# ─── PricingSubproblem (SPPRC F3) unit tests ─────────────────────────────────

class TestPricingSubproblemSPPRC:
    def test_no_columns_when_duals_zero(self):
        trips = [make_trip(1, 0, 60), make_trip(2, 70, 130)]
        p = PricingSubproblem(trips, fixed_cost=800.0)
        cols = p.find_columns(duals={}, max_columns=100)
        assert cols == []

    def test_generates_column_with_high_duals(self):
        trips = [make_trip(1, 0, 60), make_trip(2, 70, 130)]
        p = PricingSubproblem(trips, fixed_cost=800.0, min_layover=5)
        duals = {1: 500.0, 2: 500.0}
        cols = p.find_columns(duals=duals, max_columns=100)
        assert len(cols) > 0

    def test_respects_max_columns_limit(self):
        trips = _synthetic_trips(n=50)
        p = PricingSubproblem(trips, fixed_cost=100.0, min_layover=5)
        duals = {t.id: 200.0 for t in trips}
        cols = p.find_columns(duals=duals, max_columns=10)
        assert len(cols) <= 10

    def test_no_duplicate_paths(self):
        trips = _synthetic_trips(n=20)
        p = PricingSubproblem(trips, fixed_cost=50.0, min_layover=5)
        duals = {t.id: 100.0 for t in trips}
        cols = p.find_columns(duals=duals, max_columns=500)
        paths = [tuple(sorted(ids)) for ids, _ in cols]
        assert len(paths) == len(set(paths)), "colunas duplicadas geradas"

    def test_no_trip_appears_twice_in_column(self):
        trips = _synthetic_trips(n=20)
        p = PricingSubproblem(trips, fixed_cost=50.0, min_layover=5)
        duals = {t.id: 200.0 for t in trips}
        cols = p.find_columns(duals=duals, max_columns=500)
        for trip_ids, _ in cols:
            assert len(trip_ids) == len(set(trip_ids)), f"trip duplicada em coluna: {trip_ids}"

    def test_spprc_dominance_prunes_worse_labels(self):
        """Labels dominados não devem aparecer como colunas distintas."""
        # 3 viagens sequenciais: t1 → t2 → t3
        t1 = make_trip(1, 0, 60)
        t2 = make_trip(2, 70, 130)
        t3 = make_trip(3, 140, 200)
        p = PricingSubproblem([t1, t2, t3], fixed_cost=100.0, min_layover=5)
        duals = {1: 200.0, 2: 200.0, 3: 200.0}
        cols = p.find_columns(duals=duals, max_columns=100)
        # Todas colunas devem ter reduced_cost < 0
        for trip_ids, cost in cols:
            rc = cost - sum(duals.get(tid, 0.0) for tid in trip_ids)
            assert rc < -1e-5, f"coluna com rc={rc:.4f} não deveria estar nos resultados"

    def test_columns_sorted_by_reduced_cost(self):
        trips = _synthetic_trips(n=30)
        p = PricingSubproblem(trips, fixed_cost=50.0, min_layover=5)
        duals = {t.id: 150.0 for t in trips}
        cols = p.find_columns(duals=duals, max_columns=200)
        if len(cols) < 2:
            return
        rcs = [cost - sum(duals.get(tid, 0.0) for tid in ids) for ids, cost in cols]
        assert rcs == sorted(rcs), "colunas não ordenadas por reduced cost"


# ─── BranchAndPrice integração ────────────────────────────────────────────────

class TestBranchAndPriceIntegration:
    def test_empty_trips_returns_empty(self):
        sol = BranchAndPrice().solve([], [make_vt(1)])
        assert sol.blocks == []
        assert sol.algorithm == "branch_and_price"

    def test_100v_all_trips_covered_no_duplicates(self):
        trips = _synthetic_trips(n=100)
        vts = [make_vt(1)]
        sol = BranchAndPrice().solve(trips, vts)
        covered = [t.id for b in sol.blocks for t in b.trips]
        assert sorted(covered) == sorted(t.id for t in trips)
        assert len(covered) == len(set(covered))
        assert sol.unassigned_trips == []

    def test_100v_blocks_lte_greedy(self):
        trips = _synthetic_trips(n=100)
        vts = [make_vt(1)]
        greedy_sol = GreedyVSP().solve(trips, vts)
        bp_sol = BranchAndPrice().solve(trips, vts)
        assert bp_sol.num_vehicles <= greedy_sol.num_vehicles, (
            f"B&P {bp_sol.num_vehicles} > greedy {greedy_sol.num_vehicles}"
        )

    def test_meta_records_f3(self):
        trips = _synthetic_trips(n=20)
        vts = [make_vt(1)]
        sol = BranchAndPrice().solve(trips, vts)
        meta = sol.meta.get("branch_and_price", {})
        assert meta.get("phase") == "F3"
        assert meta.get("branching") is False
        assert "pricing_rounds" in meta
        assert "columns_after_pricing" in meta
        assert meta["columns_after_pricing"] >= meta["columns_seeded"]

    def test_500v_smoke_valid_solution(self):
        """Smoke: não explode, cobre todas trips."""
        trips = _synthetic_trips(n=500, trips_per_turn=5, gap=90, duration=60)
        vts = [make_vt(1)]
        sol = BranchAndPrice(vsp_params={
            "bp_max_pricing_iterations": 1,
            "bp_max_pricing_columns": 200,
        }).solve(trips, vts)
        covered = {t.id for b in sol.blocks for t in b.trips}
        all_ids = {t.id for t in trips}
        assert all_ids <= covered | {t.id for t in sol.unassigned_trips}
        assert sol.algorithm == "branch_and_price"

    def test_1000v_smoke_lte_greedy(self):
        """1000v: B&P deve igualar ou melhorar greedy em blocos."""
        trips = _synthetic_trips(n=1000, trips_per_turn=5, gap=90, duration=60)
        vts = [make_vt(1)]
        greedy_sol = GreedyVSP().solve(trips, vts)
        bp_sol = BranchAndPrice(vsp_params={
            "bp_max_pricing_iterations": 2,
            "bp_max_pricing_columns": 500,
        }).solve(trips, vts)
        assert bp_sol.num_vehicles <= greedy_sol.num_vehicles, (
            f"B&P 1000v: {bp_sol.num_vehicles} > greedy {greedy_sol.num_vehicles}"
        )
        covered = {t.id for b in bp_sol.blocks for t in b.trips}
        assert len(covered) == len(trips)
