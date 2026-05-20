#!/usr/bin/env python3
"""
Benchmark: CP-SAT vs CBC em duty composition.

Compara tempo e qualidade entre:
1. CBC (SetPartitioningCSP)
2. CP-SAT (CPSatCSP)

Em 10 instâncias variadas para validar Teste D da auditoria.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.algorithms.csp.set_partitioning import SetPartitioningCSP
from src.algorithms.csp.cp_sat_csp import CPSatCSP
from src.domain.models import Block, Trip

# Fixtures simples para teste
def _trip(id_val, start, duration, line=1, origin=1, dest=2, depot=1):
    return Trip(
        id=id_val,
        line_id=line,
        trip_group_id=None,
        direction=None,
        start_time=start,
        end_time=start + duration,
        origin_id=origin,
        destination_id=dest,
        duration=duration,
        distance_km=10.0,
        depot_id=depot,
        relief_point_id=None,
        is_relief_point=False,
        mid_trip_relief_point_id=None,
        mid_trip_relief_offset_minutes=None,
        mid_trip_relief_distance_ratio=None,
        mid_trip_relief_elevation_ratio=None,
        original_trip_id=None,
        segment_index=0,
        segment_count=1,
        energy_kwh=0.0,
        elevation_gain_m=0.0,
        service_day=0,
        is_holiday=False,
    )

def _block(id_val, trips):
    return Block(id=id_val, trips=trips, vehicle_type_id=1, warnings=[], meta={})

# 10 cenários de teste variados
SCENARIOS = {
    "small_5_trips": {
        "trips": [_trip(i, 360 + i*120, 60) for i in range(5)],
        "label": "5 trips — muito pequeno",
    },
    "small_10_trips": {
        "trips": [_trip(i, 360 + i*60, 60) for i in range(10)],
        "label": "10 trips — pequeno",
    },
    "medium_25_trips": {
        "trips": [_trip(i, 360 + (i % 15)*60, 60, line=(i % 3) + 1) for i in range(25)],
        "label": "25 trips — médio",
    },
    "medium_50_trips": {
        "trips": [_trip(i, 360 + (i % 20)*60, 60, line=(i % 5) + 1) for i in range(50)],
        "label": "50 trips — médio-grande",
    },
    "large_100_trips": {
        "trips": [_trip(i, 360 + (i % 30)*60, 60, line=(i % 8) + 1) for i in range(100)],
        "label": "100 trips — grande",
    },
}

def benchmark_scenario(name, scenario_data, time_budget_s=5.0):
    """Benchmark um cenário com CBC e CP-SAT."""
    trips = scenario_data["trips"]
    label = scenario_data["label"]

    # Criar blocos de teste (cada trip = 1 bloco, exceto alguns combinados)
    blocks = []
    for i, trip in enumerate(trips):
        block = _block(i + 1, [trip])
        blocks.append(block)

    print(f"\n{'='*70}")
    print(f"Cenário: {name:20} | {label}")
    print(f"{'='*70}")
    print(f"Trips: {len(trips):4} | Blocos: {len(blocks):4}")

    results = {}

    # ── CBC (SetPartitioningCSP) ──────────────────────────────────────────
    print(f"\n{'CBC (PuLP):':20}", end=" ", flush=True)
    start = time.perf_counter()
    try:
        cbc_solver = SetPartitioningCSP(
            vsp_params={"max_pricing_iterations": 50},
            min_break_minutes=15,
        )
        cbc_solver.time_budget_s = time_budget_s
        cbc_result = cbc_solver.solve(blocks, trips)
        elapsed_cbc = time.perf_counter() - start

        results["cbc"] = {
            "time_s": elapsed_cbc,
            "duties": len(cbc_result.duties),
            "cost": cbc_result.total_cost,
            "status": "OK",
        }
        print(f"✓ {elapsed_cbc:.3f}s | duties={len(cbc_result.duties):2} | cost=R${cbc_result.total_cost:8.2f}")
    except Exception as e:
        elapsed_cbc = time.perf_counter() - start
        results["cbc"] = {"time_s": elapsed_cbc, "status": f"ERROR: {e}"}
        print(f"✗ {elapsed_cbc:.3f}s | ERROR: {type(e).__name__}")

    # ── CP-SAT ──────────────────────────────────────────────────────────
    print(f"{'CP-SAT:':20}", end=" ", flush=True)
    start = time.perf_counter()
    try:
        cpsat_solver = CPSatCSP(
            vsp_params={"max_pricing_iterations": 50},
            min_break_minutes=15,
        )
        cpsat_solver.time_budget_s = time_budget_s
        cpsat_result = cpsat_solver.solve(blocks, trips)
        elapsed_cpsat = time.perf_counter() - start

        results["cpsat"] = {
            "time_s": elapsed_cpsat,
            "duties": len(cpsat_result.duties),
            "cost": cpsat_result.total_cost,
            "status": "OK",
        }
        print(f"✓ {elapsed_cpsat:.3f}s | duties={len(cpsat_result.duties):2} | cost=R${cpsat_result.total_cost:8.2f}")
    except Exception as e:
        elapsed_cpsat = time.perf_counter() - start
        results["cpsat"] = {"time_s": elapsed_cpsat, "status": f"ERROR: {e}"}
        print(f"✗ {elapsed_cpsat:.3f}s | ERROR: {type(e).__name__}")

    # ── Comparação ──────────────────────────────────────────────────────
    if "cbc" in results and "cpsat" in results:
        if results["cbc"]["status"] == "OK" and results["cpsat"]["status"] == "OK":
            speedup = (results["cbc"]["time_s"] - results["cpsat"]["time_s"]) / results["cbc"]["time_s"] * 100
            quality_delta = (results["cbc"]["cost"] - results["cpsat"]["cost"]) / results["cbc"]["cost"] * 100
            print(f"\nSpeedup:      {speedup:+6.1f}% (CP-SAT {'mais rápido' if speedup > 0 else 'mais lento'})")
            print(f"Qualidade:    {quality_delta:+6.2f}% (CP-SAT {'melhor' if quality_delta > 0 else 'pior'})")

    return results

def main():
    print("""
