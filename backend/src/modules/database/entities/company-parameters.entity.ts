import { Entity, Column } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('company_parameters')
export class CompanyParameters extends TenantBaseEntity {

  // ── Custos Operacionais ──
  @Column('float', { default: 0.5 })
  driver_cost_per_minute: number;

  @Column('float', { default: 0.4 })
  collector_cost_per_minute: number;

  @Column('float', { default: 800.0 })
  vehicle_fixed_cost: number;

  @Column('float', { default: 1000.0 })
  cost_vehicle: number;

  @Column('float', { default: 1.0 })
  cost_km: number;

  @Column('float', { default: 500.0 })
  cost_duty: number;

  @Column('float', { default: 500.0 })
  cct_violation_penalty: number;

  // ── Flags de Otimização ──
  @Column('boolean', { default: true })
  force_round_trip: boolean;

  @Column('boolean', { default: false })
  allow_vehicle_swap: boolean;

  // ── Jornada Base ──
  @Column('integer', { default: 480 })
  max_driving_time_minutes: number;

  @Column('integer', { default: 60 })
  meal_break_minutes: number;

  @Column('integer', { default: 720 })
  max_shift_minutes: number;

  // ── CCT Completo (espelha CctParamsInput do Python) ──
  @Column('integer', { nullable: true })
  max_work_minutes: number;

  @Column('integer', { nullable: true })
  min_work_minutes: number;

  @Column('integer', { nullable: true })
  min_shift_minutes: number;

  @Column('integer', { nullable: true })
  overtime_limit_minutes: number;

  @Column('integer', { nullable: true })
  max_driving_minutes: number;

  @Column('integer', { nullable: true })
  min_break_minutes: number;

  @Column('boolean', { default: true })
  enforce_min_interval: boolean;

  @Column('integer', { nullable: true })
  connection_tolerance_minutes: number;

  @Column('integer', { nullable: true })
  mandatory_break_after_minutes: number;

  @Column('integer', { nullable: true })
  split_break_first_minutes: number;

  @Column('integer', { nullable: true })
  split_break_second_minutes: number;

  @Column('integer', { nullable: true })
  inter_shift_rest_minutes: number;

  @Column('integer', { nullable: true })
  weekly_rest_minutes: number;

  @Column('integer', { nullable: true })
  reduced_weekly_rest_minutes: number;

  @Column('boolean', { nullable: true })
  allow_reduced_weekly_rest: boolean;

  @Column('integer', { nullable: true })
  daily_driving_limit_minutes: number;

  @Column('integer', { nullable: true })
  extended_daily_driving_limit_minutes: number;

  @Column('integer', { nullable: true })
  max_extended_driving_days_per_week: number;

  @Column('integer', { nullable: true })
  weekly_driving_limit_minutes: number;

  @Column('integer', { nullable: true })
  fortnight_driving_limit_minutes: number;

  @Column('integer', { nullable: true })
  min_layover_minutes: number;

  @Column('integer', { nullable: true })
  pullout_minutes: number;

  @Column('integer', { nullable: true })
  pullback_minutes: number;

  @Column('boolean', { nullable: true })
  pullout_counts_in_driver_shift: boolean;

  @Column('boolean', { nullable: true })
  pullback_counts_in_driver_shift: boolean;

  @Column('boolean', { nullable: true })
  idle_time_is_paid: boolean;

  @Column('float', { nullable: true })
  waiting_time_pay_pct: number;

  @Column('integer', { nullable: true })
  min_guaranteed_work_minutes: number;

  @Column('integer', { nullable: true })
  max_unpaid_break_minutes: number;

  @Column('integer', { nullable: true })
  max_total_unpaid_break_minutes: number;

  @Column('integer', { nullable: true })
  long_unpaid_break_limit_minutes: number;

  @Column('float', { nullable: true })
  long_unpaid_break_penalty_weight: number;

  @Column('boolean', { default: false })
  allow_relief_points: boolean;

  @Column('boolean', { default: false })
  enforce_same_depot_start_end: boolean;

  @Column('float', { nullable: true })
  fairness_weight: number;

  @Column('integer', { nullable: true })
  fairness_target_work_minutes: number;

  @Column('integer', { nullable: true })
  fairness_tolerance_minutes: number;

  @Column('boolean', { nullable: true })
  operator_change_terminals_only: boolean;

  @Column('boolean', { default: true })
  enforce_trip_groups_hard: boolean;

  @Column('boolean', { default: true })
  operator_pairing_hard: boolean;

  @Column('float', { default: 240.0 })
  trip_group_keep_bonus: number;

  @Column('float', { nullable: true })
  sunday_off_weight: number;

