"""
Benchmark end-to-end OTIMIZ.

Fluxo testado:
  Backend NestJS -> PostgreSQL -> FastAPI Optimizer -> Celery -> Redis
  -> persistencia PostgreSQL -> /operations/latest-schedule.

O script cria/reusa uma empresa isolada (`otimiz-e2e-benchmark`) e nao altera as
viagens reais da empresa de origem. As viagens sinteticas sao copias temporais
das viagens reais.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import resource
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_optimizer_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_optimizer_root))

try:
    from dotenv import load_dotenv

    load_dotenv(_optimizer_root / ".env")
    load_dotenv(_optimizer_root.parent / "backend" / ".env")
except ImportError:
    pass

from scripts.benchmark_real_volumes import (  # noqa: E402
    build_default_vehicle_types,
    default_params,
    export_replay_snapshot,
    fetch_company_params,
    fetch_real_trips,
    make_safe_synthetic_rows,
    run_replay_snapshot,
)
from src.domain.models import AlgorithmType  # noqa: E402


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:3001/api/v1").rstrip("/")
JWT_SECRET = os.getenv("JWT_SECRET", "mudar_para_um_segredo_forte_em_producao")


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return float(usage.ru_utime + usage.ru_stime)


def b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def sign_jwt(company_id: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": 0,
        "email": "e2e-benchmark@otimiz.local",
        "companyId": company_id,
        "role": "super_admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 6 * 3600,
    }
    signing_input = b".".join(
        [
            b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return b".".join([signing_input, b64url(signature)]).decode("ascii")


def http_json(method: str, path: str, token: str, body: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Tuple[int, Dict[str, Any], float]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    started = now_ms()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed = now_ms() - started
            return resp.status, json.loads(raw.decode("utf-8") or "{}"), elapsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        elapsed = now_ms() - started
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return exc.code, parsed, elapsed


async def db_connect():
    import asyncpg

    return await asyncpg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5444")),
        user=os.getenv("DB_USER", os.getenv("DB_USERNAME", "otimiz_admin")),
        password=os.getenv("DB_PASSWORD", "otimiz_password"),
        database=os.getenv("DB_NAME", os.getenv("DB_DATABASE", "otimiz_db")),
        timeout=15,
    )


async def ensure_test_company(slug: str) -> int:
    conn = await db_connect()
    try:
        await conn.execute('ALTER TABLE company_parameters ADD COLUMN IF NOT EXISTS "strict_zero_gap_validation" boolean')
        await conn.execute('ALTER TABLE company_parameters ADD COLUMN IF NOT EXISTS "strict_operational_mode" boolean')
        await conn.execute('ALTER TABLE company_parameters ADD COLUMN IF NOT EXISTS "strict_hard_constraints" boolean')
        row = await conn.fetchrow('SELECT id FROM companies WHERE slug = $1', slug)
        if row:
            return int(row["id"])
        row = await conn.fetchrow(
            """
            INSERT INTO companies (name, slug, "tradeName", "isActive", "createdAt", "updatedAt")
            VALUES ($1, $2, $3, true, now(), now())
            RETURNING id
            """,
            "OTIMIZ E2E Benchmark",
            slug,
            "OTIMIZ E2E Benchmark",
        )
        return int(row["id"])
    finally:
        await conn.close()


async def reset_company_dataset(company_id: int, rows: Sequence[Dict[str, Any]], params: Dict[str, Any], algorithm: str) -> Dict[str, Any]:
    conn = await db_connect()
    try:
        async with conn.transaction():
            schedule_ids = await conn.fetch('SELECT id FROM schedules WHERE "companyId" = $1', company_id)
            ids = [int(row["id"]) for row in schedule_ids]
            if ids:
                await conn.execute('DELETE FROM duty_assignments WHERE "companyId" = $1', company_id)
                await conn.execute('DELETE FROM block_assignments WHERE "companyId" = $1', company_id)
                await conn.execute('DELETE FROM schedules WHERE "companyId" = $1', company_id)
            await conn.execute('DELETE FROM trips WHERE "companyId" = $1', company_id)
            await conn.execute('DELETE FROM company_parameters WHERE "companyId" = $1', company_id)

            await conn.executemany(
                """
                INSERT INTO trips (
                    "companyId", "tripId", "lineId", "pairId", "tripGroupId", direction,
                    "startTime", "endTime", "originId", "destinationId",
                    "distanceKm", duration,
                    "originLatitude", "originLongitude", "destinationLatitude", "destinationLongitude",
                    "createdAt", "updatedAt"
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,now(),now())
                """,
                [
                    (
                        company_id,
                        int(row["trip_id"]),
                        int(row.get("line_id") or 0),
                        row.get("pair_id"),
                        int(row["trip_group_id"]) if row.get("trip_group_id") is not None else None,
                        row.get("direction"),
                        int(row["start_time"]),
                        int(row["end_time"]),
                        int(row["origin_id"]),
                        int(row["destination_id"]),
                        float(row.get("distance_km") or 0.0),
                        int(row.get("duration") or max(0, int(row["end_time"]) - int(row["start_time"]))),
                        float(row["origin_latitude"]) if row.get("origin_latitude") is not None else None,
                        float(row["origin_longitude"]) if row.get("origin_longitude") is not None else None,
                        float(row["destination_latitude"]) if row.get("destination_latitude") is not None else None,
                        float(row["destination_longitude"]) if row.get("destination_longitude") is not None else None,
                    )
                    for row in rows
                ],
            )

            await conn.execute(
                """
                INSERT INTO company_parameters (
                    "companyId", "driver_cost_per_minute", "collector_cost_per_minute",
                    "vehicle_fixed_cost", "cost_vehicle", "cost_km", "cost_duty",
                    "cct_violation_penalty", "force_round_trip", "allow_vehicle_swap",
                    "max_driving_time_minutes", "meal_break_minutes", "max_shift_minutes",
                    "max_driving_minutes", "min_break_minutes", "enforce_min_interval",
                    "connection_tolerance_minutes", "mandatory_break_after_minutes",
                    "min_layover_minutes", "allow_relief_points", "enforce_same_depot_start_end",
                    "operator_change_terminals_only", "enforce_trip_groups_hard",
                    "operator_pairing_hard", "trip_group_keep_bonus",
                    "enforce_single_line_duty", "operator_single_vehicle_only",
                    "apply_cct", "strict_hard_validation", "strict_zero_gap_validation",
                    "strict_operational_mode", "strict_hard_constraints",
                    "strict_gps_validation", "strict_terminal_sync_validation",
                    "strict_union_rules", "time_budget_s", "random_seed",
                    "max_vehicle_shift_minutes", "max_vehicles", "deadhead_cost_per_minute",
                    "idle_cost_per_minute", "allow_multi_line_block",
                    "preferred_pair_window_minutes", "preserve_preferred_pairs",
                    "max_candidate_successors_per_task", "algorithm_preference",
                    "ilp_timeout_seconds", "terminal_location_ids", "goal_weights", "dynamic_rules",
                    "createdAt", "updatedAt"
                )
                VALUES (
                    $1,0.5,0.4,$2,$2,1.0,500.0,500.0,
                    $3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                    $14,$15,$16,$17,$18,$19,$20,$21,$22,
                    $23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,
                    $34,$35,$36,$37,$38,$39,$40,$41,'{}'::integer[],'{}'::jsonb,'[]'::jsonb,
                    now(),now()
                )
                """,
                company_id,
                float(params.get("fixed_vehicle_activation_cost", 800.0)),
                bool(params.get("force_round_trip", False)),
                bool(params.get("allow_vehicle_swap", True)),
                int(params.get("max_driving_minutes", 270)),
                int(params.get("meal_break_minutes", 60)),
                int(params.get("max_shift_minutes", 720)),
                int(params.get("max_driving_minutes", 270)),
                int(params.get("min_break_minutes", 30)),
                bool(params.get("enforce_min_interval", True)),
                int(params.get("connection_tolerance_minutes", 0)),
                int(params.get("mandatory_break_after_minutes", 270)),
                int(params.get("min_layover_minutes", 8)),
                bool(params.get("allow_relief_points", False)),
                bool(params.get("enforce_same_depot_start_end", False)),
                bool(params.get("operator_change_terminals_only", True)),
                bool(params.get("force_round_trip", False)),
                bool(params.get("force_round_trip", False)),
                float(params.get("trip_group_keep_bonus", 240.0)),
                bool(params.get("enforce_single_line_duty", False)),
                bool(params.get("operator_single_vehicle_only", not bool(params.get("allow_vehicle_swap", True)))),
                bool(params.get("apply_cct", True)),
                bool(params.get("strict_hard_validation", True)),
                bool(params.get("strict_zero_gap_validation", True)),
                bool(params.get("strict_operational_mode", True)),
                bool(params.get("strict_hard_constraints", True)),
                bool(params.get("strict_gps_validation", False)),
                bool(params.get("strict_terminal_sync_validation", False)),
                bool(params.get("strict_union_rules", True)),
                int(params.get("time_budget_s", 120)),
                int(params.get("random_seed", 42)),
                int(params.get("max_vehicle_shift_minutes", params.get("max_shift_minutes", 720))),
                None,
                float(params.get("deadhead_cost_per_minute", 1.0)),
                float(params.get("idle_cost_per_minute", 0.25)),
                bool(params.get("allow_multi_line_block", True)),
                int(params.get("preferred_pair_window_minutes", 30)),
                bool(params.get("preserve_preferred_pairs", True)),
                int(params.get("max_candidate_successors_per_task", 64)),
                algorithm,
                int(params.get("ilp_timeout_seconds", 120)),
            )
        count = await conn.fetchval('SELECT count(*) FROM trips WHERE "companyId" = $1', company_id)
        db_trip_ids = await conn.fetch(
            'SELECT id FROM trips WHERE "companyId" = $1 ORDER BY "startTime", COALESCE("tripId", id), id',
            company_id,
        )
        payload_rows = await conn.fetch(
            """
            SELECT
                id,
                COALESCE("lineId", 0) AS line_id,
                "tripGroupId" AS trip_group_id,
                direction,
                "startTime" AS start_time,
                "endTime" AS end_time,
                "originId" AS origin_id,
                "destinationId" AS destination_id,
                COALESCE("distanceKm", 0) AS distance_km,
                COALESCE(duration, GREATEST("endTime" - "startTime", 0)) AS duration,
                "originLatitude" AS origin_latitude,
                "originLongitude" AS origin_longitude,
                "destinationLatitude" AS destination_latitude,
                "destinationLongitude" AS destination_longitude
            FROM trips
            WHERE "companyId" = $1
            ORDER BY "startTime", COALESCE("tripId", id), id
            """,
            company_id,
        )
        return {
            "company_id": company_id,
            "trip_rows": int(count),
            "input_db_trip_ids": [int(row["id"]) for row in db_trip_ids],
            "payload_trip_rows": [dict(row) for row in payload_rows],
        }
    finally:
        await conn.close()


async def fetch_schedule_db(schedule_id: int, company_id: int) -> Dict[str, Any]:
    conn = await db_connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT id, status, "totalCost", "cctViolations", metadata,
                   EXTRACT(EPOCH FROM ("updatedAt" - "createdAt")) * 1000 AS elapsed_ms,
                   "createdAt", "updatedAt"
            FROM schedules
            WHERE id = $1 AND "companyId" = $2
            """,
            schedule_id,
            company_id,
        )
        if not row:
            return {}
        blocks = await conn.fetchval('SELECT count(*) FROM block_assignments WHERE "scheduleId" = $1 AND "companyId" = $2', schedule_id, company_id)
        duties = await conn.fetchval('SELECT count(*) FROM duty_assignments WHERE "scheduleId" = $1 AND "companyId" = $2', schedule_id, company_id)
        trip_ids_rows = await conn.fetch('SELECT "tripIds" FROM block_assignments WHERE "scheduleId" = $1 AND "companyId" = $2', schedule_id, company_id)
        covered: List[int] = []
        for item in trip_ids_rows:
            covered.extend([int(x) for x in item["tripIds"] or []])
        return {
            "id": int(row["id"]),
            "status": row["status"],
            "total_cost": float(row["totalCost"] or 0),
            "cct_violations": int(row["cctViolations"] or 0),
            "metadata": ensure_dict(row["metadata"]),
            "schedule_elapsed_ms": float(row["elapsed_ms"] or 0),
            "blocks": int(blocks or 0),
            "duties": int(duties or 0),
            "covered_ids": covered,
        }
    finally:
        await conn.close()


