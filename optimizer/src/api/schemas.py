"""
Schemas Pydantic para a API REST do OTIMIZ Optimizer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from ..domain.models import AlgorithmType

class OptimizationParametersDTO(BaseModel):
    driver_cost_per_minute: float = Field(0.0, description="Custo do motorista por minuto")
    collector_cost_per_minute: float = Field(0.0, description="Custo do coletor por minuto")
    force_round_trip: bool = Field(True, description="Forçar viagem de ida e volta")
    allow_vehicle_swap: bool = Field(True, description="Permitir troca de veículo")
    max_driving_time_minutes: int = Field(480, description="Tempo máximo de direção em minutos")
    meal_break_minutes: int = Field(60, description="Tempo de intervalo de refeição em minutos")
    vehicle_fixed_cost: float = Field(800.0, description="Custo fixo por veículo ativado")
    terminal_location_ids: List[int] = Field(default_factory=list, description="IDs dos locais que são terminais válidos para rendição")
    
    # Novos pesos de custo
    cost_vehicle: float = Field(1000.0, description="Peso para redução da frota")
    cost_km: float = Field(1.0, description="Custo por KM para redução de quilometragem morta")
    cost_duty: float = Field(500.0, description="Custo por jornada para redução do número de motoristas")


class TripInput(BaseModel):
    id: int
    line_id: int
    trip_group_id: Optional[int] = None
    direction: Optional[str] = None
    start_time: int = Field(..., description="Minutos desde meia-noite")
    end_time: int
    origin_id: int
    destination_id: int
    duration: int = 0
    distance_km: float = 0.0
    depot_id: Optional[int] = None
    relief_point_id: Optional[int] = None
    is_relief_point: bool = False
    mid_trip_relief_point_id: Optional[int] = None
    mid_trip_relief_offset_minutes: Optional[int] = None
    mid_trip_relief_distance_ratio: Optional[float] = None
    mid_trip_relief_elevation_ratio: Optional[float] = None
    energy_kwh: float = 0.0
    elevation_gain_m: float = 0.0
    service_day: Optional[int] = None
    is_holiday: bool = False
    origin_latitude: Optional[float] = None
    origin_longitude: Optional[float] = None
    destination_latitude: Optional[float] = None
    destination_longitude: Optional[float] = None
    sent_to_driver_terminal: Optional[bool] = None
    gps_valid: Optional[bool] = None
    deadhead_times: Dict[int, int] = Field(default_factory=dict)
    idle_before_minutes: int = 0
    idle_after_minutes: int = 0
    is_pull_out: bool = False
    is_pull_back: bool = False

    @model_validator(mode="after")
    def validate_mid_trip_relief(self) -> "TripInput":
        has_point = self.mid_trip_relief_point_id is not None
        has_offset = self.mid_trip_relief_offset_minutes is not None
        if has_point != has_offset:
            raise ValueError("mid_trip_relief_point_id e mid_trip_relief_offset_minutes devem ser informados juntos")
        if not has_point:
            return self

        split_offset = int(self.mid_trip_relief_offset_minutes or 0)
        trip_duration = int(self.duration or max(0, self.end_time - self.start_time))
        if split_offset <= 0:
            raise ValueError("mid_trip_relief_offset_minutes deve ser maior que zero")
        if trip_duration > 0 and split_offset >= trip_duration:
            raise ValueError("mid_trip_relief_offset_minutes deve cair dentro da viagem")
        if int(self.mid_trip_relief_point_id or 0) in {int(self.origin_id), int(self.destination_id)}:
            raise ValueError("mid_trip_relief_point_id deve representar um ponto intermediario, nao a origem/destino")
        if self.mid_trip_relief_distance_ratio is not None and not (0.0 < float(self.mid_trip_relief_distance_ratio) < 1.0):
            raise ValueError("mid_trip_relief_distance_ratio deve estar entre 0 e 1")
        if self.mid_trip_relief_elevation_ratio is not None and not (0.0 < float(self.mid_trip_relief_elevation_ratio) < 1.0):
            raise ValueError("mid_trip_relief_elevation_ratio deve estar entre 0 e 1")
        return self


class OperatorProfileInput(BaseModel):
    id: str
    name: str
    cp: str
    last_shift_end: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VehicleTypeInput(BaseModel):
    id: int
    name: str
    passenger_capacity: int = 40
    cost_per_km: float = 0.0
    cost_per_hour: float = 0.0
    fixed_cost: float = 800.0
    is_electric: bool = False
    battery_capacity_kwh: float = 0.0
    minimum_soc: float = 0.15
    charge_rate_kw: float = 0.0
    energy_cost_per_kwh: float = 0.0
    depot_id: Optional[int] = None


class CctParamsInput(BaseModel):
    max_shift_minutes: Optional[int] = None
    max_work_minutes: Optional[int] = None
    min_work_minutes: Optional[int] = None
    min_shift_minutes: Optional[int] = None
    overtime_limit_minutes: Optional[int] = None
    max_driving_minutes: Optional[int] = None
    min_break_minutes: Optional[int] = None
    connection_tolerance_minutes: Optional[int] = None
    mandatory_break_after_minutes: Optional[int] = None
    split_break_first_minutes: Optional[int] = None
    split_break_second_minutes: Optional[int] = None
    meal_break_minutes: Optional[int] = None
    inter_shift_rest_minutes: Optional[int] = None
    weekly_rest_minutes: Optional[int] = None
    reduced_weekly_rest_minutes: Optional[int] = None
    allow_reduced_weekly_rest: Optional[bool] = None
    daily_driving_limit_minutes: Optional[int] = None
    extended_daily_driving_limit_minutes: Optional[int] = None
    max_extended_driving_days_per_week: Optional[int] = None
    weekly_driving_limit_minutes: Optional[int] = None
    fortnight_driving_limit_minutes: Optional[int] = None
    min_layover_minutes: Optional[int] = None
    pullout_minutes: Optional[int] = None
    pullback_minutes: Optional[int] = None
    idle_time_is_paid: Optional[bool] = None
    waiting_time_pay_pct: Optional[float] = None
    min_guaranteed_work_minutes: Optional[int] = None
    max_unpaid_break_minutes: Optional[int] = None
    max_total_unpaid_break_minutes: Optional[int] = None
    long_unpaid_break_limit_minutes: Optional[int] = None
    long_unpaid_break_penalty_weight: Optional[float] = None
    allow_relief_points: Optional[bool] = None
    enforce_same_depot_start_end: Optional[bool] = None
    fairness_weight: Optional[float] = None
    fairness_target_work_minutes: Optional[int] = None
    fairness_tolerance_minutes: Optional[int] = None
    operator_change_terminals_only: Optional[bool] = None
    enforce_trip_groups_hard: Optional[bool] = None
    operator_pairing_hard: Optional[bool] = None
    sunday_off_weight: Optional[float] = None
    holiday_extra_pct: Optional[float] = None
    enforce_single_line_duty: Optional[bool] = None
    operator_single_vehicle_only: Optional[bool] = None
    nocturnal_start_hour: Optional[int] = None
    nocturnal_end_hour: Optional[int] = None
    nocturnal_factor: Optional[float] = None
    nocturnal_extra_pct: Optional[float] = None
    goal_weights: Optional[Dict[str, float]] = None
    mandatory_trip_groups_same_duty: Optional[List[List[int]]] = None
    strict_hard_validation: Optional[bool] = None
    strict_gps_validation: Optional[bool] = None
    strict_terminal_sync_validation: Optional[bool] = None
    strict_union_rules: Optional[bool] = None
    terminal_location_ids: Optional[List[int]] = None
    operator_profiles: List[OperatorProfileInput] = Field(default_factory=list)
    natural_language_rules: List[str] = Field(default_factory=list)
    apply_cct: Optional[bool] = None
    dynamic_rules: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Regras dinâmicas de custo no formato JSON Logic. "
            "Aplicadas como modificadores APÓS o cálculo base do CostEvaluator. "
            "Ex: {\"condition\": {\"field\": \"is_holiday\", \"op\": \"==\", \"value\": true}, "
            "\"action\": {\"target\": \"overtime_cost\", \"type\": \"multiply\", \"value\": 1.5}}"
        ),
    )


class VspParamsInput(BaseModel):
    time_budget_s: Optional[float] = None
    random_seed: Optional[int] = None
    max_vehicle_shift_minutes: Optional[int] = None
    max_vehicles: Optional[int] = None
    maxVehicles: Optional[int] = None
    min_layover_minutes: Optional[int] = None
    fixed_vehicle_activation_cost: Optional[float] = None
    deadhead_cost_per_minute: Optional[float] = None
    idle_cost_per_minute: Optional[float] = None
    same_depot_required: Optional[bool] = None
    allow_multi_line_block: Optional[bool] = None
    allow_vehicle_split_shifts: Optional[bool] = None
    split_shift_min_gap_minutes: Optional[int] = None
    split_shift_max_gap_minutes: Optional[int] = None
    max_simultaneous_chargers: Optional[int] = None
    enable_column_generation: Optional[bool] = None
    pricing_enabled: Optional[bool] = None
    use_set_covering: Optional[bool] = None
    min_workpiece_minutes: Optional[int] = None
    max_workpiece_minutes: Optional[int] = None
    min_trips_per_piece: Optional[int] = None
    max_trips_per_piece: Optional[int] = None
    peak_energy_cost_per_kwh: Optional[float] = None
    offpeak_energy_cost_per_kwh: Optional[float] = None
    preserve_preferred_pairs: Optional[bool] = None
    preferred_pair_window_minutes: Optional[int] = None
    pair_break_penalty: Optional[float] = None
    paired_trip_bonus: Optional[float] = None
    max_connection_cost_for_reuse_ratio: Optional[float] = None
    max_candidate_successors_per_task: Optional[int] = None
    max_generated_columns: Optional[int] = None
    max_pricing_iterations: Optional[int] = None
    max_pricing_additions: Optional[int] = None
    strict_hard_validation: Optional[bool] = None
    goal_weights: Dict[str, float] = Field(default_factory=dict)
    natural_language_rules: List[str] = Field(default_factory=list)


class OptimizeRequest(BaseModel):
    trips: List[TripInput]
    vehicle_types: List[VehicleTypeInput] = Field(default_factory=list)
    algorithm: AlgorithmType = AlgorithmType.HYBRID_PIPELINE
    depot_id: Optional[int] = None
    time_budget_s: Optional[float] = None
    line_id: Optional[int] = None
    company_id: Optional[int] = None
    run_id: Optional[int] = None
    cct_params: Optional[CctParamsInput] = None
    vsp_params: Optional[VspParamsInput] = None
    optimization_params: Optional[OptimizationParametersDTO] = None


class BlockOutput(BaseModel):
    block_id: int
    trips: List[int]
    num_trips: int
    start_time: int
    end_time: int
    activation_cost: float = 0.0
    connection_cost: float = 0.0
    distance_cost: float = 0.0
    time_cost: float = 0.0
    idle_cost: float = 0.0
    total_cost: float = 0.0
    warnings: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class DutyOutput(BaseModel):
    duty_id: int
    blocks: List[int]
    trip_ids: List[int] = Field(default_factory=list)
    trips: List[Any] = Field(default_factory=list)
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    work_time: int
    spread_time: int
    rest_violations: int
    warnings: List[str] = Field(default_factory=list)
    paid_minutes: int = 0
    overtime_minutes: int = 0
    nocturnal_minutes: int = 0
    work_cost: float = 0.0
    guaranteed_cost: float = 0.0
    waiting_cost: float = 0.0
    overtime_cost: float = 0.0
    long_unpaid_break_penalty: float = 0.0
    nocturnal_extra_cost: float = 0.0
    holiday_extra_cost: float = 0.0
    cct_penalties_cost: float = 0.0
    total_cost: float = 0.0
    meta: Dict[str, Any] = Field(default_factory=dict)


class OptimizeResponse(BaseModel):
    status: str = "ok"
    vehicles: int
    crew: int
    total_trips: int = 0
    total_cost: float
    cct_violations: int
    unassigned_trips: int
    uncovered_blocks: int
    vsp_algorithm: str
    csp_algorithm: str
    elapsed_ms: float
    blocks: List[BlockOutput]
    duties: List[DutyOutput]
    warnings: List[str] = Field(default_factory=list)
    cost_breakdown: Dict[str, Any] = Field(default_factory=dict)
    solver_explanation: Dict[str, Any] = Field(default_factory=dict)
    phase_summary: Dict[str, Any] = Field(default_factory=dict)
    trip_group_audit: Dict[str, Any] = Field(default_factory=dict)
    reproducibility: Dict[str, Any] = Field(default_factory=dict)
    performance: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    algorithms: List[str] = Field(default_factory=lambda: [a.value for a in AlgorithmType])


class ErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class TaskSubmittedResponse(BaseModel):
    """Resposta imediata do POST /optimize/ após enfileirar no Celery."""
    status: str = "processing"
    task_id: str


class TaskStatusResponse(BaseModel):
    """Resposta do polling GET /optimize/status/{task_id}."""
    status: str  # "processing" | "completed" | "failed"
    task_id: str
    result: Optional[OptimizeResponse] = None
    error: Optional[Dict[str, Any]] = None


class MacroEstimateRequest(BaseModel):
    trips: List[TripInput]
    cct_params: Optional[CctParamsInput] = None
    vsp_params: Optional[VspParamsInput] = None
    optimization_params: Optional[OptimizationParametersDTO] = None
    scenario_name: Optional[str] = None


class MacroEstimateResponse(BaseModel):
    status: str = "ok"
    scenario_name: Optional[str] = None
    estimated_vehicles: int
    estimated_crew: int
    estimated_total_cost: float
    estimated_vehicle_cost: float
    estimated_crew_cost: float
    notes: List[str] = Field(default_factory=list)
    assumptions: Dict[str, Any] = Field(default_factory=dict)


class WhatIfScenarioInput(BaseModel):
    name: str
    cct_params: Optional[CctParamsInput] = None
    vsp_params: Optional[VspParamsInput] = None


class WhatIfRequest(BaseModel):
    trips: List[TripInput]
    scenarios: List[WhatIfScenarioInput]
    optimization_params: Optional[OptimizationParametersDTO] = None


class WhatIfScenarioResult(BaseModel):
    name: str
    estimated_vehicles: int
    estimated_crew: int
    estimated_total_cost: float
    estimated_vehicle_cost: float
    estimated_crew_cost: float
    assumptions: Dict[str, Any] = Field(default_factory=dict)


class WhatIfResponse(BaseModel):
    status: str = "ok"
    scenarios: List[WhatIfScenarioResult] = Field(default_factory=list)


class ActualTripInput(BaseModel):
    trip_id: int
    actual_start_time: Optional[int] = None
    actual_end_time: Optional[int] = None
    vehicle_id: Optional[int] = None
    gps_valid: Optional[bool] = None
    sent_to_driver_terminal: Optional[bool] = None


class PlanVsRealRequest(BaseModel):
    planned_trips: List[TripInput]
    actual_trips: List[ActualTripInput]


class PlanVsRealResponse(BaseModel):
    status: str = "ok"
    kpis: Dict[str, Any] = Field(default_factory=dict)
    alerts: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class SaveScenarioRequest(BaseModel):
    scenario_name: str
    trips: List[TripInput]
    cct_params: Optional[CctParamsInput] = None
    vsp_params: Optional[VspParamsInput] = None


class SavedScenarioEstimate(BaseModel):
    estimated_vehicles: int
    estimated_crew: int
    estimated_total_cost: float
    estimated_vehicle_cost: float
    estimated_crew_cost: float
    assumptions: Dict[str, Any] = Field(default_factory=dict)


class SaveScenarioResponse(BaseModel):
    status: str = "ok"
    scenario_id: int
    scenario_name: str
    created_at: str
    estimate: SavedScenarioEstimate


class ScenarioListItem(BaseModel):
    id: int
    scenario_name: str
    created_at: str
    estimated_total_cost: float
    estimated_vehicles: int
    estimated_crew: int


class ListScenariosResponse(BaseModel):
    status: str = "ok"
    scenarios: List[ScenarioListItem] = Field(default_factory=list)


class FeedRecordInput(BaseModel):
    trip_id: int
    actual_start_time: Optional[int] = None
    actual_end_time: Optional[int] = None
    vehicle_id: Optional[int] = None
    gps_valid: Optional[bool] = None
    sent_to_driver_terminal: Optional[bool] = None
    source: str = "avl"


class IngestFeedRequest(BaseModel):
    records: List[FeedRecordInput]
    auto_reconcile: bool = True
    scenario_id: Optional[int] = None


class IngestFeedResponse(BaseModel):
    status: str = "ok"
    snapshot_id: int
    quality: Dict[str, Any] = Field(default_factory=dict)
    reconciliation_report_id: Optional[int] = None


class RunReconciliationRequest(BaseModel):
    scenario_id: Optional[int] = None


class RunReconciliationResponse(BaseModel):
    status: str = "ok"
    report_id: int
    report: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationReportItem(BaseModel):
    id: int
    created_at: str
    report: Dict[str, Any] = Field(default_factory=dict)


class ListReconciliationReportsResponse(BaseModel):
    status: str = "ok"
    reports: List[ReconciliationReportItem] = Field(default_factory=list)


class RunRetentionCleanupRequest(BaseModel):
    max_scenarios: Optional[int] = None
    max_feed_snapshots: Optional[int] = None
    max_reports: Optional[int] = None
    max_age_days: Optional[int] = None


class RunRetentionCleanupResponse(BaseModel):
    status: str = "ok"
    cleanup_stats: Dict[str, int] = Field(default_factory=dict)
    performed_at: str


class WorkerStatusResponse(BaseModel):
    status: str = "ok"
    worker: Dict[str, Any] = Field(default_factory=dict)


class RosteringRuleInput(BaseModel):
    rule_id: str
    type: str  # "HARD" | "SOFT"
    weight: float = 0.0
    meta: Dict[str, Any] = Field(default_factory=dict)


class NominalRosteringRequest(BaseModel):
    duties: List[DutyOutput]
    operators: List[OperatorProfileInput]
    rules: List[RosteringRuleInput]
    inter_shift_rest_minutes: int = 660


class AssignmentOutput(BaseModel):
    operator_id: str
    operator_name: str
    duty_id: int
    score: float
    explanations: List[str]


class NominalRosteringResponse(BaseModel):
    status: str = "ok"
    assignments: List[AssignmentOutput]
    unassigned_duties: List[int]
    total_utility: float
    elapsed_ms: float
    logs: List[str]
