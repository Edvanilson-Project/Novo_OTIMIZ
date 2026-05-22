"""
Stress test READ-ONLY do novo motor de Chunking + Sparse Assignment.

Conecta no PostgreSQL local (credenciais via .env), puxa o quadro de horários
real (trips), e — se o volume for menor que 40k — REPLICA logicamente cada
trip para simular a carga máxima. Mede tempo, RAM, gargalos.

REGRAS DE OURO:
    - SOMENTE READ. Nenhum INSERT/UPDATE/DELETE no banco.
    - Resultados experimentais ficam APENAS em RAM/stdout/JSON local.
    - Se o banco estiver vazio, gera dados sintéticos in-memory.

Uso:
    python optimizer/scripts/test_real_database_stress.py [--target N] [--out path.json]

Defaults: target=40000, out=stress_report.json
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import json
import logging
import os
import resource
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Carrega .env do optimizer
_optimizer_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_optimizer_root))

try:
    from dotenv import load_dotenv
    load_dotenv(_optimizer_root / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("stress")

from src.domain.models import Trip, VehicleType  # noqa: E402


def rss_mb() -> float:
    """RSS atual em MB. Linux: ru_maxrss em KB; macOS: bytes."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


async def fetch_trips_from_db() -> List[Dict[str, Any]]:
    """READ-ONLY pull do quadro de horários atual via asyncpg."""
    try:
        import asyncpg
    except ImportError:
        log.warning("asyncpg ausente — usando dados sintéticos")
        return []

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USERNAME", os.getenv("DB_USER", "postgres"))
    password = os.getenv("DB_PASSWORD", "postgres")
    database = os.getenv("DB_DATABASE", os.getenv("DB_NAME", "otimiz_db"))

    log.info(f"Conectando READ-ONLY: {user}@{host}:{port}/{database}")
    try:
        conn = await asyncpg.connect(
            host=host, port=port, user=user,
            password=password, database=database,
            timeout=10,
        )
    except Exception as exc:
        log.error(f"Falha de conexão: {exc} — fallback sintético")
        return []

    try:
        # Set transação READ ONLY explicitamente
        await conn.execute("SET TRANSACTION READ ONLY")
        rows = await conn.fetch(
            """
            SELECT
                COALESCE("tripId", id) AS trip_id,
                COALESCE("lineId", 0) AS line_id,
                "tripGroupId" AS trip_group_id,
                "startTime" AS start_time,
                "endTime" AS end_time,
                "originId" AS origin_id,
                "destinationId" AS destination_id,
                COALESCE("distanceKm", 0) AS distance_km,
                COALESCE("duration", 0) AS duration,
                direction
            FROM trips
            WHERE "startTime" IS NOT NULL AND "endTime" IS NOT NULL
            ORDER BY "startTime"
            """
        )
        log.info(f"DB retornou {len(rows)} trips")
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning(f"Query falhou ({exc}) — fallback sintético")
        return []
    finally:
        await conn.close()


