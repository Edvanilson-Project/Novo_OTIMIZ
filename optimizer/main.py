"""
OTIMIZ Optimizer — FastAPI Microservice
Ponto de entrada da aplicação.
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.routes import health, optimize, strategy, whatif, rostering
from src.core.config import get_settings
from src.core.logging import configure_logging
from src.domain.models import Trip
from src.services import StrategyPersistenceService, StrategyService, worker_state

log = structlog.get_logger(__name__)
settings = get_settings()

# ── Dependency: Validates Internal Key ─────────────────────────────────────
async def verify_internal_key(
    x_internal_key: str = Header(None, alias="X-Internal-Key")
):
    if not settings.internal_security_key: # Fail-fast se não configurado
        log.error("security_key_not_configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security key not configured on server",
        )
    
    if x_internal_key != settings.internal_security_key:
        log.warning("invalid_internal_key_attempt", header=x_internal_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal security key",
        )
    return x_internal_key

# ── Middleware: Tracking & Logging Correlation ID & Multi-Tenancy ───────
class TenantLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", "internal-task")
        company_id = request.headers.get("X-Company-ID", "unknown")
        
        # Injeta variáveis no contexto de log do structlog
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            company_id=company_id
        )
        
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Company-ID"] = company_id
        return response


def _trip_from_dict(item: dict) -> Trip:
    return Trip(
        id=int(item.get("id", 0)),
        line_id=int(item.get("line_id", 0)),
        trip_group_id=item.get("trip_group_id"),
        direction=item.get("direction"),
        start_time=int(item.get("start_time", 0)),
        end_time=int(item.get("end_time", 0)),
        origin_id=int(item.get("origin_id", 0)),
        destination_id=int(item.get("destination_id", 0)),
        duration=int(item.get("duration", 0)),
        distance_km=float(item.get("distance_km", 0.0)),
        depot_id=item.get("depot_id"),
        relief_point_id=item.get("relief_point_id"),
        is_relief_point=bool(item.get("is_relief_point", False)),
        energy_kwh=float(item.get("energy_kwh", 0.0)),
        elevation_gain_m=float(item.get("elevation_gain_m", 0.0)),
        service_day=item.get("service_day"),
        is_holiday=bool(item.get("is_holiday", False)),
        origin_latitude=item.get("origin_latitude"),
        origin_longitude=item.get("origin_longitude"),
        destination_latitude=item.get("destination_latitude"),
        destination_longitude=item.get("destination_longitude"),
        sent_to_driver_terminal=item.get("sent_to_driver_terminal"),
        gps_valid=item.get("gps_valid"),
        deadhead_times={
            int(k): int(v)
            for k, v in (item.get("deadhead_times") or {}).items()
        },
    )


async def _auto_reconcile_loop() -> None:
    persistence = StrategyPersistenceService(settings.strategy_data_dir)
    strategy_service = StrategyService()
    reconcile_interval = max(30, int(settings.strategy_reconcile_interval_seconds))
    feed_poll_interval = max(5, int(settings.strategy_feed_poll_interval_seconds))
    loop_interval = min(reconcile_interval, feed_poll_interval)

    inbox_path = Path(settings.strategy_feed_inbox_dir)
    archive_path = Path(settings.strategy_feed_archive_dir)
    inbox_path.mkdir(parents=True, exist_ok=True)
    archive_path.mkdir(parents=True, exist_ok=True)

    last_reconciled_snapshot_id = 0
    last_cleanup_ts = 0.0
    worker_state.update(status="running", started_at=worker_state.utc_now_iso(), last_error=None)

    def _normalize_records(payload: object) -> list[dict]:
        records: object = payload
        if isinstance(payload, dict):
            records = payload.get("records", [])
        if not isinstance(records, list):
            return []
        normalized: list[dict] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            trip_id = item.get("trip_id")
            if trip_id is None:
                continue
            try:
                normalized.append(
                    {
                        "trip_id": int(trip_id),
                        "actual_start_time": item.get("actual_start_time"),
                        "actual_end_time": item.get("actual_end_time"),
                        "vehicle_id": item.get("vehicle_id"),
                        "gps_valid": item.get("gps_valid"),
                        "sent_to_driver_terminal": item.get("sent_to_driver_terminal"),
                        "source": str(item.get("source", "file")),
                    }
                )
            except Exception:
                continue
        return normalized

    def _reconcile_latest_if_needed() -> None:
        nonlocal last_reconciled_snapshot_id
        scenario = persistence.get_latest_scenario()
        snapshot = persistence.get_latest_feed_snapshot()
        if not scenario or not snapshot:
            return

        snapshot_id = int(snapshot.get("id", 0) or 0)
        if snapshot_id <= 0 or snapshot_id == last_reconciled_snapshot_id:
            return

        planned = [_trip_from_dict(item) for item in scenario.get("trips", [])]
        if not planned:
            return

        report = strategy_service.plan_vs_real(planned, snapshot.get("records", []))
        report["scenario_id"] = int(scenario.get("id", 0))
        report["scenario_name"] = str(scenario.get("scenario_name", ""))
        report["source_snapshot_id"] = snapshot_id
        persistence.save_reconciliation_report(report)
        last_reconciled_snapshot_id = snapshot_id
        worker_state.update(
            last_reconcile_at=worker_state.utc_now_iso(),
            last_reconcile_scenario_id=report["scenario_id"],
            last_reconcile_snapshot_id=snapshot_id,
            last_error=None,
        )
        log.info(
            "strategy_auto_reconcile_ok",
            scenario_id=report["scenario_id"],
            source_snapshot_id=snapshot_id,
        )

    def _process_feed_inbox() -> None:
        for file_path in sorted(inbox_path.glob("*.json")):
            target_name = f"{int(time.time() * 1000)}-{file_path.name}"
            archived_ok_path = archive_path / target_name
            archived_err_path = archive_path / f"error-{target_name}"
            try:
                raw = json.loads(file_path.read_text(encoding="utf-8"))
                records = _normalize_records(raw)
                if not records:
                    file_path.replace(archived_err_path)
                    log.warning("strategy_feed_inbox_empty_or_invalid", file=str(file_path))
                    continue

                persistence.ingest_feed(records)
                file_path.replace(archived_ok_path)
                worker_state.update(
                    last_ingest_at=worker_state.utc_now_iso(),
                    last_ingest_file=file_path.name,
                    last_ingest_records=len(records),
                    last_error=None,
                )
                log.info(
                    "strategy_feed_ingested",
                    file=str(file_path.name),
                    records=len(records),
                )

                if settings.strategy_feed_auto_reconcile_on_ingest:
                    _reconcile_latest_if_needed()
            except Exception as exc:  # pragma: no cover - robustez em background
                with suppress(Exception):
                    file_path.replace(archived_err_path)
                log.warning(
                    "strategy_feed_ingest_failed",
                    file=str(file_path.name),
                    error=str(exc),
                )
                worker_state.update(last_error=str(exc))

    while True:
        try:
            worker_state.update(last_poll_at=worker_state.utc_now_iso())
            _process_feed_inbox()
            _reconcile_latest_if_needed()

            now_ts = time.time()
            if now_ts - last_cleanup_ts >= max(60, int(settings.strategy_retention_cleanup_interval_seconds)):
                stats = persistence.prune_data(
                    max_scenarios=max(1, int(settings.strategy_retention_max_scenarios)),
                    max_feed_snapshots=max(1, int(settings.strategy_retention_max_feed_snapshots)),
                    max_reports=max(1, int(settings.strategy_retention_max_reports)),
                    max_age_days=max(0, int(settings.strategy_retention_max_age_days)),
                )
                last_cleanup_ts = now_ts
                worker_state.update(
                    last_cleanup_at=worker_state.utc_now_iso(),
                    last_cleanup_stats=stats,
                )
                if any(v > 0 for v in stats.values()):
                    log.info("strategy_retention_cleanup", **stats)
        except Exception as exc:  # pragma: no cover - robustez em background
            log.warning("strategy_auto_reconcile_failed", error=str(exc))
            worker_state.update(last_error=str(exc))

        await asyncio.sleep(loop_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    log.info(
        "optimizer_starting",
        version=settings.app_version,
        algorithms=settings.enabled_algorithms,
    )
    task = None
    if settings.strategy_auto_reconcile_enabled:
        task = asyncio.create_task(_auto_reconcile_loop())
        log.info(
            "strategy_auto_reconcile_enabled",
            interval_seconds=max(30, int(settings.strategy_reconcile_interval_seconds)),
        )
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    log.info("optimizer_shutdown")


app = FastAPI(
    title="OTIMIZ Optimizer Service",
    description="""
