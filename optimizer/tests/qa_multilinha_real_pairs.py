"""
QA multi-linhas com cenário real para validar agrupamento IDA↔VOLTA.

Objetivos:
- Garantir que pares naturais (ida/volta da mesma linha e continuidade temporal) permaneçam agrupados.
- Exercitar algoritmos principais com regras CCT + preservação de pares.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

BASE_URLS = ["http://127.0.0.1:8000", "http://127.0.0.1:8001"]
ALGORITHMS = [
    "greedy",
    "set_partitioning",
    "hybrid_pipeline",
]


def hm_to_min(raw: str) -> int:
    h, m = raw.strip().split(":")
    return int(h) * 60 + int(m)


@dataclass
class SeedRow:
    line_code: str
    ida_start: str
    ida_end: str
    volta_start: str
    volta_end: str


RAW_ROWS = [
    SeedRow("815VC", "03:40", "04:45", "04:45", "06:30"),
    SeedRow("826URA", "03:45", "04:50", "", ""),
    SeedRow("815VF", "03:50", "05:00", "05:00", "06:35"),
    SeedRow("872TF", "04:00", "05:02", "05:02", "06:02"),
    SeedRow("815VF", "04:00", "05:20", "05:20", "07:00"),
    SeedRow("815VF", "04:15", "05:40", "05:40", "07:25"),
    SeedRow("819IVF", "04:15", "05:00", "05:00", "06:10"),
    SeedRow("869VF3", "04:20", "04:55", "", ""),
    SeedRow("819IVF", "04:30", "05:15", "05:15", "06:15"),
    SeedRow("815VF", "04:30", "06:00", "06:00", "07:45"),
    SeedRow("826UVF", "04:35", "06:05", "06:05", "07:25"),
    SeedRow("820VF", "04:38", "05:33", "05:33", "06:41"),
    SeedRow("872", "04:40", "05:38", "05:38", "06:48"),
    SeedRow("869VF3", "04:40", "05:30", "", ""),
    SeedRow("826URA", "04:40", "05:50", "", ""),
    SeedRow("819IVF", "04:45", "05:30", "05:30", "06:30"),
    SeedRow("815VF", "04:45", "06:20", "06:20", "08:05"),
    SeedRow("826UVF", "04:55", "06:25", "06:25", "07:45"),
    SeedRow("873A", "05:00", "05:58", "05:58", "06:50"),
    SeedRow("815VF", "05:00", "06:40", "06:40", "08:30"),
    SeedRow("819IVF", "05:00", "05:45", "05:45", "06:53"),
    SeedRow("869VF3", "05:00", "05:40", "", ""),
    SeedRow("869VFC", "05:10", "06:14", "", ""),
    SeedRow("869IVF", "05:12", "06:00", "06:00", "06:50"),
    SeedRow("819IVF", "05:12", "06:02", "06:02", "07:10"),
    SeedRow("826UVF", "05:15", "06:50", "06:50", "08:10"),
    SeedRow("815VF", "05:15", "07:05", "07:05", "08:55"),
    SeedRow("869I2", "05:16", "06:24", "", ""),
    SeedRow("869VF2", "05:20", "06:10", "", ""),
    SeedRow("819VFC", "05:23", "06:23", "06:23", "07:35"),
    SeedRow("869IVF", "05:24", "06:16", "06:16", "07:10"),
    SeedRow("819IVF", "05:24", "06:14", "06:14", "07:20"),
    SeedRow("872", "05:30", "06:47", "06:47", "08:05"),
    SeedRow("815VF", "05:30", "07:25", "07:25", "09:15"),
    SeedRow("820VF", "05:30", "06:30", "06:30", "07:35"),
    SeedRow("869VF2", "05:35", "06:30", "", ""),
    SeedRow("826B", "05:35", "06:15", "", ""),
    SeedRow("869IVF", "05:36", "06:32", "06:32", "07:24"),
    SeedRow("819IVF", "05:36", "06:30", "06:30", "07:40"),
    SeedRow("826UVF", "05:40", "07:15", "07:15", "08:35"),
    SeedRow("869I2", "05:45", "07:00", "", ""),
    SeedRow("819VFC", "05:47", "06:50", "06:50", "08:00"),
    SeedRow("869IVF", "05:48", "06:40", "06:40", "07:32"),
    SeedRow("819IVF", "05:48", "06:40", "06:40", "07:52"),
    SeedRow("869VF2", "05:50", "06:40", "", ""),
    SeedRow("815VF", "05:55", "07:50", "07:50", "09:40"),
    SeedRow("873A", "06:00", "07:19", "07:19", "08:27"),
    SeedRow("869IVF", "06:00", "06:50", "06:50", "07:45"),
    SeedRow("819IVF", "06:00", "07:00", "07:00", "08:12"),
    SeedRow("826B", "06:05", "06:40", "", ""),
    SeedRow("820VF", "06:06", "07:12", "07:12", "08:22"),
    SeedRow("869VF2", "06:08", "07:00", "", ""),
    SeedRow("819IVF", "06:12", "07:10", "07:10", "08:25"),
    SeedRow("869IVF", "06:12", "07:10", "07:10", "08:04"),
    SeedRow("826UVF", "06:15", "07:55", "07:55", "09:15"),
    SeedRow("819IVF", "06:24", "07:20", "07:20", "08:35"),
    SeedRow("869IVF", "06:24", "07:20", "07:20", "08:10"),
    SeedRow("869VF2", "06:24", "07:18", "", ""),
    SeedRow("815VF", "06:25", "08:15", "08:15", "10:05"),
    SeedRow("869I2", "06:25", "07:36", "", ""),
    SeedRow("872", "06:30", "07:50", "07:50", "09:00"),
    SeedRow("820VF", "06:30", "07:40", "07:40", "08:50"),
    SeedRow("869IVF", "06:36", "07:28", "07:28", "08:19"),
    SeedRow("819IVF", "06:36", "07:30", "07:30", "08:45"),
    SeedRow("869IVF", "06:48", "07:44", "07:44", "08:35"),
    SeedRow("819IVF", "06:48", "07:40", "07:40", "08:55"),
    SeedRow("869IVF", "07:00", "08:00", "08:00", "08:50"),
    SeedRow("819IVF", "07:00", "07:59", "07:59", "09:06"),
    SeedRow("815VF", "07:00", "08:50", "08:50", "10:37"),
    SeedRow("873A", "07:15", "08:25", "08:25", "09:20"),
    SeedRow("869IVF", "07:20", "08:20", "08:20", "09:17"),
    SeedRow("819IVF", "07:22", "08:19", "08:19", "09:27"),
    SeedRow("820", "07:30", "08:40", "08:40", "09:50"),
    SeedRow("872", "07:35", "08:53", "08:53", "10:09"),
    SeedRow("869IVF", "07:40", "08:40", "08:40", "09:30"),
    SeedRow("819IVF", "07:44", "08:39", "08:39", "09:44"),
    SeedRow("815", "07:50", "09:40", "09:40", "11:20"),
    SeedRow("819I2", "08:36", "09:31", "09:31", "10:32"),
    SeedRow("815", "08:45", "10:30", "10:30", "12:15"),
    SeedRow("820", "08:50", "10:00", "10:00", "11:10"),
    SeedRow("872", "09:35", "10:45", "10:45", "12:00"),
    SeedRow("819I2", "09:36", "10:31", "10:31", "11:31"),
    SeedRow("815", "09:40", "11:20", "11:20", "13:05"),
    SeedRow("820", "09:55", "11:05", "11:05", "12:15"),
    SeedRow("819I2", "10:06", "11:01", "11:01", "12:01"),
    SeedRow("815", "10:35", "12:15", "12:15", "14:00"),
    SeedRow("826A", "10:50", "12:20", "12:20", "13:45"),
    SeedRow("872", "11:00", "12:10", "12:10", "13:25"),
    SeedRow("819I2", "11:06", "12:01", "12:01", "13:02"),
    SeedRow("820", "11:20", "12:30", "12:30", "13:40"),
    SeedRow("815", "11:25", "13:05", "13:05", "14:47"),
    SeedRow("872", "12:10", "13:20", "13:20", "14:30"),
    SeedRow("815", "12:10", "13:50", "13:50", "15:30"),
    SeedRow("819I2", "12:18", "13:16", "13:16", "14:20"),
    SeedRow("820", "12:30", "13:38", "13:38", "14:48"),
    SeedRow("826A", "12:30", "14:00", "14:00", "15:25"),
    SeedRow("815", "13:00", "14:35", "14:35", "16:15"),
    SeedRow("819I2", "13:05", "13:55", "13:55", "15:00"),
    SeedRow("872", "13:15", "14:25", "14:25", "15:35"),
    SeedRow("819I2", "13:30", "14:22", "14:22", "15:28"),
    SeedRow("826A", "13:40", "15:15", "15:15", "16:40"),
    SeedRow("815", "13:50", "15:30", "15:30", "17:20"),
    SeedRow("820", "13:50", "15:00", "15:00", "16:10"),
    SeedRow("819I2", "14:00", "14:53", "14:53", "15:57"),
    SeedRow("826A", "14:20", "15:55", "15:55", "17:15"),
    SeedRow("872", "14:25", "15:40", "15:40", "16:50"),
    SeedRow("815", "14:30", "16:10", "16:10", "18:00"),
    SeedRow("819IF", "15:15", "16:05", "16:05", "17:15"),
    SeedRow("869IF", "15:15", "16:05", "16:05", "16:55"),
    SeedRow("815IF", "15:20", "17:10", "17:10", "19:01"),
    SeedRow("819IF", "15:30", "16:20", "16:20", "17:30"),
    SeedRow("820IF", "15:38", "16:48", "16:48", "17:58"),
    SeedRow("815IF", "15:40", "17:30", "17:30", "19:26"),
    SeedRow("819IF", "15:45", "16:35", "16:35", "17:50"),
    SeedRow("872", "16:00", "17:20", "17:20", "18:40"),
    SeedRow("819IF", "16:00", "16:50", "16:50", "18:00"),
    SeedRow("826A", "16:00", "17:44", "17:44", "19:10"),
    SeedRow("819IF", "16:12", "17:05", "17:05", "18:15"),
    SeedRow("826A", "16:17", "18:05", "18:05", "19:25"),
    SeedRow("820IF", "16:20", "17:30", "17:30", "18:40"),
    SeedRow("815IF", "16:20", "18:10", "18:10", "20:05"),
    SeedRow("819IF", "16:24", "17:20", "17:20", "18:30"),
    SeedRow("873A", "16:35", "17:55", "17:55", "19:05"),
    SeedRow("815IF", "16:40", "18:30", "18:30", "20:25"),
    SeedRow("820IF", "16:42", "17:52", "17:52", "19:01"),
    SeedRow("819IF", "16:48", "17:47", "17:47", "18:57"),
    SeedRow("826A", "16:50", "18:30", "18:30", "19:55"),
    SeedRow("815IF", "17:00", "18:50", "18:50", "20:38"),
    SeedRow("819IF", "17:00", "18:00", "18:00", "19:10"),
    SeedRow("872", "17:00", "18:20", "18:20", "19:40"),
    SeedRow("826A", "17:15", "18:55", "18:55", "20:20"),
    SeedRow("819IF", "17:16", "18:15", "18:15", "19:25"),
    SeedRow("815", "17:28", "19:15", "19:15", "20:43"),
    SeedRow("872", "17:30", "18:50", "18:50", "20:10"),
    SeedRow("819I2", "17:33", "18:30", "18:30", "19:40"),
    SeedRow("820", "17:42", "18:45", "18:45", "19:40"),
    SeedRow("826A", "17:45", "19:25", "19:25", "20:45"),
    SeedRow("819I2", "18:00", "19:00", "19:00", "20:10"),
    SeedRow("815", "18:00", "19:37", "19:37", "21:05"),
    SeedRow("872", "18:30", "19:35", "19:35", "20:45"),
    SeedRow("819I2", "18:30", "19:20", "19:20", "20:20"),
    SeedRow("815", "18:40", "20:00", "20:00", "21:10"),
    SeedRow("826A", "19:00", "20:30", "20:30", "21:50"),
    SeedRow("819I2", "19:00", "19:50", "19:50", "20:50"),
    SeedRow("873A", "19:20", "20:20", "20:20", "21:20"),
    SeedRow("815", "19:30", "20:50", "20:50", "22:00"),
    SeedRow("819I2", "19:40", "20:30", "20:30", "21:30"),
    SeedRow("872", "20:15", "21:15", "21:15", "22:20"),
    SeedRow("819I2", "20:30", "21:20", "21:20", "22:10"),
    SeedRow("869I", "21:30", "22:20", "22:20", "23:00"),
    SeedRow("819I2", "21:35", "22:15", "22:15", "23:00"),
    SeedRow("872", "21:35", "22:35", "22:35", "23:35"),
    SeedRow("869I", "22:25", "23:15", "23:15", "23:55"),
]


def choose_base_url() -> str:
    for url in BASE_URLS:
        try:
            resp = requests.get(f"{url}/health/", timeout=3)
            if resp.status_code == 200:
                return url
        except Exception:
            pass
    raise RuntimeError("Nenhuma API optimizer disponível em 8000/8001")


def build_dataset() -> Tuple[List[Dict], List[Tuple[int, int]]]:
    lines = sorted({row.line_code for row in RAW_ROWS})
    line_to_id = {code: idx + 1 for idx, code in enumerate(lines)}

    trips: List[Dict] = []
    expected_pairs: List[Tuple[int, int]] = []
    tid = 1
    gid = 1

    for row in RAW_ROWS:
        line_id = line_to_id[row.line_code]

        ida_start = hm_to_min(row.ida_start)
        ida_end = hm_to_min(row.ida_end)
        ida_trip_id = tid
        trips.append(
            {
                "id": ida_trip_id,
                "line_id": line_id,
                "trip_group_id": gid if row.volta_start and row.volta_end else None,
                "start_time": ida_start,
                "end_time": ida_end,
                "origin_id": line_id * 1000 + 1,
                "destination_id": line_id * 1000 + 2,
                "duration": ida_end - ida_start,
                "distance_km": max(8.0, (ida_end - ida_start) * 0.45),
                "deadhead_times": {
                    str(line_id * 1000 + 1): 0,
                    str(line_id * 1000 + 2): 0,
                },
            }
        )
        tid += 1

        if row.volta_start and row.volta_end:
            volta_start = hm_to_min(row.volta_start)
            volta_end = hm_to_min(row.volta_end)
            volta_trip_id = tid
            trips.append(
                {
                    "id": volta_trip_id,
                    "line_id": line_id,
                    "trip_group_id": gid,
                    "start_time": volta_start,
                    "end_time": volta_end,
                    "origin_id": line_id * 1000 + 2,
                    "destination_id": line_id * 1000 + 1,
                    "duration": volta_end - volta_start,
                    "distance_km": max(8.0, (volta_end - volta_start) * 0.45),
                    "deadhead_times": {
                        str(line_id * 1000 + 1): 0,
                        str(line_id * 1000 + 2): 0,
                    },
                }
            )
            expected_pairs.append((ida_trip_id, volta_trip_id))
            tid += 1
            gid += 1

    return trips, expected_pairs


def index_block_duty(data: Dict) -> Tuple[Dict[int, int], Dict[int, int]]:
    block_by_trip: Dict[int, int] = {}
    duty_by_trip: Dict[int, int] = {}

    for block in data.get("blocks", []):
        block_id = int(block.get("block_id"))
        for trip_id in block.get("trips", []):
            block_by_trip[int(trip_id)] = block_id

    for duty in data.get("duties", []):
        duty_id = int(duty.get("duty_id"))
        for trip_id in duty.get("trip_ids", []):
            duty_by_trip[int(trip_id)] = duty_id

    return block_by_trip, duty_by_trip


def run_algo(base_url: str, algo: str, trips: List[Dict], expected_pairs: List[Tuple[int, int]]) -> Dict:
    payload = {
        "algorithm": algo,
        "trips": trips,
        "vehicle_types": [],
        "cct_params": {
            "apply_cct": True,
            "max_shift_minutes": 560,
            "max_work_minutes": 520,
            "max_driving_minutes": 240,
            "min_break_minutes": 20,
            "min_layover_minutes": 0,
            "enforce_single_line_duty": True,
            "strict_hard_validation": True,
        },
        "vsp_params": {
            "min_layover_minutes": 0,
            "preserve_preferred_pairs": True,
            "preferred_pair_window_minutes": 45,
            "pair_break_penalty": 1800.0,
            "paired_trip_bonus": 120.0,
            "strict_hard_validation": True,
        },
    }

    t0 = time.time()
    resp = requests.post(f"{base_url}/optimize/", json=payload, timeout=240)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        return {
            "ok": False,
            "algo": algo,
            "error": f"HTTP {resp.status_code}: {str(resp.text)[:220]}",
            "elapsed": elapsed,
        }

    data = resp.json()
    block_by_trip, duty_by_trip = index_block_duty(data)

    same_block = 0
    same_duty = 0
    split = 0
    missing = 0
    for ida, volta in expected_pairs:
        b1 = block_by_trip.get(ida)
        b2 = block_by_trip.get(volta)
        d1 = duty_by_trip.get(ida)
        d2 = duty_by_trip.get(volta)
        if b1 is None or b2 is None or d1 is None or d2 is None:
            missing += 1
            continue
        if b1 == b2:
            same_block += 1
        elif d1 == d2:
            same_duty += 1
        else:
            split += 1

    return {
        "ok": data.get("unassigned_trips", 1) == 0 and data.get("cct_violations", 1) == 0 and split == 0,
        "algo": algo,
        "elapsed": elapsed,
        "vehicles": data.get("vehicles", 0),
        "crew": data.get("crew", 0),
        "unassigned": data.get("unassigned_trips", -1),
        "cct": data.get("cct_violations", -1),
        "pair_total": len(expected_pairs),
        "pair_same_block": same_block,
        "pair_same_duty": same_duty,
        "pair_split": split,
        "pair_missing": missing,
        "warnings": data.get("warnings", []),
    }


def main() -> int:
    base_url = choose_base_url()
    trips, expected_pairs = build_dataset()

    print(f"API: {base_url}")
    print(f"Dataset real: {len(trips)} viagens, {len(expected_pairs)} pares IDA↔VOLTA esperados")

    failures: List[Dict] = []
    for algo in ALGORITHMS:
        result = run_algo(base_url, algo, trips, expected_pairs)
        if not result.get("ok"):
            failures.append(result)
            print(f"[FAIL] {algo:<18} {result}")
            continue

        print(
            f"[OK]   {algo:<18} {result['elapsed']:.2f}s  "
            f"veh={result['vehicles']} crew={result['crew']}  "
            f"pairs: bloco={result['pair_same_block']} duty={result['pair_same_duty']} "
            f"split={result['pair_split']}"
        )

    if failures:
        print("\nFalhas detectadas:")
        for item in failures:
            print(item)
        return 1

    print("\nTodos os algoritmos passaram no cenário multi-linhas real com agrupamento íntegro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
