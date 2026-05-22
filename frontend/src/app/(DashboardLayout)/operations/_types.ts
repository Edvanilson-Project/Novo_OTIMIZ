// ═══════════════════════════════════════════════════════════════════
// OTIMIZ — Tipos de domínio compartilhados
// Schema sincronizado com o banco de dados (TypeORM)
// ═══════════════════════════════════════════════════════════════════

export interface Company {
  id: number;
  name: string;
  /** CNPJ é obrigatório no banco (NOT NULL) */
  cnpj: string;
  tradeName?: string;
  status: 'active' | 'inactive';
  address?: string;
  city?: string;
  state?: string;
  phone?: string;
  logoUrl?: string;
  fleetSize?: number;
  dailyTrips?: number;
  createdAt: string;
  updatedAt: string;
}

export interface Terminal {
  id: number;
  /** company_id é NOT NULL no banco */
  companyId: number;
  name: string;
  /** Coluna short_name no banco */
  shortName?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  isGarage: boolean;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Line {
  id: number;
  companyId: number;
  lineId: string;           // código alfanumérico (ex: "101-A")
  name: string;
  description?: string;
  isActive: boolean;

  // Terminais operacionais — IDA; VOLTA inverte origin↔destination
  originTerminalId?: number;
  destinationTerminalId?: number;

  // Distâncias e durações operacionais
  distanceKm?: number;
  returnDistanceKm?: number;
  avgTripDurationMinutes?: number;
  avgReturnDurationMinutes?: number;

  // Garagem / Soltura / Recolhimento
  garageTerminalId?: number;
  garageDistanceKm?: number;      // km garagem → primeiro terminal (soltura)
  solturaMinutes?: number;         // min garagem → primeiro terminal
  recolhimentoDistanceKm?: number; // km último terminal → garagem
  recolhimentoMinutes?: number;    // min último terminal → garagem

  createdAt?: string;
  updatedAt?: string;
}

export interface VehicleType {
  id: number;
  companyId: number;
  name: string;
  /** Código opcional (ex: BUS-STD) */
  code?: string;
  /** Capacidade de passageiros (passenger_capacity) */
  passengerCapacity: number;
  costPerKm: number;
  costPerHour: number;
  fixedCost: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export type UserRole = 'super_admin' | 'company_admin' | 'analyst' | 'operator';
export type UserStatus = 'active' | 'inactive';

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  companyId?: number;
  avatarUrl?: string;
  lastLoginAt?: string;
  createdAt: string;
  updatedAt: string;
}

export type OptimizationStatus =
  | 'processing'
  | 'completed'
  | 'failed';

export type OptimizationAlgorithm =
  | 'full_pipeline'
  | 'hybrid_pipeline'
  | 'greedy'
  | 'vsp_only'
  | 'csp_only'
  | 'genetic'
  | 'simulated_annealing'
  | 'tabu_search'
  | 'set_partitioning'
  | 'joint_solver';

export interface OptimizationRun {
  name?: string;
  id: number;
  lineId?: number | null;
  lineIds?: number[] | null;
  scheduleId?: number | null;
  profileId?: number | null;
  profileName?: string | null;
  line?: Line;
  companyId: number;
  algorithm: OptimizationAlgorithm;
  status: OptimizationStatus;
  operationMode?: 'urban' | 'charter';
  /** total_vehicles no banco */
  totalVehicles?: number;
  /** total_crew no banco */
  totalCrew?: number;
  totalTrips?: number;
  totalCost?: number;
  cctViolations?: number;
  durationMs?: number;
  errorMessage?: string;
  params?: Record<string, unknown>;
  resultSummary?: OptimizationResultSummary | null;
  startedAt?: string;
  finishedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface OptimizationComparisonMetric {
  base: number;
  other: number;
  delta: number;
  pctDelta: number;
}

export interface OptimizationCostBreakdownBucket {
  total?: number;
  activation?: number;
  connection?: number;
  distance?: number;
  time?: number;
  idle_cost?: number;
  work_cost?: number;
  guaranteed_cost?: number;
  waiting_cost?: number;
  overtime_cost?: number;
  long_unpaid_break_penalty?: number;
  nocturnal_extra?: number;
  holiday_extra?: number;
  cct_penalties?: number;
  [key: string]: number | undefined;
}

export interface OptimizationCostBreakdown {
  total?: number;
  vsp?: OptimizationCostBreakdownBucket;
  csp?: OptimizationCostBreakdownBucket;
  [key: string]: unknown;
}

export interface OptimizationStructuredIssue {
  raw?: string;
  code?: string;
  severity?: string;
  phase?: string;
  refs?: string[];
  message?: string;
}

export interface OptimizationPhaseDominantComponent {
  component?: string;
  value?: number;
  share?: number;
}

export interface OptimizationPhaseSummaryBucket {
  vehicles?: number;
  assigned_trips?: number;
  unassigned_trips?: number;
  warnings_count?: number;
  cost?: number;
  duties?: number;
  crew?: number;
  rosters?: number;
  uncovered_blocks?: number;
  cct_violations?: number;
  dominant_cost_component?: OptimizationPhaseDominantComponent;
  [key: string]: unknown;
}

export interface OptimizationPhaseSummary {
  vsp?: OptimizationPhaseSummaryBucket;
  csp?: OptimizationPhaseSummaryBucket;
}

export interface OptimizationTripGroupSplitSample {
  trip_group_id?: number;
  trip_ids?: number[];
  block_ids?: number[];
  duty_ids?: number[];
  roster_ids?: number[];
}

export interface OptimizationTripGroupAudit {
  groups_total?: number;
  groups_fully_assigned?: number;
  same_block_groups?: number;
  same_duty_groups?: number;
  same_roster_groups?: number;
  split_groups?: number;
  missing_groups?: number;
  same_roster_ratio?: number;
  sample_splits?: OptimizationTripGroupSplitSample[];
}

export interface OptimizationReproducibility {
  algorithm?: string;
  random_seed?: number | null;
  randomSeed?: number | null;
  stochastic_algorithm?: boolean;
  stochasticAlgorithm?: boolean | null;
  deterministic_replay_possible?: boolean;
  deterministicReplayPossible?: boolean | null;
  input_hash?: string | null;
  inputHash?: string | null;
  params_hash?: string | null;
  paramsHash?: string | null;
  time_budget_s?: number | null;
  timeBudgetS?: number | null;
  note?: string;
}

export interface OptimizationPerformance {
  phase_timings_ms?: Record<string, number>;
  total_elapsed_ms?: number;
  trip_count?: number;
  vehicle_type_count?: number;
  [key: string]: unknown;
}

export interface OptimizationFailureDiagnostics {
  code?: string;
  userMessage?: string;
  summary?: string;
  hints?: string[];
  currentSettings?: Record<string, unknown>;
  optimizerDiagnostics?: Record<string, unknown> | null;
}

export interface OptimizationSolverExplanation {
  status?: string;
  headline?: string;
  summary?: string[];
  issues?: {
    hard?: OptimizationStructuredIssue[];
    soft?: OptimizationStructuredIssue[];
  };
  recommendations?: string[];
  phase_summary?: OptimizationPhaseSummary;
  trip_group_audit?: OptimizationTripGroupAudit;
}

export interface OptimizationRunAuditResult extends OptimizationResultSummary {
  warningsCount?: number;
  tripDetailsCount?: number;
  solverVersion?: string | null;
  failureDiagnostics?: OptimizationFailureDiagnostics | null;
  optimizerDiagnostics?: Record<string, unknown> | null;
  performance?: OptimizationPerformance | null;
  reproducibility?: OptimizationReproducibility | null;
  phaseSummary?: OptimizationPhaseSummary | null;
  tripGroupAudit?: OptimizationTripGroupAudit | null;
  hardConstraintReport?: Record<string, unknown> | null;
}

export type OperationalQualityMode = 'strict' | 'balanced' | 'optimized';

export interface OperationalQualityScenarioSummary {
  total_cost?: number;
  vehicles?: number;
  duties?: number;
  crew?: number;
  duties_below_25_pct?: number;
  duties_below_30_pct?: number;
  duties_above_12h?: number;
  avg_utilization_pct?: number;
  avg_idle_minutes?: number;
  overtime_minutes?: number;
  critical_count?: number;
  borderline_count?: number;
  acceptable_count?: number;
  hard_violation_count?: number;
  labels?: string[];
}

export interface OperationalQualityScenarioOption {
  scenario_id: string;
  title?: string;
  labels?: string[];
  candidate_note?: string | null;
  summary?: OperationalQualityScenarioSummary | null;
}

export interface OperationalQualityRejectedScenario {
  scenario_id: string;
  title?: string;
  reason?: string;
  summary?: OperationalQualityScenarioSummary | null;
}

export interface OperationalQualityDecision {
  mode?: OperationalQualityMode;
  chosen_scenario?: string;
  chosen_title?: string;
  justification?: string[];
  trade_offs?: string[];
  criteria?: Record<string, string>;
  available_scenarios?: OperationalQualityScenarioOption[];
  rejected_scenarios?: OperationalQualityRejectedScenario[];
  selected_summary?: OperationalQualityScenarioSummary | null;
}

export interface OptimizationResultSummary {
  vehicles?: number;
  num_vehicles?: number;
  crew?: number;
  num_crew?: number;
  total_cost?: number;
  totalCost?: number;
  cct_violations?: number;
  cctViolations?: number;
  total_trips?: number;
  totalTrips?: number;
  unassigned_trips?: number[] | TripDetail[];
  blocks?: OptimizationBlock[];
  duties?: OptimizationDuty[];
  warnings?: string[] | OptimizationStructuredIssue[];
  solver_source?: string;
  vsp_algorithm?: string;
  csp_algorithm?: string;
  elapsed_ms?: number;
  costBreakdown?: OptimizationCostBreakdown | null;
  solverExplanation?: OptimizationSolverExplanation | null;
  /** Insight em linguagem natural gerado pelo AI Copilot (OpenRouter). Null se indisponível. */
  aiCopilotInsight?: string | null;
  /** Snake_case alias vindo direto da API Python (antes da normalização NestJS). */
  ai_copilot_insight?: string | null;
  phaseSummary?: OptimizationPhaseSummary | null;
  tripGroupAudit?: OptimizationTripGroupAudit | null;
  reproducibility?: OptimizationReproducibility | null;
  performance?: OptimizationPerformance | null;
  hardConstraintReport?: Record<string, unknown> | null;
  chosenScenario?: string | null;
  chosen_scenario?: string | null;
  rejectedScenarios?: OperationalQualityRejectedScenario[];
  rejected_scenarios?: OperationalQualityRejectedScenario[];
  justification?: string[];
  tradeOffs?: string[];
  trade_offs?: string[];
  operationalQualityDecision?: OperationalQualityDecision | null;
  operational_quality_decision?: OperationalQualityDecision | null;
  metadata?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  /** Resolved optimizer parameters (snake_case from Python API) */
  resolved_params?: Record<string, unknown>;
  /** Run-level fields present when a full OptimizationRun is passed as this type */
  id?: number;
  scheduleId?: number;
  updatedAt?: string;
  createdAt?: string;
  /** Snake_case wrapper sometimes returned by the API before normalization */
  result?: OptimizationResultSummary;
  /** Nested summary when full run object is passed to components expecting this type */
  resultSummary?: OptimizationResultSummary | null;
  /** Schedule entity fields (status, error info) present when the full entity is used */
  status?: OptimizationStatus;
  error_code?: string;
  error_message?: string;
  hard_constraint_report?: Record<string, unknown> | null;
}

export interface OptimizationParameters {
  dynamic_rules?: unknown[];
  operational_quality_mode?: string;
  algorithm_preference?: string;
  preferred_algorithm?: string;
  min_break_minutes?: number;
  meal_break_minutes?: number;
  min_layover_minutes?: number;
  connection_tolerance_minutes?: number;
  pullout_minutes?: number;
  pullback_minutes?: number;
  [key: string]: unknown;
}

export interface ScheduleValidationIssue {
  detail: string;
  suggestedFix?: string;
}

export interface ScheduleValidationStats {
  totalTrips?: number;
  allocatedTrips?: number;
  totalVehicles?: number;
  totalDuties?: number;
  totalOperatorHours?: number;
  allocationPercentage?: number;
}

export interface ScheduleValidationResult {
  valid: boolean;
  errorCount?: number;
  stats?: ScheduleValidationStats;
  errors?: ScheduleValidationIssue[];
  warnings?: ScheduleValidationIssue[];
}

export interface OptimizationRunComparisonPerformance {
  totalElapsedMs?: OptimizationComparisonMetric;
  tripCount?: OptimizationComparisonMetric;
  vehicleTypeCount?: OptimizationComparisonMetric;
  phaseTimings?: Record<string, OptimizationComparisonMetric>;
}

export interface OptimizationRunComparisonReproducibilitySnapshot {
  algorithm?: string | null;
  randomSeed?: number | null;
  stochasticAlgorithm?: boolean | null;
  deterministicReplayPossible?: boolean | null;
  inputHash?: string | null;
  paramsHash?: string | null;
  timeBudgetS?: number | null;
  note?: string | null;
}

export interface OptimizationRunComparisonReproducibility {
  base?: OptimizationRunComparisonReproducibilitySnapshot | null;
  other?: OptimizationRunComparisonReproducibilitySnapshot | null;
  sameInputHash?: boolean | null;
  sameParamsHash?: boolean | null;
  sameTimeBudget?: boolean | null;
}

export interface OptimizationBlock {
  block_id: number;
  /** camelCase fallback for block_id */
  blockId?: number;
  /** Legacy id alias */
  id?: number;
  trips?: number[] | TripDetail[];
  trip_details?: TripDetail[];
  num_trips?: number;
  start_time?: number;
  /** camelCase fallback for start_time */
  startTime?: number;
  end_time?: number;
  /** camelCase fallback for end_time */
  endTime?: number;
  spread_minutes?: number;
  idle_minutes?: number;
  total_cost?: number;
  cost?: number;
  idle_cost?: number;
  distance_cost?: number;
  activation_cost?: number;
  connection_cost?: number;
  deadhead_cost?: number;
  meta?: Record<string, unknown>;
}



export interface OptimizationDutyTimeSegment {
  type?: string;
  event_type?: string;
  segment_sequence?: number;
  distance_km?: number;
  /** Legacy single-trip id fields (some API responses include these on segments) */
  tripId?: number;
  trip_id?: number;
  event_scope?: string;
  bundle_event_type?: string;
  start?: number;
  end?: number;
  duration?: number;
  duration_minutes?: number;
  event_label?: string;
  is_work_time?: boolean;
  is_driving_time?: boolean;
  is_idle_time?: boolean;
  is_normal_break?: boolean;
  is_mandatory_rest?: boolean;
  is_pullout?: boolean;
  is_pullback?: boolean;
  rest_valid?: boolean;
  rule_code?: string;
  violation_code?: string;
  explanation?: string;
  trip_ids?: number[];
  trip_count?: number;
  trip_group_ids?: number[];
  trip_directions?: string[];
  block_id?: number | string;
  from_block_id?: number | string;
  to_block_id?: number | string;
  from_vehicle_id?: number | string;
  to_vehicle_id?: number | string;
  vehicle_id?: number | string;
  location?: number | string;
  location_start?: number | string;
  location_end?: number | string;
}

export interface OptimizationOperationalTimeReport {
  duty_start?: number;
  duty_end?: number;
  spread_time?: number;
  window_time?: number;
  work_time?: number;
  driving_time?: number;
  idle_time?: number;
  normal_break_time?: number;
  mandatory_rest_time?: number;
  pullout_time?: number;
  pullback_time?: number;
  mandatory_rest?: {
    mandatory_rest_required?: boolean;
    has_valid_mandatory_rest?: boolean;
    violations?: string[];
  };
  operator?: {
    operator_not_assigned?: boolean;
  };
  /** Flat aliases sometimes returned directly by the API (without nesting) */
  violations?: string[];
  operator_not_assigned?: boolean;
  mandatory_rest_required?: boolean;
  has_valid_mandatory_rest?: boolean | null;
  suggestion?: string;
  user_explanation?: string;
}

export interface OptimizationDuty {
  duty_id: number;
  /** Legacy id field used as fallback for duty_id in some API responses */
  id?: number;
  blocks?: number[];
  trip_ids?: number[];
  trips?: TripDetail[];
  segments?: OptimizationDutySegment[];
  duty_time_segments?: OptimizationDutyTimeSegment[];
  detailed_trip_assignments?: TripDetail[];
  operational_time_report?: OptimizationOperationalTimeReport;
  work_time: number;
  spread_time: number;
  start_time: number;
  end_time: number;
  total_cost?: number;
  work_cost?: number;
  overtime_cost?: number;
  overtime_minutes?: number;
  nocturnal_extra_cost?: number;
  guaranteed_cost?: number;
  waiting_cost?: number;
  shift_violations?: number;
  rest_violations?: number;
  cct_penalties_cost?: number;
  warnings?: string[];
  meta?: Record<string, unknown>;
}

export interface OptimizationDutySegment {
  block_id: number;
  drive_minutes: number;
  trip_ids: number[];
  trips?: TripDetail[];
}

export interface TripDetail {
  id: number;
  source_trip_id?: number;
  public_trip_id?: number;
  trip_id?: number;
  block_id?: number;
  vehicle_id?: number;
  duty_id?: number;
  driver_id?: number;
  roster_id?: number;
  operator_id?: number | null;
  operator_name?: string | null;
  sequence_in_duty?: number;
  sequence_in_block?: number;
  segment_sequence?: number | null;
  sequence_in_bundle?: number;
  bundle_trip_count?: number;
  bundle_event_type?: string;
  pair_id?: string | null;
  segment_index?: number;
  segment_count?: number;
  start_time: number;
  end_time: number;
  origin_id?: number | string;
  destination_id?: number | string;
  origin_name?: string;
  destination_name?: string;
  duration?: number;
  line_id?: number | null;
  trip_group_id?: number | null;
  is_pull_out?: boolean;
  is_pull_back?: boolean;
  is_paired?: boolean;
  direction?: 'outbound' | 'inbound';
  destination_terminal_id?: number | null;
  /** camelCase aliases present when trip comes from the hydrated blocks */
  tripId?: number;
  lineId?: number | null;
  lineCode?: string;
  line_code?: string;
  startTime?: number;
  endTime?: number;
  color?: string;
  sentido?: string;
  distance_km?: number;
  [key: string]: unknown;
}