def dupes(items: Iterable[int]) -> List[int]:
    seen = set()
    out = set()
    for item in items:
        if item in seen:
            out.add(item)
        seen.add(item)
    return sorted(out)


def ensure_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def proc_stats(pattern: str) -> Dict[str, Any]:
    try:
        out = subprocess.check_output(["pgrep", "-af", pattern], text=True)
    except Exception:
        return {"pattern": pattern, "found": False}
    pids = []
    cmdlines = []
    rss_kb = 0
    cpu_s = 0.0
    clk = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    for line in out.strip().splitlines():
        parts = line.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        pids.append(pid)
        cmdlines.append(parts[1] if len(parts) > 1 else "")
        try:
            status = Path(f"/proc/{pid}/status").read_text()
            for status_line in status.splitlines():
                if status_line.startswith("VmRSS:"):
                    rss_kb += int(status_line.split()[1])
        except Exception:
            pass
        try:
            stat = Path(f"/proc/{pid}/stat").read_text().split()
            cpu_s += (int(stat[13]) + int(stat[14])) / clk
        except Exception:
            pass
    return {
        "pattern": pattern,
        "found": bool(pids),
        "pids": pids,
        "rss_mb": round(rss_kb / 1024, 1),
        "cpu_s": round(cpu_s, 3),
        "cmdlines": cmdlines[:3],
    }