## Motor de Otimização de Transporte Público

Resolve **VSP** (Vehicle Scheduling Problem) e **CSP** (Crew Scheduling Problem)
com múltiplos algoritmos:

| Categoria   | Algoritmo              | Complexidade |
|-------------|------------------------|-------------|
| Construtivo | Greedy                 | O(n log n)  |
| Metaheur.   | Genetic Algorithm      | O(g·n·pop)  |
| Metaheur.   | Simulated Annealing    | O(t·n)      |
| Metaheur.   | Tabu Search            | O(i·n²)     |
| Exato       | Set Partitioning (ILP) | NP          |
| Integrado   | VSP+CSP Joint Solver   | —           |
| Híbrido     | Pipeline Completo      | —           |
""",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Multi-Tenancy & Correlation ID ──────────────────────────────────────────
app.add_middleware(TenantLoggingMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ───────────────────────────────────────────────────────
Instrumentator(excluded_handlers=["/health", "/metrics"]).instrument(app).expose(app)

# ── Rotas ────────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/health", tags=["Health"])

# Proteção global das rotas operacionais
app.include_router(
    optimize.router, 
    prefix="/optimize", 
    tags=["Optimize"],
    dependencies=[Depends(verify_internal_key)]
)
app.include_router(
    strategy.router, 
    prefix="/strategy", 
    tags=["Strategy"],
    dependencies=[Depends(verify_internal_key)]
)
app.include_router(
    rostering.router, 
    prefix="/optimize/rostering", 
    tags=["Rostering"],
    dependencies=[Depends(verify_internal_key)]
)
app.include_router(
    whatif.router, 
    prefix="/api/v1", 
    tags=["What-If"],
    dependencies=[Depends(verify_internal_key)]
)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
