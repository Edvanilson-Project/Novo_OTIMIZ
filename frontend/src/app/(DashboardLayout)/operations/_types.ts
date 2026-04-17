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
  code: string;
  name: string;
  originTerminalId: number;
  destinationTerminalId: number;
  originTerminal?: Terminal;
  destinationTerminal?: Terminal;
  distanceKm?: number;
  returnDistanceKm?: number;
  avgTripDurationMinutes?: number;
  status: 'active' | 'inactive';
  colorHex?: string;
  idleTerminalId?: number;
  idleDistanceKm?: number;
  idleReturnDistanceKm?: number;
  garageTerminalId?: number;
  garageDistanceKm?: number;
  vehicleTypeId?: number;
  operationMode?: 'roundtrip' | 'outbound_only' | 'return_only' | 'flexible';
  createdAt: string;
  updatedAt: string;
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
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

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
  metadata?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
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
  trips: number[] | TripDetail[];
  trip_details?: TripDetail[];
  num_trips?: number;
  start_time?: number;
  end_time?: number;
  spread_minutes?: number;
  idle_minutes?: number;
  total_cost?: number;
  cost?: number;
  idle_cost?: number;
  distance_cost?: number;
  activation_cost?: number;
  connection_cost?: number;
  deadhead_cost?: number;
  meta?: Record<string, any>;
}

export interface OptimizationDuty {
  duty_id: number;
  blocks: number[];
  trip_ids: number[];
  trips?: TripDetail[];
  segments?: OptimizationDutySegment[];
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
  meta?: Record<string, any>;
}

export interface OptimizationDutySegment {
  block_id: number;
  drive_minutes: number;
  trip_ids: number[];
  trips?: TripDetail[];
}

export interface TripDetail {
  id: number;
  trip_id?: number;
  block_id?: number;
  duty_id?: number;
  roster_id?: number;
  operator_id?: number | null;
  operator_name?: string | null;
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
  is_pull_out?: boolean;
  is_pull_back?: boolean;
  is_paired?: boolean;
  direction?: 'outbound' | 'inbound';
  destination_terminal_id?: number | null;
}