def redis_usage(task_id: Optional[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    try:
        import redis

        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6388/0"), decode_responses=False)
        info["used_memory_bytes"] = int(client.info("memory").get("used_memory", 0))
        info["optimizer_queue_len"] = int(client.llen("optimizer"))
        if task_id:
            for key in [f"celery-task-meta-{task_id}", f"optimizer:task_timestamp:{task_id}"]:
                usage = client.memory_usage(key)
                if usage is not None:
                    info[f"memory_usage:{key}"] = int(usage)
        client.close()
    except Exception as exc:
        info["error"] = str(exc)
    return info


def summarize_chunk_map(scale_decomposition: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    chunks = scale_decomposition.get("chunks") or []
    return {
        int(chunk.get("chunk_index")): {
            "trip_count": int(chunk.get("trip_count") or 0),
            "vehicles": int(chunk.get("vehicles") or 0),
            "duties": int(chunk.get("duties") or 0),
            "status": str(chunk.get("status") or ""),
            "split_groups": int(chunk.get("split_groups") or 0),
            "hard_issues": int(chunk.get("hard_issues") or 0),
        }
        for chunk in chunks
    }


def compare_chunk_metrics(direct_scale: Dict[str, Any], e2e_scale: Dict[str, Any]) -> Dict[str, Any]:
    direct_map = summarize_chunk_map(direct_scale or {})
    e2e_map = summarize_chunk_map(e2e_scale or {})
    indexes = sorted(set(direct_map) | set(e2e_map))
    chunks: List[Dict[str, Any]] = []
    for index in indexes:
        direct = direct_map.get(index) or {}
        e2e = e2e_map.get(index) or {}
        chunks.append(
            {
                "chunk_index": index,
                "trip_count": e2e.get("trip_count") or direct.get("trip_count") or 0,
                "direct_status": direct.get("status"),
                "e2e_status": e2e.get("status"),
                "direct_vehicles": direct.get("vehicles"),
                "e2e_vehicles": e2e.get("vehicles"),
                "vehicle_delta": int(e2e.get("vehicles") or 0) - int(direct.get("vehicles") or 0),
                "direct_duties": direct.get("duties"),
                "e2e_duties": e2e.get("duties"),
                "duty_delta": int(e2e.get("duties") or 0) - int(direct.get("duties") or 0),
                "direct_split_groups": direct.get("split_groups"),
                "e2e_split_groups": e2e.get("split_groups"),
                "direct_hard_issues": direct.get("hard_issues"),
                "e2e_hard_issues": e2e.get("hard_issues"),
            }
        )
    direct_stitch = (direct_scale or {}).get("stitching") or {}
    e2e_stitch = (e2e_scale or {}).get("stitching") or {}
    return {
        "chunks": chunks,
        "stitching": {
            "direct": direct_stitch,
            "e2e": e2e_stitch,
            "accepted_delta": int(e2e_stitch.get("accepted") or 0) - int(direct_stitch.get("accepted") or 0),
            "rejected_delta": int(e2e_stitch.get("rejected") or 0) - int(direct_stitch.get("rejected") or 0),
            "input_blocks_delta": int(e2e_stitch.get("input_blocks") or 0) - int(direct_stitch.get("input_blocks") or 0),
            "output_blocks_delta": int(e2e_stitch.get("output_blocks") or 0) - int(direct_stitch.get("output_blocks") or 0),
        },
    }


def matrix_from_args(args: argparse.Namespace) -> List[Tuple[str, int]]:
    volumes = [int(v.strip()) for v in args.volumes.split(",") if v.strip()]
    algs = [a.strip() for a in args.algorithms.split(",") if a.strip()]
    matrix: List[Tuple[str, int]] = []
    for alg in algs:
        for volume in volumes:
            if alg == "mcnf" and volume > args.mcnf_max_volume:
                continue
            if alg in {"simulated_annealing", "tabu_search"} and volume not in {298, 1000}:
                continue
            if volume == 5000 and alg not in {"assignment_vsp", "hybrid_pipeline"}:
                continue
            matrix.append((alg, volume))
    return matrix


async def run_case(
    company_id: int,
    token: str,
    base_rows: Sequence[Dict[str, Any]],
    db_params: Dict[str, Any],
    algorithm: str,
    volume: int,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    rows = make_safe_synthetic_rows(base_rows, volume)
    params = default_params(db_params, fail_on_hard_violations=True)
    params.update(
        {
            "strict_hard_validation": True,
            "strict_zero_gap_validation": True,
            "strict_operational_mode": True,
            "strict_hard_constraints": True,
            "time_budget_s": int(args.time_budget_s),
        }
    )

    setup = await reset_company_dataset(company_id, rows, params, algorithm)
    input_ids = [int(item) for item in setup.get("input_db_trip_ids", [])] or [int(row["trip_id"]) for row in rows]

    backend_before = proc_stats("node dist/main")
    celery_before = proc_stats("celery.*src.worker|celery.*src.core.celery_app")
    redis_before = redis_usage(None)
    submit_status, submit_body, submit_ms = http_json("POST", "/operations/optimize", token, {"algorithm": algorithm}, timeout=60)
    schedule_id = submit_body.get("scheduleId")
    task_id = submit_body.get("taskId") or submit_body.get("task_id")

    case_started = now_ms()
    latest_body: Dict[str, Any] = {}
    latest_ms = 0.0
    final_db: Dict[str, Any] = {}
    state = "submitted" if submit_status < 400 else "submit_failed"
    if submit_status < 400 and schedule_id:
        deadline = time.time() + args.case_timeout_s
        while time.time() < deadline:
            final_db = await fetch_schedule_db(int(schedule_id), company_id)
            if final_db.get("status") in {"completed", "failed"}:
                state = final_db["status"]
                break
            time.sleep(args.poll_interval_s)
        latest_status, latest_body, latest_ms = http_json("GET", "/operations/latest-schedule", token, None, timeout=60)
        if latest_status >= 400:
            latest_body = {"http_status": latest_status, "body": latest_body}
    total_e2e_ms = now_ms() - case_started

    redis_after = redis_usage(task_id)
    backend_after = proc_stats("node dist/main")
    celery_after = proc_stats("celery.*src.worker|celery.*src.core.celery_app")

    covered_ids = final_db.get("covered_ids") or []
    missing = sorted(set(input_ids) - set(covered_ids))
    duplicated = dupes(covered_ids)
    meta = ensure_dict(final_db.get("metadata"))
    hard_report = ensure_dict(meta.get("hard_constraint_report"))
    output_report = ensure_dict(hard_report.get("output"))
    hard_issues = output_report.get("issues") or []
    perf = meta.get("performance") or {}
    scale_decomposition = perf.get("scale_decomposition") or {}
    result_summary = latest_body.get("resultSummary") or {}
    resolved_params = ensure_dict(meta.get("resolved_params"))
    run_snapshot = ensure_dict(meta.get("run_snapshot"))
    submitted_params = ensure_dict(run_snapshot.get("submitted_params"))
    replay_snapshot_path = Path(
        f"optimizer/replays/e2e_{algorithm}_{volume}_schedule_{schedule_id or 'unknown'}.json"
    )
    vehicle_type_rows = build_default_vehicle_types(
        ensure_dict(submitted_params.get("vsp_params"))
        or ensure_dict(resolved_params.get("vsp_params"))
        or ensure_dict(resolved_params.get("optimization_params"))
        or params
    )
    replay_direct: Dict[str, Any]
    replay_rows = setup.get("payload_trip_rows") or rows
    if resolved_params and run_snapshot:
        replay_snapshot = export_replay_snapshot(
            rows=replay_rows,
            vehicle_type_rows=vehicle_type_rows,
            algorithm=algorithm,
            time_budget_s=float(run_snapshot.get("time_budget_s") or args.time_budget_s),
            cct_params=ensure_dict(submitted_params.get("cct_params")) or ensure_dict(resolved_params.get("submitted_cct_params")),
            vsp_params=ensure_dict(submitted_params.get("vsp_params")) or ensure_dict(resolved_params.get("submitted_vsp_params")),
            optimization_params=ensure_dict(submitted_params.get("optimization_params")) or ensure_dict(resolved_params.get("submitted_optimization_params")),
            request_metadata=ensure_dict(run_snapshot.get("request_metadata")),
            run_snapshot=run_snapshot,
            out_path=replay_snapshot_path,
        )
        replay_direct = run_replay_snapshot(replay_snapshot)
    else:
        replay_direct = {
            "status": "error",
            "error": "missing_resolved_params_or_run_snapshot",
        }

    e2e = {
        "status": state,
        "submit_http_status": submit_status,
        "schedule_id": schedule_id,
        "task_id": task_id,
        "submit_time_ms": round(submit_ms, 2),
        "backend_total_time_ms": round(total_e2e_ms, 2),
        "schedule_created_to_updated_ms": round(final_db.get("schedule_elapsed_ms", 0), 2),
        "frontend_read_time_ms": round(latest_ms, 2),
        "optimizer_solver_ms": (perf.get("phase_timings_ms") or {}).get("solver_ms"),
        "optimizer_total_elapsed_ms": perf.get("total_elapsed_ms"),
        "scale_decomposition": scale_decomposition,
        "scale_chunk_count": scale_decomposition.get("chunk_count"),
        "scale_fallback_chunk_count": scale_decomposition.get("fallback_chunk_count"),
        "scale_stitching": scale_decomposition.get("stitching") or {},
        "redis_before": redis_before,
        "redis_after": redis_after,
        "backend_process_before": backend_before,
        "backend_process_after": backend_after,
        "celery_process_before": celery_before,
        "celery_process_after": celery_after,
        "vehicles": final_db.get("blocks", 0),
        "duties": final_db.get("duties", 0),
        "total_cost": final_db.get("total_cost", 0),
        "input_trips": len(input_ids),
        "covered_trips": len(covered_ids),
        "missing_trips": len(missing),
        "duplicated_trips": len(duplicated),
        "hard_violations": len(hard_issues),
        "soft_violations": int((meta.get("soft_issue_count") or 0)),
        "cct_violations": final_db.get("cct_violations", 0),
        "error_type": meta.get("error_type"),
        "error_code": meta.get("error_code"),
        "error_message": meta.get("error_message"),
        "error_details": meta.get("error_details"),
        "latest_schedule_status": latest_body.get("status"),
        "latest_has_hard_constraint_report": bool(result_summary.get("hardConstraintReport")),
        "latest_has_performance": bool(result_summary.get("performance")),
        "metadata_has_hard_constraint_report": bool(hard_report),
        "metadata_has_performance": bool(perf),
        "resolved_params": resolved_params,
        "run_snapshot": run_snapshot,
        "replay_snapshot_path": str(replay_snapshot_path) if replay_snapshot_path.exists() else None,
        "sample_missing_trip_ids": missing[:20],
        "sample_duplicated_trip_ids": duplicated[:20],
        "sample_hard_issues": [str(x) for x in hard_issues[:20]],
        "setup": setup,
    }

    replay_snapshot_meta = replay_direct.get("run_snapshot") or {}
    replay_group_report = replay_direct.get("trip_group_inference_report") or {}
    e2e_group_report = (run_snapshot.get("trip_group_inference_report") or {})
    comparison = {
        "direct_status": replay_direct.get("status"),
        "direct_time_ms": round(float(replay_direct.get("wall_time_s") or 0.0) * 1000, 2),
        "cost_delta": round(float(e2e["total_cost"] or 0) - float(replay_direct.get("total_cost") or 0), 2),
        "vehicle_delta": int(e2e["vehicles"] or 0) - int(replay_direct.get("vehicles") or 0),
        "duty_delta": int(e2e["duties"] or 0) - int(replay_direct.get("duties") or 0),
        "time_delta_ms": round(float(e2e["backend_total_time_ms"] or 0) - (float(replay_direct.get("wall_time_s") or 0.0) * 1000), 2),
        "hard_violation_delta": int(e2e["hard_violations"] or 0) - int(replay_direct.get("hard_violations") or 0),
        "snapshot_path": str(replay_snapshot_path) if replay_snapshot_path.exists() else None,
        "snapshot_parity": {
            "resolved_params_match": (
                ensure_dict((replay_direct.get("resolved_params") or {}).get("cct_params"))
                == ensure_dict((run_snapshot.get("resolved_params") or {}).get("cct_params"))
                and ensure_dict((replay_direct.get("resolved_params") or {}).get("vsp_params"))
                == ensure_dict((run_snapshot.get("resolved_params") or {}).get("vsp_params"))
                and ensure_dict((replay_direct.get("resolved_params") or {}).get("optimization_params"))
                == ensure_dict((run_snapshot.get("resolved_params") or {}).get("optimization_params"))
            ),
            "trips_hash_match": replay_snapshot_meta.get("trips_hash") == run_snapshot.get("trips_hash"),
            "vehicle_types_hash_match": replay_snapshot_meta.get("vehicle_types_hash") == run_snapshot.get("vehicle_types_hash"),
            "seed_match": replay_snapshot_meta.get("seed") == run_snapshot.get("seed"),
            "effective_groups_match": (
                ensure_dict(replay_group_report.get("optimizer_effective_stats"))
                == ensure_dict(e2e_group_report.get("optimizer_effective_stats"))
            ),
        },
        "chunk_comparison": compare_chunk_metrics(
            replay_direct.get("scale_decomposition") or {},
            e2e.get("scale_decomposition") or {},
        ),
    }

    bugs: List[str] = []
    if state == "completed" and e2e["missing_trips"]:
        bugs.append("P0: viagens perdidas no resultado persistido")
    if state == "completed" and e2e["duplicated_trips"]:
        bugs.append("P0: viagens duplicadas no resultado persistido")
    if state == "completed" and e2e["hard_violations"]:
        bugs.append("P1: hard violations em strict mode")
    if state == "failed" and not e2e.get("error_code"):
        bugs.append("P0: falha sem error_code persistido")
    if state == "failed" and not e2e.get("error_message"):
        bugs.append("P0: falha sem error_message persistido")
    if e2e["metadata_has_hard_constraint_report"] and not e2e["latest_has_hard_constraint_report"]:
        bugs.append("P1: hardConstraintReport existe no metadata mas nao aparece na resposta da tela")
    if e2e["metadata_has_performance"] and not e2e["latest_has_performance"]:
        bugs.append("P1: performance existe no metadata mas nao aparece na resposta da tela")
    parity = comparison.get("snapshot_parity") or {}
    if not parity.get("resolved_params_match"):
        bugs.append("P0: replay direto nao recebeu o mesmo pacote final de parametros")
    if not parity.get("trips_hash_match"):
        bugs.append("P0: replay direto nao recebeu o mesmo hash de trips do E2E")
    if not parity.get("seed_match"):
        bugs.append("P1: seed divergiu entre E2E e replay direto")
    if not parity.get("effective_groups_match"):
        bugs.append("P1: grupos efetivos divergiram entre E2E e replay direto")

    return {
        "algorithm": algorithm,
        "volume": volume,
        "direct_python": replay_direct,
        "e2e": e2e,
        "comparison": comparison,
        "bugs": bugs,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# OTIMIZ E2E Benchmark",
        "",
        f"- backend_url: `{report.get('backend_url')}`",
        f"- company_id: `{report.get('company_id')}`",
        f"- source_real_trips: `{report.get('source_real_trips')}`",
        "",
        "| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report.get("results", []):
        if "e2e" not in item:
            lines.append(
                f"| {item.get('algorithm')} | {item.get('volume')} | script_error |  |  |  |  |  |  |  |  |  |  |  |  | |"
            )
            continue
        e = item["e2e"]
        redis_bytes = ""
        task_id = e.get("task_id")
        if task_id:
            redis_bytes = e.get("redis_after", {}).get(f"memory_usage:celery-task-meta-{task_id}", "")
        celery_rss = e.get("celery_process_after", {}).get("rss_mb", "")
        stitching = e.get("scale_stitching") or {}
        lines.append(
            f"| {item['algorithm']} | {item['volume']} | {e.get('status')} | "
            f"{round((e.get('backend_total_time_ms') or 0)/1000, 3)} | "
            f"{round((e.get('optimizer_total_elapsed_ms') or 0)/1000, 3) if e.get('optimizer_total_elapsed_ms') else ''} | "
            f"{e.get('frontend_read_time_ms')} | {redis_bytes} | {celery_rss} | "
            f"{e.get('scale_chunk_count') or ''} | {e.get('scale_fallback_chunk_count') or ''} | "
            f"{stitching.get('accepted', '')}/{stitching.get('rejected', '')} | "
            f"{e.get('total_cost')} | {e.get('vehicles')} | {e.get('duties')} | "
            f"{e.get('missing_trips')} | {e.get('duplicated_trips')} | "
            f"{e.get('hard_violations')} | {e.get('soft_violations')} | "
            f"{e.get('latest_has_hard_constraint_report')}/{e.get('latest_has_performance')} |"
        )
    lines.append("")
    lines.append("## Comparacao Direto Python vs E2E")
    lines.append("")
    lines.append("| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta | params/hash/seed/groups |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for item in report.get("results", []):
        if "comparison" not in item:
            continue
        c = item["comparison"]
        parity = c.get("snapshot_parity") or {}
        lines.append(
            f"| {item['algorithm']} | {item['volume']} | {c.get('cost_delta')} | {c.get('vehicle_delta')} | "
            f"{c.get('duty_delta')} | {c.get('time_delta_ms')} | {c.get('hard_violation_delta')} | "
            f"{parity.get('resolved_params_match')}/{parity.get('trips_hash_match')}/{parity.get('seed_match')}/{parity.get('effective_groups_match')} |"
        )
    for item in report.get("results", []):
        c = item.get("comparison") or {}
        chunk_comparison = c.get("chunk_comparison") or {}
        chunks = chunk_comparison.get("chunks") or []
        if not chunks:
            continue
        lines.append("")
        lines.append(f"## Chunk Diff {item['algorithm']} {item['volume']}")
        lines.append("")
        lines.append("| chunk | trips | direct status | e2e status | direct veic. | e2e veic. | delta veic. | direct duties | e2e duties | delta duties |")
        lines.append("|---:|---:|---|---|---:|---:|---:|---:|---:|---:|")
        for chunk in chunks:
            lines.append(
                f"| {chunk.get('chunk_index')} | {chunk.get('trip_count')} | {chunk.get('direct_status')} | "
                f"{chunk.get('e2e_status')} | {chunk.get('direct_vehicles')} | {chunk.get('e2e_vehicles')} | "
                f"{chunk.get('vehicle_delta')} | {chunk.get('direct_duties')} | {chunk.get('e2e_duties')} | "
                f"{chunk.get('duty_delta')} |"
            )
        stitching = chunk_comparison.get("stitching") or {}
        lines.append("")
        lines.append(
            "- stitching direct/e2e: "
            f"accepted `{(stitching.get('direct') or {}).get('accepted', 0)}` / `{(stitching.get('e2e') or {}).get('accepted', 0)}`, "
            f"rejected `{(stitching.get('direct') or {}).get('rejected', 0)}` / `{(stitching.get('e2e') or {}).get('rejected', 0)}`, "
            f"output blocks `{(stitching.get('direct') or {}).get('output_blocks', 0)}` / `{(stitching.get('e2e') or {}).get('output_blocks', 0)}`."
        )
        if c.get("snapshot_path"):
            lines.append(f"- replay snapshot: `{c.get('snapshot_path')}`")
    all_bugs = []
    for item in report.get("results", []):
        for bug in item.get("bugs", []):
            all_bugs.append(f"{item['algorithm']} {item['volume']}: {bug}")
    lines.append("")
    lines.append("## Bugs Encontrados")
    lines.append("")
    if all_bugs:
        lines.extend(f"- {bug}" for bug in all_bugs)
    else:
        lines.append("- Nenhum bug novo detectado nos cenarios executados.")
    lines.append("")
    lines.append("## Logs Principais")
    lines.append("")
    for log in report.get("logs", []):
        lines.append(f"- `{log}`")
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> None:
    test_company_id = await ensure_test_company(args.test_company_slug)
    source_rows = await fetch_real_trips(company_id=args.source_company_id, limit=args.source_limit)
    if not source_rows:
        raise SystemExit("Nao encontrei viagens reais de origem no banco.")
    source_company_id = args.source_company_id or int(source_rows[0]["company_id"])
    db_params = await fetch_company_params(source_company_id)
    token = sign_jwt(test_company_id)

    report: Dict[str, Any] = {
        "backend_url": BACKEND_URL,
        "company_id": test_company_id,
        "source_company_id": source_company_id,
        "source_real_trips": len(source_rows),
        "matrix": matrix_from_args(args),
        "results": [],
        "logs": [
            "/tmp/otimiz-e2e-celery.log",
            "backend stdout session",
            "optimizer uvicorn stdout session",
        ],
    }

    for algorithm, volume in matrix_from_args(args):
        print(f"RUN {algorithm} {volume}", flush=True)
        try:
            result = await run_case(test_company_id, token, source_rows, db_params, algorithm, volume, args)
        except Exception as exc:
            result = {
                "algorithm": algorithm,
                "volume": volume,
                "error": f"{type(exc).__name__}: {exc}",
                "bugs": [f"P0: caso nao executou: {type(exc).__name__}: {exc}"],
            }
        report["results"].append(result)
        args.out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        args.out_md.write_text(markdown(report))

    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-company-id", type=int, default=None)
    parser.add_argument("--source-limit", type=int, default=None)
    parser.add_argument("--test-company-slug", default="otimiz-e2e-benchmark")
    parser.add_argument("--volumes", default="298,596,1000,2000,5000")
    parser.add_argument("--algorithms", default="assignment_vsp,hybrid_pipeline,mcnf,simulated_annealing,tabu_search")
    parser.add_argument("--mcnf-max-volume", type=int, default=1000)
    parser.add_argument("--time-budget-s", type=int, default=120)
    parser.add_argument("--case-timeout-s", type=int, default=900)
    parser.add_argument("--poll-interval-s", type=float, default=2.0)
    parser.add_argument("--out-json", type=Path, default=Path("optimizer/e2e_benchmark_report.json"))
    parser.add_argument("--out-md", type=Path, default=Path("optimizer/e2e_benchmark_report.md"))
    return parser


def main() -> None:
    asyncio.run(main_async(build_parser().parse_args()))


if __name__ == "__main__":
    main()
