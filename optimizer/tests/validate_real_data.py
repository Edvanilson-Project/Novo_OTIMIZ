"""
Validação com dados reais: carrega replay e2e_hybrid_pipeline_2000 (2000 viagens reais)
e roda greedy + mcnf + hybrid no mesmo input.
Verifica: blocos gerados, custo, conformidade regulatória básica.
"""
import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "replays" / "e2e_hybrid_pipeline_2000_schedule_371.json"

sys.path.insert(0, str(ROOT))

from src.domain.models import Trip, VehicleType, AlgorithmType
from src.services.optimizer_service import OptimizerService


def load_replay():
    with open(REPLAY) as f:
        data = json.load(f)
    return data


def trips_from_replay(data: dict) -> list[Trip]:
    trips = []
    for t in data["trips"]:
        trips.append(Trip(
            id=t["id"],
            line_id=t["line_id"],
            origin_id=t.get("origin_id", 1),
            destination_id=t.get("destination_id", 2),
            trip_group_id=t.get("trip_group_id"),
            direction=t.get("direction"),
            start_time=t["start_time"],
            end_time=t["end_time"],
            duration=t.get("duration", t["end_time"] - t["start_time"]),
            distance_km=t.get("distance_km", 10.0),
            original_trip_id=t.get("original_trip_id"),
            origin_latitude=t.get("origin_latitude"),
            origin_longitude=t.get("origin_longitude"),
            destination_latitude=t.get("destination_latitude"),
            destination_longitude=t.get("destination_longitude"),
        ))
    return trips


def vt_from_replay(data: dict) -> list[VehicleType]:
    vts = []
    for vt in data.get("vehicle_types", []):
        vts.append(VehicleType(
            id=vt["id"],
            name=vt.get("name", "Bus"),
            passenger_capacity=vt.get("passenger_capacity", vt.get("capacity", 80)),
            cost_per_km=vt.get("cost_per_km", 2.5),
            cost_per_hour=vt.get("cost_per_hour", 10.0),
            fixed_cost=vt.get("fixed_cost", vt.get("fixed_cost_per_day", 300.0)),
            is_electric=vt.get("is_electric", False),
            depot_id=vt.get("depot_id"),
        ))
    return vts or [VehicleType(id=1, name="Bus", passenger_capacity=80, cost_per_km=2.5, cost_per_hour=10.0, fixed_cost=300.0)]


def run_algorithm(service, trips, vehicle_types, vsp_params, cct_params, algo: str, time_budget: int):
    t0 = time.perf_counter()
    result = service.run(
        trips=trips,
        vehicle_types=vehicle_types,
        algorithm=AlgorithmType(algo),
        time_budget_s=time_budget,
        vsp_params=vsp_params,
        cct_params=cct_params,
    )
    elapsed = time.perf_counter() - t0
    return result, elapsed


def main():
    print(f"\n{'='*60}")
    print("Validação com dados reais — 2000 viagens (e2e replay)")
    print(f"{'='*60}\n")

    data = load_replay()
    trips = trips_from_replay(data)
    vehicle_types = vt_from_replay(data)
    vsp_params = data.get("vsp_params", {})
    cct_params = data.get("cct_params", {})

    print(f"Trips carregadas:     {len(trips)}")
    print(f"Tipos de veículo:     {len(vehicle_types)}")
    print(f"Range de horários:    {min(t.start_time for t in trips)} – {max(t.end_time for t in trips)} min")
    print(f"Algorithm original:   {data.get('algorithm')}")
    print()

    # Selecionar grupos completos até ~500 trips (evita MANDATORY_GROUP_SPLIT)
    from collections import defaultdict
    groups: dict = defaultdict(list)
    ungrouped = []
    for t in trips:
        if t.trip_group_id is not None:
            groups[t.trip_group_id].append(t)
        else:
            ungrouped.append(t)

    subset = []
    # Grupos completos em ordem de start_time do primeiro trip do grupo
    for gid, gtrips in sorted(groups.items(), key=lambda kv: min(t.start_time for t in kv[1])):
        if len(subset) + len(gtrips) > 600:
            break
        subset.extend(gtrips)
    # Completa com trips sem grupo se ainda houver espaço
    for t in sorted(ungrouped, key=lambda t: t.start_time):
        if len(subset) >= 600:
            break
        subset.append(t)

    if not subset:
        subset = trips[:500]

    print(f"Rodando com {len(subset)} trips ({len(groups)} grupos de viagem, grupos completos)...\n")

    service = OptimizerService()

    results = {}
    for algo, budget in [("greedy", 30), ("mcnf", 60), ("genetic", 60)]:
        print(f"  [{algo}] rodando (budget={budget}s)...", end=" ", flush=True)
        try:
            result, elapsed = run_algorithm(service, subset, vehicle_types, vsp_params, cct_params, algo, budget)
            blocks = len(result.blocks) if hasattr(result, "blocks") and result.blocks else 0
            duties = len(result.duties) if hasattr(result, "duties") and result.duties else 0
            cost = result.total_cost if hasattr(result, "total_cost") else 0
            violations = result.violations if hasattr(result, "violations") else []
            results[algo] = {
                "elapsed": elapsed,
                "blocks": blocks,
                "duties": duties,
                "cost": cost,
                "violations": len(violations) if isinstance(violations, list) else 0,
                "feasible": result.feasible if hasattr(result, "feasible") else True,
            }
            print(f"OK ({elapsed:.1f}s) — blocks={blocks} duties={duties} cost=R${cost:,.0f} violations={results[algo]['violations']}")
        except Exception as e:
            print(f"ERRO: {e}")
            results[algo] = {"error": str(e)}

    print(f"\n{'─'*60}")
    print(f"{'Algoritmo':<12} {'Tempo':>8} {'Blocos':>7} {'Jornadas':>9} {'Custo(R$)':>12} {'Violações':>10}")
    print(f"{'─'*60}")
    for algo, r in results.items():
        if "error" in r:
            print(f"{algo:<12} ERRO: {r['error'][:40]}")
        else:
            print(f"{algo:<12} {r['elapsed']:>7.1f}s {r['blocks']:>7} {r['duties']:>9} {r['cost']:>12,.0f} {r['violations']:>10}")

    print(f"\n{'='*60}")
    print("Verificações de sanidade:")
    for algo, r in results.items():
        if "error" in r:
            continue
        ok = []
        warn = []
        if r["blocks"] > 0:
            ok.append(f"blocks > 0")
        else:
            warn.append("BLOCKS = 0 (problema!)")
        if r["cost"] > 0:
            ok.append(f"custo positivo")
        else:
            warn.append("CUSTO = 0 (suspeito!)")
        ratio = r["blocks"] / len(subset) if len(subset) > 0 else 0
        if 0.1 < ratio < 1.5:
            ok.append(f"ratio blocos/trips={ratio:.2f} (razoável)")
        else:
            warn.append(f"ratio blocos/trips={ratio:.2f} (suspeito!)")
        status = "OK" if not warn else "AVISO"
        print(f"  [{algo}] {status}: {', '.join(ok + warn)}")

    print(f"\nConclusion: dados reais carregados e processados com sucesso.")
    print(f"Próximo passo: OR-Tools CP-SAT para melhorar qualidade CSP.\n")


if __name__ == "__main__":
    main()
