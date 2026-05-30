"""Real in-process benchmark of ALL registered algorithms.

Runs the same OptimizerService the Celery worker uses, on a Salvador-scale
instance, and checks optimization quality invariants per algorithm:
  - coverage: all trips assigned (no unassigned)
  - feasibility: no overlapping trips inside a block
  - cost: strictly positive, finite
  - vehicles vs max-concurrency lower bound (single-depot optimum proxy)
  - runtime

Usage: venv/bin/python scratch/bench_all_algorithms.py [n_linhas] [volume_scale]
"""
import sys, os, time, math, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType

# All VSP/joint algorithms that produce a vehicle schedule we can score.
ALGOS = [
    "greedy", "genetic", "simulated_annealing", "tabu_search",
    "mcnf", "assignment_vsp", "alns", "branch_and_price",
    "set_partitioning", "hybrid_pipeline", "joint_solver",
    "vcsp_pulp", "joint_bp", "regional", "lagrangean_joint",
    "bundle_method", "joint_timetable",
]


def max_concurrency(trips):
    ev = []
    for t in trips:
        ev.append((t.start_time, 1)); ev.append((t.end_time, -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = peak = 0
    for _, d in ev:
        cur += d; peak = max(peak, cur)
    return peak


def block_overlaps(block):
    ts = sorted(block.trips, key=lambda t: t.start_time)
    return sum(1 for a, b in zip(ts, ts[1:]) if b.start_time < a.end_time)


def main():
    n_linhas = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 2.1
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0

    trips = make_salvador_trips(n_linhas=n_linhas, seed=42, volume_scale=scale)
    lb = max_concurrency(trips)
    vt = vt_salvador()
    svc = OptimizerService()
    vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}

    print(f"INSTANCE trips={len(trips)} lines={n_linhas} scale={scale} "
          f"concurrency_LB={lb} time_budget={budget}s\n")
    hdr = f"{'algo':<20}{'s':>7}{'veh':>6}{'cov':>10}{'ovl':>5}{'cost':>14}{'gap%':>7}  status"
    print(hdr); print("-" * len(hdr))

    rows = []
    for algo in ALGOS:
        t0 = time.perf_counter()
        try:
            res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType(algo),
                          time_budget_s=budget, vsp_params=dict(vsp_params), cct_params={})
            el = time.perf_counter() - t0
            blocks = res.vsp.blocks if res.vsp else []
            uncov = len(res.vsp.unassigned_trips) if (res.vsp and res.vsp.unassigned_trips is not None) else -1
            covered = sum(len(b.trips) for b in blocks)
            overlaps = sum(block_overlaps(b) for b in blocks)
            cost = res.total_cost or 0.0
            gap = (len(blocks) - lb) / lb * 100 if lb else 0.0
            ok = (uncov == 0 and overlaps == 0 and cost > 0 and math.isfinite(cost)
                  and covered == len(trips) and len(blocks) >= lb)
            status = "OK" if ok else "FAIL"
            problems = []
            if covered != len(trips): problems.append(f"covered {covered}/{len(trips)}")
            if uncov not in (0, -1): problems.append(f"unassigned={uncov}")
            if overlaps: problems.append(f"overlaps={overlaps}")
            if not (cost > 0 and math.isfinite(cost)): problems.append(f"cost={cost}")
            if len(blocks) < lb: problems.append(f"veh<{lb}")
            if problems: status = "FAIL: " + ", ".join(problems)
            print(f"{algo:<20}{el:>7.1f}{len(blocks):>6}{covered:>7}/{len(trips):<3}"
                  f"{overlaps:>5}{cost:>14,.0f}{gap:>7.0f}  {status}")
            rows.append((algo, el, len(blocks), covered, overlaps, cost, gap, status))
        except Exception as e:
            el = time.perf_counter() - t0
            print(f"{algo:<20}{el:>7.1f}{'-':>6}{'-':>10}{'-':>5}{'-':>14}{'-':>7}  ERROR: {type(e).__name__}: {e}")
            rows.append((algo, el, None, None, None, None, None, f"ERROR: {e}"))

    print("\nSUMMARY")
    ok = [r for r in rows if r[7] == "OK"]
    print(f"  OK: {len(ok)}/{len(rows)}")
    valid = [r for r in ok]
    if valid:
        best = min(valid, key=lambda r: (r[2], r[5]))
        print(f"  best feasible: {best[0]} veh={best[2]} cost=R${best[5]:,.0f} gap={best[6]:.0f}%")
    for r in rows:
        if not str(r[7]).startswith("OK"):
            print(f"  ! {r[0]}: {r[7]}")


if __name__ == "__main__":
    main()
