"""
Benchmark read-only com viagens reais e multiplicacao sintetica segura.

Objetivo:
  - ler viagens reais do PostgreSQL sem escrever no banco;
  - gerar volumes maiores por copia temporal dos dados reais;
  - rodar um algoritmo configuravel do optimizer Python;
  - medir tempo, CPU, memoria, viagens perdidas/duplicadas, hard violations e custo;
  - gerar relatorio JSON e Markdown por volume.

Uso:
  python optimizer/scripts/benchmark_real_volumes.py --volumes 298,596,1000 --algorithm assignment_vsp

Por seguranca, o script nao usa VCSP_PULP por padrao e nao seleciona MCNF/HybridPipeline
automaticamente. Escolha outro algoritmo apenas quando quiser medir explicitamente.
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_optimizer_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_optimizer_root))

try:
    from dotenv import load_dotenv

    load_dotenv(_optimizer_root / ".env")
    load_dotenv(_optimizer_root.parent / ".env")
except ImportError:
    pass

from src.domain.models import AlgorithmType, Trip, VehicleType  # noqa: E402
from src.services.optimizer_service import OptimizerService  # noqa: E402


def rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def process_cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return float(usage.ru_utime + usage.ru_stime)


def parse_volumes(raw: str) -> List[int]:
    volumes = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            volumes.append(int(item))
    if not volumes:
        raise ValueError("Informe pelo menos um volume")
    return volumes


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return int(value)


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


async def fetch_real_trips(company_id: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError("asyncpg nao esta instalado; instale para ler o PostgreSQL") from exc

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", os.getenv("DB_USERNAME", "otimiz_admin"))
    password = os.getenv("DB_PASSWORD", "otimiz_password")
    database = os.getenv("DB_NAME", os.getenv("DB_DATABASE", "otimiz_db"))

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        timeout=15,
    )
    try:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    "companyId" AS company_id,
                    COALESCE("tripId", id) AS trip_id,
                    COALESCE("lineId", 0) AS line_id,
                    "pairId" AS pair_id,
                    "tripGroupId" AS trip_group_id,
                    direction,
                    "startTime" AS start_time,
                    "endTime" AS end_time,
                    "originId" AS origin_id,
                    "destinationId" AS destination_id,
                    COALESCE("distanceKm", 0) AS distance_km,
                    COALESCE("duration", GREATEST("endTime" - "startTime", 0)) AS duration,
                    "originLatitude" AS origin_latitude,
                    "originLongitude" AS origin_longitude,
                    "destinationLatitude" AS destination_latitude,
                    "destinationLongitude" AS destination_longitude
                FROM trips
                WHERE "startTime" IS NOT NULL
                  AND "endTime" IS NOT NULL
                  AND ($1::int IS NULL OR "companyId" = $1::int)
                ORDER BY "startTime", COALESCE("tripId", id), id
                LIMIT COALESCE($2::int, 2147483647)
                """,
                company_id,
                limit,
            )
            return [dict(row) for row in rows]
    finally:
        await conn.close()


