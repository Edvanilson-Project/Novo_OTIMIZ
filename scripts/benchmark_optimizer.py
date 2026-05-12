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
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Iterable

try:
    import psutil  # noqa: F401
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

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


def make_synthetic_trips(n: int, seed: int = 42, difficulty: str = "easy") -> list[dict]:
    """
    Gera N trips sintéticas em um dia (00:00–23:59 = 0..1439 min).

    Difficulty profiles:
      - easy:    4 terminais, durações 30–80min, 3 linhas, distribuição uniforme.
                 Conexões fáceis, gaps grandes — VSP puro, sem violações CCT.
      - hard:    8 terminais, durações 60–150min, 5 linhas, picos manhã/tarde
                 (forçando rush). Gaps curtos → mais probabilidade de violar
                 condução contínua (>270min).
      - extreme: 12 terminais, durações 90–240min, 7 linhas, distribuição
                 concentrada em horário de pico (06–10 + 16–20). Stress real para
                 hybrid/joint resolverem com 0 violações.
    """
    rng = random.Random(seed)
    if difficulty == "easy":
        terminals = list(range(1, 5))  # 4
        lines = [1, 2, 3]
        dur_min, dur_max = 30, 80
        peak_concentration = 0.0
    elif difficulty == "hard":
        terminals = list(range(1, 9))  # 8
        lines = list(range(1, 6))  # 5
        dur_min, dur_max = 60, 150
        peak_concentration = 0.4  # 40% das trips em rush hours
    elif difficulty == "extreme":
        terminals = list(range(1, 13))  # 12
        lines = list(range(1, 8))  # 7
        dur_min, dur_max = 90, 240
        peak_concentration = 0.7
    elif difficulty == "violator":
        # Força violações CCT: cadeias longas de trips consecutivas (gap pequeno) na mesma linha,
        # somando >270min de condução contínua sem pausa válida. Stress real para penalty engine.
        return _make_violator_trips(n, seed)
    else:
        raise ValueError(f"difficulty inválida: {difficulty}")

    trips: list[dict] = []
    # Rush hours em minutos do dia
    morning = (6 * 60, 10 * 60)
    evening = (16 * 60, 20 * 60)
    for i in range(n):
        if rng.random() < peak_concentration:
            window = rng.choice([morning, evening])
            start = rng.randint(window[0], max(window[0], window[1] - dur_min))
        else:
            start = rng.randint(0, 1440 - dur_min)
        duration = rng.randint(dur_min, dur_max)
        end = min(start + duration, 1439)
        origin = rng.choice(terminals)
        dest = rng.choice([t for t in terminals if t != origin])
        line = rng.choice(lines)
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


