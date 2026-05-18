import { Injectable, BadRequestException } from '@nestjs/common';
import { TenantContext } from '../../common/context/tenant-context';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { CompanyParametersRepository } from '../database/repositories/company-parameters.repository';
import { normalizeLegacyCompanyParameters } from './parameter-normalization';

@Injectable()
export class ParametersService {
  constructor(
    private readonly parametersRepository: CompanyParametersRepository,
    private readonly tenantContext: TenantContext,
  ) {}

  async getParameters(): Promise<CompanyParameters> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Company ID not found in context');

    const params = await this.parametersRepository.findOne({
      where: { companyId },
    });
    if (!params) {
      // Se não houver, criamos o padrão para o tenant
      return this.createDefaultParameters();
    }

    if (this.applyLegacyPercentageNormalization(params)) {
      return this.parametersRepository.save(params);
    }

    return params;
  }

  async updateParameters(
    updateData: Partial<CompanyParameters>,
  ): Promise<CompanyParameters> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Company ID not found in context');

    let params = await this.parametersRepository.findOne({
      where: { companyId },
    });

    if (!params) {
      params = await this.createDefaultParameters();
    }

    this.applyLegacyPercentageNormalization(params);

    const {
      id: _id,
      companyId: _ignoredCompanyId,
      createdAt: _createdAt,
      updatedAt: _updatedAt,
      ...validData
    } = updateData as any;

    const sanitizedData = this.validateAndSanitizeParameters(validData);

    Object.assign(params, sanitizedData);
    this.validateParameterRanges(params);
    this.validateCrossFieldRelations(params);
    return this.parametersRepository.save(params);
  }

  private applyLegacyPercentageNormalization(
    params: CompanyParameters,
  ): boolean {
    const { normalized, changed } = normalizeLegacyCompanyParameters(params);
    if (changed) {
      Object.assign(params, normalized);
    }
    return changed;
  }

  private validateParameterRanges(params: CompanyParameters) {
    const ranges: Record<string, { min: number; max: number }> = {
      min_break_minutes: { min: 5, max: 60 },
      meal_break_minutes: { min: 15, max: 180 },
      max_shift_minutes: { min: 240, max: 1440 },
      max_driving_time_minutes: { min: 120, max: 960 },
      min_shift_minutes: { min: 60, max: 960 },
      max_work_minutes: { min: 60, max: 960 },
      min_work_minutes: { min: 30, max: 480 },
      mandatory_break_after_minutes: { min: 60, max: 600 },
      min_layover_minutes: { min: 5, max: 120 },
      connection_tolerance_minutes: { min: 0, max: 60 },
      pullout_minutes: { min: 0, max: 120 },
      pullback_minutes: { min: 0, max: 120 },
      inter_shift_rest_minutes: { min: 30, max: 720 },
      weekly_rest_minutes: { min: 480, max: 2880 },
      daily_driving_limit_minutes: { min: 120, max: 600 },
      weekly_driving_limit_minutes: { min: 300, max: 3600 },
      fortnight_driving_limit_minutes: { min: 600, max: 7200 },
      max_driving_minutes: { min: 60, max: 960 },
      min_guaranteed_work_minutes: { min: 60, max: 600 },
      max_unpaid_break_minutes: { min: 5, max: 120 },
      long_unpaid_break_limit_minutes: { min: 30, max: 300 },
      vehicle_idle_gap_threshold_minutes: { min: 0, max: 120 },
      preferred_pair_window_minutes: { min: 0, max: 600 },
      min_workpiece_minutes: { min: 30, max: 480 },
      max_workpiece_minutes: { min: 60, max: 960 },
      min_trips_per_piece: { min: 1, max: 20 },
      max_trips_per_piece: { min: 1, max: 100 },
      ilp_timeout_seconds: { min: 1, max: 3600 },
      max_vehicles: { min: 1, max: 10000 },
      max_extended_driving_days_per_week: { min: 1, max: 7 },
      split_shift_min_gap_minutes: { min: 30, max: 300 },
      split_shift_max_gap_minutes: { min: 60, max: 600 },
      split_break_first_minutes: { min: 5, max: 180 },
      split_break_second_minutes: { min: 5, max: 180 },
    };

    for (const [key, range] of Object.entries(ranges)) {
      const value = (params as any)[key];
      if (value !== null && value !== undefined) {
        if (value < range.min || value > range.max) {
          throw new BadRequestException(
            `${key} deve estar entre ${range.min} e ${range.max}, recebido: ${value}`,
          );
        }
      }
    }
  }

  private validateCrossFieldRelations(params: CompanyParameters) {
    if (
      params.min_shift_minutes !== null &&
      params.max_shift_minutes !== null
    ) {
      if (params.min_shift_minutes > params.max_shift_minutes) {
        throw new BadRequestException(
          'min_shift_minutes nao pode ser maior que max_shift_minutes',
        );
      }
    }

    if (params.min_work_minutes !== null && params.max_work_minutes !== null) {
      if (params.min_work_minutes > params.max_work_minutes) {
        throw new BadRequestException(
          'min_work_minutes nao pode ser maior que max_work_minutes',
        );
      }
    }

    if (
      params.min_trips_per_piece !== null &&
      params.max_trips_per_piece !== null
    ) {
      if (params.min_trips_per_piece > params.max_trips_per_piece) {
        throw new BadRequestException(
          'min_trips_per_piece nao pode ser maior que max_trips_per_piece',
        );
      }
    }

    if (
      params.min_workpiece_minutes !== null &&
      params.max_workpiece_minutes !== null
    ) {
      if (params.min_workpiece_minutes > params.max_workpiece_minutes) {
        throw new BadRequestException(
          'min_workpiece_minutes nao pode ser maior que max_workpiece_minutes',
        );
      }
    }

    if (
      params.split_shift_min_gap_minutes !== null &&
      params.split_shift_max_gap_minutes !== null
    ) {
      if (
        params.split_shift_min_gap_minutes > params.split_shift_max_gap_minutes
      ) {
        throw new BadRequestException(
          'split_shift_min_gap_minutes nao pode ser maior que split_shift_max_gap_minutes',
        );
      }
    }

    if (
      params.nocturnal_start_hour !== null &&
      params.nocturnal_end_hour !== null &&
      params.nocturnal_start_hour === params.nocturnal_end_hour
    ) {
      throw new BadRequestException(
        'nocturnal_start_hour e nocturnal_end_hour nao podem ser iguais',
      );
    }

    if (
      params.max_shift_minutes !== null &&
      params.max_work_minutes !== null &&
      params.meal_break_minutes !== null
    ) {
      if (
        params.max_shift_minutes <
        params.max_work_minutes + params.meal_break_minutes
      ) {
        throw new BadRequestException(
          'max_shift_minutes deve ser maior ou igual a max_work_minutes + meal_break_minutes',
        );
      }
    }
  }

  private async createDefaultParameters(): Promise<CompanyParameters> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Company ID not found in context');

    const newParams = this.parametersRepository.create({
      companyId,
      driver_cost_per_minute: 0.5,
      collector_cost_per_minute: 0.4,
      force_round_trip: true,
      allow_vehicle_swap: false,
      max_driving_time_minutes: 480,
      meal_break_minutes: 60,
      min_break_minutes: 30,
      min_layover_minutes: 30,
      mandatory_break_after_minutes: 270,
      connection_tolerance_minutes: 0,
      pullout_counts_in_driver_shift: true,
      pullback_counts_in_driver_shift: true,
      vehicle_fixed_cost: 800.0,
      enforce_trip_groups_hard: true,
      operator_pairing_hard: true,
      operator_single_vehicle_only: true,
      operator_change_terminals_only: true,
      allow_relief_points: false,
      enforce_same_depot_start_end: false,
      enforce_single_line_duty: false,
      apply_cct: true,
      enforce_min_interval: true,
      strict_hard_validation: true,
      strict_zero_gap_validation: false,
      strict_operational_mode: false,
      strict_hard_constraints: false,
      strict_gps_validation: true,
      strict_terminal_sync_validation: true,
      strict_union_rules: true,
      group_infeasibility_mode: 'strict',
      operational_quality_mode: 'balanced',
      preserve_preferred_pairs: true,
      cct_violation_penalty: 500.0,
      trip_group_keep_bonus: 240.0,
      algorithm_preference: 'hybrid_pipeline',
      ilp_timeout_seconds: 120,
      nocturnal_start_hour: null,
      nocturnal_end_hour: null,
    });

    return this.parametersRepository.save(newParams);
  }

  private validateAndSanitizeParameters(
    data: Partial<CompanyParameters>,
  ): Partial<CompanyParameters> {
    const allowedAlgorithms = [
      'hybrid_pipeline',
      'assignment_vsp',
      'greedy',
      'genetic',
      'tabu_search',
      'simulated_annealing',
      'set_partitioning',
      'mcnf',
      'joint_solver',
      'vcsp_pulp',
    ];

    const allowedIdleGapBehaviors = [
      'solver_decides',
      'stay_at_terminal',
      'return_to_garage',
    ];
    const allowedOperationalQualityModes = ['strict', 'balanced', 'optimized'];

    const integerFields: (keyof CompanyParameters)[] = [
      'max_shift_minutes',
      'min_shift_minutes',
      'min_break_minutes',
      'nocturnal_start_hour',
      'nocturnal_end_hour',
      'max_work_minutes',
      'min_work_minutes',
      'overtime_limit_minutes',
      'max_driving_minutes',
      'meal_break_minutes',
      'max_driving_time_minutes',
      'connection_tolerance_minutes',
      'mandatory_break_after_minutes',
      'split_break_first_minutes',
      'split_break_second_minutes',
      'inter_shift_rest_minutes',
      'weekly_rest_minutes',
      'reduced_weekly_rest_minutes',
      'daily_driving_limit_minutes',
      'extended_daily_driving_limit_minutes',
      'max_extended_driving_days_per_week',
      'weekly_driving_limit_minutes',
      'fortnight_driving_limit_minutes',
      'min_layover_minutes',
      'pullout_minutes',
      'pullback_minutes',
      'min_guaranteed_work_minutes',
      'max_unpaid_break_minutes',
      'max_total_unpaid_break_minutes',
      'long_unpaid_break_limit_minutes',
      'fairness_target_work_minutes',
      'fairness_tolerance_minutes',
      'time_budget_s',
      'random_seed',
      'max_vehicle_shift_minutes',
      'max_vehicles',
      'ilp_timeout_seconds',
      'vehicle_idle_gap_threshold_minutes',
      'preferred_pair_window_minutes',
      'max_candidate_successors_per_task',
      'max_generated_columns',
      'max_pricing_iterations',
      'max_pricing_additions',
      'split_shift_min_gap_minutes',
      'split_shift_max_gap_minutes',
      'max_simultaneous_chargers',
      'min_workpiece_minutes',
      'max_workpiece_minutes',
      'min_trips_per_piece',
      'max_trips_per_piece',
    ];

    const percentageFields: (keyof CompanyParameters)[] = [
      'waiting_time_pay_pct',
      'holiday_extra_pct',
      'nocturnal_extra_pct',
    ];

    const nonNegativeNumberFields: (keyof CompanyParameters)[] = [
      'driver_cost_per_minute',
      'collector_cost_per_minute',
      'vehicle_fixed_cost',
      'cost_vehicle',
      'cost_km',
      'cost_duty',
      'cct_violation_penalty',
      'deadhead_cost_per_minute',
      'idle_cost_per_minute',
      'pair_break_penalty',
      'paired_trip_bonus',
      'trip_group_keep_bonus',
      'sunday_off_weight',
      'fairness_weight',
      'long_unpaid_break_penalty_weight',
      'peak_energy_cost_per_kwh',
      'offpeak_energy_cost_per_kwh',
      'max_connection_cost_for_reuse_ratio',
      'nocturnal_factor',
    ];

    const booleanFields: (keyof CompanyParameters)[] = [
      'force_round_trip',
      'allow_vehicle_swap',
      'enforce_min_interval',
      'allow_reduced_weekly_rest',
      'idle_time_is_paid',
      'pullout_counts_in_driver_shift',
      'pullback_counts_in_driver_shift',
      'allow_relief_points',
      'enforce_same_depot_start_end',
      'operator_change_terminals_only',
      'enforce_trip_groups_hard',
      'operator_pairing_hard',
      'enforce_single_line_duty',
      'operator_single_vehicle_only',
      'apply_cct',
      'strict_hard_validation',
      'strict_zero_gap_validation',
      'strict_operational_mode',
      'strict_hard_constraints',
      'strict_gps_validation',
      'strict_terminal_sync_validation',
      'strict_union_rules',
      'allow_multi_line_block',
      'allow_vehicle_split_shifts',
      'enable_column_generation',
      'pricing_enabled',
      'use_set_covering',
      'preserve_preferred_pairs',
    ];

    const sanitized: Partial<CompanyParameters> = {};

    for (const [key, value] of Object.entries(data)) {
      if (value === null || value === undefined || value === '') {
        (sanitized as any)[key] = null;
        continue;
      }

      if (integerFields.includes(key as keyof CompanyParameters)) {
        const parsed = Number(value);

        if (!Number.isInteger(parsed) || parsed < 0) {
          throw new BadRequestException(
            `${key} deve ser um numero inteiro maior ou igual a zero`,
          );
        }

        if (
          ['nocturnal_start_hour', 'nocturnal_end_hour'].includes(key) &&
          (parsed < 0 || parsed > 23)
        ) {
          throw new BadRequestException(`${key} deve estar entre 0 e 23`);
        }

        (sanitized as any)[key] = parsed;
        continue;
      }

      if (percentageFields.includes(key as keyof CompanyParameters)) {
        const parsed = Number(value);

        if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
          throw new BadRequestException(`${key} deve estar entre 0 e 100`);
        }

        (sanitized as any)[key] = parsed / 100;
        continue;
      }

      if (nonNegativeNumberFields.includes(key as keyof CompanyParameters)) {
        const parsed = Number(value);

        if (!Number.isFinite(parsed) || parsed < 0) {
          throw new BadRequestException(
            `${key} deve ser um numero maior ou igual a zero`,
          );
        }

        (sanitized as any)[key] = parsed;
        continue;
      }

      if (booleanFields.includes(key as keyof CompanyParameters)) {
        if (
          typeof value !== 'boolean' &&
          value !== 'true' &&
          value !== 'false'
        ) {
          throw new BadRequestException(`${key} deve ser um booleano`);
        }
        (sanitized as any)[key] = value === true || value === 'true';
        continue;
      }

      if (key === 'algorithm_preference') {
        // eslint-disable-next-line @typescript-eslint/no-base-to-string
        if (!allowedAlgorithms.includes(String(value))) {
          throw new BadRequestException(`algorithm_preference invalido`);
        }
        // eslint-disable-next-line @typescript-eslint/no-base-to-string
        (sanitized as any)[key] = String(value);
        continue;
      }

      if (key === 'vehicle_idle_gap_behavior') {
        // eslint-disable-next-line @typescript-eslint/no-base-to-string
        if (!allowedIdleGapBehaviors.includes(String(value))) {
          throw new BadRequestException(`vehicle_idle_gap_behavior invalido`);
        }
        // eslint-disable-next-line @typescript-eslint/no-base-to-string
        (sanitized as any)[key] = String(value);
        continue;
      }

      if (key === 'group_infeasibility_mode') {
        // eslint-disable-next-line @typescript-eslint/no-base-to-string
        const normalized = String(value).trim().toLowerCase();
        if (!['strict', 'production', 'assisted'].includes(normalized)) {
          throw new BadRequestException(`group_infeasibility_mode invalido`);
        }

        (sanitized as any)[key] = normalized;
        continue;
      }

      if (key === 'operational_quality_mode') {
        // eslint-disable-next-line @typescript-eslint/no-base-to-string
        const normalized = String(value).trim().toLowerCase();
        if (!allowedOperationalQualityModes.includes(normalized)) {
          throw new BadRequestException(`operational_quality_mode invalido`);
        }

        (sanitized as any)[key] = normalized;
        continue;
      }

      if (key === 'terminal_location_ids') {
        if (!Array.isArray(value)) {
          throw new BadRequestException(
            `terminal_location_ids deve ser uma lista`,
          );
        }

        const ids = value.map(Number);

        if (ids.some((id) => !Number.isInteger(id) || id <= 0)) {
          throw new BadRequestException(
            `terminal_location_ids contem IDs invalidos`,
          );
        }

        (sanitized as any)[key] = ids;
        continue;
      }

      if (key === 'goal_weights') {
        if (typeof value !== 'object' || Array.isArray(value)) {
          throw new BadRequestException(`goal_weights deve ser um objeto JSON`);
        }

        for (const [goalKey, goalValue] of Object.entries(
          value as Record<string, any>,
        )) {
          const parsed = Number(goalValue);

          if (!Number.isFinite(parsed) || parsed < 0) {
            throw new BadRequestException(
              `Peso invalido em goal_weights.${goalKey}`,
            );
          }
        }

        (sanitized as any)[key] = value;
        continue;
      }

      if (key === 'dynamic_rules') {
        if (!Array.isArray(value)) {
          throw new BadRequestException(`dynamic_rules deve ser uma lista`);
        }

        (sanitized as any)[key] = value;
        continue;
      }

      throw new BadRequestException(
        `Parametro nao permitido ou sem validacao: ${key}`,
      );
    }

    return sanitized;
  }
}
