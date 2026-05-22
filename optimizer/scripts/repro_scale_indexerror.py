"""
Reproduz o 'list index out of range' no chunk final da scale decomposition.
Cria 2000 viagens sintéticas com trip_group_ids e executa via OptimizerService.
"""
import os
import sys
import random
import logging

logging.basicConfig(level=logging.WARNING)
# Captura warnings de SCALE para ver traceback
logging.getLogger("optimizer_service").setLevel(logging.DEBUG)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6")

from src.domain.models import Trip, VehicleType
from src.services.optimizer_service import OptimizerService, AlgorithmType


def make_trips(n: int, seed: int = 42) -> list:
    rng = random.Random(seed)
    trips = []
    n_lines = max(1, n // 60)
    n_terminals = max(2, n // 30)
    n_groups = max(1, n // 4)

    for i in range(1, n + 1):
        line_id = rng.randint(1, n_lines)
        origin = rng.randint(1, n_terminals)
        dest = rng.randint(1, n_terminals)
        while dest == origin:
            dest = rng.randint(1, n_terminals)
        start = rng.randint(300, 1380)
        dur = rng.randint(15, 90)
        group_id = rng.randint(1, n_groups) if rng.random() < 0.4 else None
        trips.append(Trip(
            id=i,
            line_id=line_id,
            origin_id=origin,
            destination_id=dest,
            start_time=start,
            end_time=start + dur,
            duration=dur,
            trip_group_id=group_id,
        ))
    trips.sort(key=lambda t: t.start_time)
    return trips


def run(n_trips: int):
    print(f"\n{'='*60}")
    print(f"Scale decomposition test: {n_trips} trips")
    print(f"{'='*60}")

    trips = make_trips(n_trips)
    vehicle_types = [VehicleType(id=1, name="Standard", passenger_capacity=40, fixed_cost=800.0)]

    svc = OptimizerService()
    try:
        result = svc.run(
            trips=trips,
            vehicle_types=vehicle_types,
            algorithm=AlgorithmType.HYBRID_PIPELINE,
            depot_id=None,
            time_budget_s=60.0,
            cct_params={},
            vsp_params={"random_seed": 42},
            optimization_params={"n_trips": n_trips},
        )
        status = result.meta.get("scale", {}).get("status", "no_scale") if result.meta else "ok"
        print(f"SUCCESS: status={status}, blocks={len(result.vsp.blocks)}, crew={result.csp.num_crew}")
    except Exception as exc:
        import traceback
        print(f"ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()


if __name__ == "__main__":
    for n in [2000, 5000]:
        run(n)
