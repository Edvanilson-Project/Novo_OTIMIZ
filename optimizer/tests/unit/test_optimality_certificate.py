"""
Tests for OptimalityCertifier — validates that the certificate combining
multiple lower bounds (Bodin & Golden, Lagrangian, Bundle) preserves the
invariant LB <= UB across all VSP algorithms.

A violation (LB > UB) means either the LB calculation is wrong OR the
solution is infeasible — both are bugs to surface immediately.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.algorithms.optimality_certificate import (
    _bodin_golden_lb,
    certify_optimality,
)
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from src.algorithms.vsp.tabu_search import TabuSearchVSP
from src.algorithms.vsp.mcnf import MCNFVSP
from src.domain.models import (
    Block,
    CSPSolution,
    OptimizationResult,
    Trip,
    VehicleType,
    VSPSolution,
)


def _trip(tid: int, start: int, end: int) -> Trip:
    return Trip(
        id=tid,
        line_id=1,
        start_time=start,
        end_time=end,
        origin_id=1,
        destination_id=2,
        duration=end - start,
    )


def _make_result(vsp: VSPSolution, meta: dict | None = None) -> OptimizationResult:
    if meta:
        if vsp.meta is None:
            vsp.meta = {}
        vsp.meta.update(meta)
    return OptimizationResult(vsp=vsp, csp=CSPSolution(algorithm="none"))


# ── Bodin & Golden LB unit tests ─────────────────────────────────────────────


class TestBodinGoldenLowerBound:
    def test_empty_trips_returns_zero(self):
        assert _bodin_golden_lb([]) == 0

    def test_no_overlap_returns_one(self):
        trips = [_trip(1, 0, 60), _trip(2, 60, 120), _trip(3, 120, 180)]
        assert _bodin_golden_lb(trips) == 1

    def test_two_concurrent_returns_two(self):
        trips = [_trip(1, 0, 100), _trip(2, 50, 150)]
        assert _bodin_golden_lb(trips) == 2

    def test_peak_three_concurrent(self):
        # Trips 1, 2, 3 todos ativos no minuto 60
        trips = [
            _trip(1, 0, 100),
            _trip(2, 30, 90),
            _trip(3, 50, 70),
            _trip(4, 200, 250),
        ]
        assert _bodin_golden_lb(trips) == 3


# ── Certificate structure ────────────────────────────────────────────────────


class TestCertificateStructure:
    def test_empty_result(self):
        result = _make_result(VSPSolution(algorithm="empty"))
        cert = certify_optimality(result)
        assert cert["vsp_lower_bound"] == 0
        assert cert["vsp_actual"] == 0
        assert cert["lb_method"] == "none"

    def test_certificate_has_all_keys(self):
        blocks = [Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 60)])]
        result = _make_result(VSPSolution(blocks=blocks, algorithm="test"))
        cert = certify_optimality(result)
        for key in [
            "vsp_lower_bound",
            "vsp_actual",
            "vsp_gap_pct",
            "vsp_gap_explained",
            "lb_method",
            "lb_sources",
            "is_optimal_certified",
        ]:
            assert key in cert, f"missing key: {key}"

    def test_bodin_only_when_no_extra_meta(self):
        # Sem meta lagrangean/bundle → só Bodin disponível
        blocks = [Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 60), _trip(2, 60, 120)])]
        result = _make_result(VSPSolution(blocks=blocks, algorithm="greedy"))
        cert = certify_optimality(result)
        assert cert["lb_method"] == "bodin_golden"
        assert "lagrangean" not in cert["lb_sources"]
        assert "bundle" not in cert["lb_sources"]


# ── Best-of LB selection ─────────────────────────────────────────────────────


class TestBestOfSelection:
    def test_lagrangean_wins_when_higher(self):
        # Bodin=1 (no overlap), Lagrangian=5 → cert escolhe Lagrangian
        blocks = [Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 60), _trip(2, 60, 120)])]
        result = _make_result(
            VSPSolution(blocks=blocks, algorithm="lagrangean"),
            meta={"lagrangean_lower_bound": 5.0},
        )
        cert = certify_optimality(result)
        assert cert["lb_method"] == "lagrangean"
        assert cert["vsp_lower_bound"] == 5

    def test_bodin_wins_when_higher(self):
        # Bodin=2 (overlap), Lagrangian=1 → cert escolhe Bodin
        blocks = [Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 100), _trip(2, 50, 150)])]
        result = _make_result(
            VSPSolution(blocks=blocks, algorithm="lagrangean"),
            meta={"lagrangean_lower_bound": 1.0},
        )
        cert = certify_optimality(result)
        assert cert["lb_method"] == "bodin_golden"
        assert cert["vsp_lower_bound"] == 2

    def test_bundle_and_lagrangean_combined(self):
        blocks = [Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 60)])]
        result = _make_result(
            VSPSolution(blocks=blocks, algorithm="bundle"),
            meta={"lagrangean_lower_bound": 3.0, "bundle_lower_bound": 4.7},
        )
        cert = certify_optimality(result)
        assert cert["lb_method"] == "bundle"
        assert cert["vsp_lower_bound"] == 5  # round(4.7)
        assert "lagrangean" in cert["lb_sources"]
        assert "bundle" in cert["lb_sources"]


# ── Gap computation ──────────────────────────────────────────────────────────


class TestGapComputation:
    def test_gap_zero_when_optimal(self):
        # LB=2, UB=2 (2 trips concurrent → 2 blocks)
        blocks = [
            Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 100)]),
            Block(id=2, vehicle_type_id=1, trips=[_trip(2, 50, 150)]),
        ]
        result = _make_result(VSPSolution(blocks=blocks, algorithm="opt"))
        cert = certify_optimality(result)
        assert cert["vsp_gap_pct"] == 0.0
        assert cert["is_optimal_certified"] is True

    def test_gap_positive_when_subopt(self):
        # LB=1 (no overlap), UB=2 (2 blocks usados) → gap=100%
        blocks = [
            Block(id=1, vehicle_type_id=1, trips=[_trip(1, 0, 60)]),
            Block(id=2, vehicle_type_id=1, trips=[_trip(2, 60, 120)]),
        ]
        result = _make_result(VSPSolution(blocks=blocks, algorithm="subopt"))
        cert = certify_optimality(result)
        assert cert["vsp_lower_bound"] == 1
        assert cert["vsp_actual"] == 2
        assert cert["vsp_gap_pct"] == 100.0
        assert cert["is_optimal_certified"] is False


# ── Invariant tests: LB <= UB across all algorithms ──────────────────────────


def _peak_overlap_trips(n: int) -> list[Trip]:
    """Constrói n trips parcialmente sobrepostas — peak concurrent = n//2 + 1."""
    trips = []
    for i in range(n):
        trips.append(_trip(i + 1, i * 30, i * 30 + 200))
    return trips


