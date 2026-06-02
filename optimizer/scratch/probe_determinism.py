"""Probe: WHAT actually varies run-to-run? Generator vs algorithm seed vs time-budget.

Runs a small pinned instance and repeats each algorithm twice, comparing
vehicles+cost. Writes JSON to /tmp/probe_determinism.json (reliable read)."""
import sys, os, json, time, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType

# Small pinned instance for speed.
SEED, N_LINHAS, SCALE, BUDGET = 42, 2, 0.6, 5.0


def trips_hash(trips):
    sig = [(t.id, t.start_time, t.end_time, t.origin_id, t.destination_id) for t in trips]
    return hashlib.sha256(repr(sig).encode()).hexdigest()[:12]


def run_once(svc, algo, trips, vt):
    vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}
    res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType(algo),
                  time_budget_s=BUDGET, vsp_params=vsp_params, cct_params={})
    return {
        "veh": len(res.vsp.blocks) if res.vsp else None,
        "cost": round(res.total_cost, 2) if res.total_cost else None,
    }


def main():
    out = {"instance": {"seed": SEED, "n_linhas": N_LINHAS, "scale": SCALE, "budget_s": BUDGET}}

    # 1) generator determinism
    h1 = trips_hash(make_salvador_trips(n_linhas=N_LINHAS, seed=SEED, volume_scale=SCALE))
    h2 = trips_hash(make_salvador_trips(n_linhas=N_LINHAS, seed=SEED, volume_scale=SCALE))
    out["generator"] = {"hash_run1": h1, "hash_run2": h2, "deterministic": h1 == h2}

    trips = make_salvador_trips(n_linhas=N_LINHAS, seed=SEED, volume_scale=SCALE)
    out["instance"]["n_trips"] = len(trips)
    vt = vt_salvador()
    svc = OptimizerService()

    out["algorithms"] = {}
    for algo in ["greedy", "mcnf", "simulated_annealing", "tabu_search", "hybrid_pipeline"]:
        r1 = run_once(svc, algo, trips, vt)
        r2 = run_once(svc, algo, trips, vt)
        out["algorithms"][algo] = {
            "run1": r1, "run2": r2,
            "deterministic": (r1["veh"] == r2["veh"] and r1["cost"] == r2["cost"]),
        }

    with open("/tmp/probe_determinism.json", "w") as f:
        json.dump(out, f, indent=2)
    print("WROTE /tmp/probe_determinism.json")


if __name__ == "__main__":
    main()
