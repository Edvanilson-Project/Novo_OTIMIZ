"""
Diagnóstico: medir efeito de scale_stitch_max_gap_minutes em 2000v.

Hipótese: gap atual de 60min é conservador. Aumentar para 180/240min
deveria reduzir o número de blocos no hybrid_pipeline decomposed.

Como rodar:
    cd optimizer && source venv/bin/activate
    INTERNAL_OPTIMIZER_KEY="diagnostic-key-32chars-long-ok-now" python -m tests.diagnostic_2000v_stitching
"""
import time
from typing import Dict

from src.domain.models import AlgorithmType
from src.services.optimizer_service import OptimizerService
from tests.benchmark_sla import make_trips, make_vehicles


def run_one(max_gap: int) -> Dict:
    svc = OptimizerService()
    trips = make_trips(2000, seed=42)
    vehicles = make_vehicles()
    t0 = time.perf_counter()
    result = svc.run(
        trips=trips,
        vehicle_types=vehicles,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        depot_id=1,
        time_budget_s=600.0,
        vsp_params={"scale_stitch_max_gap_minutes": max_gap},
    )
    elapsed = time.perf_counter() - t0
    n_blocks = len(result.vsp.blocks) if result.vsp else 0
    cost = result.total_cost if result.total_cost is not None else 0.0
    stitching = (
        ((result.meta or {}).get("performance") or {}).get("scale_decomposition", {}).get("stitching", {})
    )
    return {
        "max_gap": max_gap,
        "elapsed_s": round(elapsed, 2),
        "n_blocks": n_blocks,
        "total_cost": round(cost, 2),
        "stitching": stitching,
    }


if __name__ == "__main__":
    print("Diagnostic: scale_stitch_max_gap_minutes effect on 2000v hybrid_pipeline\n")
    rows = []
    for gap in (60, 240):
        print(f"Running max_gap={gap}min...")
        r = run_one(gap)
        rows.append(r)
        print(f"  → blocks={r['n_blocks']}, time={r['elapsed_s']}s, cost={r['total_cost']:.0f}")
        print(f"  → stitching: attempted={r['stitching'].get('attempted', 0)} accepted={r['stitching'].get('accepted', 0)} rejected={r['stitching'].get('rejected', 0)}")
        print()

    print("\nSummary:")
    print(f"{'max_gap':>8} {'blocks':>7} {'time_s':>8} {'cost':>12} {'stitched':>9}")
    for r in rows:
        st = r["stitching"]
        print(f"{r['max_gap']:>8} {r['n_blocks']:>7} {r['elapsed_s']:>8.2f} {r['total_cost']:>12.2f} {st.get('accepted', 0):>9}")
