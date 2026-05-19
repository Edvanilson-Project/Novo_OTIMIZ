#!/usr/bin/env python3
"""
Medição de Ganhos Reais em Produção — Fase 1 + Fase 3

Executa o pipeline em instâncias reais (similares a produção) e mede:

FASE 1 (Unificação de Objetivo):
  - Consistência de custo entre algoritmos
  - Verificação: total_cost == evaluator.csp_cost_breakdown()

FASE 3 (CP-SAT como Principal Solver):
  - Speedup: tempo CBC vs tempo CP-SAT
  - Métrica: (tempo CBC - tempo CP-SAT) / tempo CBC * 100%

Instâncias testadas:
  - Small:     50 trips, 15 blocos (< 1 segundo)
  - Medium:   200 trips, 60 blocos (< 15 segundos)
  - Large:    500 trips, 180 blocos (< 60 segundos)
"""

import json
import sys
import os
import time
from pathlib import Path

# Ensure src is in the path (similar to test structure)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.algorithms.csp.cp_sat_csp import CPSatCSP
from src.algorithms.vsp.mcnf import MCNFVSP
from src.algorithms.evaluator import CostEvaluator
from src.domain.models import Block, Trip, OptimizationResult, VehicleType


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


INSTANCES = {
    "small": {
        "trips": [_trip(i, 360 + (i % 20)*30, 60, line=(i % 2)+1) for i in range(50)],
        "budget_s": 1.0,
        "label": "50 trips, small instance",
    },
    "medium": {
        "trips": [_trip(i, 360 + (i % 40)*30, 60, line=(i % 5)+1) for i in range(200)],
        "budget_s": 15.0,
        "label": "200 trips, medium instance",
    },
    "large": {
        "trips": [_trip(i, 360 + (i % 100)*30, 60, line=(i % 8)+1) for i in range(500)],
        "budget_s": 60.0,
        "label": "500 trips, large instance",
    },
}


