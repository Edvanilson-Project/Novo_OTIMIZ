"""Test hypothesis: mcnf loses optimality at scale because temporal/line clustering
doesn't reuse vehicles across chunks. Stitching its output should reduce the fleet."""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.test_gtfs_real_salvador import build_real_salvador_trips
from src.domain.models import VehicleType
from src.algorithms.vsp.mcnf import MCNFVSP
from src.algorithms.vsp.regional_decomposition import _stitch_blocks


def inject_deadhead(trips, stops):
    stop_ids = [s["stop_id"] for s in stops if s.get("stop_id")]
    coord = {}
    for idx, sid in enumerate(stop_ids):
        srow = next((s for s in stops if s.get("stop_id") == sid), None)
        if srow and srow.get("stop_lat") and srow.get("stop_lon"):
            try:
                coord[idx + 1] = (float(srow["stop_lat"]), float(srow["stop_lon"]))
            except ValueError:
                pass
    def hav(a, b):
        R = 6371.0; p1, p2 = math.radians(a[0]), math.radians(b[0])
        dphi = math.radians(b[0]-a[0]); dl = math.radians(b[1]-a[1])
        h = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*R*math.asin(math.sqrt(h))
    terms = sorted({t.origin_id for t in trips} | {t.destination_id for t in trips})
    dh = {a: {b: (int(round(hav(coord[a], coord[b])/25.0*60)) if a in coord and b in coord else 0)
              for b in terms} for a in terms}
    for t in trips:
        t.deadhead_times = dict(dh.get(t.destination_id, {}))


def overlaps(blocks):
    n = 0
    for b in blocks:
        ts = sorted(b.trips, key=lambda x: x.start_time)
        n += sum(1 for a, c in zip(ts, ts[1:]) if c.start_time < a.end_time)
    return n


def covered(blocks):
    return len({t.id for b in blocks for t in b.trips})


def run(routes):
    trips, stops, _ = build_real_salvador_trips(max_routes=routes)
    inject_deadhead(trips, stops)
    vt = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800, cost_per_km=2.5, cost_per_hour=30)]
    vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "deadhead_cost_per_minute": 1.0}
    solver = MCNFVSP(vsp_params=vsp_params)
    sol = solver.solve(trips, vt)
    before = len(sol.blocks)
    stitched = _stitch_blocks(list(sol.blocks), vsp_params)
    after = len(stitched)
    print(f"routes={routes} trips={len(trips)}: mcnf blocks={before} -> stitched={after} "
          f"(reduction {before-after}, {(before-after)/before*100:.0f}%) | "
          f"covered before/after={covered(sol.blocks)}/{covered(stitched)} "
          f"overlaps before/after={overlaps(sol.blocks)}/{overlaps(stitched)}")


if __name__ == "__main__":
    for r in (int(sys.argv[1]) if len(sys.argv) > 1 else 40,):
        run(r)