def _make_violator_trips(n: int, seed: int = 42) -> list[dict]:
    """
    Profile que FORÇA violações CCT.
    Estratégia: gerar cadeias longas de trips consecutivas (gap=0 ou 5min) na mesma linha,
    cada uma de 45–75min. Uma cadeia de 6+ trips somando >270min força violação de
    condução contínua (max_driving_minutes default = 270). Sem pausa entre.
    """
    rng = random.Random(seed)
    trips: list[dict] = []
    terminals = [1, 2, 3, 4]
    chain_size = 7  # 7 × ~50min = ~350min > 270 → força violação de condução contínua
    chain_count = max(1, n // chain_size)
    leftover = n - chain_count * chain_size
    trip_id = 1
    cursor = 5 * 60  # começa às 5h
    for _ in range(chain_count):
        # Wrap se não cabe a cadeia inteira no dia
        chain_window = chain_size * 75 + (chain_size - 1) * 5  # worst-case
        if cursor + chain_window > 1430:
            cursor = 5 * 60
        line = rng.choice([1, 2, 3])
        origin = rng.choice(terminals)
        dest = rng.choice([t for t in terminals if t != origin])
        for k in range(chain_size):
            dur = rng.randint(45, 75)
            start = cursor
            end = start + dur
            if end > 1439:
                end = 1439
                dur = end - start
                if dur <= 0:
                    break  # sem espaço — pula resto da cadeia
            trips.append({
                "id": trip_id, "line_id": line, "trip_group_id": None,
                "direction": "IDA" if k % 2 == 0 else "VOLTA",
                "origin_id": origin if k % 2 == 0 else dest,
                "destination_id": dest if k % 2 == 0 else origin,
                "start_time": start, "end_time": end,
                "duration": dur, "distance_km": dur * 0.4,
                "origin_latitude": None, "origin_longitude": None,
                "destination_latitude": None, "destination_longitude": None,
            })
            trip_id += 1
            cursor = end + rng.choice([0, 0, 5])  # gap 0 ou 5min — nunca pausa válida (min_break=30)
        cursor += 30  # gap entre cadeias
    # filler para N exato
    for _ in range(leftover):
        start = rng.randint(0, 1380)
        dur = rng.randint(30, 60)
        terms = terminals
        o = rng.choice(terms); d = rng.choice([t for t in terms if t != o])
        trips.append({
            "id": trip_id, "line_id": rng.choice([1, 2, 3]), "trip_group_id": None,
            "direction": "IDA", "origin_id": o, "destination_id": d,
            "start_time": start, "end_time": min(start + dur, 1439),
            "duration": dur, "distance_km": dur * 0.4,
            "origin_latitude": None, "origin_longitude": None,
            "destination_latitude": None, "destination_longitude": None,
        })
        trip_id += 1
    return trips


class ResourceSampler:
    """
    Amostra CPU+RSS de processos celery (workers) durante uma run. Roda thread
    em background polando a cada 1s. Retorna pico de RSS e CPU acumulado.
    Quando psutil não disponível, retorna None nos campos.
    """

    def __init__(self, target_pids: list[int]):
        self.target_pids = target_pids
        self.peak_rss_mb = 0.0
        self.cpu_seconds = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cpu_start: float | None = None
        self.enabled = _HAS_PSUTIL and bool(target_pids)

    def _walk_processes(self):
        for pid in self.target_pids:
            try:
                p = psutil.Process(pid)
                yield p
                for child in p.children(recursive=True):
                    yield child
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _snapshot_cpu(self) -> float:
        total = 0.0
        for p in self._walk_processes():
            try:
                t = p.cpu_times()
                total += t.user + t.system
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total

    def start(self) -> None:
        if not self.enabled:
            return
        self._cpu_start = self._snapshot_cpu()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            for p in self._walk_processes():
                try:
                    rss = p.memory_info().rss / 1024 / 1024
                    if rss > self.peak_rss_mb:
                        self.peak_rss_mb = rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            time.sleep(1)

    def stop(self) -> dict:
        if not self.enabled:
            return {"peak_rss_mb": None, "cpu_seconds": None}
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        cpu_end = self._snapshot_cpu()
        self.cpu_seconds = (cpu_end - (self._cpu_start or 0.0))
        return {
            "peak_rss_mb": round(self.peak_rss_mb, 1),
            "cpu_seconds": round(self.cpu_seconds, 2),
        }


def _find_celery_pid() -> int | None:
    """
    Localiza PID do worker celery (lê /tmp/celery-worker.pid se existir; senão psutil scan).
    """
    pid_file = "/tmp/celery-worker.pid"
    if os.path.exists(pid_file):
        try:
            return int(open(pid_file).read().strip())
        except (OSError, ValueError):
            pass
    if not _HAS_PSUTIL:
        return None
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "celery" in cmd and "-A src.core.celery_app" in cmd:
                return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


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


_CELERY_PID_CACHED: int | None = None


def submit_and_poll(payload: dict) -> dict[str, Any]:
    global _CELERY_PID_CACHED
    if _CELERY_PID_CACHED is None:
        _CELERY_PID_CACHED = _find_celery_pid()
    sampler = ResourceSampler([_CELERY_PID_CACHED] if _CELERY_PID_CACHED else [])
    sampler.start()
    t0 = time.monotonic()
    try:
        submit = _http_post("/optimize/", payload)
    except urllib.error.HTTPError as err:
        sampler.stop()
        body = err.read().decode(errors="replace")[:500]
        return {
            "status": "failed",
            "error": f"HTTP {err.code}: {body}",
            "submit_latency_ms": (time.monotonic() - t0) * 1000,
        }
    submit_latency_ms = (time.monotonic() - t0) * 1000
    task_id = submit.get("task_id")
    if not task_id:
        sampler.stop()
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
            resources = sampler.stop()
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
                "solver_status": (result.get("solver_explanation") or {}).get("status"),
                "fairness_gini": (fairness.get("work_time") or {}).get("gini"),
                "fairness_cv": (fairness.get("work_time") or {}).get("cv"),
                "algorithm_resolved": result.get("vsp_algorithm"),
                "peak_rss_mb": resources.get("peak_rss_mb"),
                "cpu_seconds": resources.get("cpu_seconds"),
            }
        if st == "failed":
            resources = sampler.stop()
            return {
                "status": "failed",
                "submit_latency_ms": submit_latency_ms,
                "solve_latency_ms": (time.monotonic() - t0) * 1000,
                "error": status.get("message") or status.get("error", {}).get("message"),
                "peak_rss_mb": resources.get("peak_rss_mb"),
                "cpu_seconds": resources.get("cpu_seconds"),
            }
        time.sleep(POLL_INTERVAL_S)
    resources = sampler.stop()
    return {
        "status": "timeout",
        "submit_latency_ms": submit_latency_ms,
        "solve_latency_ms": (time.monotonic() - t0) * 1000,
        "peak_rss_mb": resources.get("peak_rss_mb"),
        "cpu_seconds": resources.get("cpu_seconds"),
    }


