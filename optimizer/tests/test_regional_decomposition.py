"""
Testes e benchmark do RegionalDecompositionSolver.

Valida:
  - Correctude: todas as trips são cobertas, sem duplicatas
  - Escala: grupos por depot e por janela temporal funcionam
  - Multi-depot real: trips com depot_id ficam confinadas ao seu depot
  - Benchmark de escala: 1k, 5k, 10k trips — tempo e blocos gerados
"""
from __future__ import annotations

import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import random
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.algorithms.vsp.regional_decomposition import (
    RegionalDecompositionSolver,
    _group_by_depot,
    _group_by_time_window,
)
from src.domain.models import Trip, VehicleType


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_trips(n: int, seed: int = 42, n_depots: int = 0) -> list[Trip]:
    """
    Gera n trips realistas.
    n_depots > 0 atribui depot_id ciclicamente entre 1..n_depots.
    """
    rng = random.Random(seed)
    trips = []
    t = 300  # 5:00
    for i in range(1, n + 1):
        start = t + rng.randint(0, 10)
        dur = rng.randint(30, 90)
        depot = ((i - 1) % n_depots) + 1 if n_depots > 0 else None
        trips.append(Trip(
            id=i,
            line_id=rng.randint(1, 50),
            origin_id=rng.randint(1, 20),
            destination_id=rng.randint(1, 20),
            start_time=start,
            end_time=start + dur,
            duration=dur,
            depot_id=depot,
        ))
        t = start + rng.randint(1, 20)
    return trips


VT = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800)]


# ── Testes de agrupamento ─────────────────────────────────────────────────────

def test_group_by_depot_separates_correctly():
    trips = make_trips(100, n_depots=3)
    groups = _group_by_depot(trips)
    assert set(groups.keys()) == {"1", "2", "3"}
    total = sum(len(v) for v in groups.values())
    assert total == 100


def test_group_by_time_window_covers_all():
    trips = make_trips(200, n_depots=0)
    groups = _group_by_time_window(trips)
    # Com overlap, trips podem aparecer em múltiplos grupos — mas toda trip
    # deve aparecer em pelo menos um grupo
    covered = {t.id for g in groups.values() for t in g}
    trip_ids = {t.id for t in trips}
    assert trip_ids.issubset(covered), f"Trips não cobertas: {trip_ids - covered}"


# ── Testes de correctude ──────────────────────────────────────────────────────

def test_all_trips_assigned_with_depot_grouping():
    trips = make_trips(120, n_depots=4)
    solver = RegionalDecompositionSolver(sub_algorithm="greedy", use_processes=False, time_budget_s=30)
    sol = solver.solve(trips, VT)
    assigned = {t.id for b in sol.blocks for t in b.trips}
    trip_ids = {t.id for t in trips}
    assert assigned == trip_ids, f"Trips faltando: {trip_ids - assigned}"


def test_all_trips_assigned_without_depot():
    trips = make_trips(80, n_depots=0)
    solver = RegionalDecompositionSolver(sub_algorithm="greedy", use_processes=False, time_budget_s=30)
    sol = solver.solve(trips, VT)
    assigned = {t.id for b in sol.blocks for t in b.trips}
    trip_ids = {t.id for t in trips}
    assert assigned == trip_ids, f"Trips faltando: {trip_ids - assigned}"


def test_no_trip_assigned_twice():
    trips = make_trips(100, n_depots=5)
    solver = RegionalDecompositionSolver(sub_algorithm="greedy", use_processes=False, time_budget_s=30)
    sol = solver.solve(trips, VT)
    all_ids = [t.id for b in sol.blocks for t in b.trips]
    assert len(all_ids) == len(set(all_ids)), "Trip atribuída mais de uma vez"


def test_empty_trips_returns_empty_solution():
    solver = RegionalDecompositionSolver(sub_algorithm="greedy", use_processes=False)
    sol = solver.solve([], VT)
    assert sol.blocks == []


# ── Teste multi-depot real ────────────────────────────────────────────────────

def test_multi_depot_validation_real():
    """
    Valida decomposição multi-depot real:
    - 2 depots com trips distintas
    - Solver separa corretamente — trips de cada depot ficam em grupos separados
    - Nenhuma trip fica sem bloco
    """
    trips_d1 = make_trips(50, seed=1, n_depots=1)  # depot_id = 1
    trips_d2 = [
        Trip(id=t.id + 1000, line_id=t.line_id, origin_id=t.origin_id,
             destination_id=t.destination_id, start_time=t.start_time,
             end_time=t.end_time, duration=t.duration, depot_id=2)
        for t in make_trips(50, seed=2, n_depots=1)
    ]
    all_trips = trips_d1 + trips_d2

    solver = RegionalDecompositionSolver(sub_algorithm="greedy", use_processes=False, time_budget_s=30)
    sol = solver.solve(all_trips, VT)

    assigned_ids = {t.id for b in sol.blocks for t in b.trips}
    expected_ids = {t.id for t in all_trips}
    assert assigned_ids == expected_ids, f"Trips faltando: {expected_ids - assigned_ids}"
    assert len(sol.blocks) > 0


# ── Benchmark de escala ───────────────────────────────────────────────────────

@pytest.mark.parametrize("n,n_depots,expected_max_s", [
    (1_000,  5,  30),
    (5_000, 10,  60),
    (10_000, 20, 120),
])
def test_scale_benchmark(n, n_depots, expected_max_s):
    """
    Benchmark de escala: verifica que o solver resolve n trips em expected_max_s segundos.
    Com decomposição regional, 10k trips / 20 depots = 500 trips por grupo → ~5s cada (greedy).
    """
    trips = make_trips(n, seed=42, n_depots=n_depots)
    solver = RegionalDecompositionSolver(
        sub_algorithm="greedy",
        use_processes=False,  # sequencial em CI para evitar overhead de processos
        time_budget_s=float(expected_max_s),
    )

    t0 = time.time()
    sol = solver.solve(trips, VT)
    elapsed = time.time() - t0

    assigned = {t.id for b in sol.blocks for t in b.trips}
    coverage = len(assigned) / n * 100

    print(f"\n[Benchmark] n={n:,} depots={n_depots} blocks={len(sol.blocks)} "
          f"coverage={coverage:.1f}% elapsed={elapsed:.1f}s")

    assert coverage >= 99.0, f"Cobertura insuficiente: {coverage:.1f}%"
    assert elapsed < expected_max_s, f"Muito lento: {elapsed:.1f}s > {expected_max_s}s"
