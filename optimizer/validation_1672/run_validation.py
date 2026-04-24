"""
Validação empírica dos algoritmos de otimização usando a programação real
da linha 1672 (Alto de Coutos) — 92 viagens, 2 terminais, janela 04:40-23:51.

Executa cada algoritmo individualmente e compara KPIs (nº veículos, crew, CCT,
unassigned, custo, tempo) contra um baseline.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE_URL = os.environ.get("OPTIMIZER_BASE_URL", "http://127.0.0.1:8000")
INTERNAL_KEY = os.environ.get("INTERNAL_OPTIMIZER_KEY", "internal-key-123456")
HEADERS = {"X-Internal-Key": INTERNAL_KEY}
CSV_PATH = Path(__file__).parent / "trips_1672.csv"
REPORT_PATH = Path(__file__).parent / "validation_report.json"
SUMMARY_PATH = Path(__file__).parent / "validation_summary.md"

ALGORITHMS = [
    "greedy",
    "mcnf",
    "genetic",
    "simulated_annealing",
    "tabu_search",
    "set_partitioning",
    "joint_solver",
    "hybrid_pipeline",
    "vcsp_pulp",
]

# Generous budgets — we want true optimization, not a smoke test.
TIMEOUT_BY_ALGO = {
    "greedy": 30,
    "mcnf": 30,
    "genetic": 60,
    "simulated_annealing": 60,
    "tabu_search": 60,
    "set_partitioning": 60,
    "joint_solver": 90,
    "hybrid_pipeline": 90,
    "vcsp_pulp": 120,
}
TIME_BUDGET_BY_ALGO = {k: max(5, v - 10) for k, v in TIMEOUT_BY_ALGO.items()}

MIN_LAYOVER = 8


def _export_csv_if_missing() -> None:
    if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
        return
    cmd = [
        "docker", "exec", "otimiz-v2-postgres",
        "psql", "-U", "otimiz_admin", "-d", "otimiz_db",
        "-c",
        "\\COPY (SELECT id, \"tripId\", \"lineCode\", direction, \"startTime\", "
        "\"endTime\", \"originId\", \"destinationId\", \"distanceKm\", duration "
        "FROM trips WHERE \"lineCode\"='1672' ORDER BY \"startTime\") "
        "TO STDOUT WITH CSV HEADER",
    ]
    out = subprocess.check_output(cmd)
    CSV_PATH.write_bytes(out)


def load_trips_1672() -> List[Dict[str, Any]]:
    _export_csv_if_missing()
    trips: List[Dict[str, Any]] = []
    with CSV_PATH.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            start = int(row["startTime"])
            end = int(row["endTime"])
            # Normaliza travessia de meia-noite: se endTime < startTime, soma 1440
            if end < start:
                end += 1440
            origin = int(row["originId"])
            destination = int(row["destinationId"])
            duration = int(row["duration"]) or (end - start)
            trips.append({
                "id": int(row["id"]),
                "line_id": 2,  # lines.id for lineId='1672'
                "trip_group_id": None,
                "start_time": start,
                "end_time": end,
                "origin_id": origin,
                "destination_id": destination,
                "duration": duration,
                "distance_km": float(row["distanceKm"]),
                "direction": "outbound" if row["direction"] == "IDA" else "return",
                "deadhead_times": {
                    "1": MIN_LAYOVER if destination == 1 else 12,
                    "2": MIN_LAYOVER if destination == 2 else 12,
                },
            })
    trips.sort(key=lambda t: (t["start_time"], t["id"]))
    return trips


def build_payload(algorithm: str, trips: List[Dict[str, Any]]) -> Dict[str, Any]:
    tb = TIME_BUDGET_BY_ALGO[algorithm]
    return {
        "algorithm": algorithm,
        "time_budget_s": tb,
        "wait_for_completion": True,
        "trips": trips,
        "vehicle_types": [
            {
                "id": 1,
                "name": "Padrao",
                "passenger_capacity": 40,
                "cost_per_km": 2.5,
                "cost_per_hour": 60.0,
                "fixed_cost": 800.0,
            }
        ],
        "cct_params": {
            "apply_cct": True,
            "max_shift_minutes": 600,
            "max_work_minutes": 520,
            "max_driving_minutes": 240,
            "min_break_minutes": 20,
            "min_layover_minutes": MIN_LAYOVER,
            "enforce_single_line_duty": False,
            "strict_hard_validation": True,
            "terminal_location_ids": [1, 2],
        },
        "vsp_params": {
            "time_budget_s": tb,
            "min_layover_minutes": MIN_LAYOVER,
            "preserve_preferred_pairs": True,
            "preferred_pair_window_minutes": 20,
            "allow_multi_line_block": True,
            "strict_hard_validation": True,
            "max_generated_columns": 300,
            "max_pricing_iterations": 2,
            "max_pricing_additions": 48,
        },
    }


def run_single(algorithm: str, trips: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = build_payload(algorithm, trips)
    t0 = time.time()
    try:
        resp = requests.post(
            f"{BASE_URL}/optimize/",
            json=payload,
            headers=HEADERS,
            timeout=TIMEOUT_BY_ALGO[algorithm],
        )
    except Exception as exc:
        return {
            "algorithm": algorithm, "ok": False, "status": "EXC",
            "elapsed_s": round(time.time() - t0, 2),
            "error": repr(exc)[:400],
        }
    elapsed = round(time.time() - t0, 2)

    if resp.status_code != 200:
        return {
            "algorithm": algorithm, "ok": False, "status": resp.status_code,
            "elapsed_s": elapsed, "error": resp.text[:600],
        }

    data = resp.json()
    vehicles = data.get("vehicles")
    crew = data.get("crew")
    unassigned = data.get("unassigned_trips")
    cct_violations = data.get("cct_violations")
    total_cost = data.get("total_cost")
    warnings = data.get("warnings") or []

    ok = (
        vehicles is not None
        and unassigned == 0
        and (cct_violations is None or cct_violations == 0)
    )
    return {
        "algorithm": algorithm, "ok": ok, "status": 200, "elapsed_s": elapsed,
        "vehicles": vehicles, "crew": crew,
        "unassigned_trips": unassigned,
        "cct_violations": cct_violations,
        "total_cost": total_cost,
        "num_warnings": len(warnings),
        "warnings_sample": warnings[:3],
        "has_blocks": bool(data.get("blocks")),
        "has_duties": bool(data.get("duties")),
        "n_blocks": len(data.get("blocks") or []),
        "n_duties": len(data.get("duties") or []),
        "phase_timings_ms": (data.get("meta") or {}).get("performance", {}).get("phase_timings_ms") or data.get("meta", {}).get("phase_timings_ms"),
    }


def main() -> int:
    trips = load_trips_1672()
    print(f"Linha 1672 — {len(trips)} viagens carregadas "
          f"(janela {trips[0]['start_time']}..{trips[-1]['end_time']} min)")

    results: List[Dict[str, Any]] = []
    for algo in ALGORITHMS:
        print(f"\n▶ {algo} (timeout={TIMEOUT_BY_ALGO[algo]}s, budget={TIME_BUDGET_BY_ALGO[algo]}s)")
        r = run_single(algo, trips)
        if r["ok"]:
            print(f"  [OK] veic={r['vehicles']} crew={r.get('crew')} "
                  f"cct={r.get('cct_violations')} "
                  f"cost={r.get('total_cost')} elapsed={r['elapsed_s']}s")
        else:
            print(f"  [FAIL] status={r.get('status')} err={str(r.get('error'))[:200]}")
        results.append(r)

    REPORT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Summary markdown
    header = "| Algoritmo | OK | Veic | Crew | CCT | Unassigned | Custo | Tempo(s) | Obs |\n"
    header += "|---|---|---|---|---|---|---|---|---|\n"
    rows = []
    for r in results:
        if r["ok"]:
            obs = ""
        else:
            obs = f"status={r.get('status')} err={str(r.get('error'))[:80]}"
        rows.append(
            f"| {r['algorithm']} | {'✓' if r['ok'] else '✗'} | "
            f"{r.get('vehicles','-')} | {r.get('crew','-')} | "
            f"{r.get('cct_violations','-')} | {r.get('unassigned_trips','-')} | "
            f"{r.get('total_cost','-')} | {r.get('elapsed_s','-')} | {obs} |"
        )
    SUMMARY_PATH.write_text(
        f"# Validação Linha 1672 — 92 viagens\n\nBaseURL: {BASE_URL}\n\n"
        + header + "\n".join(rows) + "\n"
    )

    passed = sum(1 for r in results if r["ok"])
    print(f"\n=== {passed}/{len(results)} algoritmos passaram ===")
    print(f"Relatório: {REPORT_PATH}")
    print(f"Resumo: {SUMMARY_PATH}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
