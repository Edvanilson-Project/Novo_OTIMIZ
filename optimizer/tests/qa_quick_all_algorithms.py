from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, List

ALGORITHMS = [
    "greedy",
    "genetic",
    "simulated_annealing",
    "tabu_search",
    "set_partitioning",
    "mcnf",
    "joint_solver",
    "hybrid_pipeline",
    "vcsp_pulp",
    "assignment_vsp",
]

BASE_URLS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"]
INTERNAL_KEY = os.environ.get("INTERNAL_OPTIMIZER_KEY", "internal-key-123456")

TIMEOUT_BY_ALGO = {
    "greedy": 20,
    "genetic": 30,
    "simulated_annealing": 40,
    "tabu_search": 40,
    "set_partitioning": 35,
    "mcnf": 25,
    "joint_solver": 45,
    "hybrid_pipeline": 45,
    "vcsp_pulp": 45,
    "assignment_vsp": 20,
}

TIME_BUDGET_BY_ALGO = {
    "greedy": 8,
    "genetic": 10,
    "simulated_annealing": 12,
    "tabu_search": 12,
    "set_partitioning": 12,
    "mcnf": 10,
    "joint_solver": 14,
    "hybrid_pipeline": 16,
    "vcsp_pulp": 14,
    "assignment_vsp": 8,
}

MIN_LAYOVER = 8


def _http_json(url: str, payload: Dict | None = None, timeout: float = 10.0) -> tuple[int, Dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if "/optimize/" in url:
        headers["X-Internal-Key"] = INTERNAL_KEY

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") or "{}"
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"detail": body}
        return exc.code, parsed


def choose_base_url() -> str:
    for base_url in BASE_URLS:
        try:
            status, _ = _http_json(f"{base_url}/health/", timeout=2)
            if status == 200:
                return base_url
        except Exception:
            pass
    raise RuntimeError("Optimizer API offline em 8000/8001")


def build_deadhead_times(destination: int) -> Dict[str, int]:
    return {
        "1": MIN_LAYOVER if destination == 1 else 12,
        "2": MIN_LAYOVER if destination == 2 else 12,
    }


def trip(
    trip_id: int,
    line_id: int,
    start_time: int,
    duration: int,
    origin: int,
    destination: int,
    group_id: int | None = None,
) -> Dict:
    return {
        "id": trip_id,
        "line_id": line_id,
        "trip_group_id": group_id,
        "start_time": start_time,
        "end_time": start_time + duration,
        "origin_id": origin,
        "destination_id": destination,
        "duration": duration,
        "distance_km": round(duration * 0.42, 2),
        "deadhead_times": build_deadhead_times(destination),
    }


def build_dataset() -> List[Dict]:
    trips: List[Dict] = []
    trip_id = 1
    pair_id = 1

    lines = [815, 819, 826]
    base_starts = [300, 480, 660, 840]
    line_offsets = {815: 0, 819: 18, 826: 36}
    line_duration_bias = {815: 0, 819: 4, 826: 8}

    for line in lines:
        for wave_index, base_start in enumerate(base_starts):
            start = base_start + line_offsets[line]
            duration_outbound = 42 + line_duration_bias[line] + wave_index
            duration_return = 40 + line_duration_bias[line] + (wave_index % 2)

            trips.append(trip(trip_id, line, start, duration_outbound, 1, 2, pair_id))
            trip_id += 1

            return_start = start + duration_outbound
            trips.append(trip(trip_id, line, return_start, duration_return, 2, 1, pair_id))
            trip_id += 1

            pair_id += 1

    trips.sort(key=lambda item: (item["start_time"], item["line_id"], item["id"]))
    return trips


def run_once(base_url: str, algorithm: str, trips: List[Dict]) -> Dict:
    time_budget_s = TIME_BUDGET_BY_ALGO.get(algorithm, 12)
    payload = {
        "algorithm": algorithm,
        "time_budget_s": time_budget_s,
        "trips": trips,
        "vehicle_types": [
            {
                "id": 1,
                "name": "Padrao",
                "passenger_capacity": 40,
                "cost_per_km": 1.0,
                "cost_per_hour": 10.0,
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
        },
        "vsp_params": {
            "time_budget_s": time_budget_s,
            "min_layover_minutes": MIN_LAYOVER,
            "preserve_preferred_pairs": True,
            "preferred_pair_window_minutes": 20,
            "allow_multi_line_block": True,
            "strict_hard_validation": True,
            "max_generated_columns": 180,
            "max_pricing_iterations": 1,
            "max_pricing_additions": 32,
        },
        "wait_for_completion": True,
    }

    start = time.time()
    status_code, data = _http_json(
        f"{base_url}/optimize/",
        payload=payload,
        timeout=TIMEOUT_BY_ALGO.get(algorithm, 40),
    )
    elapsed = time.time() - start

    if status_code != 200:
        return {
            "ok": False,
            "algorithm": algorithm,
            "status": status_code,
            "elapsed": round(elapsed, 2),
            "error": str(data)[:180],
        }

    return {
        "ok": data.get("unassigned_trips", 0) == 0 and data.get("cct_violations", 0) == 0,
        "algorithm": algorithm,
        "status": status_code,
        "elapsed": round(elapsed, 2),
        "vehicles": data.get("vehicles", 0),
        "crew": data.get("crew", 0),
        "unassigned": data.get("unassigned_trips", -1),
        "cct_violations": data.get("cct_violations", -1),
        "warnings": len(data.get("warnings", [])),
    }


def main() -> int:
    base_url = choose_base_url()
    trips = build_dataset()
    print(f"API: {base_url}")
    print(f"Dataset: {len(trips)} viagens multi-linhas")

    failures: List[Dict] = []
    for algorithm in ALGORITHMS:
        try:
            result = run_once(base_url, algorithm, trips)
        except Exception as exc:
            result = {
                "ok": False,
                "algorithm": algorithm,
                "status": "EXC",
                "elapsed": -1,
                "error": repr(exc)[:180],
            }

        if result.get("ok"):
            print(
                f"[OK] {algorithm:<20} "
                f"{result['elapsed']:>5}s  "
                f"veh={result.get('vehicles', 0):>3} "
                f"crew={result.get('crew', 0):>3} "
                f"warn={result.get('warnings', 0):>2}"
            )
        else:
            failures.append(result)
            print(f"[FAIL] {algorithm:<20} {result}")

    print("\nResumo:")
    print(f"- total algoritmos: {len(ALGORITHMS)}")
    print(f"- falhas: {len(failures)}")

    if failures:
        print("\nFalhas detectadas:")
        for item in failures:
            print(item)
        return 1

    print("Todos os algoritmos passaram no smoke test rápido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
