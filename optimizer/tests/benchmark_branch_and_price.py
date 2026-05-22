"""
Benchmark comparativo: greedy vs branch_and_price (F3 SPPRC).

Objetivo: medir gap de blocos e custo entre B&P e greedy em instâncias
de 500, 1000 e 2000 viagens sintéticas (seed=42, mesmo padrão do SLA).

Uso:
    cd optimizer
    python -m tests.benchmark_branch_and_price

Interpreta resultado:
    delta_blocks < 0 → B&P melhor (menos blocos = menos veículos)
    delta_blocks = 0 → empatou com greedy (warm-start domina)
    delta_blocks > 0 → B&P pior (bug ou MIP não convergiu no budget)
"""
import random
import time
from dataclasses import dataclass
from typing import List

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService

SEED = 42
SIZES = [500, 1000, 2000]

# B&P params por tamanho — mais iterações onde temos mais tempo
BP_PARAMS: dict = {
    500:  {"bp_max_pricing_iterations": 5,  "bp_max_pricing_columns": 1000, "bp_max_labels_per_node": 20},
    1000: {"bp_max_pricing_iterations": 3,  "bp_max_pricing_columns": 1000, "bp_max_labels_per_node": 15},
    2000: {"bp_max_pricing_iterations": 2,  "bp_max_pricing_columns": 500,  "bp_max_labels_per_node": 10},
}

# Budget em segundos
BUDGET: dict = {500: 120, 1000: 300, 2000: 600}


def make_trips(n: int, seed: int = SEED) -> List[Trip]:
    rng = random.Random(seed)
    terminals = list(range(1, 11))
    trips: List[Trip] = []
    for i in range(1, n + 1):
        start = rng.randint(300, 1200)
        dur = rng.randint(20, 90)
        orig = rng.choice(terminals)
        dest = rng.choice([t for t in terminals if t != orig])
        t = Trip(
            id=i,
            line_id=rng.randint(1, 10),
            start_time=start,
            end_time=start + dur,
            origin_id=orig,
            destination_id=dest,
            duration=dur,
            distance_km=round(rng.uniform(5.0, 25.0), 2),
            depot_id=1,
        )
        t.deadhead_times = {}
        trips.append(t)
    return trips


def make_vehicles() -> List[VehicleType]:
    return [VehicleType(id=1, name="Standard", passenger_capacity=50,
                        fixed_cost=800.0, cost_per_km=2.5, cost_per_hour=30.0)]


@dataclass
class Row:
    n: int
    algorithm: str
    elapsed_s: float
    blocks: int
    cost: float
    pricing_rounds: int
    new_cols: int


def run_one(svc, trips, vehicles, alg, budget_s, vsp_params=None) -> Row:
    n = len(trips)
    t0 = time.perf_counter()
    try:
        result = svc.run(
            trips=trips,
            vehicle_types=vehicles,
            algorithm=alg,
            depot_id=1,
            time_budget_s=float(budget_s),
            vsp_params=vsp_params or {},
        )
        elapsed = time.perf_counter() - t0
        blocks = len(result.vsp.blocks) if result.vsp else -1
        cost = float(result.total_cost or 0.0)
        bp_meta = (result.vsp.meta or {}).get("branch_and_price", {}) if result.vsp else {}
        pricing_rounds = bp_meta.get("pricing_rounds", 0)
        new_cols = bp_meta.get("new_cols_from_pricing", 0)
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        blocks, cost, pricing_rounds, new_cols = -1, -1.0, 0, 0
        print(f"  ERROR {alg.value} n={n}: {exc}")
    return Row(n, alg.value, round(elapsed, 2), blocks, round(cost, 2), pricing_rounds, new_cols)


def print_comparison(rows: list[Row]) -> None:
    # Group by n
    sizes = sorted({r.n for r in rows})
    header = f"{'n':>6} {'algorithm':<22} {'time_s':>8} {'blocks':>7} {'cost':>12} {'Δblocks':>8} {'rounds':>7} {'new_cols':>9}"
    sep = "─" * len(header)
    print(sep)
    print(header)
    print(sep)
    for n in sizes:
        n_rows = {r.algorithm: r for r in rows if r.n == n}
        greedy = n_rows.get("greedy")
        bp = n_rows.get("branch_and_price")
        for alg in ("greedy", "branch_and_price"):
            r = n_rows.get(alg)
            if not r:
                continue
            delta = ""
            if alg == "branch_and_price" and greedy and r.blocks >= 0 and greedy.blocks >= 0:
                d = r.blocks - greedy.blocks
                sign = "+" if d > 0 else ""
                delta = f"{sign}{d}"
            print(f"{r.n:>6} {r.algorithm:<22} {r.elapsed_s:>8.2f} {r.blocks:>7} {r.cost:>12.2f} {delta:>8} {r.pricing_rounds:>7} {r.new_cols:>9}")
        print()
    print(sep)


if __name__ == "__main__":
    svc = OptimizerService()
    vehicles = make_vehicles()
    all_rows: list[Row] = []

    print(f"\nBenchmark B&P vs Greedy — seed={SEED}, sizes={SIZES}\n")

    for n in SIZES:
        trips = make_trips(n)
        bp_params = BP_PARAMS[n]
        budget = BUDGET[n]

        print(f"n={n}: rodando greedy...", end=" ", flush=True)
        row_g = run_one(svc, trips, vehicles, AlgorithmType.GREEDY, budget)
        print(f"{row_g.elapsed_s:.1f}s → {row_g.blocks} blocos")
        all_rows.append(row_g)

        print(f"n={n}: rodando branch_and_price (iters={bp_params['bp_max_pricing_iterations']}, labels/nó={bp_params['bp_max_labels_per_node']})...", end=" ", flush=True)
        row_bp = run_one(svc, trips, vehicles, AlgorithmType.BRANCH_AND_PRICE, budget, vsp_params=bp_params)
        delta = row_bp.blocks - row_g.blocks if row_g.blocks > 0 else "?"
        sign = "+" if isinstance(delta, int) and delta > 0 else ""
        print(f"{row_bp.elapsed_s:.1f}s → {row_bp.blocks} blocos (Δ={sign}{delta})")
        all_rows.append(row_bp)

    print("\n=== TABELA COMPARATIVA ===\n")
    print_comparison(all_rows)

    # Resumo
    improvements = [
        r for r in all_rows if r.algorithm == "branch_and_price" and r.blocks >= 0
    ]
    greedy_map = {r.n: r.blocks for r in all_rows if r.algorithm == "greedy"}
    wins = sum(1 for r in improvements if r.blocks < greedy_map.get(r.n, 99999))
    ties = sum(1 for r in improvements if r.blocks == greedy_map.get(r.n, 99999))
    losses = sum(1 for r in improvements if r.blocks > greedy_map.get(r.n, 0))
    print(f"B&P melhor que greedy: {wins}/{len(improvements)} tamanhos")
    print(f"Empate:                {ties}/{len(improvements)}")
    print(f"B&P pior:              {losses}/{len(improvements)}")