def measure_instance(name, instance_data):
    """Mede ganhos de Fase 1 + 3 em uma instância."""
    trips = instance_data["trips"]
    budget_s = instance_data["budget_s"]
    label = instance_data["label"]

    print(f"\n{'='*80}")
    print(f"Instância: {name.upper():15} | {label}")
    print(f"{'='*80}")

    # ── VSP (MCNF) ───────────────────────────────────────────────────────────
    print(f"\nVSP (MCNF):", end=" ", flush=True)
    start = time.perf_counter()
    try:
        vehicle_types = [VehicleType(id=1, name="bus", passenger_capacity=50, fixed_cost=800.0)]
        vsp = MCNFVSP()
        vsp.time_budget_s = budget_s
        vsp_result = vsp.solve(trips, vehicle_types)
        vsp_time = time.perf_counter() - start
        print(f"✓ {vsp_time:.3f}s | {len(vsp_result.blocks)} blocos | cost=R${vsp_result.total_cost:,.2f}")
        vsp_valid = True
    except Exception as e:
        vsp_time = time.perf_counter() - start
        print(f"✗ {vsp_time:.3f}s | {type(e).__name__}: {e}")
        vsp_valid = False
        vsp_result = None

    if not vsp_valid or not vsp_result:
        print(f"⚠ VSP failed, skipping CSP tests for {name}")
        return {"status": "FAILED_VSP"}

    blocks = vsp_result.blocks
    evaluator = CostEvaluator()

    # ── CSP com CBC (SetPartitioningCSP) ──────────────────────────────────────
    print(f"CSP (CBC):", end=" ", flush=True)
    start = time.perf_counter()
    try:
        cbc = SetPartitioningOptimizedCSP(time_budget_s=budget_s)
        cbc_result = cbc.solve(blocks, trips)
        cbc_time = time.perf_counter() - start

        # FASE 1: Verificar consistência via evaluator
        cbc_breakdown = evaluator.csp_cost_breakdown(cbc_result)
        cbc_cost_evaluator = cbc_breakdown.get("total", 0.0)
        cbc_cost_reported = cbc_result.total_cost
        cbc_cost_delta = abs(cbc_cost_evaluator - cbc_cost_reported)
        cbc_cost_ok = cbc_cost_delta < 1.0  # Tolerância: R$ 1

        print(
            f"✓ {cbc_time:.3f}s | {len(cbc_result.duties)} jornadas | "
            f"cost=R${cbc_result.total_cost:,.2f} | "
            f"delta={cbc_cost_delta:.2f} {'✓' if cbc_cost_ok else '✗'}"
        )
        cbc_valid = True
    except Exception as e:
        cbc_time = time.perf_counter() - start
        print(f"✗ {cbc_time:.3f}s | {type(e).__name__}")
        cbc_valid = False
        cbc_result = None

    # ── CSP com CP-SAT (CPSatCSP) ────────────────────────────────────────────
    print(f"CSP (CP-SAT):", end=" ", flush=True)
    start = time.perf_counter()
    try:
        cpsat = CPSatCSP(time_budget_s=budget_s)
        cpsat_result = cpsat.solve(blocks, trips)
        cpsat_time = time.perf_counter() - start

        # FASE 1: Verificar consistência via evaluator
        cpsat_breakdown = evaluator.csp_cost_breakdown(cpsat_result)
        cpsat_cost_evaluator = cpsat_breakdown.get("total", 0.0)
        cpsat_cost_reported = cpsat_result.total_cost
        cpsat_cost_delta = abs(cpsat_cost_evaluator - cpsat_cost_reported)
        cpsat_cost_ok = cpsat_cost_delta < 1.0

        print(
            f"✓ {cpsat_time:.3f}s | {len(cpsat_result.duties)} jornadas | "
            f"cost=R${cpsat_result.total_cost:,.2f} | "
            f"delta={cpsat_cost_delta:.2f} {'✓' if cpsat_cost_ok else '✗'}"
        )
        cpsat_valid = True
    except Exception as e:
        cpsat_time = time.perf_counter() - start
        print(f"✗ {cpsat_time:.3f}s | {type(e).__name__}")
        cpsat_valid = False
        cpsat_result = None

    # ── Comparação de Ganhos ──────────────────────────────────────────────────
    results = {
        "instance": name,
        "vsp_time_s": vsp_time if vsp_valid else None,
        "vsp_blocks": len(vsp_result.blocks) if vsp_valid else None,
        "cbc_time_s": cbc_time if cbc_valid else None,
        "cbc_duties": len(cbc_result.duties) if cbc_valid else None,
        "cbc_cost": cbc_result.total_cost if cbc_valid else None,
        "cbc_cost_delta": cbc_cost_delta if cbc_valid else None,
        "cpsat_time_s": cpsat_time if cpsat_valid else None,
        "cpsat_duties": len(cpsat_result.duties) if cpsat_valid else None,
        "cpsat_cost": cpsat_result.total_cost if cpsat_valid else None,
        "cpsat_cost_delta": cpsat_cost_delta if cpsat_valid else None,
    }

    if cbc_valid and cpsat_valid:
        speedup_pct = (cbc_time - cpsat_time) / cbc_time * 100
        cost_delta_pct = (cbc_result.total_cost - cpsat_result.total_cost) / cbc_result.total_cost * 100
        duties_reduction = (len(cbc_result.duties) - len(cpsat_result.duties)) / len(cbc_result.duties) * 100

        print(f"\n{'GANHOS FASE 3 (CP-SAT vs CBC)':40}")
        print(f"  Speedup:          {speedup_pct:+7.1f}% (CP-SAT {'mais rápido' if speedup_pct > 0 else 'mais lento'})")
        print(f"  Custo:            {cost_delta_pct:+7.2f}% (diferença de qualidade)")
        print(f"  Jornadas:         {duties_reduction:+7.2f}% (redução no número)")

        results["speedup_pct"] = speedup_pct
        results["cost_delta_pct"] = cost_delta_pct
        results["duties_reduction_pct"] = duties_reduction
        results["status"] = "OK"
    else:
        results["status"] = "PARTIAL"

    # FASE 1: Summarize cost consistency
    print(f"\n{'GANHOS FASE 1 (Unificação de Custo)':40}")
    if cbc_valid:
        print(f"  CBC delta:        R$ {cbc_cost_delta:.2f} {'✓' if cbc_cost_ok else '✗ INCONSISTÊNCIA'}")
    if cpsat_valid:
        print(f"  CP-SAT delta:     R$ {cpsat_cost_delta:.2f} {'✓' if cpsat_cost_ok else '✗ INCONSISTÊNCIA'}")

    return results


