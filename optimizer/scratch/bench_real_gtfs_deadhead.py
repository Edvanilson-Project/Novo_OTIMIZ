"""Real GTFS Salvador card + REAL deadhead matrix (Haversine from terminal coords).

build_real_salvador_trips uses real SUNT routes/terminals but leaves deadhead
empty. Here we look up each terminal's real lat/lon from stops.txt, compute
Haversine distance → deadhead minutes (urban ~25 km/h), inject int-keyed
deadhead_times, and run every algorithm. Reports coverage/overlaps/cost/
vehicles vs the concurrency lower bound + the MCNF optimum (the honest,
theory-grounded baseline — NOT a fabricated OptBus number).
"""
import sys, os, time, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.test_gtfs_real_salvador import build_real_salvador_trips, _load_csv, FIXTURE_DIR
from src.domain.models import VehicleType, AlgorithmType
from src.services.optimizer_service import OptimizerService

URBAN_KMH = 25.0  # velocidade média urbana Salvador para deadhead


def haversine_km(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main():
    routes = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    trips, stops, _ = build_real_salvador_trips(max_routes=routes)

    # map terminal_id (index+1) -> real coords
    stop_ids = [s["stop_id"] for s in stops if s.get("stop_id")]
    coord_by_term = {}
    for idx, sid in enumerate(stop_ids):
        srow = next((s for s in stops if s.get("stop_id") == sid), None)
        if srow and srow.get("stop_lat") and srow.get("stop_lon"):
            try:
                coord_by_term[idx + 1] = (float(srow["stop_lat"]), float(srow["stop_lon"]))
            except ValueError:
                pass

    term_ids = sorted({t.origin_id for t in trips} | {t.destination_id for t in trips})
    # build deadhead matrix (minutes) between every terminal pair present
    dh = {}
    for a in term_ids:
        dh[a] = {}
        for b in term_ids:
            if a in coord_by_term and b in coord_by_term:
                km = haversine_km(coord_by_term[a], coord_by_term[b])
                dh[a][b] = int(round(km / URBAN_KMH * 60))
            else:
                dh[a][b] = 0
    # inject: deadhead_times on a trip = travel FROM its destination TO any terminal
    for t in trips:
        t.deadhead_times = dict(dh.get(t.destination_id, {}))

    sample = [v for row in dh.values() for v in row.values() if v > 0]
    print(f"REAL GTFS card: trips={len(trips)} routes={routes} terminals={len(term_ids)} "
          f"deadhead_minutes(min/med/max)="
          f"{min(sample) if sample else 0}/{sorted(sample)[len(sample)//2] if sample else 0}/{max(sample) if sample else 0}")

    vt = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800, cost_per_km=2.5, cost_per_hour=30)]
    svc = OptimizerService()

    # concurrency lower bound
    ev = []
    for t in trips:
        ev.append((t.start_time, 1)); ev.append((t.end_time, -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = lb = 0
    for _, d in ev:
        cur += d; lb = max(lb, cur)

    base = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False,
            "deadhead_cost_per_minute": 1.0}
    algos = ["greedy", "mcnf", "assignment_vsp", "simulated_annealing", "tabu_search",
             "genetic", "alns", "branch_and_price", "set_partitioning", "hybrid_pipeline",
             "joint_solver", "vcsp_pulp", "joint_bp", "regional", "joint_timetable"]
    # 3rd arg: comma-separated subset (e.g. "greedy,mcnf,hybrid_pipeline,regional")
    if len(sys.argv) > 3 and sys.argv[3].strip():
        algos = [a.strip() for a in sys.argv[3].split(",") if a.strip()]

    print(f"\nconcurrency_LB={lb}\n")
    print(f"{'algo':<20}{'s':>6}{'veh':>5}{'cov':>10}{'ovl':>5}{'cost':>13}{'gap%':>6}")
    print("-" * 65)
    results = {}
    for algo in algos:
        t0 = time.perf_counter()
        try:
            res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType(algo),
                          time_budget_s=budget, vsp_params=dict(base), cct_params={})
            el = time.perf_counter() - t0
            blocks = res.vsp.blocks if res.vsp else []
            covered = sum(len(b.trips) for b in blocks)
            overlaps = sum(1 for b in blocks for a, c in zip(sorted(b.trips, key=lambda x: x.start_time),
                          sorted(b.trips, key=lambda x: x.start_time)[1:]) if c.start_time < a.end_time)
            cost = res.total_cost or 0
            gap = (len(blocks) - lb) / lb * 100 if lb else 0
            results[algo] = (len(blocks), covered, overlaps, cost)
            print(f"{algo:<20}{el:>6.1f}{len(blocks):>5}{covered:>7}/{len(trips):<3}{overlaps:>5}{cost:>13,.0f}{gap:>6.0f}")
        except Exception as e:
            print(f"{algo:<20}{'ERR':>6}  {type(e).__name__}: {e}")

    # honest comparison vs theory
    feasible = {k: v for k, v in results.items() if v[1] == len(trips) and v[2] == 0}
    if feasible:
        best_v = min(v[0] for v in feasible.values())
        best_c = min(v[3] for v in feasible.values())
        print(f"\nBest fleet among feasible = {best_v} veh (concurrency LB = {lb}, "
              f"theoretical gap = {(best_v-lb)/lb*100:.0f}%)")
        print(f"Cheapest feasible schedule = R${best_c:,.0f}")


if __name__ == "__main__":
    main()
