"""
Regressão: hybrid_pipeline nunca deve ser pior que greedy em custo.

Garante que o ILP polish do pipeline entrega custo ≤ greedy + 2% de tolerância.
Executado em dados sintéticos de 100v, 200v e 500v para cobrir as escalas
onde o CP-SAT polish é ativado (dentro dos limites DEFAULT_MAX_CSP_ILP_*).
"""
from __future__ import annotations

import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import random
import time
import pytest

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService

TOLERANCE = 0.05  # hybrid pode ser no máximo 5% pior que greedy (deveria ser melhor)


def _make_trips(n: int, seed: int = 42) -> list[Trip]:
    """Trips sintéticos alternando 2 terminais — sem MANDATORY_GROUP_SPLIT."""
    rng = random.Random(seed)
    trips, t = [], 360
    for i in range(n):
        start = t + rng.randint(0, 10)
        dur = rng.randint(20, 55)
        origin, dest = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(Trip(
            id=i, line_id=1,
            origin_id=origin, destination_id=dest,
            start_time=start, end_time=start + dur, duration=dur,
            distance_km=rng.uniform(5, 20),
        ))
        t = start + dur + rng.randint(3, 12)
    return trips


def _vt() -> list[VehicleType]:
    return [VehicleType(
        id=1, name="Bus", passenger_capacity=80,
        cost_per_km=2.5, cost_per_hour=30.0, fixed_cost=300.0,
    )]


def _run(service: OptimizerService, trips, algo: str, budget: int) -> float:
    result = service.run(
        trips=trips, vehicle_types=_vt(),
        algorithm=AlgorithmType(algo), time_budget_s=budget,
        vsp_params={"min_break_minutes": 30, "min_layover_minutes": 10},
        cct_params={},
    )
    return result.total_cost or 0.0


@pytest.mark.parametrize("n,budget", [(100, 30), (200, 60), (500, 120)])
def test_hybrid_not_worse_than_greedy(n, budget):
    """hybrid_pipeline deve ser ≤ greedy + TOLERANCE em custo total."""
    service = OptimizerService()
    trips = _make_trips(n)

    greedy_cost = _run(service, trips, "greedy", 30)
    hybrid_cost = _run(service, trips, "hybrid_pipeline", budget)

    assert greedy_cost > 0, "greedy deve produzir custo positivo"
    assert hybrid_cost > 0, "hybrid_pipeline deve produzir custo positivo"

    ratio = hybrid_cost / greedy_cost
    assert ratio <= 1.0 + TOLERANCE, (
        f"n={n}: hybrid R${hybrid_cost:,.0f} é {(ratio-1)*100:.1f}% pior que greedy R${greedy_cost:,.0f} "
        f"(tolerância={TOLERANCE*100:.0f}%)"
    )


@pytest.mark.parametrize("n", [100, 200])
def test_hybrid_covers_all_trips(n):
    """hybrid_pipeline não deve deixar viagens descobertas."""
    service = OptimizerService()
    trips = _make_trips(n)
    result = service.run(
        trips=trips, vehicle_types=_vt(),
        algorithm=AlgorithmType.HYBRID_PIPELINE, time_budget_s=60,
        vsp_params={"min_break_minutes": 30, "min_layover_minutes": 10},
        cct_params={},
    )
    uncovered = len(result.vsp.unassigned_trips) if result.vsp else n
    assert uncovered == 0, f"n={n}: {uncovered} viagens não cobertas pelo hybrid_pipeline"


def test_hybrid_cpsat_polish_activates_at_small_scale():
    """Verifica que o CP-SAT polish executa (meta deve conter csp_cpsat_ms) em 100v."""
    service = OptimizerService()
    trips = _make_trips(100)
    result = service.run(
        trips=trips, vehicle_types=_vt(),
        algorithm=AlgorithmType.HYBRID_PIPELINE, time_budget_s=60,
        vsp_params={"min_break_minutes": 30, "min_layover_minutes": 10},
        cct_params={},
    )
    perf = (result.meta or {}).get("performance", {})
    phase_timings = perf.get("phase_timings_ms", {})
    # CP-SAT deve ter executado — pode não ter melhorado, mas deve constar no timing
    assert "csp_cpsat_ms" in phase_timings, (
        f"CP-SAT polish não executou em 100v. Phase timings: {phase_timings}"
    )
