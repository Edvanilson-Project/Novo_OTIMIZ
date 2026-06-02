"""Mede ONDE o HybridPipeline gasta tempo na instância Salvador (298 trips).
Grava JSON em /tmp/hybrid_phases.json para leitura confiável (stdout flaky)."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType

trips = make_salvador_trips(n_linhas=2, seed=42, volume_scale=2.1)
vt = vt_salvador()
svc = OptimizerService()
vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}

t0 = time.perf_counter()
res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType("hybrid_pipeline"),
              time_budget_s=20.0, vsp_params=dict(vsp_params), cct_params={})
wall = time.perf_counter() - t0

perf = (res.meta or {}).get("performance", {}) if res.meta else {}
out = {
    "wall_s": round(wall, 2),
    "vehicles": len(res.vsp.blocks) if res.vsp else None,
    "total_cost": round(res.total_cost, 2) if res.total_cost else None,
    "phase_timings_ms": perf.get("phase_timings_ms", {}),
    "selected_vsp_algorithm": perf.get("selected_vsp_algorithm"),
    "benchmark": perf.get("benchmark"),
    "vsp_metaheuristics_skipped": perf.get("vsp_metaheuristics_skipped"),
}
with open("/tmp/hybrid_phases.json", "w") as f:
    json.dump(out, f, indent=2)
print("WROTE /tmp/hybrid_phases.json")
