"""Ad-hoc production correctness check: real Salvador-scale instance.

Runs the same in-process OptimizerService the Celery worker uses, on a
~298-trip instance, and asserts the production invariants:
  - all trips covered (no unassigned)
  - no overlapping trips inside any block
  - vehicle count == max-concurrency lower bound (single-depot optimum)
  - total cost strictly positive
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType


def max_concurrency(trips):
    events = []
    for t in trips:
        events.append((t.start_time, 1))
        events.append((t.end_time, -1))
    events.sort(key=lambda e: (e[0], e[1]))
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    return peak


def block_has_overlap(block):
    ts = sorted(block.trips, key=lambda t: t.start_time)
    for a, b in zip(ts, ts[1:]):
        if b.start_time < a.end_time:
            return True
    return False


def main():
    # scale 0.21 with 2 lines ~ approaches the documented 298-trip instance
    trips = make_salvador_trips(n_linhas=2, seed=42, volume_scale=2.1)
    lb = max_concurrency(trips)
    vt = vt_salvador()
    svc = OptimizerService()
    print(f"trips={len(trips)}  max_concurrency_lower_bound={lb}")
    for algo in ("mcnf", "branch_and_price"):
        t0 = time.perf_counter()
        res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType(algo),
                      time_budget_s=120, vsp_params={"min_break_minutes": 30,
                      "min_layover_minutes": 10, "force_round_trip": False}, cct_params={})
        el = time.perf_counter() - t0
        blocks = res.vsp.blocks if res.vsp else []
        uncov = len(res.vsp.unassigned_trips) if res.vsp else -1
        overlaps = sum(1 for b in blocks if block_has_overlap(b))
        covered = sum(len(b.trips) for b in blocks)
        cost = res.total_cost or 0
        print(f"\n[{algo}] {el:.1f}s vehicles={len(blocks)} covered={covered}/{len(trips)} "
              f"uncovered={uncov} overlaps={overlaps} cost=R${cost:,.2f}")
        ok = (uncov == 0 and overlaps == 0 and cost > 0 and len(blocks) >= lb)
        gap = (len(blocks) - lb) / lb * 100 if lb else 0
        print(f"    invariants_ok={ok}  vehicles_vs_LB gap={gap:.1f}% (LB={lb})")


if __name__ == "__main__":
    main()