def fmt_cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def main(sizes: list[int], algos: list[str], seeds: list[int], difficulties: list[str]) -> None:
    results: list[dict[str, Any]] = []
    print(
        f"Benchmark — optimizer={OPTIMIZER_URL} sizes={sizes} algorithms={algos} "
        f"seeds={seeds} difficulties={difficulties} "
        f"started={dt.datetime.now().isoformat(timespec='seconds')}"
    )
    for difficulty in difficulties:
        for n in sizes:
            for seed in seeds:
                trips = make_synthetic_trips(n, seed=seed, difficulty=difficulty)
                for algo in algos:
                    print(
                        f"\n→ N={n}  diff={difficulty}  seed={seed}  algo={algo}  ...",
                        flush=True,
                    )
                    outcome = submit_and_poll(build_payload(trips, algo, time_budget_s=120))
                    outcome["n_trips"] = n
                    outcome["algorithm"] = algo
                    outcome["seed"] = seed
                    outcome["difficulty"] = difficulty
                    results.append(outcome)
                    print(
                        f"   status={outcome.get('status')} "
                        f"solve={fmt_cell(outcome.get('solve_latency_ms'))}ms "
                        f"cost={fmt_cell(outcome.get('total_cost'))} "
                        f"vehicles={fmt_cell(outcome.get('num_vehicles'))} "
                        f"gini={fmt_cell(outcome.get('fairness_gini'))} "
                        f"violations={fmt_cell(outcome.get('cct_violations'))} "
                        f"hard={fmt_cell(outcome.get('hard_issue_count'))}",
                    )

    # Tabela markdown completa (uma linha por run)
    print("\n## Runs individuais\n")
    headers = [
        "Diff",
        "N",
        "Seed",
        "Algo",
        "Status",
        "Solver",
        "Solve ms",
        "Custo R$",
        "Veículos",
        "Duties",
        "Órfãs",
        "Violações",
        "Hard",
        "Gini",
        "RSS MB",
        "CPU s",
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for r in results:
        row = [
            r.get("difficulty"),
            r["n_trips"],
            r.get("seed"),
            r["algorithm"],
            r.get("status"),
            r.get("solver_status", "—"),
            fmt_cell(r.get("solve_latency_ms")),
            fmt_cell(r.get("total_cost")),
            fmt_cell(r.get("num_vehicles")),
            fmt_cell(r.get("num_duties")),
            fmt_cell(r.get("unassigned_trips")),
            fmt_cell(r.get("cct_violations")),
            fmt_cell(r.get("hard_issue_count")),
            fmt_cell(r.get("fairness_gini")),
            fmt_cell(r.get("peak_rss_mb")),
            fmt_cell(r.get("cpu_seconds")),
        ]
        print("| " + " | ".join(str(c) for c in row) + " |")

    # Sumário agregado (média/desvio por config)
    print("\n## Sumário por config (média ± desvio sobre seeds)\n")
    agg: dict[tuple, list[dict]] = {}
    for r in results:
        if r.get("status") != "completed":
            continue
        key = (r.get("difficulty"), r["n_trips"], r["algorithm"])
        agg.setdefault(key, []).append(r)

    print("| Diff | N | Algo | n_seeds | Solve ms μ±σ | Custo R$ μ±σ | Veículos μ | Violações μ |")
    print("|---|---|---|---|---|---|---|---|")
    for key in sorted(agg.keys()):
        diff, n, algo = key
        runs = agg[key]
        latencies = [r.get("solve_latency_ms", 0) for r in runs]
        costs = [r.get("total_cost", 0) or 0 for r in runs]
        vehicles = [r.get("num_vehicles", 0) or 0 for r in runs]
        violations = [r.get("cct_violations", 0) or 0 for r in runs]
        mean_l = sum(latencies) / len(latencies)
        std_l = (sum((x - mean_l) ** 2 for x in latencies) / len(latencies)) ** 0.5
        mean_c = sum(costs) / len(costs)
        std_c = (sum((x - mean_c) ** 2 for x in costs) / len(costs)) ** 0.5
        mean_v = sum(vehicles) / len(vehicles)
        mean_viol = sum(violations) / len(violations)
        print(
            f"| {diff} | {n} | {algo} | {len(runs)} | "
            f"{mean_l:.0f} ± {std_l:.0f} | "
            f"{mean_c:.0f} ± {std_c:.0f} | "
            f"{mean_v:.1f} | "
            f"{mean_viol:.1f} |"
        )

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
        help="CSV de tamanhos de trips (ex: 100,500,1000,2000)",
    )
    p.add_argument(
        "--algo",
        default="hybrid_pipeline,mcnf,simulated_annealing",
        help="CSV de algoritmos. Opções: greedy, genetic, simulated_annealing, tabu_search, "
        "set_partitioning, mcnf, joint_solver, hybrid_pipeline, vcsp_pulp, assignment_vsp",
    )
    p.add_argument(
        "--seeds",
        default="42",
        help="CSV de seeds (ex: 42,43,44). Múltiplas seeds permitem média ± desvio.",
    )
    p.add_argument(
        "--difficulty",
        default="easy",
        help="CSV de difficulties: easy, hard, extreme (ex: easy,hard).",
    )
    return p.parse_args(list(argv))


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    algos = [a.strip() for a in args.algo.split(",") if a.strip()]
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    difficulties = [d.strip() for d in args.difficulty.split(",") if d.strip()]
    main(sizes, algos, seeds, difficulties)
