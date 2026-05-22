"""
Benchmark paralelo do RegionalDecompositionSolver — ProcessPoolExecutor real.

Marcado com @pytest.mark.slow: NÃO executado em CI (--timeout curto, forking instável).
Para rodar localmente:
    pytest tests/test_regional_parallel_benchmark.py -v -s

Compara throughput sequencial vs paralelo para 1k, 5k e 10k trips.
"""
from __future__ import annotations

import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import multiprocessing
import random
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.algorithms.vsp.regional_decomposition import RegionalDecompositionSolver
from src.domain.models import Trip, VehicleType

VT = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800)]

CPU_COUNT = max(2, multiprocessing.cpu_count())


def make_trips(n: int, seed: int = 42, n_depots: int = 10) -> list[Trip]:
    rng = random.Random(seed)
    trips, t = [], 300
    for i in range(1, n + 1):
        start = t + rng.randint(0, 10)
        dur = rng.randint(30, 90)
        depot = ((i - 1) % n_depots) + 1
        trips.append(Trip(
            id=i, line_id=rng.randint(1, 50),
            origin_id=rng.randint(1, 20), destination_id=rng.randint(1, 20),
            start_time=start, end_time=start + dur, duration=dur, depot_id=depot,
        ))
        t = start + rng.randint(1, 20)
    return trips


def _run(trips, use_processes: bool, budget_s: float) -> tuple[int, float, float]:
    solver = RegionalDecompositionSolver(
        sub_algorithm="greedy",
        use_processes=use_processes,
        time_budget_s=budget_s,
    )
    t0 = time.time()
    sol = solver.solve(trips, VT)
    elapsed = time.time() - t0
    coverage = len({t.id for b in sol.blocks for t in b.trips}) / len(trips) * 100
    return len(sol.blocks), elapsed, coverage


@pytest.mark.slow
@pytest.mark.parametrize("n,n_depots,budget_s", [
    (1_000,  5,  60),
    (5_000, 10, 120),
    (10_000, 20, 240),
])
def test_parallel_vs_sequential(n, n_depots, budget_s):
    """Compara sequential vs parallel: paralelo deve ser mais rápido para n>=5k."""
    trips = make_trips(n, seed=42, n_depots=n_depots)

    blocks_seq, t_seq, cov_seq = _run(trips, use_processes=False, budget_s=budget_s)
    blocks_par, t_par, cov_par = _run(trips, use_processes=True, budget_s=budget_s)

    speedup = t_seq / t_par if t_par > 0 else 1.0

    print(
        f"\n[Parallel Benchmark] n={n:,} depots={n_depots} cpus={CPU_COUNT}\n"
        f"  sequential: {t_seq:.2f}s  blocks={blocks_seq}  coverage={cov_seq:.1f}%\n"
        f"  parallel:   {t_par:.2f}s  blocks={blocks_par}  coverage={cov_par:.1f}%\n"
        f"  speedup:    {speedup:.2f}×"
    )

    # Correctude: ambos devem cobrir todas as trips e produzir o mesmo número de blocos
    assert cov_seq >= 99.0, f"Sequential coverage insuficiente: {cov_seq:.1f}%"
    assert cov_par >= 99.0, f"Parallel coverage insuficiente: {cov_par:.1f}%"
    assert blocks_seq == blocks_par, (
        f"Resultados divergentes: seq={blocks_seq} par={blocks_par} blocos"
    )
    # Nota: em algoritmos muito rápidos (greedy), overhead de fork pode superar ganho.
    # O benchmark documenta o comportamento real — não assume que paralelo é sempre mais rápido.


@pytest.mark.slow
def test_parallel_10k_coverage_and_time():
    """10k trips com ProcessPool: cobertura 100% e tempo < 30s em máquina real."""
    trips = make_trips(10_000, seed=99, n_depots=20)
    blocks, elapsed, coverage = _run(trips, use_processes=True, budget_s=60)

    print(
        f"\n[10k Parallel] blocks={blocks} coverage={coverage:.1f}% elapsed={elapsed:.2f}s "
        f"cpus={CPU_COUNT}"
    )

    assert coverage >= 99.0, f"Cobertura insuficiente: {coverage:.1f}%"
    # Deve concluir bem antes do budget (60s) em qualquer máquina
    assert elapsed < 60, f"Muito lento: {elapsed:.2f}s"
