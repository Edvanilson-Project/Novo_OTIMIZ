"""Real in-process benchmark of ALL registered algorithms.

Runs the same OptimizerService the Celery worker uses, on a Salvador-scale
instance, and checks optimization quality invariants per algorithm:
  - coverage: all trips assigned (no unassigned)
  - feasibility: no overlapping trips inside a block
  - cost: strictly positive, finite
  - vehicles vs max-concurrency lower bound (single-depot optimum proxy)
  - runtime

Usage: venv/bin/python scratch/bench_all_algorithms.py [--lines N] [--scale F]
                                                        [--budget S] [--out PATH]
                                                        [--repeat K]

--out writes a structured JSON (reliable read; stdout is flaky in this sandbox).
--repeat K runs the whole sweep K times and flags any algorithm whose
  (vehicles, cost) is not byte-identical across runs (determinism check).
"""
import sys, os, time, math, json, argparse
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


def run_sweep(svc, trips, vt, lb, budget, vsp_params):
    """One full pass over ALGOS. Returns list of per-algo result dicts."""
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
            viols = res.csp.cct_violations if res.csp else -1
            seed = (res.meta or {}).get("reproducibility", {}).get("random_seed") if res.meta else None
            gap = (len(blocks) - lb) / lb * 100 if lb else 0.0
            ok = (uncov == 0 and overlaps == 0 and cost > 0 and math.isfinite(cost)
                  and covered == len(trips) and len(blocks) >= lb)
            problems = []
            if covered != len(trips): problems.append(f"covered {covered}/{len(trips)}")
            if uncov not in (0, -1): problems.append(f"unassigned={uncov}")
            if overlaps: problems.append(f"overlaps={overlaps}")
            if not (cost > 0 and math.isfinite(cost)): problems.append(f"cost={cost}")
            if len(blocks) < lb: problems.append(f"veh<{lb}")
            status = "OK" if ok else "FAIL: " + ", ".join(problems)
            print(f"{algo:<20}{el:>7.1f}{len(blocks):>6}{covered:>7}/{len(trips):<3}"
                  f"{overlaps:>5}{cost:>14,.0f}{gap:>7.0f}  {status}")
            rows.append({"algo": algo, "elapsed_s": round(el, 2), "vehicles": len(blocks),
                         "covered": covered, "overlaps": overlaps, "cost": round(cost, 2),
                         "cct_violations": viols, "gap_pct": round(gap, 1),
                         "random_seed": seed, "status": status})
        except Exception as e:
            el = time.perf_counter() - t0
            print(f"{algo:<20}{el:>7.1f}{'-':>6}{'-':>10}{'-':>5}{'-':>14}{'-':>7}  ERROR: {type(e).__name__}: {e}")
            rows.append({"algo": algo, "elapsed_s": round(el, 2), "vehicles": None,
                         "covered": None, "overlaps": None, "cost": None,
                         "cct_violations": None, "gap_pct": None,
                         "random_seed": None, "status": f"ERROR: {type(e).__name__}: {e}"})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=2)
    ap.add_argument("--scale", type=float, default=2.1)
    ap.add_argument("--budget", type=float, default=60.0)
    ap.add_argument("--out", type=str, default=None, help="write JSON results to this path")
    ap.add_argument("--repeat", type=int, default=1, help="run sweep K times; flag non-determinism")
    args = ap.parse_args()

    trips = make_salvador_trips(n_linhas=args.lines, seed=42, volume_scale=args.scale)
    lb = max_concurrency(trips)
    vt = vt_salvador()
    svc = OptimizerService()
    vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}

    print(f"INSTANCE trips={len(trips)} lines={args.lines} scale={args.scale} "
          f"concurrency_LB={lb} time_budget={args.budget}s repeat={args.repeat}\n")

    passes = []
    for k in range(args.repeat):
        if args.repeat > 1:
            print(f"\n===== PASS {k + 1}/{args.repeat} =====")
        passes.append(run_sweep(svc, trips, vt, lb, args.budget, vsp_params))

    rows = passes[0]
    print("\nSUMMARY")
    ok = [r for r in rows if r["status"] == "OK"]
    print(f"  OK: {len(ok)}/{len(rows)}")
    if ok:
        best = min(ok, key=lambda r: (r["vehicles"], r["cost"]))
        print(f"  best feasible: {best['algo']} veh={best['vehicles']} "
              f"cost=R${best['cost']:,.0f} gap={best['gap_pct']:.0f}%")
    for r in rows:
        if not str(r["status"]).startswith("OK"):
            print(f"  ! {r['algo']}: {r['status']}")

    # Determinism check across passes (vehicles + cost must match byte-for-byte).
    determinism = {}
    if args.repeat > 1:
        print("\nDETERMINISM (vehicles+cost across passes)")
        for i, algo in enumerate(ALGOS):
            sigs = {(p[i]["vehicles"], p[i]["cost"]) for p in passes}
            stable = len(sigs) == 1
            determinism[algo] = {"stable": stable, "signatures": sorted(str(s) for s in sigs)}
            if not stable:
                print(f"  ! {algo} VARIES: {sorted(str(s) for s in sigs)}")
        if all(v["stable"] for v in determinism.values()):
            print("  all algorithms reproducible across passes ✓")

    if args.out:
        out = {
            "instance": {"lines": args.lines, "scale": args.scale, "n_trips": len(trips),
                         "gen_seed": 42, "concurrency_lb": lb, "time_budget_s": args.budget},
            "passes": passes,
            "determinism": determinism,
        }
        with open(args.out, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"\nWROTE {args.out}")


if __name__ == "__main__":
    main()