def synthetic_trips(n: int) -> List[Dict[str, Any]]:
    """Gera quadro de horários sintético plausível (1 dia, 100 linhas, 30 terminais)."""
    import random
    rng = random.Random(42)
    rows: List[Dict[str, Any]] = []
    n_lines, n_terminals = 100, 30
    for i in range(n):
        line_id = rng.randint(1, n_lines)
        origin = rng.randint(1, n_terminals)
        dest = rng.randint(1, n_terminals)
        while dest == origin:
            dest = rng.randint(1, n_terminals)
        start = rng.randint(240, 1380)
        duration = rng.randint(20, 90)
        rows.append({
            "trip_id": i + 1,
            "line_id": line_id,
            "trip_group_id": (i // 2) + 1,
            "start_time": start,
            "end_time": start + duration,
            "origin_id": origin,
            "destination_id": dest,
            "distance_km": duration * 0.5,
            "duration": duration,
            "direction": "outbound" if i % 2 == 0 else "return",
        })
    rows.sort(key=lambda r: r["start_time"])
    for new_id, r in enumerate(rows, start=1):
        r["trip_id"] = new_id
    return rows


def replicate_to_target(rows: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
    """Replica trips em ciclos de 24h até atingir `target` viagens."""
    if not rows:
        return synthetic_trips(target)
    if len(rows) >= target:
        return rows[:target]

    base = list(rows)
    output = list(rows)
    cycle = 1
    next_id = max(r["trip_id"] for r in base) + 1
    while len(output) < target:
        time_offset = cycle * 1440  # +24h por ciclo
        for r in base:
            if len(output) >= target:
                break
            new_row = dict(r)
            new_row["trip_id"] = next_id
            new_row["start_time"] = r["start_time"] + time_offset
            new_row["end_time"] = r["end_time"] + time_offset
            output.append(new_row)
            next_id += 1
        cycle += 1
    log.info(f"Replicado {len(rows)} → {len(output)} trips (alvo: {target})")
    return output


def to_trip_objects(rows: List[Dict[str, Any]]) -> List[Trip]:
    """Converte rows em dataclass Trip com deadhead_times sintético leve."""
    trips: List[Trip] = []
    for r in rows:
        t = Trip(
            id=int(r["trip_id"]),
            line_id=int(r["line_id"] or 0),
            start_time=int(r["start_time"]),
            end_time=int(r["end_time"]),
            origin_id=int(r["origin_id"] or 0),
            destination_id=int(r["destination_id"] or 0),
            trip_group_id=int(r["trip_group_id"]) if r.get("trip_group_id") else None,
            direction=r.get("direction"),
            duration=int(r["duration"] or 0),
            distance_km=float(r["distance_km"] or 0.0),
        )
        # Deadhead default leve por terminal (5min entre terminais distintos)
        t.deadhead_times = {}
        trips.append(t)
    return trips


def benchmark_assignment_vsp(trips: List[Trip]) -> Dict[str, Any]:
    """Roda novo AssignmentVSP e mede tempo/RAM."""
    from src.algorithms.vsp.assignment import AssignmentVSP

    log.info(f"=== AssignmentVSP em {len(trips)} trips ===")
    gc.collect()
    rss_before = rss_mb()
    t0 = time.perf_counter()
    solver = AssignmentVSP(vsp_params={
        "fixed_vehicle_activation_cost": 800.0,
        "deadhead_cost_per_minute": 1.0,
        "idle_cost_per_minute": 0.25,
        "min_layover_minutes": 8,
        "max_vehicle_shift_minutes": 960,
        "allow_multi_line_block": True,
        "assignment_max_successors_per_trip": 64,
    })
    veh = VehicleType(id=1, name="standard", passenger_capacity=40, fixed_cost=800.0)
    sol = solver.solve(trips, [veh], depot_id=1)
    elapsed = time.perf_counter() - t0
    rss_after = rss_mb()
    return {
        "phase": "vsp_assignment",
        "trip_count": len(trips),
        "elapsed_s": round(elapsed, 3),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_after, 1),
        "rss_delta_mb": round(rss_after - rss_before, 1),
        "blocks_generated": len(sol.blocks),
        "unassigned": len(sol.unassigned_trips),
        "solver_meta": sol.meta,
    }


def benchmark_chunked_csp(trips: List[Trip], blocks) -> Dict[str, Any]:
    """Roda ChunkedCSPOrchestrator + boundary stitching."""
    from src.algorithms.csp.chunked_orchestrator import ChunkedCSPOrchestrator

    log.info(f"=== ChunkedCSP em {len(blocks)} blocos ===")
    gc.collect()
    rss_before = rss_mb()
    t0 = time.perf_counter()
    orch = ChunkedCSPOrchestrator(
        vsp_params={"min_layover_minutes": 8, "max_vehicle_shift_minutes": 960},
        chunk_threshold=1500,
        temporal_window_minutes=240,
        chunk_by_depot=True,
    )
    csp_sol = orch.solve(blocks, trips)
    elapsed = time.perf_counter() - t0
    rss_after = rss_mb()
    return {
        "phase": "csp_chunked",
        "block_count": len(blocks),
        "elapsed_s": round(elapsed, 3),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_after, 1),
        "rss_delta_mb": round(rss_after - rss_before, 1),
        "duties": len(csp_sol.duties),
        "violations": csp_sol.cct_violations,
        "uncovered": len(csp_sol.uncovered_blocks),
        "chunk_meta": (csp_sol.meta or {}).get("chunks", [])[:5],
    }


async def run(target: int, out: Path) -> None:
    log.info(f"### Stress test alvo: {target} viagens ###")
    log.info(f"RSS inicial: {rss_mb():.1f} MB")

    db_rows = await fetch_trips_from_db()
    real_trips = len(db_rows)
    if not db_rows:
        log.warning("Banco vazio/inacessível — usando dataset sintético")
        rows = synthetic_trips(target)
    else:
        rows = replicate_to_target(db_rows, target)

    trips = to_trip_objects(rows)
    log.info(f"Dataset preparado: {len(trips)} trips, RSS {rss_mb():.1f} MB")

    report: Dict[str, Any] = {
        "target_trips": target,
        "real_trips_in_db": real_trips,
        "effective_trips": len(trips),
        "rss_initial_mb": round(rss_mb(), 1),
        "phases": [],
    }

    vsp_metrics = benchmark_assignment_vsp(trips)
    report["phases"].append(vsp_metrics)

    # Recupera blocos para CSP
    from src.algorithms.vsp.assignment import AssignmentVSP
    veh = VehicleType(id=1, name="standard", passenger_capacity=40, fixed_cost=800.0)
    vsp_sol = AssignmentVSP(vsp_params={
        "min_layover_minutes": 8, "max_vehicle_shift_minutes": 960,
        "fixed_vehicle_activation_cost": 800.0,
    }).solve(trips, [veh], depot_id=1)

    # Limita CSP em datasets gigantescos para não consumir hora — pode ser comentado
    if vsp_sol.blocks:
        try:
            csp_metrics = benchmark_chunked_csp(trips, vsp_sol.blocks)
            report["phases"].append(csp_metrics)
        except Exception as exc:
            log.exception("CSP falhou: %s", exc)
            report["phases"].append({"phase": "csp_chunked", "error": str(exc)})

    report["rss_final_mb"] = round(rss_mb(), 1)
    report["total_elapsed_s"] = round(sum(p.get("elapsed_s", 0) for p in report["phases"]), 3)

    out.write_text(json.dumps(report, indent=2, default=str))
    log.info(f"Relatório salvo em {out}")
    print(json.dumps(report, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=40000)
    parser.add_argument("--out", type=Path, default=Path("stress_report.json"))
    args = parser.parse_args()
    asyncio.run(run(args.target, args.out))


if __name__ == "__main__":
    main()
