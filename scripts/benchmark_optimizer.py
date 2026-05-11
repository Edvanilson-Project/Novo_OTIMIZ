#!/usr/bin/env python3
"""
Benchmark do motor de otimização (FastAPI + Celery) sob carga sintética.

Dispara POST /optimize/ com datasets de N=100, 1000, 2000 trips e mede:
  - submit_latency_ms  — tempo até taskId retornar (deve ser <100ms)
  - solve_latency_ms   — tempo até polling retornar status=completed
  - status             — completed/failed/timeout
  - total_cost         — qualidade da solução
  - num_vehicles       — frota usada
  - cct_violations     — número de violações
  - fairness_gini      — equidade da distribuição de jornada (0 ideal, 1 ruim)
  - infeasibility      — viagens não cobertas

Uso:
    python scripts/benchmark_optimizer.py [--sizes 100,1000,2000] [--algo hybrid_pipeline,vcsp_pulp,mcnf]

Saída: tabela markdown + JSON em /tmp/benchmark_<timestamp>.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Iterable

OPTIMIZER_URL = os.environ.get("OPTIMIZER_URL", "http://localhost:8000")
INTERNAL_KEY = os.environ.get("INTERNAL_OPTIMIZER_KEY", "internal-key-123456")
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = 600  # 10min teto absoluto por instância


def _http_post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{OPTIMIZER_URL}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Internal-Key": INTERNAL_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _http_get(path: str) -> dict:
    req = urllib.request.Request(
        f"{OPTIMIZER_URL}{path}",
        headers={"X-Internal-Key": INTERNAL_KEY},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def make_synthetic_trips(n: int, seed: int = 42) -> list[dict]:
    """
    Gera N trips sintéticas em um dia (00:00–23:59 = 0..1439 min).
    Estratégia: linhas 1..3, deadhead 0, durações 30–80min, 4 terminais (1..4),
    distribuição uniforme nos horários. Garante origin != destination.
    """
    rng = random.Random(seed)
    terminals = [1, 2, 3, 4]
    trips: list[dict] = []
    for i in range(n):
        start = rng.randint(0, 1380)
        duration = rng.randint(30, 80)
        end = min(start + duration, 1439)
        origin = rng.choice(terminals)
        dest = rng.choice([t for t in terminals if t != origin])
        line = rng.choice([1, 2, 3])
        trips.append(
            {
                "id": i + 1,
                "line_id": line,
                "trip_group_id": None,
                "direction": "IDA" if i % 2 == 0 else "VOLTA",
                "origin_id": origin,
                "destination_id": dest,
                "start_time": start,
                "end_time": end,
                "duration": duration,
                "distance_km": float(duration) * 0.4,
                "origin_latitude": None,
                "origin_longitude": None,
                "destination_latitude": None,
                "destination_longitude": None,
            }
        )
    return trips


VEHICLE_TYPES = [
    {
        "id": 1,
        "name": "Micro-ônibus",
        "capacity": 20,
        "cost_per_day": 600.0,
        "fixed_cost": 800.0,
        "cost_per_km": 1.2,
        "accessibility": False,
    },
    {
        "id": 2,
        "name": "Convencional",
        "capacity": 40,
        "cost_per_day": 900.0,
        "fixed_cost": 1200.0,
        "cost_per_km": 1.5,
        "accessibility": True,
    },
]


def build_payload(trips: list[dict], algorithm: str, time_budget_s: float | None = 60) -> dict:
    return {
        "trips": trips,
        "vehicle_types": VEHICLE_TYPES,
        "cct_params": {
            "max_shift_minutes": 720,
            "max_work_minutes": 480,
            "max_driving_minutes": 270,
            "min_break_minutes": 30,
            "min_layover_minutes": 5,
            "meal_break_minutes": 30,
            "mandatory_break_after_minutes": 270,
            "connection_tolerance_minutes": 10,
            "enforce_min_interval": True,
            "strict_hard_validation": False,
            "strict_zero_gap_validation": False,
            "strict_operational_mode": False,
            "strict_hard_constraints": False,
            "strict_union_rules": False,
            "group_infeasibility_mode": "production",
        },
        "vsp_params": {},
        "optimization_params": {
            "cost_vehicle": 1000.0,
            "cost_km": 1.0,
            "cost_duty": 500.0,
            "driver_cost_per_minute": 0.0,
            "collector_cost_per_minute": 0.0,
            "cct_violation_penalty": 500.0,
            "ilp_timeout_seconds": 120,
            "time_budget_s": time_budget_s,
            "random_seed": 42,
            "force_round_trip": False,
            "allow_vehicle_swap": True,
        },
        "time_budget_s": time_budget_s,
        "algorithm": algorithm,
        "company_id": 16,
        "run_id": int(time.time() * 1000) % 10_000_000,
        "request_metadata": {
            "trip_group_inference_mode": "optimizer_only",
            "scenario_id": f"benchmark-{algorithm}-{len(trips)}",
            "run_id": int(time.time() * 1000) % 10_000_000,
            "company_id": 16,
        },
    }


def submit_and_poll(payload: dict) -> dict[str, Any]:
    t0 = time.monotonic()
    submit = _http_post("/optimize/", payload)
    submit_latency_ms = (time.monotonic() - t0) * 1000
    task_id = submit.get("task_id")
    if not task_id:
        return {"status": "failed", "error": "no task_id", "submit_latency_ms": submit_latency_ms}

    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            status = _http_get(f"/optimize/status/{task_id}")
        except urllib.error.URLError as err:
            time.sleep(POLL_INTERVAL_S)
            continue
        st = status.get("status")
        if st == "completed":
            elapsed_ms = (time.monotonic() - t0) * 1000
            result = status.get("result", {}) or {}
            fairness = (
                ((result.get("cost_breakdown") or {}).get("csp") or {}).get("fairness") or {}
            )
            return {
                "status": "completed",
                "submit_latency_ms": submit_latency_ms,
                "solve_latency_ms": elapsed_ms,
                "total_cost": result.get("total_cost"),
                "num_vehicles": result.get("vehicles"),
                "num_duties": result.get("crew") or (result.get("meta", {}) or {}).get("roster_count"),
                "total_trips": result.get("total_trips"),
                "unassigned_trips": result.get("unassigned_trips"),
                "cct_violations": result.get("cct_violations"),
                "hard_issue_count": ((result.get("solver_explanation") or {}).get("issues") or {}).get(
                    "hard_count", 0
                ),
                "fairness_gini": (fairness.get("work_time") or {}).get("gini"),
                "fairness_cv": (fairness.get("work_time") or {}).get("cv"),
                "algorithm_resolved": result.get("vsp_algorithm"),
            }
        if st == "failed":
            return {
                "status": "failed",
                "submit_latency_ms": submit_latency_ms,
                "solve_latency_ms": (time.monotonic() - t0) * 1000,
                "error": status.get("message") or status.get("error", {}).get("message"),
            }
        time.sleep(POLL_INTERVAL_S)
    return {
        "status": "timeout",
        "submit_latency_ms": submit_latency_ms,
        "solve_latency_ms": (time.monotonic() - t0) * 1000,
    }


def fmt_cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def main(sizes: list[int], algos: list[str]) -> None:
    results: list[dict[str, Any]] = []
    print(
        f"Benchmark — optimizer={OPTIMIZER_URL} sizes={sizes} algorithms={algos} "
        f"started={dt.datetime.now().isoformat(timespec='seconds')}"
    )
    for n in sizes:
        trips = make_synthetic_trips(n)
        for algo in algos:
            print(f"\n→ N={n}  algo={algo}  ...", flush=True)
            outcome = submit_and_poll(build_payload(trips, algo, time_budget_s=120))
            outcome["n_trips"] = n
            outcome["algorithm"] = algo
            results.append(outcome)
            print(
                f"   status={outcome.get('status')} "
                f"solve={fmt_cell(outcome.get('solve_latency_ms'))}ms "
                f"cost={fmt_cell(outcome.get('total_cost'))} "
                f"vehicles={fmt_cell(outcome.get('num_vehicles'))} "
                f"gini={fmt_cell(outcome.get('fairness_gini'))} "
                f"violations={fmt_cell(outcome.get('cct_violations'))}",
            )

    # Tabela markdown final
    print("\n## Resultados\n")
    headers = [
        "N",
        "Algo",
        "Status",
        "Solve ms",
        "Custo R$",
        "Veículos",
        "Duties",
        "Trips→",
        "Órfãs",
        "Violações CCT",
        "Hard issues",
        "Gini",
        "CV",
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for r in results:
        row = [
            r["n_trips"],
            r["algorithm"],
            r.get("status"),
            fmt_cell(r.get("solve_latency_ms")),
            fmt_cell(r.get("total_cost")),
            fmt_cell(r.get("num_vehicles")),
            fmt_cell(r.get("num_duties")),
            fmt_cell(r.get("total_trips")),
            fmt_cell(r.get("unassigned_trips")),
            fmt_cell(r.get("cct_violations")),
            fmt_cell(r.get("hard_issue_count")),
            fmt_cell(r.get("fairness_gini")),
            fmt_cell(r.get("fairness_cv")),
        ]
        print("| " + " | ".join(str(c) for c in row) + " |")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/tmp/benchmark_{ts}.json"
    with open(out_path, "w") as f:
        json.dump({"timestamp": ts, "results": results}, f, indent=2)
    print(f"\nJSON: {out_path}")


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--sizes",
        default="100,500,1000,2000",
        help="Lista CSV de tamanhos de trips a benchmarkar (ex: 100,500,1000,2000)",
    )
    p.add_argument(
        "--algo",
        default="hybrid_pipeline,vcsp_pulp,mcnf,sa",
        help="Lista CSV de algoritmos. Disponíveis: greedy, genetic, sa, ts, sp, mcnf, "
        "joint, hybrid_pipeline, vcsp_pulp, assignment_vsp",
    )
    return p.parse_args(list(argv))


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    algos = [a.strip() for a in args.algo.split(",") if a.strip()]
    main(sizes, algos)