  @Column('float', { nullable: true })
  holiday_extra_pct: number;

  @Column('boolean', { default: false })
  enforce_single_line_duty: boolean;

  @Column('boolean', { default: true })
  operator_single_vehicle_only: boolean;

  @Column('integer', { nullable: true })
  nocturnal_start_hour: number;

  @Column('integer', { nullable: true })
  nocturnal_end_hour: number;

  @Column('float', { nullable: true })
  nocturnal_factor: number;

  @Column('float', { nullable: true })
  nocturnal_extra_pct: number;

  @Column('boolean', { nullable: true })
  apply_cct: boolean;

  @Column('boolean', { nullable: true })
  strict_hard_validation: boolean;

  @Column('boolean', { nullable: true })
  strict_zero_gap_validation: boolean;

  @Column('boolean', { nullable: true })
  strict_operational_mode: boolean;

  @Column('boolean', { nullable: true })
  strict_hard_constraints: boolean;

  @Column('boolean', { nullable: true })
  strict_gps_validation: boolean;

  @Column('boolean', { nullable: true })
  strict_terminal_sync_validation: boolean;

  @Column('boolean', { nullable: true })
  strict_union_rules: boolean;

  @Column({ nullable: true, default: 'strict' })
  group_infeasibility_mode: string;

  @Column({ nullable: true, default: 'balanced' })
  operational_quality_mode: string;

  // ── Terminais ──
  @Column('integer', { array: true, default: '{}' })
  terminal_location_ids: number[];

  // ── Solver — Controle do Motor de Otimização ──
  @Column('float', { nullable: true })
  time_budget_s: number;

  @Column('integer', { nullable: true })
  random_seed: number;

  @Column('integer', { nullable: true })
  max_vehicle_shift_minutes: number;

  @Column('integer', { nullable: true })
  max_vehicles: number;

  @Column('float', { nullable: true })
  deadhead_cost_per_minute: number;

  @Column('float', { nullable: true })
  idle_cost_per_minute: number;

  @Column('boolean', { nullable: true })
  allow_multi_line_block: boolean;

  @Column('boolean', { nullable: true })
  allow_vehicle_split_shifts: boolean;

  @Column('integer', { nullable: true })
  split_shift_min_gap_minutes: number;

  @Column('integer', { nullable: true })
  split_shift_max_gap_minutes: number;

  @Column('integer', { nullable: true })
  max_simultaneous_chargers: number;

  @Column('boolean', { nullable: true })
  enable_column_generation: boolean;

  @Column('boolean', { nullable: true })
  pricing_enabled: boolean;

  @Column('boolean', { nullable: true })
  use_set_covering: boolean;

  @Column('integer', { nullable: true })
  min_workpiece_minutes: number;

  @Column('integer', { nullable: true })
  max_workpiece_minutes: number;

  @Column('integer', { nullable: true })
  min_trips_per_piece: number;

  @Column('integer', { nullable: true })
  max_trips_per_piece: number;

  @Column('float', { nullable: true })
  peak_energy_cost_per_kwh: number;

  @Column('float', { nullable: true })
  offpeak_energy_cost_per_kwh: number;

  @Column('integer', { nullable: true })
  preferred_pair_window_minutes: number;

  @Column('boolean', { nullable: true })
  preserve_preferred_pairs: boolean;

  @Column('float', { nullable: true })
  pair_break_penalty: number;

  @Column('float', { nullable: true })
  paired_trip_bonus: number;

  @Column('float', { nullable: true })
  max_connection_cost_for_reuse_ratio: number;

  @Column('integer', { nullable: true })
  max_candidate_successors_per_task: number;

  @Column('integer', { nullable: true })
  max_generated_columns: number;

  @Column('integer', { nullable: true })
  max_pricing_iterations: number;

  @Column('integer', { nullable: true })
  max_pricing_additions: number;

  // Comportamento do veículo em intervalos longos:
  // 'solver_decides' | 'stay_at_terminal' | 'return_to_garage'
  @Column({ nullable: true, default: 'solver_decides' })
  vehicle_idle_gap_behavior: string;

  // Limite em minutos acima do qual aplica o behavior acima (null = padrão do solver)
  @Column('integer', { nullable: true })
  vehicle_idle_gap_threshold_minutes: number;

  @Column({ default: 'hybrid_pipeline' })
  algorithm_preference: string;

  @Column('integer', { default: 120 })
  ilp_timeout_seconds: number;

  // ── JSON Complexo ──
  @Column('jsonb', { nullable: true })
  goal_weights: Record<string, number>;

  @Column('jsonb', { nullable: true })
  dynamic_rules: any[];
}
