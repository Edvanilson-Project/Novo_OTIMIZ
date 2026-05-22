"""
Script para reproduzir 'list index out of range' no chunk final do hybrid pipeline.
Simula um chunk de ~200 viagens (tamanho típico do último chunk para 2000/5000 trips).
"""
import sys
import os
import traceback
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain.models import Trip, VehicleType
from src.algorithms.hybrid.pipeline import HybridPipeline


def make_trips(n: int, seed: int = 42) -> list[Trip]:
    rng = random.Random(seed)
    trips = []
    base = 360  # 6h
    for i in range(1, n + 1):
        start = base + rng.randint(0, 960)
        duration = rng.randint(20, 90)
        end = start + duration
        t = Trip(
            id=i,
            line_id=rng.randint(1, 5),
            origin_id=rng.randint(1, 10),
            destination_id=rng.randint(1, 10),
            start_time=start,
            end_time=end,
            duration=duration,
        )
        trips.append(t)
    trips.sort(key=lambda t: t.start_time)
    return trips


def make_vehicle_types() -> list[VehicleType]:
    return [VehicleType(id=1, name="Standard", passenger_capacity=40, fixed_cost=800.0)]


def run(n_trips: int, seed: int = 42):
    print(f"\n{'='*60}")
    print(f"Running hybrid pipeline with {n_trips} trips (seed={seed})")
    print(f"{'='*60}")
    trips = make_trips(n_trips, seed)
    vehicle_types = make_vehicle_types()
    pipeline = HybridPipeline(time_budget_s=30.0, cct_params={}, vsp_params={"random_seed": seed})
    try:
        result = pipeline.solve(trips, vehicle_types)
        print(f"SUCCESS: {len(result.vsp.blocks)} blocks, {result.csp.num_crew} crew, {result.csp.cct_violations} violations")
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()


if __name__ == "__main__":
    # Testa vários tamanhos, especialmente tamanhos de chunk final típicos
    for n in [5, 10, 15, 20, 50, 100, 200, 250]:
        run(n)
