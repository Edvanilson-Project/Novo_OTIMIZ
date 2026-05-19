#!/usr/bin/env python3
"""
Benchmark Realista: CP-SAT vs CBC em Duty Composition

Executa ambos os solvers em instâncias progressivamente maiores
e mede o speedup real de CP-SAT vs CBC.

Instâncias:
  - Pequena:   100 trips, 30 blocos
  - Média:     300 trips, 90 blocos
  - Grande:    800 trips, 250 blocos
  - Muito grande: 1500 trips, 450 blocos (onde CP-SAT deve ganhar)
"""

import sys
import os
import time
import json
from pathlib import Path

# Setup path como em test_algorithms.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.algorithms.csp.cp_sat_csp import CPSatCSP
from src.algorithms.vsp.mcnf import MCNFVSP
from src.algorithms.evaluator import CostEvaluator
from src.domain.models import Block, Trip, VehicleType


def _trip(id_val, start, duration, line=1, origin=1, dest=2, depot=1):
    """Cria uma viagem simples para teste."""
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
    """Cria um bloco com as viagens dadas."""
    return Block(id=id_val, trips=trips, vehicle_type_id=1, warnings=[], meta={})


SCENARIOS = {
    "small_100": {
        "trips": [_trip(i, 360 + (i % 40)*30, 60, line=(i % 3)+1) for i in range(100)],
        "budget_s": 5.0,
        "label": "100 trips → ~30 blocos (pequeno)",
    },
    "medium_300": {
        "trips": [_trip(i, 360 + (i % 80)*30, 60, line=(i % 5)+1) for i in range(300)],
        "budget_s": 30.0,
        "label": "300 trips → ~90 blocos (médio)",
    },
    "large_800": {
        "trips": [_trip(i, 360 + (i % 150)*30, 60, line=(i % 8)+1) for i in range(800)],
        "budget_s": 60.0,
        "label": "800 trips → ~250 blocos (grande)",
    },
    "xlarge_1500": {
        "trips": [_trip(i, 360 + (i % 300)*30, 60, line=(i % 10)+1) for i in range(1500)],
        "budget_s": 120.0,
        "label": "1500 trips → ~450 blocos (muito grande — CP-SAT deve ganhar aqui!)",
    },
}


def benchmark_scenario(name, scenario_data):
    """Executa CBC vs CP-SAT em um cenário e mede o speedup."""
    trips = scenario_data["trips"]
    budget_s = scenario_data["budget_s"]
    label = scenario_data["label"]

    print(f"\n{'='*90}")
    print(f"Cenário: {name.upper():20} | {label}")
    print(f"{'='*90}")
    print(f"Trips: {len(trips):4} | Budget: {budget_s:6.1f}s")

    # ── VSP primeiro (MCNF) ───────────────────────────────────────────────────
    print(f"\n[VSP] Executando MCNF...", end=" ", flush=True)
    start = time.perf_counter()
    try:
        vehicle_types = [VehicleType(id=1, name="bus", passenger_capacity=50, fixed_cost=800.0)]
        vsp = MCNFVSP()
        vsp.time_budget_s = budget_s
        vsp_result = vsp.solve(trips, vehicle_types)
        vsp_time = time.perf_counter() - start
        print(f"✓ {vsp_time:.3f}s | {len(vsp_result.blocks)} blocos")
        vsp_valid = True
        blocks = vsp_result.blocks
    except Exception as e:
        vsp_time = time.perf_counter() - start
        print(f"✗ {vsp_time:.3f}s | {type(e).__name__}: {str(e)[:50]}")
        vsp_valid = False
        return {"status": "FAILED_VSP", "vsp_time": vsp_time}

    if not vsp_valid:
        return {"status": "FAILED_VSP"}

    evaluator = CostEvaluator()
    results = {"vsp_time_s": vsp_time, "num_blocks": len(blocks)}

    # ── CBC (SetPartitioningOptimizedCSP) ──────────────────────────────────────
    print(f"[CSP] Executando CBC...", end=" ", flush=True)
    start = time.perf_counter()
    try:
        cbc = SetPartitioningOptimizedCSP()
        cbc.time_budget_s = budget_s
        cbc_result = cbc.solve(blocks, trips)
        cbc_time = time.perf_counter() - start

        # Validar custo via evaluator (Fase 1)
        cbc_breakdown = evaluator.csp_cost_breakdown(cbc_result)
        cbc_cost_evaluator = cbc_breakdown.get("total", 0.0)
        cbc_cost_delta = abs(cbc_result.total_cost - cbc_cost_evaluator)

        print(
            f"✓ {cbc_time:.3f}s | {len(cbc_result.duties):3} jorn | "
            f"R${cbc_result.total_cost:10,.2f} | Δ=R${cbc_cost_delta:6.2f}"
        )
        cbc_valid = True
    except Exception as e:
        cbc_time = time.perf_counter() - start
        print(f"✗ {cbc_time:.3f}s | {type(e).__name__}: {str(e)[:50]}")
        cbc_valid = False
        cbc_result = None

    results["cbc_time_s"] = cbc_time
    if cbc_valid:
        results["cbc_duties"] = len(cbc_result.duties)
        results["cbc_cost"] = cbc_result.total_cost

    # ── CP-SAT (CPSatCSP) ──────────────────────────────────────────────────────
    print(f"[CSP] Executando CP-SAT...", end=" ", flush=True)
    start = time.perf_counter()
    try:
        cpsat = CPSatCSP()
        cpsat.time_budget_s = budget_s
        cpsat_result = cpsat.solve(blocks, trips)
        cpsat_time = time.perf_counter() - start

        # Validar custo via evaluator (Fase 1)
        cpsat_breakdown = evaluator.csp_cost_breakdown(cpsat_result)
        cpsat_cost_evaluator = cpsat_breakdown.get("total", 0.0)
        cpsat_cost_delta = abs(cpsat_result.total_cost - cpsat_cost_evaluator)

        # Se custo é 0 ou muito baixo, usar evaluator (bug conhecido)
        if cpsat_result.total_cost < 100:
            cpsat_final_cost = cpsat_cost_evaluator
        else:
            cpsat_final_cost = cpsat_result.total_cost

        print(
            f"✓ {cpsat_time:.3f}s | {len(cpsat_result.duties):3} jorn | "
            f"R${cpsat_final_cost:10,.2f} | Δ=R${cpsat_cost_delta:6.2f}"
        )
        cpsat_valid = True
    except Exception as e:
        cpsat_time = time.perf_counter() - start
        print(f"✗ {cpsat_time:.3f}s | {type(e).__name__}: {str(e)[:50]}")
        cpsat_valid = False
        cpsat_result = None

    results["cpsat_time_s"] = cpsat_time
    if cpsat_valid:
        results["cpsat_duties"] = len(cpsat_result.duties)
        results["cpsat_cost"] = cpsat_final_cost if cpsat_result.total_cost < 100 else cpsat_result.total_cost

    # ── Comparação ──────────────────────────────────────────────────────────────
    if cbc_valid and cpsat_valid:
        speedup_pct = (cbc_time - cpsat_time) / cbc_time * 100
        cost_ratio = cpsat_final_cost / cbc_result.total_cost if cbc_result.total_cost > 0 else 1.0
        cost_delta_pct = (cost_ratio - 1.0) * 100

        # Symbolo para ganho
        if speedup_pct > 20:
            speedup_emoji = "🚀"
        elif speedup_pct > 0:
            speedup_emoji = "✓"
        else:
            speedup_emoji = "⚠️"

        print(f"\n{'SPEEDUP':40}")
        print(f"  CBC time:        {cbc_time:7.3f}s")
        print(f"  CP-SAT time:     {cpsat_time:7.3f}s")
        print(f"  Speedup:         {speedup_pct:+7.1f}%  {speedup_emoji}")
        print(f"  Qualidade:       {cost_delta_pct:+7.2f}% (custo CP-SAT vs CBC)")

        results["speedup_pct"] = speedup_pct
        results["cost_delta_pct"] = cost_delta_pct
        results["status"] = "OK"
    else:
        results["status"] = "PARTIAL"

    return results


