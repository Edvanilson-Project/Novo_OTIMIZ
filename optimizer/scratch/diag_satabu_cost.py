"""Decompose WHY SA/Tabu cost > greedy at the same fleet.

Runs greedy/mcnf/SA/tabu/hybrid on a small pinned instance and splits the real
cost (CostEvaluator) into VSP parts (activation/idle/deadhead) + CSP crew.
Writes /tmp/diag_satabu.json (reliable read)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType
from src.algorithms.evaluator import CostEvaluator

SEED, N_LINHAS, SCALE, BUDGET = 42, 2, 2.1, 20.0  # 160-trip baseline instance


def main():
    trips = make_salvador_trips(n_linhas=N_LINHAS, seed=SEED, volume_scale=SCALE)
    vt = vt_salvador()
    svc = OptimizerService()
    ev = CostEvaluator()
    vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}

    out = {"instance": {"n_trips": len(trips), "budget_s": BUDGET}, "algos": {}}
    for algo in ["greedy", "mcnf", "simulated_annealing", "tabu_search", "hybrid_pipeline"]:
        res = svc.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType(algo),
                      time_budget_s=BUDGET, vsp_params=dict(vsp_params), cct_params={})
        bd = ev.total_cost_breakdown(res, vt)
        vsp, csp = bd["vsp"], bd["csp"]
        out["algos"][algo] = {
            "total": bd["total"],
            "vehicles": vsp["num_blocks"],
            "crew": res.csp.num_crew if res.csp else None,
            "vsp_total": vsp["total"],
            "activation": vsp["activation"],
            "idle_cost": vsp["idle_cost"],
            "deadhead_min": vsp["total_deadhead_minutes"],
            "distance+time": round(vsp["distance"] + vsp["time"], 2),
            "csp_total": csp["total"],
        }

    with open("/tmp/diag_satabu.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("WROTE /tmp/diag_satabu.json")


if __name__ == "__main__":
    main()
