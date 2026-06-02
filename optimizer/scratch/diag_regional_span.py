"""Validate the regional stitch span fix: max_block_span (1440, vehicle) vs the
old max_vehicle_shift (960, driver) cap. A/B on the same code via param override.
Checks coverage + overlaps stay intact. Writes /tmp/diag_regional.json."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType


def block_overlaps(block):
    ts = sorted(block.trips, key=lambda t: t.start_time)
    return sum(1 for a, b in zip(ts, ts[1:]) if b.start_time < a.end_time)


def run(svc, trips, vt, extra):
    vsp = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False, **extra}
    res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType("regional"),
                  time_budget_s=30.0, vsp_params=vsp, cct_params={})
    blocks = res.vsp.blocks if res.vsp else []
    covered = sum(len(b.trips) for b in blocks)
    return {
        "vehicles": len(blocks),
        "covered": covered,
        "overlaps": sum(block_overlaps(b) for b in blocks),
        "cost": round(res.total_cost, 2) if res.total_cost else None,
    }


def main():
    out = {}
    svc = OptimizerService()
    for scale, label in [(2.1, "160t"), (4.0, "~300t")]:
        trips = make_salvador_trips(n_linhas=2, seed=42, volume_scale=scale)
        vt = vt_salvador()
        out[label] = {
            "n_trips": len(trips),
            "old_960_shift_cap": run(svc, trips, vt, {"max_block_span_minutes": 960}),
            "new_1440_span_default": run(svc, trips, vt, {}),
        }
    with open("/tmp/diag_regional.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("WROTE /tmp/diag_regional.json")


if __name__ == "__main__":
    main()
