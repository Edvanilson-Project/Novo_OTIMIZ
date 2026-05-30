"""Repro the hybrid_pipeline scale-decomposition failure and print the real cause."""
import sys, os, json, math, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
logging.basicConfig(level=logging.ERROR)

from tests.test_gtfs_real_salvador import build_real_salvador_trips
from src.domain.models import VehicleType, AlgorithmType
from src.services.optimizer_service import OptimizerService
from src.core.exceptions import OptimizerError

trips, stops, _ = build_real_salvador_trips(max_routes=40)

# Inject the same real Haversine deadhead matrix the bench used (this is what triggers the bug).
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
dh = {a: {b: (int(round(hav(coord[a], coord[b])/25.0*60)) if a in coord and b in coord else 0) for b in terms} for a in terms}
for t in trips:
    t.deadhead_times = dict(dh.get(t.destination_id, {}))

vt = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800, cost_per_km=2.5, cost_per_hour=30)]
svc = OptimizerService()
print(f"trips={len(trips)}")
import time as _t
_t0 = _t.perf_counter()
try:
    res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType("hybrid_pipeline"),
                  time_budget_s=30, vsp_params={"min_break_minutes": 30, "min_layover_minutes": 10,
                  "deadhead_cost_per_minute": 1.0},
                  cct_params={})
    fb = (res.meta.get("performance", {}) or {}).get("scale_decomposition_fallback")
    print(f"elapsed={_t.perf_counter()-_t0:.1f}s  fallback={fb}")
    print("OK", len(res.vsp.blocks))
except OptimizerError as e:
    print("OptimizerError code:", getattr(e, "code", None))
    details = getattr(e, "details", {}) or {}
    print("chunk_count:", details.get("chunk_count"))
    for fc in details.get("failed_chunks", []):
        print("FAILED CHUNK:", json.dumps({
            "chunk_index": fc.get("chunk_index"),
            "trip_count": fc.get("trip_count"),
            "error_code": fc.get("error_code"),
            "issues": fc.get("issues", [])[:8],
        }, ensure_ascii=False, indent=2))
except Exception as e:
    import traceback
    traceback.print_exc()
