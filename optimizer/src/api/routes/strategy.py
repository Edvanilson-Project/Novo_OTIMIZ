"""
Rotas estratégicas: macro-estimate, what-if e feedback planejado vs realizado.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ...core.config import get_settings
from ...domain.models import Trip
from ...services import StrategyPersistenceService, StrategyService, worker_state
from ..converters import to_trip as _to_trip
from ..schemas import (
    FeedRecordInput,
    IngestFeedRequest,
    IngestFeedResponse,
    ListReconciliationReportsResponse,
    ListScenariosResponse,
    MacroEstimateRequest,
    MacroEstimateResponse,
    PlanVsRealRequest,
    PlanVsRealResponse,
    ReconciliationReportItem,
    RunReconciliationRequest,
    RunReconciliationResponse,
    RunRetentionCleanupRequest,
    RunRetentionCleanupResponse,
    SaveScenarioRequest,
    SaveScenarioResponse,
    SavedScenarioEstimate,
    ScenarioListItem,
    WhatIfRequest,
    WhatIfResponse,
    WhatIfScenarioResult,
    WorkerStatusResponse,
)

router = APIRouter()
_service = StrategyService()
_settings = get_settings()
_persistence = StrategyPersistenceService(_settings.strategy_data_dir)


def _trip_from_dict(item: dict) -> Trip:
    return Trip(
        id=int(item.get("id", 0)),
        line_id=int(item.get("line_id", 0)),
        trip_group_id=item.get("trip_group_id"),
        start_time=int(item.get("start_time", 0)),
        end_time=int(item.get("end_time", 0)),
        origin_id=int(item.get("origin_id", 0)),
        destination_id=int(item.get("destination_id", 0)),
        duration=int(item.get("duration", 0)),
        distance_km=float(item.get("distance_km", 0.0)),
        depot_id=item.get("depot_id"),
        relief_point_id=item.get("relief_point_id"),
        is_relief_point=bool(item.get("is_relief_point", False)),
        mid_trip_relief_point_id=item.get("mid_trip_relief_point_id"),
        mid_trip_relief_offset_minutes=item.get("mid_trip_relief_offset_minutes"),
        mid_trip_relief_distance_ratio=item.get("mid_trip_relief_distance_ratio"),
        mid_trip_relief_elevation_ratio=item.get("mid_trip_relief_elevation_ratio"),
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


def _to_actual_record(t: FeedRecordInput) -> dict:
    return {
        "trip_id": t.trip_id,
        "actual_start_time": t.actual_start_time,
        "actual_end_time": t.actual_end_time,
        "vehicle_id": t.vehicle_id,
        "gps_valid": t.gps_valid,
        "sent_to_driver_terminal": t.sent_to_driver_terminal,
        "source": t.source,
    }


def _run_reconciliation_for_scenario(scenario_id: int | None = None) -> dict:
    scenario = _persistence.get_scenario(scenario_id) if scenario_id else _persistence.get_latest_scenario()
    if scenario is None:
        raise HTTPException(status_code=404, detail="No saved scenario available for reconciliation")

    planned_data = scenario.get("trips", [])
    planned = [_trip_from_dict(item) for item in planned_data]
    actual = _persistence.get_latest_feed_records()
    if not actual:
        raise HTTPException(status_code=404, detail="No feed snapshot available for reconciliation")

    report = _service.plan_vs_real(planned, actual)
    report["scenario_id"] = int(scenario.get("id", 0))
    report["scenario_name"] = str(scenario.get("scenario_name", ""))
    saved_report = _persistence.save_reconciliation_report(report)
    return saved_report


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/macro-estimate", response_model=MacroEstimateResponse)
async def macro_estimate(body: MacroEstimateRequest) -> MacroEstimateResponse:
    if not body.trips:
        raise HTTPException(status_code=400, detail="trips list cannot be empty")

    estimate = _service.macro_estimate(
        trips=[_to_trip(item) for item in body.trips],
        cct_params=body.cct_params.model_dump(exclude_none=True) if body.cct_params else {},
        vsp_params=body.vsp_params.model_dump(exclude_none=True) if body.vsp_params else {},
        optimization_params=body.optimization_params,
    )

    return MacroEstimateResponse(
        status="ok",
        scenario_name=body.scenario_name,
        estimated_vehicles=estimate.estimated_vehicles,
        estimated_crew=estimate.estimated_crew,
        estimated_total_cost=estimate.estimated_total_cost,
        estimated_vehicle_cost=estimate.estimated_vehicle_cost,
        estimated_crew_cost=estimate.estimated_crew_cost,
        notes=estimate.notes,
        assumptions=estimate.assumptions,
    )


@router.post("/what-if", response_model=WhatIfResponse)
async def what_if(body: WhatIfRequest) -> WhatIfResponse:
    if not body.trips:
        raise HTTPException(status_code=400, detail="trips list cannot be empty")
    if not body.scenarios:
        raise HTTPException(status_code=400, detail="scenarios list cannot be empty")

    trips = [_to_trip(item) for item in body.trips]
    scenarios = [
        {
            "name": scenario.name,
            "cct_params": scenario.cct_params.model_dump(exclude_none=True) if scenario.cct_params else {},
            "vsp_params": scenario.vsp_params.model_dump(exclude_none=True) if scenario.vsp_params else {},
            "optimization_params": body.optimization_params.model_dump(exclude_none=True) if body.optimization_params else {},
        }
        for scenario in body.scenarios
    ]

    results = _service.what_if(trips, scenarios)
    return WhatIfResponse(
        status="ok",
        scenarios=[WhatIfScenarioResult(**result) for result in results],
    )


@router.post("/feedback/plan-vs-real", response_model=PlanVsRealResponse)
async def plan_vs_real(body: PlanVsRealRequest) -> PlanVsRealResponse:
    planned = [_to_trip(item) for item in body.planned_trips]
    actual = [item.model_dump(exclude_none=True) for item in body.actual_trips]

    report = _service.plan_vs_real(planned, actual)
    return PlanVsRealResponse(
        status="ok",
        kpis=report.get("kpis", {}),
        alerts=report.get("alerts", []),
        recommendations=report.get("recommendations", []),
    )


@router.post("/scenarios/save", response_model=SaveScenarioResponse)
async def save_scenario(body: SaveScenarioRequest) -> SaveScenarioResponse:
    if not body.trips:
        raise HTTPException(status_code=400, detail="trips list cannot be empty")

    trips = [_to_trip(item) for item in body.trips]
    estimate = _service.macro_estimate(
        trips=trips,
        cct_params=body.cct_params.model_dump(exclude_none=True) if body.cct_params else {},
        vsp_params=body.vsp_params.model_dump(exclude_none=True) if body.vsp_params else {},
        optimization_params=body.optimization_params,
    )

    saved = _persistence.save_scenario(
        {
            "scenario_name": body.scenario_name,
            "trips": [item.model_dump(exclude_none=True) for item in body.trips],
            "cct_params": body.cct_params.model_dump(exclude_none=True) if body.cct_params else {},
            "vsp_params": body.vsp_params.model_dump(exclude_none=True) if body.vsp_params else {},
            "optimization_params": body.optimization_params.model_dump(exclude_none=True) if body.optimization_params else {},
            "estimate": {
                "estimated_vehicles": estimate.estimated_vehicles,
                "estimated_crew": estimate.estimated_crew,
                "estimated_total_cost": estimate.estimated_total_cost,
                "estimated_vehicle_cost": estimate.estimated_vehicle_cost,
                "estimated_crew_cost": estimate.estimated_crew_cost,
                "assumptions": estimate.assumptions,
            },
        }
    )

    estimate_data = saved.get("estimate", {})
    return SaveScenarioResponse(
        status="ok",
        scenario_id=int(saved.get("id", 0)),
        scenario_name=str(saved.get("scenario_name", "")),
        created_at=str(saved.get("created_at", "")),
        estimate=SavedScenarioEstimate(**estimate_data),
    )


@router.get("/scenarios", response_model=ListScenariosResponse)
async def list_scenarios(limit: int = 20) -> ListScenariosResponse:
    items = _persistence.list_scenarios(limit=max(1, min(limit, 200)))
    scenarios = [
        ScenarioListItem(
            id=int(item.get("id", 0)),
            scenario_name=str(item.get("scenario_name", "")),
            created_at=str(item.get("created_at", "")),
            estimated_total_cost=float(item.get("estimate", {}).get("estimated_total_cost", 0.0)),
            estimated_vehicles=int(item.get("estimate", {}).get("estimated_vehicles", 0)),
            estimated_crew=int(item.get("estimate", {}).get("estimated_crew", 0)),
        )
        for item in items
    ]
    return ListScenariosResponse(status="ok", scenarios=scenarios)


@router.post("/feeds/ingest", response_model=IngestFeedResponse)
async def ingest_feed(body: IngestFeedRequest) -> IngestFeedResponse:
    if not body.records:
        raise HTTPException(status_code=400, detail="records list cannot be empty")

    records = [_to_actual_record(item) for item in body.records]
    ingest = _persistence.ingest_feed(records)
    report_id: int | None = None

    if body.auto_reconcile:
        try:
            saved_report = _run_reconciliation_for_scenario(body.scenario_id)
            report_id = int(saved_report.get("id", 0))
        except HTTPException:
            report_id = None

    return IngestFeedResponse(
        status="ok",
        snapshot_id=int(ingest.get("snapshot_id", 0)),
        quality=ingest.get("quality", {}),
        reconciliation_report_id=report_id,
    )


@router.post("/reconciliation/run", response_model=RunReconciliationResponse)
async def run_reconciliation(body: RunReconciliationRequest) -> RunReconciliationResponse:
    saved_report = _run_reconciliation_for_scenario(body.scenario_id)
    return RunReconciliationResponse(
        status="ok",
        report_id=int(saved_report.get("id", 0)),
        report=saved_report.get("report", {}),
    )


@router.get("/reconciliation/reports", response_model=ListReconciliationReportsResponse)
async def list_reconciliation_reports(limit: int = 20) -> ListReconciliationReportsResponse:
    reports = _persistence.list_reconciliation_reports(limit=max(1, min(limit, 200)))
    payload = [
        ReconciliationReportItem(
            id=int(item.get("id", 0)),
            created_at=str(item.get("created_at", "")),
            report=item.get("report", {}),
        )
        for item in reports
    ]
    return ListReconciliationReportsResponse(status="ok", reports=payload)


@router.get("/admin/worker-status", response_model=WorkerStatusResponse)
async def worker_status() -> WorkerStatusResponse:
    return WorkerStatusResponse(status="ok", worker=worker_state.snapshot())


@router.post("/admin/cleanup", response_model=RunRetentionCleanupResponse)
async def run_cleanup(body: RunRetentionCleanupRequest) -> RunRetentionCleanupResponse:
    cleanup_stats = _persistence.prune_data(
        max_scenarios=max(1, int(body.max_scenarios or _settings.strategy_retention_max_scenarios)),
        max_feed_snapshots=max(1, int(body.max_feed_snapshots or _settings.strategy_retention_max_feed_snapshots)),
        max_reports=max(1, int(body.max_reports or _settings.strategy_retention_max_reports)),
        max_age_days=max(0, int(body.max_age_days or _settings.strategy_retention_max_age_days)),
    )
    now = _utc_now_iso()
    worker_state.update(last_cleanup_at=now, last_cleanup_stats=cleanup_stats)
    return RunRetentionCleanupResponse(
        status="ok",
        cleanup_stats=cleanup_stats,
        performed_at=now,
    )