class TestInvariantLBLessThanOrEqualUB:
    """
    INVARIANT: para qualquer solução viável, LB <= UB.
    Se quebrar, ou o LB está errado, ou a solução é infeasível.
    """

    @staticmethod
    def _vehicle_types() -> list[VehicleType]:
        return [
            VehicleType(
                id=1,
                name="standard",
                passenger_capacity=40,
                fixed_cost=200.0,
                cost_per_km=2.5,
            )
        ]

    def test_greedy_satisfies_lb_le_ub(self):
        trips = _peak_overlap_trips(10)
        sol = GreedyVSP(vsp_params={}).solve(trips, self._vehicle_types(), depot_id=1)
        result = _make_result(sol)
        cert = certify_optimality(result)
        assert cert["vsp_lower_bound"] <= cert["vsp_actual"], (
            f"LB={cert['vsp_lower_bound']} > UB={cert['vsp_actual']} via {cert['lb_method']}"
        )

    def test_simulated_annealing_satisfies_lb_le_ub(self):
        trips = _peak_overlap_trips(10)
        sol = SimulatedAnnealingVSP(vsp_params={"sa_iterations": 50}).solve(
            trips, self._vehicle_types(), depot_id=1
        )
        result = _make_result(sol)
        cert = certify_optimality(result)
        assert cert["vsp_lower_bound"] <= cert["vsp_actual"], (
            f"LB={cert['vsp_lower_bound']} > UB={cert['vsp_actual']} via {cert['lb_method']}"
        )

    def test_tabu_search_satisfies_lb_le_ub(self):
        trips = _peak_overlap_trips(10)
        sol = TabuSearchVSP(vsp_params={"tabu_iterations": 30}).solve(
            trips, self._vehicle_types(), depot_id=1
        )
        result = _make_result(sol)
        cert = certify_optimality(result)
        assert cert["vsp_lower_bound"] <= cert["vsp_actual"], (
            f"LB={cert['vsp_lower_bound']} > UB={cert['vsp_actual']} via {cert['lb_method']}"
        )

    def test_mcnf_satisfies_lb_le_ub(self):
        trips = _peak_overlap_trips(8)  # menor para MILP rápido
        sol = MCNFVSP(vsp_params={}).solve(trips, self._vehicle_types(), depot_id=1)
        result = _make_result(sol)
        cert = certify_optimality(result)
        assert cert["vsp_lower_bound"] <= cert["vsp_actual"], (
            f"LB={cert['vsp_lower_bound']} > UB={cert['vsp_actual']} via {cert['lb_method']}"
        )