def main():
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║           BENCHMARK REALISTA: CP-SAT vs CBC — Speedup Real                ║
║                                                                            ║
║  Mede o desempenho de CP-SAT vs CBC em instâncias progressivamente        ║
║  maiores para demonstrar o ganho de 68% esperado em produção             ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    all_results = {}
    for scenario_name, scenario_data in SCENARIOS.items():
        results = benchmark_scenario(scenario_name, scenario_data)
        all_results[scenario_name] = results

    # ── Resumo Final ──────────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print("RESUMO FINAL — COMPROVAÇÃO DO SPEEDUP CP-SAT")
    print(f"{'='*90}\n")

    speedups = []
    for scenario_name, results in all_results.items():
        if "speedup_pct" in results:
            speedups.append((scenario_name, results["speedup_pct"]))

    if speedups:
        print("Speedup por cenário:")
        print("  Cenário            | Speedup  | Verdict")
        print("  ──────────────────┼──────────┼─────────────────────────")
        for scenario_name, speedup in speedups:
            name_short = scenario_name.replace("_", " ")[:20].ljust(20)
            if speedup > 50:
                verdict = "🚀 CP-SAT MUITO mais rápido!"
            elif speedup > 20:
                verdict = "✓ CP-SAT significativamente mais rápido"
            elif speedup > 0:
                verdict = "✓ CP-SAT um pouco mais rápido"
            else:
                verdict = "⚠️ CBC mais rápido neste cenário"
            print(f"  {name_short} | {speedup:+7.1f}% | {verdict}")

        avg_speedup = sum(s for _, s in speedups) / len(speedups)
        max_speedup = max(s for _, s in speedups)
        min_speedup = min(s for _, s in speedups)

        print(f"\n  Média:            {avg_speedup:+7.1f}%")
        print(f"  Máximo:           {max_speedup:+7.1f}%")
        print(f"  Mínimo:           {min_speedup:+7.1f}%")

        print(f"\nConclusão:")
        if avg_speedup > 30:
            print(f"  ✅ CP-SAT merece investimento! Speedup real: {avg_speedup:.1f}%")
            print(f"     (Esperado 68%, obtido {avg_speedup:.1f}% em cenários de teste)")
        elif avg_speedup > 10:
            print(f"  ⚠️ CP-SAT é competitivo ({avg_speedup:.1f}%), use em instâncias grandes")
        else:
            print(f"  ❌ CBC é mais rápido ({-avg_speedup:.1f}%)")
    else:
        print("  ⚠️ Nenhum cenário completou com sucesso")

    # Salvar resultados em JSON
    json_output = json.dumps(all_results, indent=2)
    output_path = Path(__file__).parent / "benchmark_results.json"
    with open(output_path, "w") as f:
        f.write(json_output)
    print(f"\n📊 Resultados salvos em: {output_path}")

    return 0 if speedups else 1


if __name__ == "__main__":
    sys.exit(main())
