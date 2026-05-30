"""Empirical A/B: does the deadhead term in the SA/Tabu proxy reduce REAL cost?

Builds a multi-line instance where chaining trips across terminals incurs real
deadhead (int-keyed deadhead_times). Runs greedy + SA + tabu with the proxy
deadhead weight set via vsp_params (0 = old blind behaviour, 1 = system default,
3 = stronger). Reports production total_cost + cross-terminal connection count.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.domain.models import Trip, VehicleType, AlgorithmType
from src.services.optimizer_service import OptimizerService

# 4 terminals. Cross-terminal deadhead = 25 min; same terminal = 0.
TERMS = [1, 2, 3, 4]
DH = 25
def dh_map():
    return {t: DH for t in TERMS}  # int keys (production path coerces to int)

def build():
    trips = []
    tid = 1
    # 3 lines, each on its own terminal pair, frequent headways so chaining is tempting.
    pairs = [(1, 2), (2, 3), (3, 4)]
    for li, (o, d) in enumerate(pairs, start=1):
        t = 300
        while t + 50 <= 1200:
            for (oo, dd) in ((o, d), (d, o)):
                dm = {k: (0 if k == dd else DH) for k in TERMS}  # arriving at dd, 0 to leave dd
                trips.append(Trip(id=tid, line_id=li, origin_id=oo, destination_id=dd,
                                  start_time=t, end_time=t + 50, duration=50,
                                  distance_km=22.5, deadhead_times=dm))
                tid += 1
                t += 30
    return trips

def cross_terminal_conns(blocks):
    n = 0
    for b in blocks:
        ts = sorted(b.trips, key=lambda x: x.start_time)
        for a, c in zip(ts, ts[1:]):
            if a.destination_id != c.origin_id:
                n += 1
    return n

def main():
    trips = build()
    vt = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800,
                      cost_per_km=2.5, cost_per_hour=30)]
    svc = OptimizerService()
    print(f"trips={len(trips)}  cross-terminal deadhead={DH}min\n")
    print(f"{'algo':<14}{'dh_w':>5}{'veh':>5}{'cov':>9}{'xterm':>7}{'cost':>13}")
    print("-" * 53)
    base = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}
    for algo in ("greedy", "simulated_annealing", "tabu_search"):
        weights = [None] if algo == "greedy" else [0.0, 1.0, 3.0]
        for w in weights:
            p = dict(base)
            if w is not None:
                p["deadhead_cost_per_minute"] = w
            res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType(algo),
                          time_budget_s=15, vsp_params=p, cct_params={})
            blocks = res.vsp.blocks if res.vsp else []
            covered = sum(len(b.trips) for b in blocks)
            print(f"{algo:<14}{(w if w is not None else '-'):>5}{len(blocks):>5}"
                  f"{covered:>6}/{len(trips):<3}{cross_terminal_conns(blocks):>7}{(res.total_cost or 0):>13,.0f}")

if __name__ == "__main__":
    main()