async def fetch_company_params(company_id: Optional[int]) -> Dict[str, Any]:
    if company_id is None:
        return {}
    try:
        import asyncpg
    except ImportError:
        return {}

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", os.getenv("DB_USERNAME", "otimiz_admin"))
    password = os.getenv("DB_PASSWORD", "otimiz_password")
    database = os.getenv("DB_NAME", os.getenv("DB_DATABASE", "otimiz_db"))

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        timeout=15,
    )
    try:
        async with conn.transaction(readonly=True):
            row = await conn.fetchrow(
                """
                SELECT *
                FROM company_parameters
                WHERE "companyId" = $1::int
                ORDER BY "updatedAt" DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                company_id,
            )
            return dict(row) if row else {}
    finally:
        await conn.close()


def make_safe_synthetic_rows(base_rows: Sequence[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
    if not base_rows:
        raise ValueError("Nao ha viagens reais para multiplicar")

    base = sorted(base_rows, key=lambda r: (as_int(r.get("start_time")), as_int(r.get("trip_id"))))
    base_trip_ids = [as_int(r.get("trip_id") or r.get("id")) for r in base]
    base_groups = [as_int(r.get("trip_group_id")) for r in base if r.get("trip_group_id") is not None]
    trip_stride = max(max(base_trip_ids, default=0) + 1, len(base) + 1, 1_000_000)
    group_stride = max(max(base_groups, default=0) + 1, len(base) + 1, 1_000_000)

    output: List[Dict[str, Any]] = []
    copy_idx = 0
    while len(output) < target:
        time_offset = copy_idx * 1440
        for row_index, row in enumerate(base):
            if len(output) >= target:
                break
            new_row = dict(row)
            original_trip_id = as_int(row.get("trip_id") or row.get("id"), row_index + 1)
            new_row["original_trip_id"] = original_trip_id
            new_row["synthetic_copy_index"] = copy_idx
            new_row["trip_id"] = original_trip_id + (copy_idx * trip_stride)
            new_row["start_time"] = as_int(row.get("start_time")) + time_offset
            new_row["end_time"] = as_int(row.get("end_time")) + time_offset
            if row.get("trip_group_id") is not None:
                new_row["trip_group_id"] = as_int(row.get("trip_group_id")) + (copy_idx * group_stride)
            if row.get("pair_id"):
                new_row["pair_id"] = f"{row.get('pair_id')}__copy_{copy_idx}"
            output.append(new_row)
        copy_idx += 1
    return output


def rows_to_trips(rows: Sequence[Dict[str, Any]]) -> List[Trip]:
    trips: List[Trip] = []
    for row in sorted(rows, key=lambda item: (as_int(item.get("start_time")), as_int(item.get("trip_id") or item.get("id")), as_int(item.get("id"), 0))):
        trip = Trip(
            id=as_int(row.get("trip_id") or row.get("id")),
            line_id=as_int(row.get("line_id")),
            start_time=as_int(row.get("start_time")),
            end_time=as_int(row.get("end_time")),
            origin_id=as_int(row.get("origin_id")),
            destination_id=as_int(row.get("destination_id")),
            trip_group_id=as_int(row.get("trip_group_id")) if row.get("trip_group_id") is not None else None,
            direction=row.get("direction"),
            duration=as_int(row.get("duration")),
            distance_km=as_float(row.get("distance_km")),
            original_trip_id=as_int(row.get("original_trip_id")) if row.get("original_trip_id") is not None else None,
            origin_latitude=as_float(row.get("origin_latitude")) if row.get("origin_latitude") is not None else None,
            origin_longitude=as_float(row.get("origin_longitude")) if row.get("origin_longitude") is not None else None,
            destination_latitude=as_float(row.get("destination_latitude")) if row.get("destination_latitude") is not None else None,
            destination_longitude=as_float(row.get("destination_longitude")) if row.get("destination_longitude") is not None else None,
        )
        trips.append(trip)
    return trips


def default_params(db_params: Dict[str, Any], fail_on_hard_violations: bool) -> Dict[str, Any]:
    max_shift_minutes = int(db_params.get("max_shift_minutes") or 720)
    max_vehicle_shift_minutes = int(
        db_params.get("max_vehicle_shift_minutes")
        or db_params.get("max_shift_minutes")
        or max_shift_minutes
    )
    max_driving_minutes = int(
        db_params.get("max_driving_minutes")
        or db_params.get("max_driving_time_minutes")
        or 270
    )
    allow_vehicle_swap = bool(
        db_params.get("allow_vehicle_swap")
        if db_params.get("allow_vehicle_swap") is not None
        else not bool(db_params.get("operator_single_vehicle_only", False))
    )
    params = {
        "apply_cct": True,
        "strict_hard_validation": fail_on_hard_violations,
        "strict_zero_gap_validation": bool(db_params.get("strict_zero_gap_validation", False)),
        "strict_operational_mode": bool(db_params.get("strict_operational_mode", False)),
        "strict_hard_constraints": bool(db_params.get("strict_hard_constraints", False)),
        "min_layover_minutes": int(db_params.get("min_layover_minutes") or 8),
        "min_break_minutes": int(db_params.get("min_break_minutes") or 30),
        "enforce_min_interval": bool(db_params.get("enforce_min_interval", True)),
        "connection_tolerance_minutes": int(db_params.get("connection_tolerance_minutes") or 0),
        "max_shift_minutes": max_shift_minutes,
        "max_vehicle_shift_minutes": max_vehicle_shift_minutes,
        "max_driving_minutes": max_driving_minutes,
        "meal_break_minutes": int(db_params.get("meal_break_minutes") or 60),
        "mandatory_break_after_minutes": int(db_params.get("mandatory_break_after_minutes") or 270),
        "force_round_trip": bool(db_params.get("force_round_trip", False)),
        "allow_vehicle_swap": allow_vehicle_swap,
        "allow_multi_line_block": bool(db_params.get("allow_multi_line_block", True)),
        "operator_single_vehicle_only": bool(db_params.get("operator_single_vehicle_only", not allow_vehicle_swap)),
        "fixed_vehicle_activation_cost": float(
            db_params.get("vehicle_fixed_cost")
            or db_params.get("fixed_vehicle_activation_cost")
            or 800.0
        ),
        "deadhead_cost_per_minute": float(db_params.get("deadhead_cost_per_minute") or 1.0),
        "idle_cost_per_minute": float(db_params.get("idle_cost_per_minute") or 0.25),
        "max_candidate_successors_per_task": int(db_params.get("max_candidate_successors_per_task") or 64),
        "random_seed": int(db_params.get("random_seed") or 42),
        "preferred_pair_window_minutes": int(db_params.get("preferred_pair_window_minutes") or 30),
        "preserve_preferred_pairs": bool(
            db_params.get("preserve_preferred_pairs")
            if db_params.get("preserve_preferred_pairs") is not None
            else True
        ),
    }
    return params


def build_default_vehicle_types(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "id": 1,
            "name": "Padrao",
            "passenger_capacity": 40,
            "cost_per_km": 1.0,
            "cost_per_hour": 10.0,
            "fixed_cost": float(params.get("fixed_vehicle_activation_cost", 800.0)),
            "is_electric": False,
            "battery_capacity_kwh": 0.0,
            "minimum_soc": 0.15,
            "charge_rate_kw": 0.0,
            "energy_cost_per_kwh": 0.0,
            "depot_id": None,
        }
    ]


def _vehicle_types_from_rows(vehicle_type_rows: Sequence[Dict[str, Any]]) -> List[VehicleType]:
    return [
        VehicleType(
            id=int(item["id"]),
            name=str(item.get("name", "")),
            passenger_capacity=int(item.get("passenger_capacity", 40)),
            cost_per_km=float(item.get("cost_per_km", 0.0)),
            cost_per_hour=float(item.get("cost_per_hour", 0.0)),
            fixed_cost=float(item.get("fixed_cost", 800.0)),
            is_electric=bool(item.get("is_electric", False)),
            battery_capacity_kwh=float(item.get("battery_capacity_kwh", 0.0)),
            minimum_soc=float(item.get("minimum_soc", 0.15)),
            charge_rate_kw=float(item.get("charge_rate_kw", 0.0)),
            energy_cost_per_kwh=float(item.get("energy_cost_per_kwh", 0.0)),
            depot_id=item.get("depot_id"),
        )
        for item in vehicle_type_rows
    ]


def export_replay_snapshot(
    *,
    rows: Sequence[Dict[str, Any]],
    vehicle_type_rows: Sequence[Dict[str, Any]],
    algorithm: str,
    time_budget_s: float,
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    optimization_params: Dict[str, Any],
    request_metadata: Dict[str, Any],
    run_snapshot: Dict[str, Any],
    out_path: Path,
) -> Dict[str, Any]:
    snapshot = {
        "schema_version": "optimization_replay_export_v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": algorithm,
        "time_budget_s": float(time_budget_s),
        "trips": list(rows),
        "vehicle_types": list(vehicle_type_rows),
        "cct_params": dict(cct_params),
        "vsp_params": dict(vsp_params),
        "optimization_params": dict(optimization_params),
        "request_metadata": dict(request_metadata),
        "run_snapshot": dict(run_snapshot),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str))
    return snapshot


def run_replay_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    rows = snapshot.get("trips") or []
    vehicle_type_rows = snapshot.get("vehicle_types") or []
    algorithm = AlgorithmType(str(snapshot["algorithm"]))
    return run_one_volume_split(
        rows,
        algorithm,
        cct_params=dict(snapshot.get("cct_params") or {}),
        vsp_params=dict(snapshot.get("vsp_params") or {}),
        optimization_params=dict(snapshot.get("optimization_params") or {}),
        time_budget_s=float(snapshot.get("time_budget_s") or 0.0),
        request_metadata=dict(snapshot.get("request_metadata") or {}),
        vehicle_type_rows=vehicle_type_rows,
    )


def covered_trip_ids(result: Any) -> List[int]:
    ids: List[int] = []
    for block in result.vsp.blocks or []:
        ids.extend(int(trip.id) for trip in block.trips)
    return ids


def duplicate_ids(ids: Iterable[int]) -> List[int]:
    seen = set()
    duplicates = set()
    for item in ids:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return sorted(duplicates)


def output_hard_issues(result: Any) -> List[str]:
    report = ((result.meta or {}).get("hard_constraint_report") or {}).get("output") or {}
    issues = report.get("issues") or []
    return [str(issue) for issue in issues]


def run_one_volume(
    rows: Sequence[Dict[str, Any]],
    algorithm: AlgorithmType,
    params: Dict[str, Any],
    time_budget_s: float,
) -> Dict[str, Any]:
    return run_one_volume_split(
        rows,
        algorithm,
        cct_params=dict(params),
        vsp_params=dict(params),
        optimization_params=dict(params),
        time_budget_s=time_budget_s,
        request_metadata={},
        vehicle_type_rows=build_default_vehicle_types(params),
    )


def run_one_volume_split(
    rows: Sequence[Dict[str, Any]],
    algorithm: AlgorithmType,
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    optimization_params: Dict[str, Any],
    time_budget_s: float,
    request_metadata: Optional[Dict[str, Any]] = None,
    vehicle_type_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    gc.collect()
    trips = rows_to_trips(rows)
    input_ids = [int(trip.id) for trip in trips]
    input_duplicates = duplicate_ids(input_ids)

    service = OptimizerService()
    vehicle_rows = list(vehicle_type_rows or build_default_vehicle_types(vsp_params))
    vehicle_types = _vehicle_types_from_rows(vehicle_rows)

    rss_before = rss_mb()
    cpu_before = process_cpu_seconds()
    wall_before = time.perf_counter()
    try:
        result = service.run(
            trips,
            vehicle_types,
            algorithm=algorithm,
            time_budget_s=time_budget_s,
            cct_params=dict(cct_params),
            vsp_params=dict(vsp_params),
            optimization_params=dict(optimization_params),
            request_metadata=dict(request_metadata or {}),
        )
        error = None
    except Exception as exc:
        result = None
        error = f"{type(exc).__name__}: {exc}"
    wall_after = time.perf_counter()
    cpu_after = process_cpu_seconds()
    rss_after = rss_mb()

    if result is None:
        return {
            "volume": len(rows),
            "algorithm": algorithm.value,
            "status": "error",
            "error": error,
            "wall_time_s": round(wall_after - wall_before, 3),
            "cpu_time_s": round(cpu_after - cpu_before, 3),
            "rss_before_mb": round(rss_before, 1),
            "rss_after_mb": round(rss_after, 1),
            "rss_delta_mb": round(rss_after - rss_before, 1),
            "input_duplicate_trips": len(input_duplicates),
        }

    covered_ids = covered_trip_ids(result)
    covered_set = set(covered_ids)
    input_set = set(input_ids)
    duplicated = duplicate_ids(covered_ids)
    missing = sorted(input_set - covered_set)
    extra = sorted(covered_set - input_set)
    hard_issues = output_hard_issues(result)
    performance_meta = (result.meta or {}).get("performance") or {}
    resolved_input = (result.meta or {}).get("input") or {}
    run_snapshot = (result.meta or {}).get("run_snapshot") or resolved_input.get("run_snapshot") or {}
    group_report = resolved_input.get("group_inference_report") or {}

    return {
        "volume": len(rows),
        "algorithm": algorithm.value,
        "status": "ok",
        "wall_time_s": round(wall_after - wall_before, 3),
        "cpu_time_s": round(cpu_after - cpu_before, 3),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_after, 1),
        "rss_delta_mb": round(rss_after - rss_before, 1),
        "total_cost": round(float(result.total_cost or 0.0), 2),
        "vehicles": len(result.vsp.blocks or []),
        "duties": len(result.csp.duties or []),
        "input_trips": len(input_ids),
        "covered_trips": len(covered_ids),
        "unique_covered_trips": len(covered_set),
        "missing_trips": len(missing),
        "duplicated_trips": len(duplicated),
        "extra_trips": len(extra),
        "input_duplicate_trips": len(input_duplicates),
        "unassigned_trips": len(result.vsp.unassigned_trips or []),
        "uncovered_blocks": len(result.csp.uncovered_blocks or []),
        "hard_violations": len(hard_issues),
        "cct_violations": int(result.csp.cct_violations or 0),
        "sample_missing_trip_ids": missing[:20],
        "sample_duplicated_trip_ids": duplicated[:20],
        "sample_hard_issues": hard_issues[:20],
        "phase_timings_ms": performance_meta.get("phase_timings_ms") or {},
        "scale_decomposition": performance_meta.get("scale_decomposition") or {},
        "scale_execution_status": (result.meta or {}).get("scale_execution_status"),
        "run_snapshot": run_snapshot,
        "resolved_params": {
            "cct_params": resolved_input.get("cct_params") or {},
            "vsp_params": resolved_input.get("vsp_params") or {},
            "optimization_params": resolved_input.get("optimization_params") or {},
            "request_metadata": resolved_input.get("request_metadata") or {},
        },
        "trip_group_inference_report": group_report,
    }


def markdown_report(report: Dict[str, Any]) -> str:
    rows = report.get("results") or []
    lines = [
        "# OTIMIZ Benchmark Report",
        "",
        f"- algoritmo: `{report.get('algorithm')}`",
        f"- viagens reais lidas: `{report.get('real_trip_count')}`",
        f"- company_id: `{report.get('company_id')}`",
        f"- fail_on_hard_violations: `{report.get('fail_on_hard_violations')}`",
        "",
        "| volume | status | tempo s | CPU s | RSS delta MB | custo | veiculos | duties | perdidas | duplicadas | hard violations |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        lines.append(
            "| {volume} | {status} | {wall_time_s} | {cpu_time_s} | {rss_delta_mb} | {total_cost} | "
            "{vehicles} | {duties} | {missing_trips} | {duplicated_trips} | {hard_violations} |".format(
                volume=item.get("volume"),
                status=item.get("status"),
                wall_time_s=item.get("wall_time_s"),
                cpu_time_s=item.get("cpu_time_s"),
                rss_delta_mb=item.get("rss_delta_mb"),
                total_cost=item.get("total_cost", ""),
                vehicles=item.get("vehicles", ""),
                duties=item.get("duties", ""),
                missing_trips=item.get("missing_trips", ""),
                duplicated_trips=item.get("duplicated_trips", ""),
                hard_violations=item.get("hard_violations", ""),
            )
        )
    lines.append("")
    for item in rows:
        if item.get("status") != "ok":
            lines.extend([f"## Volume {item.get('volume')}", "", f"Erro: `{item.get('error')}`", ""])
            continue
        if item.get("sample_missing_trip_ids") or item.get("sample_duplicated_trip_ids") or item.get("sample_hard_issues"):
            lines.extend([f"## Volume {item.get('volume')}", ""])
            if item.get("sample_missing_trip_ids"):
                lines.append(f"- sample_missing_trip_ids: `{item.get('sample_missing_trip_ids')}`")
            if item.get("sample_duplicated_trip_ids"):
                lines.append(f"- sample_duplicated_trip_ids: `{item.get('sample_duplicated_trip_ids')}`")
            if item.get("sample_hard_issues"):
                lines.append(f"- sample_hard_issues: `{item.get('sample_hard_issues')}`")
            lines.append("")
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> None:
    algorithm = AlgorithmType(args.algorithm)
    if algorithm == AlgorithmType.VCSP_PULP and args.allow_vcsp_pulp is not True:
        raise SystemExit("VCSP_PULP bloqueado neste benchmark. Use --allow-vcsp-pulp explicitamente para instancia pequena.")

    volumes = parse_volumes(args.volumes)
    real_rows = await fetch_real_trips(company_id=args.company_id, limit=args.real_limit)
    if not real_rows:
        raise SystemExit("Nenhuma viagem real encontrada no banco; benchmark cancelado.")

    effective_company_id = args.company_id or real_rows[0].get("company_id")
    db_params = await fetch_company_params(int(effective_company_id) if effective_company_id is not None else None)
    params = default_params(db_params, fail_on_hard_violations=args.fail_on_hard_violations)
    if args.strict_zero_gap_validation is not None:
        params["strict_zero_gap_validation"] = args.strict_zero_gap_validation
    if args.strict_operational_mode is not None:
        params["strict_operational_mode"] = args.strict_operational_mode
    if args.strict_hard_constraints is not None:
        params["strict_hard_constraints"] = args.strict_hard_constraints

    report: Dict[str, Any] = {
        "algorithm": algorithm.value,
        "company_id": effective_company_id,
        "real_trip_count": len(real_rows),
        "volumes": volumes,
        "fail_on_hard_violations": args.fail_on_hard_violations,
        "params": params,
        "results": [],
    }

    for volume in volumes:
        rows = make_safe_synthetic_rows(real_rows, volume)
        result = run_one_volume(rows, algorithm, params, time_budget_s=args.time_budget_s)
        report["results"].append(result)
        print(json.dumps(result, ensure_ascii=False, default=str))

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(markdown_report(report))
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")


def optional_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "sim"}:
        return True
    if normalized in {"0", "false", "no", "n", "nao", "não"}:
        return False
    raise argparse.ArgumentTypeError(f"Boolean invalido: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--real-limit", type=int, default=None)
    parser.add_argument("--volumes", default="298,596,1000")
    parser.add_argument("--algorithm", default=AlgorithmType.ASSIGNMENT_VSP.value, choices=[item.value for item in AlgorithmType])
    parser.add_argument("--time-budget-s", type=float, default=120.0)
    parser.add_argument("--fail-on-hard-violations", action="store_true")
    parser.add_argument("--allow-vcsp-pulp", action="store_true")
    parser.add_argument("--strict-zero-gap-validation", type=optional_bool, default=None)
    parser.add_argument("--strict-operational-mode", type=optional_bool, default=None)
    parser.add_argument("--strict-hard-constraints", type=optional_bool, default=None)
    parser.add_argument("--out-json", type=Path, default=Path("optimizer/benchmark_report.json"))
    parser.add_argument("--out-md", type=Path, default=Path("optimizer/benchmark_report.md"))
    return parser


def main() -> None:
    asyncio.run(main_async(build_parser().parse_args()))


if __name__ == "__main__":
    main()