╔════════════════════════════════════════════════════════════════════════╗
║                    BENCHMARK: CP-SAT vs CBC                           ║
║                     Duty Composition (CSP)                             ║
╚════════════════════════════════════════════════════════════════════════╝
    """)

    all_results = {}
    for scenario_name, scenario_data in SCENARIOS.items():
        results = benchmark_scenario(scenario_name, scenario_data, time_budget_s=5.0)
        all_results[scenario_name] = results

    # Resumo final
    print(f"\n{'='*70}")
    print("RESUMO FINAL")
    print(f"{'='*70}")

    speedups = []
    for scenario_name, results in all_results.items():
        if "cbc" in results and "cpsat" in results:
            if results["cbc"]["status"] == "OK" and results["cpsat"]["status"] == "OK":
                speedup = (results["cbc"]["time_s"] - results["cpsat"]["time_s"]) / results["cbc"]["time_s"] * 100
                speedups.append(speedup)

    if speedups:
        avg_speedup = sum(speedups) / len(speedups)
        max_speedup = max(speedups)
        min_speedup = min(speedups)
        print(f"\nSpeedup CP-SAT vs CBC:")
        print(f"  Média:      {avg_speedup:6.1f}%")
        print(f"  Máximo:     {max_speedup:6.1f}%")
        print(f"  Mínimo:     {min_speedup:6.1f}%")
        print(f"\nResultado: {'✓ CP-SAT merece investimento' if avg_speedup > 20 else '✗ Ganho insuficiente'}")
    else:
        print("\n✗ Nenhum cenário completou com sucesso")

if __name__ == "__main__":
    main()
