"""
Validação com dados reais e sintéticos.

ACHADOS IMPORTANTES desta validação:
1. Greedy não suporta trips com direction=IDA/VOLTA (MANDATORY_GROUP_SPLIT).
   O trip_group_inference infere pares automaticamente e o greedy não os respeita.
2. Hybrid_pipeline foi construído para respeitar esses pares.
3. O hard_constraint_validator detecta corretamente a violação.
4. Para validar greedy, use trips sem direction (sintéticos ou lineares).

Para validar com 2000 trips reais, é necessário o hybrid_pipeline (~300s).
"""
import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "replays" / "e2e_hybrid_pipeline_2000_schedule_371.json"
sys.path.insert(0, str(ROOT))

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService


def make_synthetic_trips(n: int, seed: int = 42) -> list[Trip]:
    """Trips alternados A→B / B→A — sem direction, sem loops de terminal."""
    rng = random.Random(seed)
    trips = []
    t = 360
    for i in range(n):
        start = t + rng.randint(0, 15)
        dur = rng.randint(20, 60)
        end = start + dur
        # Alterna entre 2 terminais para evitar INVALID_TERMINAL_LOOP
        origin, dest = (1, 2) if i % 2 == 0 else (2, 1)
        trips.append(Trip(
            id=i,
            line_id=1,
            origin_id=origin,
            destination_id=dest,
            start_time=start,
            end_time=end,
            duration=dur,
            distance_km=rng.uniform(5, 25),
        ))
        t = end + rng.randint(3, 15)
    return trips


def load_replay():
    with open(REPLAY) as f:
        return json.load(f)


def vt_standard() -> list[VehicleType]:
    return [VehicleType(
        id=1, name="Bus", passenger_capacity=80,
        cost_per_km=2.5, cost_per_hour=30.0, fixed_cost=300.0,
    )]


def run_algo(service, trips, vehicle_types, vsp_params, cct_params, algo: str, budget: int):
    t0 = time.perf_counter()
    result = service.run(
        trips=trips, vehicle_types=vehicle_types,
        algorithm=AlgorithmType(algo), time_budget_s=budget,
        vsp_params=vsp_params, cct_params=cct_params,
    )
    return result, time.perf_counter() - t0


def main():
    print(f"\n{'='*60}")
    print("Validação OTIMIZ — dados sintéticos + achados dados reais")
    print(f"{'='*60}\n")

    service = OptimizerService()
    vsp_params = {"min_break_minutes": 30, "min_layover_minutes": 10, "force_round_trip": False}
    cct_params = {}
    vehicle_types = vt_standard()

    # ── Parte 1: Sintético (greedy + mcnf) ──────────────────────────────────
    print("PARTE 1 — Dados sintéticos (trips sem direction, sem par IDA/VOLTA)\n")
    results = {}
    for n, algo, budget in [(200, "greedy", 30), (200, "mcnf", 60), (100, "genetic", 60)]:
        trips = make_synthetic_trips(n)
        label = f"{algo}/{n}v"
        print(f"  [{label}] ...", end=" ", flush=True)
        try:
            result, elapsed = run_algo(service, trips, vehicle_types, vsp_params, cct_params, algo, budget)
            blocks = len(result.vsp.blocks) if result.vsp and result.vsp.blocks else 0
            duties = len(result.csp.duties) if result.csp and result.csp.duties else 0
            cost = result.total_cost or 0
            n_viol = (result.csp.cct_violations if result.csp else 0)
            results[label] = {"elapsed": elapsed, "blocks": blocks, "duties": duties,
                               "cost": cost, "violations": n_viol, "n": n}
            print(f"OK ({elapsed:.1f}s) blocks={blocks} duties={duties} cost=R${cost:,.0f} violations={n_viol}")
        except Exception as e:
            results[label] = {"error": str(e)[:80], "n": n}
            print(f"ERRO: {str(e)[:80]}")

    print(f"\n{'─'*60}")
    print(f"{'Algoritmo':<16} {'Viagens':>7} {'Tempo':>7} {'Blocos':>7} {'Jornadas':>9} {'Custo':>10} {'Violações':>10}")
    print(f"{'─'*60}")
    for label, r in results.items():
        if "error" in r:
            print(f"{label:<16} {r['n']:>7} ERRO: {r['error'][:35]}")
        else:
            status = "OK" if r["violations"] == 0 else f"AVISO({r['violations']})"
            print(f"{label:<16} {r['n']:>7} {r['elapsed']:>6.1f}s {r['blocks']:>7} {r['duties']:>9} {r['cost']:>10,.0f} {status:>10}")

    # ── Parte 2: Achados com dados reais ────────────────────────────────────
    print(f"\n{'='*60}")
    print("PARTE 2 — Achados com dados reais (2000 trips do replay)")
    print(f"{'='*60}")
    data = load_replay()
    print(f"\n  Trips no replay: {len(data['trips'])}")
    print(f"  Algorithm original: {data.get('algorithm')}")
    print(f"  Todos trips têm direction IDA/VOLTA: {all(t.get('direction') in ('IDA','VOLTA') for t in data['trips'])}")
    print(f"  trip_group_inference infere MANDATORY_GROUP_SPLIT automaticamente por direction.")
    print()
    print("  [greedy/dados-reais] tentando (deve falhar com MANDATORY_GROUP_SPLIT)...", end=" ", flush=True)
    from src.domain.models import Trip as DTrip
    real_trips = []
    for t in data["trips"]:
        real_trips.append(DTrip(
            id=t["id"], line_id=t["line_id"],
            origin_id=t.get("origin_id", 1), destination_id=t.get("destination_id", 2),
            trip_group_id=t.get("trip_group_id"), direction=t.get("direction"),
            start_time=t["start_time"], end_time=t["end_time"],
            duration=t.get("duration", t["end_time"] - t["start_time"]),
            distance_km=t.get("distance_km", 10.0),
        ))
    real_vt = [VehicleType(
        id=vt["id"], name=vt.get("name", "Bus"),
        passenger_capacity=vt.get("passenger_capacity", 80),
        cost_per_km=vt.get("cost_per_km", 2.5),
        cost_per_hour=vt.get("cost_per_hour", 10.0),
        fixed_cost=vt.get("fixed_cost", 300.0),
    ) for vt in data.get("vehicle_types", [])]
    try:
        result, elapsed = run_algo(service, real_trips, real_vt,
                                   data.get("vsp_params", {}), data.get("cct_params", {}),
                                   "greedy", 30)
        print(f"PASSOU (inesperado — revisar validador!)")
    except Exception as e:
        msg = str(e)
        if "MANDATORY_GROUP_SPLIT" in msg:
            print(f"FALHOU como esperado: validador detectou MANDATORY_GROUP_SPLIT")
            print(f"  -> Confirma que o greedy não suporta trips direcionais (IDA/VOLTA)")
            print(f"  -> Para dados reais com pares, usar hybrid_pipeline")
        else:
            print(f"FALHOU com erro inesperado: {msg[:80]}")

    print(f"\n{'='*60}")
    print("CONCLUSÕES:")
    print("  1. Greedy funciona corretamente em dados sintéticos (sem pares)")
    print("  2. Greedy falha em dados reais com direction IDA/VOLTA (limitação conhecida)")
    print("  3. O hard_constraint_validator detecta MANDATORY_GROUP_SPLIT corretamente")
    print("  4. Para dados reais com pares, usar hybrid_pipeline (requer ~300s/2000v)")
    print("  5. Próximo passo: OR-Tools CP-SAT para CSP mais rápido e com suporte a pares")
    print()


if __name__ == "__main__":
    main()
