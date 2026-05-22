"""
Benchmark de SLA do optimizer — executa in-process (sem HTTP).

Uso:
    cd optimizer && source venv/bin/activate
    python -m tests.benchmark_sla

Saída: tabela com (algoritmo, n_trips, tempo_s, n_blocks, custo_total).
"""
import random
import time
from dataclasses import dataclass
from typing import List, Tuple

from src.domain.models import Trip, VehicleType, AlgorithmType
from src.services.optimizer_service import OptimizerService

SEED = 42
SIZES = [100, 500, 1000, 2000]
ALGORITHMS = [
    AlgorithmType.GREEDY,
    AlgorithmType.MCNF,
    AlgorithmType.GENETIC,
    AlgorithmType.ASSIGNMENT_VSP,
    AlgorithmType.HYBRID_PIPELINE,
]

# SLA targets (segundos) por tamanho — passa/falha reportado no final
SLA: dict = {
    100: 15,
    500: 60,
    1000: 300,
    2000: 600,
}


def make_trips(n: int, seed: int = SEED) -> List[Trip]:
    rng = random.Random(seed)
    trips: List[Trip] = []
    terminals = list(range(1, 11))
    for i in range(1, n + 1):
        start = rng.randint(300, 1200)
        dur = rng.randint(20, 90)
        orig = rng.choice(terminals)
        dest = rng.choice([t for t in terminals if t != orig])
        trips.append(Trip(
            id=i,
            line_id=rng.randint(1, 10),
            start_time=start,
            end_time=start + dur,
            origin_id=orig,
            destination_id=dest,
            duration=dur,
            distance_km=round(rng.uniform(5.0, 25.0), 2),
            depot_id=1,
        ))
    return trips


def make_vehicles() -> List[VehicleType]:
    return [VehicleType(id=1, name="Standard", passenger_capacity=50,
                        fixed_cost=800.0, cost_per_km=2.5, cost_per_hour=30.0)]


@dataclass
class Row:
    algorithm: str
    n_trips: int
    elapsed_s: float
    n_blocks: int
    total_cost: float
    sla_ok: bool


def run_benchmark() -> List[Row]:
    svc = OptimizerService()
    vehicles = make_vehicles()
    rows: List[Row] = []

    for n in SIZES:
        trips = make_trips(n)
        for alg in ALGORITHMS:
            t0 = time.perf_counter()
            try:
                result = svc.run(
                    trips=trips,
                    vehicle_types=vehicles,
                    algorithm=alg,
                    depot_id=1,
                    time_budget_s=float(SLA[n]),
                )
                elapsed = time.perf_counter() - t0
                n_blocks = len(result.vsp.blocks) if result.vsp and result.vsp.blocks else 0
                cost = result.total_cost if result.total_cost is not None else 0.0
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                n_blocks = -1
                cost = -1.0
                print(f"  ERROR {alg.value} n={n}: {exc}")

            rows.append(Row(
                algorithm=alg.value,
                n_trips=n,
                elapsed_s=round(elapsed, 2),
                n_blocks=n_blocks,
                total_cost=round(cost, 2),
                sla_ok=elapsed <= SLA[n],
            ))

    return rows


def print_table(rows: List[Row]) -> None:
    header = f"{'algorithm':<22} {'n_trips':>7} {'time_s':>8} {'blocks':>7} {'cost':>12} {'SLA':>5}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for r in rows:
        sla_tag = "OK" if r.sla_ok else "FAIL"
        print(f"{r.algorithm:<22} {r.n_trips:>7} {r.elapsed_s:>8.2f} {r.n_blocks:>7} {r.total_cost:>12.2f} {sla_tag:>5}")
    print(sep)


def print_summary(rows: List[Row]) -> None:
    failures = [r for r in rows if not r.sla_ok]
    errors = [r for r in rows if r.n_blocks == -1]
    print(f"\nTotal runs : {len(rows)}")
    print(f"SLA passed : {len(rows) - len(failures)}")
    print(f"SLA failed : {len(failures)}")
    print(f"Errors     : {len(errors)}")
    if failures:
        print("\nFailing SLA targets:")
        for r in failures:
            print(f"  {r.algorithm} n={r.n_trips}: {r.elapsed_s:.2f}s > {SLA[r.n_trips]}s limit")


if __name__ == "__main__":
    print(f"\nOTIMIZ Benchmark — seed={SEED}, sizes={SIZES}")
    print(f"SLA limits: {SLA}\n")
    rows = run_benchmark()
    print_table(rows)
    print_summary(rows)