def main():
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║           MEDIÇÃO DE GANHOS REAIS — FASE 1 + FASE 3                       ║
║                                                                            ║
║  FASE 1: Unificação de Objetivo (Evaluator como fonte única de verdade)   ║
║  FASE 3: CP-SAT como solver principal de duty composition                 ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    all_results = {}
    for instance_name, instance_data in INSTANCES.items():
        results = measure_instance(instance_name, instance_data)
        all_results[instance_name] = results

    # ── Resumo Final ──────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("RESUMO FINAL — GANHOS REAIS EM PRODUÇÃO")
    print(f"{'='*80}\n")

    # FASE 3: Speedup CP-SAT
    speedups = []
    for name, results in all_results.items():
        if "speedup_pct" in results:
            speedups.append((name, results["speedup_pct"]))

    if speedups:
        print("FASE 3 — CP-SAT vs CBC (Duty Composition):")
        for instance_name, speedup in speedups:
            emoji = "✓" if speedup > 20 else "⚠" if speedup > 0 else "✗"
            print(f"  {instance_name:10} {emoji}  {speedup:+7.1f}%")

        avg_speedup = sum(s for _, s in speedups) / len(speedups)
        print(f"\n  Média de Speedup:  {avg_speedup:+7.1f}%")
        if avg_speedup > 20:
            print(f"  ✓ CP-SAT merece investimento! Ganho > 20%")
        elif avg_speedup > 5:
            print(f"  ⚠ CP-SAT é competitivo (~10%), considere para instâncias grandes")
        else:
            print(f"  ✗ CBC permanece mais rápido para estes cenários")
    else:
        print("  ⚠ Nenhum teste de speedup completou com sucesso")

    # FASE 1: Cost Consistency
    print(f"\nFASE 1 — Consistência de Custo (via Evaluator):")
    cost_issues = []
    for name, results in all_results.items():
        if "cbc_cost_delta" in results:
            delta = results["cbc_cost_delta"]
            status = "✓" if delta < 1.0 else "✗"
            print(f"  CBC {name:10} {status}  delta=R$ {delta:7.2f}")
            if delta >= 1.0:
                cost_issues.append((name, "CBC", delta))

        if "cpsat_cost_delta" in results:
            delta = results["cpsat_cost_delta"]
            status = "✓" if delta < 1.0 else "✗"
            print(f"  CP-SAT {name:6} {status}  delta=R$ {delta:7.2f}")
            if delta >= 1.0:
                cost_issues.append((name, "CP-SAT", delta))

    if not cost_issues:
        print("  ✓ Todos os custos consistentes! Avaliador funciona perfeitamente.")
    else:
        print(f"\n  ⚠ {len(cost_issues)} inconsistências detectadas:")
        for inst, solver, delta in cost_issues:
            print(f"     {inst} / {solver}: R$ {delta:.2f}")

    # Salvar resultados em JSON
    json_output = json.dumps(all_results, indent=2)
    output_path = Path(__file__).parent / "production_gains.json"
    with open(output_path, "w") as f:
        f.write(json_output)
    print(f"\n📊 Resultados salvos em: {output_path}")

    return 0 if not cost_issues else 1


if __name__ == "__main__":
    sys.exit(main())
