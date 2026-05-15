"""
Benchmark HiGHS vs CBC no mesmo problema de set covering CSP.
Executa para 3 tamanhos: 50, 100, 200 tarefas (sintéticas).
Compara: tempo de solver + status + custo da solução.
"""
import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import time
import random
from typing import List

import pulp

from src.domain.models import Block, Trip


def _make_blocks(n: int, seed: int = 42) -> List[Block]:
    rng = random.Random(seed)
    blocks = []
    t = 360  # 6h
    for i in range(n):
        start = t + rng.randint(0, 30)
        dur = rng.randint(30, 90)
        end = start + dur
        trip = Trip(
            id=i,
            line_id=1,
            start_terminal="A",
            end_terminal="B",
            start_time=start,
            end_time=end,
            distance_km=rng.uniform(5, 30),
            is_deadhead=False,
        )
        block = Block(id=i, trips=[trip], start_time=start, end_time=end)
        blocks.append(block)
        t = end + rng.randint(5, 20)
    return blocks


def _build_lp(n_tasks: int, columns, seed: int = 42) -> pulp.LpProblem:
    task_ids = list(range(n_tasks))
    prob = pulp.LpProblem("CSP_Bench", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(columns))]
    prob += pulp.lpSum(cost * x[i] for i, (_, cost) in enumerate(columns))
    for task_id in task_ids:
        prob += (
            pulp.lpSum(x[i] for i, (combo, _) in enumerate(columns) if task_id in combo) >= 1,
            f"cover_{task_id}",
        )
    return prob


def _generate_columns(n_tasks: int, seed: int = 42):
    rng = random.Random(seed)
    columns = []
    # Single-task columns
    for t in range(n_tasks):
        columns.append(([t], 50.0 + rng.uniform(0, 20)))
    # Two-task columns
    for _ in range(n_tasks * 3):
        a = rng.randint(0, n_tasks - 2)
        b = rng.randint(a + 1, n_tasks - 1)
        columns.append(([a, b], 60.0 + rng.uniform(0, 30)))
    # Three-task columns
    for _ in range(n_tasks * 2):
        tasks = sorted(rng.sample(range(n_tasks), min(3, n_tasks)))
        columns.append((tasks, 80.0 + rng.uniform(0, 40)))
    return columns


def run_benchmark(n_tasks: int, solver_fn, label: str) -> dict:
    columns = _generate_columns(n_tasks)
    prob = _build_lp(n_tasks, columns)
    t0 = time.perf_counter()
    prob.solve(solver_fn())
    elapsed = time.perf_counter() - t0
    status = pulp.LpStatus[prob.status]
    obj = pulp.value(prob.objective) or -1
    return {"solver": label, "n_tasks": n_tasks, "status": status, "time_s": round(elapsed, 3), "objective": round(obj, 2)}


def main():
    sizes = [50, 100, 200, 400]
    timeout = 30

    def cbc():
        return pulp.PULP_CBC_CMD(timeLimit=timeout, msg=0, keepFiles=False)

    def highs():
        return pulp.HiGHS(timeLimit=timeout, msg=0)

    results = []
    for n in sizes:
        r_cbc = run_benchmark(n, cbc, "CBC")
        r_hi = run_benchmark(n, highs, "HiGHS")
        results.append(r_cbc)
        results.append(r_hi)

    print(f"\n{'Solver':<10} {'Tasks':>6} {'Status':<12} {'Time(s)':>8} {'Obj':>10}  {'Speedup':>8}")
    print("-" * 60)
    by_size = {}
    for r in results:
        key = r["n_tasks"]
        by_size.setdefault(key, {})[r["solver"]] = r

    for n in sizes:
        cbc_r = by_size[n].get("CBC", {})
        hi_r = by_size[n].get("HiGHS", {})
        speedup = ""
        if cbc_r.get("time_s", 0) > 0 and hi_r.get("time_s", 0) > 0:
            ratio = cbc_r["time_s"] / hi_r["time_s"]
            speedup = f"{ratio:.1f}x"
        for r in [cbc_r, hi_r]:
            su = speedup if r["solver"] == "HiGHS" else ""
            print(f"{r['solver']:<10} {r['n_tasks']:>6} {r['status']:<12} {r['time_s']:>8.3f} {r['objective']:>10.2f}  {su:>8}")
        print()

    print("\nSummary:")
    for n in sizes:
        cbc_t = by_size[n]["CBC"]["time_s"]
        hi_t = by_size[n]["HiGHS"]["time_s"]
        ratio = cbc_t / hi_t if hi_t > 0 else 0
        print(f"  {n:4d} tasks: CBC={cbc_t:.3f}s  HiGHS={hi_t:.3f}s  → HiGHS {ratio:.1f}x faster")


if __name__ == "__main__":
    main()
