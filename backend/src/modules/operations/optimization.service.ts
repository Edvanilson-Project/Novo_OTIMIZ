import {
  BadRequestException,
  ConflictException,
  Injectable,
  InternalServerErrorException,
  Logger,
  NotFoundException,
  OnModuleInit,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { InjectRepository } from '@nestjs/typeorm';
import axios from 'axios';
import * as crypto from 'crypto';
import { DataSource, In, Repository } from 'typeorm';
import { TenantContext } from '../../common/context/tenant-context';
import { RequestContext } from '../../common/context/request-context';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { Driver } from '../database/entities/driver.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
import {
  OptimizationRun,
  OptimizationRunStatus,
} from '../database/entities/optimization-run.entity';
import { Schedule, ScheduleStatus } from '../database/entities/schedule.entity';
import { Trip } from '../database/entities/trip.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { Vehicle } from '../database/entities/vehicle.entity';
import { normalizeLegacyCompanyParameters } from '../parameters/parameter-normalization';
import { OptimizationGateway } from './optimization.gateway';
import {
  DEFAULT_VEHICLE_FIXED_COST,
  DEFAULT_COST_VEHICLE,
  DEFAULT_COST_KM,
  DEFAULT_COST_DUTY,
  DEFAULT_CCT_VIOLATION_PENALTY,
  DEFAULT_ILP_TIMEOUT_SECONDS,
  SCHEDULE_CACHE_TTL_MS,
  REPORT_DETAIL_LIMIT,
} from '../../constants/optimization-defaults';

@Injectable()
export class OptimizationService implements OnModuleInit {
  private readonly logger = new Logger(OptimizationService.name);
  private scheduleCache = new Map<number, { data: any; timestamp: number }>();
  private readonly CACHE_TTL_MS = SCHEDULE_CACHE_TTL_MS;
  private readonly OPTIMIZER_URL =
    process.env.OPTIMIZER_URL || 'http://localhost:8000';
  private readonly INTERNAL_KEY: string;
  private readonly DETAIL_LIMIT = REPORT_DETAIL_LIMIT;

  constructor(
    @InjectRepository(Trip) private tripRepo: Repository<Trip>,
    @InjectRepository(Driver) private driverRepo: Repository<Driver>,
    @InjectRepository(CompanyParameters)
    private paramRepo: Repository<CompanyParameters>,
    @InjectRepository(Schedule) private scheduleRepo: Repository<Schedule>,
    @InjectRepository(VehicleType)
    private vehicleTypeRepo: Repository<VehicleType>,
    @InjectRepository(Vehicle) private vehicleRepo: Repository<Vehicle>,
    @InjectRepository(OptimizationRun)
    private optimizationRunRepo: Repository<OptimizationRun>,
    private dataSource: DataSource,
    private gateway: OptimizationGateway,
    private configService: ConfigService,
    private tenantContext: TenantContext,
  ) {
    const key = this.configService.get<string>('INTERNAL_OPTIMIZER_KEY');
    this.assertValidInternalKey(key);
    this.INTERNAL_KEY = key as string;
  }

  /**
   * Valida que INTERNAL_OPTIMIZER_KEY tem entropia mínima para uso em produção.
   * Mensagem inclui comando para gerar chave válida.
   *
   * Referências:
   *   - OWASP API Security Top 10 (2023): API4 — Unrestricted Resource Consumption
   *   - NIST SP 800-63B §5.1.1.2: minimum 32 bits entropy for secret tokens
   */
  private assertValidInternalKey(key: string | undefined): void {
    const KNOWN_DEFAULTS = new Set([
      'internal-key-123456',
      'change-me',
      'changeme',
      'default',
      'secret',
      'password',
    ]);
    const MIN_LENGTH = 32; // ~190 bits para base62

    if (!key) {
      throw new Error(
        'INTERNAL_OPTIMIZER_KEY não definido. Gere uma chave forte com: ' +
          'openssl rand -base64 48 | tr -d "\\n=+/" | cut -c-48',
      );
    }
    if (KNOWN_DEFAULTS.has(key.toLowerCase())) {
      throw new Error(
        `INTERNAL_OPTIMIZER_KEY usa valor padrão conhecido ("${key}"). ` +
          'Gere uma chave forte com: openssl rand -base64 48 | tr -d "\\n=+/" | cut -c-48',
      );
    }
    if (key.length < MIN_LENGTH) {
      throw new Error(
        `INTERNAL_OPTIMIZER_KEY muito curta (${key.length} chars, mínimo ${MIN_LENGTH}). ` +
          'Gere uma chave forte com: openssl rand -base64 48 | tr -d "\\n=+/" | cut -c-48',
      );
    }
    // Heurística simples de entropia: número de caracteres únicos
    const uniqueChars = new Set(key).size;
    if (uniqueChars < 16) {
      throw new Error(
        `INTERNAL_OPTIMIZER_KEY com baixa entropia (${uniqueChars} chars únicos < 16). ` +
          'Gere uma chave forte com: openssl rand -base64 48 | tr -d "\\n=+/" | cut -c-48',
      );
    }
  }

  /**
   * Build axios headers with internal key and correlation ID for tracing.
   * RequestContext stores the correlation ID from the incoming request's RequestLoggingInterceptor.
   */
  private getOptimizerHeaders(additionalHeaders?: Record<string, string>) {
    const { requestId } = RequestContext.get();
    return {
      'X-Internal-Key': this.INTERNAL_KEY,
      ...(requestId && { 'X-Correlation-ID': requestId }),
      ...additionalHeaders,
    };
  }

  async onModuleInit() {
    if (!process.env.OPTIMIZER_URL) {
      const fallbackMsg = `OPTIMIZER_URL não definido em env — usando fallback ${this.OPTIMIZER_URL}`;
      if (process.env.NODE_ENV === 'production') {
        this.logger.error(
          fallbackMsg +
            '. Em produção isso é incorreto e otimizações podem falhar silenciosamente.',
        );
      } else {
        this.logger.warn(fallbackMsg);
      }
    }

    const stale = await this.scheduleRepo.update(
      { status: ScheduleStatus.PROCESSING },
      {
        status: ScheduleStatus.FAILED,
        metadata: {
          status: 'failed',
          error_type: 'system',
          error_code: 'BACKEND_RESTART_STALE_PROCESSING',
          error_message:
            'Schedule estava em processamento quando o backend iniciou.',
          failed_at: new Date().toISOString(),
        } as any,
      },
    );
    if (stale.affected && stale.affected > 0) {
      this.logger.warn(
        `Cleared ${stale.affected} stale PROCESSING lock(s) on startup`,
      );
    }

    // Polling fire-and-forget é perdido em restart do backend → OptimizationRun
    // fica em RUNNING para sempre. Reconcilia o mesmo critério aplicado a schedules.
    const staleRuns = await this.optimizationRunRepo.update(
      { status: OptimizationRunStatus.RUNNING },
      {
        status: OptimizationRunStatus.FAILED,
        errorMessage:
          'OptimizationRun estava em RUNNING quando o backend iniciou (polling perdido).',
        completedAt: new Date(),
      },
    );
    if (staleRuns.affected && staleRuns.affected > 0) {
      this.logger.warn(
        `Cleared ${staleRuns.affected} stale RUNNING OptimizationRun(s) on startup`,
      );
    }
  }

  async runOptimization(
    companyId: number,
    algorithm?: string,
    operationalQualityMode?: string,
    options?: {
      scenarioId?: string;
      baselineScheduleId?: number | null;
      optimizationParamsOverride?: Record<string, any>;
      vspParamsOverride?: Record<string, any>;
      cctParamsOverride?: Record<string, any>;
      skipTenantLock?: boolean;
      depotIds?: number[];
    },
  ) {
    // 0. Tenant Lock: Verificar se já existe uma otimização em andamento.
    // Cenários paralelos (FASE 3) podem opt-out via skipTenantLock para enfileirar
    // várias runs ao mesmo tempo — a fila Celery serializa execução.
    if (!options?.skipTenantLock) {
      const activeSchedule = await this.scheduleRepo.findOne({
        where: { companyId, status: ScheduleStatus.PROCESSING },
        order: { createdAt: 'DESC' },
      });

      if (activeSchedule) {
        const oneHourAgo = new Date();
        oneHourAgo.setHours(oneHourAgo.getHours() - 1);

        if (activeSchedule.createdAt > oneHourAgo) {
          throw new ConflictException(
            'Otimização já em andamento para sua empresa. Por favor, aguarde a conclusão do processo atual.',
          );
        }
        this.logger.warn(
          `Schedule ${activeSchedule.id} preso em PROCESSING desde ${String(activeSchedule.createdAt)}. Ignorando trava por timeout (1h).`,
        );
      }
    }

    // 1. Criar registro inicial do Schedule
    const schedule = await this.scheduleRepo.save({
      companyId,
      status: ScheduleStatus.PROCESSING,
    });

    try {
      // 2. Coletar Dados para o Solver
      const [trips, _drivers, params, vehicleTypes, _vehicles] =
        await Promise.all([
          this.tripRepo.find({
            where: { companyId },
            order: { startTime: 'ASC', tripId: 'ASC', id: 'ASC' },
          }),
          this.driverRepo.find({ where: { companyId } }),
          this.paramRepo.findOne({ where: { companyId } }),
          this.vehicleTypeRepo.find({ where: { companyId } }),
          this.vehicleRepo.find({ where: { companyId }, relations: ['type'] }),
        ]);

      if (!trips.length)
        throw new Error('Nenhuma viagem encontrada para otimização.');

      const cctParams = {
        ...this.buildCctParams(params),
        ...(options?.cctParamsOverride || {}),
      };
      const vspParams = {
        ...this.buildVspParams(params, cctParams),
        ...(options?.vspParamsOverride || {}),
      };
      const forceRoundTrip =
        Boolean(params?.force_round_trip) ||
        Boolean(cctParams.enforce_trip_groups_hard) ||
        Boolean(cctParams.operator_pairing_hard);
      const allowVehicleSwap = cctParams.operator_single_vehicle_only
        ? false
        : (params?.allow_vehicle_swap ?? true);
      const backendTripGroupStats = this.summarizeTripGroupPayload(trips);
      const requestedOperationalQualityMode =
        this.normalizeOperationalQualityMode(operationalQualityMode);
      const persistedOperationalQualityMode =
        this.normalizeOperationalQualityMode(params?.operational_quality_mode);
      const resolvedOperationalQualityMode =
        this.resolveRequestedOperationalQualityMode(
          operationalQualityMode,
          params?.operational_quality_mode,
        );
      if (!resolvedOperationalQualityMode) {
        throw new BadRequestException('operational_quality_mode invalido');
      }

      this.logger.log(
        `[OP-QUALITY] backend request trace ${JSON.stringify({
          company_id: companyId,
          requested_operational_quality_mode: requestedOperationalQualityMode,
          persisted_operational_quality_mode: persistedOperationalQualityMode,
          effective_operational_quality_mode: resolvedOperationalQualityMode,
        })}`,
      );

      // 3. Chamar API Python (FastAPI/Celery)
      const invalidLoopTrips = trips.filter(
        (t) => Number(t.originId) === Number(t.destinationId),
      );
      if (invalidLoopTrips.length > 0) {
        this.logger.warn(
          `[PRE-FLIGHT] ${invalidLoopTrips.length} trip(s) com origin==destination ignoradas: ${invalidLoopTrips.map((t) => t.id).join(', ')}`,
        );
      }
      const validTrips = trips.filter(
        (t) => Number(t.originId) !== Number(t.destinationId),
      );
      if (!validTrips.length)
        throw new Error(
          'Nenhuma viagem válida para otimização após filtro de terminal loop.',
        );

      const payload = {
        trips: validTrips.map((t) => {
          const st = Number(t.startTime);
          // Normaliza virada de meia-noite: se end < start, soma 1440
          const et =
            Number(t.endTime) < st
              ? Number(t.endTime) + 1440
              : Number(t.endTime);
          return {
            id: t.id,
            line_id: this.resolveLineId(t.lineId, t.lineCode, 0),
            trip_group_id: this.normalizeTripGroupId(t.tripGroupId),
            direction: t.direction ?? null,
            start_time: st,
            end_time: et,
            origin_id: Number(t.originId),
            destination_id: Number(t.destinationId),
            origin_latitude: t.originLatitude ?? null,
            origin_longitude: t.originLongitude ?? null,
            destination_latitude: t.destinationLatitude ?? null,
            destination_longitude: t.destinationLongitude ?? null,
            duration: Number(t.duration ?? 0),
            distance_km: Number(t.distanceKm ?? 0),
            relief_point_id: t.reliefPointId ?? null,
            is_relief_point: t.isReliefPoint ?? false,
            mid_trip_relief_point_id: t.midTripReliefPointId ?? null,
            mid_trip_relief_offset_minutes:
              t.midTripReliefOffsetMinutes ?? null,
            mid_trip_relief_distance_ratio:
              t.midTripReliefDistanceRatio ?? null,
            mid_trip_relief_elevation_ratio:
              t.midTripReliefElevationRatio ?? null,
            depot_id: t.depotId ?? null,
          };
        }),
        vehicle_types: this.buildVehicleTypesPayload(vehicleTypes, params),
        cct_params: Object.assign({}, cctParams, { force_round_trip: forceRoundTrip }),
        optimization_params: {
          cost_vehicle: params?.cost_vehicle ?? DEFAULT_COST_VEHICLE,
          vehicle_fixed_cost: params?.vehicle_fixed_cost ?? null,
          cost_km: params?.cost_km ?? DEFAULT_COST_KM,
          cost_duty: params?.cost_duty ?? DEFAULT_COST_DUTY,
          driver_cost_per_minute: params?.driver_cost_per_minute ?? 0.0,
          collector_cost_per_minute: params?.collector_cost_per_minute ?? 0.0,
          cct_violation_penalty:
            params?.cct_violation_penalty ?? DEFAULT_CCT_VIOLATION_PENALTY,
          ilp_timeout_seconds:
            params?.ilp_timeout_seconds ?? DEFAULT_ILP_TIMEOUT_SECONDS,
          time_budget_s: params?.time_budget_s ?? null,
          random_seed: params?.random_seed ?? null,
          force_round_trip: forceRoundTrip,
          allow_vehicle_swap: allowVehicleSwap,
          enforce_min_interval: cctParams.enforce_min_interval,
          strict_hard_validation: cctParams.strict_hard_validation,
          strict_zero_gap_validation: cctParams.strict_zero_gap_validation,
          strict_operational_mode: cctParams.strict_operational_mode,
          strict_hard_constraints: cctParams.strict_hard_constraints,
          strict_union_rules: cctParams.strict_union_rules,
          group_infeasibility_mode: cctParams.group_infeasibility_mode,
          min_break_minutes: cctParams.min_break_minutes,
          min_layover_minutes: cctParams.min_layover_minutes,
          meal_break_minutes: cctParams.meal_break_minutes,
          mandatory_break_after_minutes:
            cctParams.mandatory_break_after_minutes,
          connection_tolerance_minutes: cctParams.connection_tolerance_minutes,
          preferred_pair_window_minutes:
            vspParams.preferred_pair_window_minutes,
          preserve_preferred_pairs: vspParams.preserve_preferred_pairs,
          pair_break_penalty: vspParams.pair_break_penalty,
          paired_trip_bonus: vspParams.paired_trip_bonus,
          allow_multi_line_block: vspParams.allow_multi_line_block,
          enable_column_generation: vspParams.enable_column_generation,
          pricing_enabled: vspParams.pricing_enabled,
          use_set_covering: vspParams.use_set_covering,
          vehicle_idle_gap_behavior: vspParams.vehicle_idle_gap_behavior,
          vehicle_idle_gap_threshold_minutes:
            vspParams.vehicle_idle_gap_threshold_minutes,
          operational_quality_mode: resolvedOperationalQualityMode,
          ...(options?.optimizationParamsOverride || {}),
        },
        vsp_params: vspParams,
        time_budget_s:
          options?.optimizationParamsOverride?.time_budget_s ??
          params?.time_budget_s ??
          null,
        algorithm:
          algorithm || params?.algorithm_preference || 'hybrid_pipeline',
        depot_ids: options?.depotIds?.length ? options.depotIds : null,
        company_id: companyId,
        run_id: schedule.id,
        request_metadata: {
          trip_group_inference_mode: 'optimizer_only',
          backend_trip_group_stats: backendTripGroupStats,
          company_id: companyId,
          scenario_id: options?.scenarioId ?? `schedule-${schedule.id}`,
          run_id: schedule.id,
          baseline_schedule_id: options?.baselineScheduleId ?? null,
          requested_operational_quality_mode: requestedOperationalQualityMode,
          persisted_operational_quality_mode: persistedOperationalQualityMode,
          effective_operational_quality_mode: resolvedOperationalQualityMode,
          operational_quality_mode: resolvedOperationalQualityMode,
        },
      };

      // 3b. Persistir OptimizationRun (link cenário → schedule resultante).
      // Cria em RUNNING porque já vamos enfileirar no optimizer. inputFingerprint
      // permite reconhecer mesma combinação (companyId, scenario, params, trips) em chamadas futuras.
      const inputFingerprint = this.computeInputFingerprint({
        companyId,
        scenarioId: options?.scenarioId ?? 'default',
        baselineScheduleId: options?.baselineScheduleId ?? null,
        algorithm: payload.algorithm,
        optimizationParams: payload.optimization_params,
        cctParams,
        vspParams,
        tripIds: validTrips.map((t) => t.id),
      });
      const optimizationRun = await this.optimizationRunRepo.save({
        companyId,
        scenarioId: options?.scenarioId ?? 'default',
        baselineScheduleId: options?.baselineScheduleId ?? null,
        resultScheduleId: schedule.id,
        inputFingerprint,
        params: {
          algorithm: payload.algorithm,
          optimization_params: payload.optimization_params,
          cct_params: cctParams,
          vsp_params: vspParams,
          operational_quality_mode: resolvedOperationalQualityMode,
        },
        algorithm: payload.algorithm,
        randomSeed:
          typeof payload.optimization_params?.random_seed === 'number'
            ? payload.optimization_params.random_seed
            : null,
        status: OptimizationRunStatus.RUNNING,
      });

      this.logger.log(
        `Enviando otimização para o motor: company_id=${payload.company_id}, enforce_min_interval=${payload.cct_params?.enforce_min_interval}, min_break=${payload.cct_params?.min_break_minutes}, strict_hard_validation=${payload.cct_params?.strict_hard_validation}, strict_zero_gap_validation=${payload.cct_params?.strict_zero_gap_validation}, strict_operational_mode=${payload.cct_params?.strict_operational_mode}, strict_hard_constraints=${payload.cct_params?.strict_hard_constraints}, group_infeasibility_mode=${payload.cct_params?.group_infeasibility_mode}, random_seed=${payload.optimization_params?.random_seed}, trip_groups=${backendTripGroupStats.group_count}, grouped_trips=${backendTripGroupStats.grouped_trip_count}`,
      );
      this.logger.log(
        `[OP-QUALITY] backend -> optimizer payload ${JSON.stringify({
          company_id: payload.company_id,
          run_id: payload.run_id,
          requested_operational_quality_mode: requestedOperationalQualityMode,
          persisted_operational_quality_mode: persistedOperationalQualityMode,
          effective_operational_quality_mode: resolvedOperationalQualityMode,
          'payload.optimization_params.operational_quality_mode':
            payload.optimization_params?.operational_quality_mode ?? null,
        })}`,
      );
      const { data: submitData } = await axios.post(
        `${this.OPTIMIZER_URL}/optimize/`,
        payload,
        {
          headers: this.getOptimizerHeaders(),
        },
      );
      const taskId = submitData.task_id;

      this.gateway.notifyOptimizationQueued(companyId, {
        scheduleId: schedule.id,
        taskId,
      });

      // 4. Iniciar Polling no Backend (Processo em Background — fire-and-forget)
      void this.pollOptimizerTask(taskId, schedule.id, companyId, {
        algorithm: payload.algorithm,
        cctParams,
        vspParams,
        optimizationParams: payload.optimization_params,
        request_metadata: payload.request_metadata,
        submittedAt: new Date().toISOString(),
        optimizationRunId: optimizationRun.id,
        scenarioId: options?.scenarioId ?? null,
      });

      return {
        scheduleId: schedule.id,
        taskId,
        optimizationRunId: optimizationRun.id,
        scenarioId: optimizationRun.scenarioId,
        inputFingerprint,
      };
    } catch (error) {
      this.logger.error(`Falha ao iniciar otimização: ${error.message}`);
      await this.scheduleRepo.update(schedule.id, {
        status: ScheduleStatus.FAILED,
      });
      throw new InternalServerErrorException(error.message);
    }
  }

  /** Hash determinístico dos inputs que afetam o resultado da otimização. */
  private computeInputFingerprint(parts: {
    companyId: number;
    scenarioId: string;
    baselineScheduleId: number | null;
    algorithm: string;
    optimizationParams: Record<string, any>;
    cctParams: Record<string, any>;
    vspParams: Record<string, any>;
    tripIds: number[];
  }): string {
    // Sort por estabilidade — ordem do hash não pode depender da ordem de inserção.
    const stableStringify = (obj: any): string => {
      if (obj === null || typeof obj !== 'object') return JSON.stringify(obj);
      if (Array.isArray(obj)) return `[${obj.map(stableStringify).join(',')}]`;
      const keys = Object.keys(obj).sort();
      return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`;
    };
    const payload = stableStringify({
      c: parts.companyId,
      s: parts.scenarioId,
      b: parts.baselineScheduleId,
      a: parts.algorithm,
      op: parts.optimizationParams,
      cct: parts.cctParams,
      vsp: parts.vspParams,
      t: [...parts.tripIds].sort((a, b) => a - b),
    });
    return crypto.createHash('sha256').update(payload).digest('hex');
  }

  /**
   * Marca OptimizationRun como concluída (COMPLETED ou FAILED). Idempotente: ignora
   * se o context não trouxer runId (chamada pré-FASE 3 sem rastreio de cenário).
   */
  private async finalizeOptimizationRun(
    context: Record<string, any>,
    update: {
      status: OptimizationRunStatus;
      metrics?: Record<string, any> | null;
      errorMessage?: string | null;
    },
  ): Promise<void> {
    const runId = context?.optimizationRunId;
    if (!runId) return;
    try {
      const run = await this.optimizationRunRepo.findOne({
        where: { id: Number(runId) },
      });
      if (!run) return;
      const submittedAt = context?.submittedAt
        ? new Date(context.submittedAt).getTime()
        : null;
      const durationMs = submittedAt ? Date.now() - submittedAt : null;
      await this.optimizationRunRepo.update(run.id, {
        status: update.status,
        metrics: update.metrics ?? null,
        errorMessage: update.errorMessage ?? null,
        durationMs,
        completedAt: new Date(),
      });
    } catch (err) {
      this.logger.warn(
        `[OPT-RUN-FINALIZE-FAIL] runId=${runId} status=${update.status} error=${(err as Error).message}`,
      );
    }
  }

  /**
   * Replay reproduzível: dado um inputFingerprint, busca a OptimizationRun original
   * e dispara nova run com os MESMOS params/algorithm. Útil para validar:
   *   (a) o motor é determinístico (seed fixa → mesmo resultado);
   *   (b) reproduzir bug em ambiente diferente;
   *   (c) regressão após upgrade do solver.
   *
   * O scenarioId da nova run vira `replay-of-<fingerprint12chars>` para distinguir.
   */
  async replayRun(companyId: number, inputFingerprint: string): Promise<any> {
    const original = await this.optimizationRunRepo.findOne({
      where: { companyId, inputFingerprint },
      order: { createdAt: 'DESC' },
    });
    if (!original) {
      throw new BadRequestException(
        `Nenhuma OptimizationRun com inputFingerprint=${inputFingerprint} para esta empresa.`,
      );
    }
    const params = original.params || {};
    const algorithm =
      original.algorithm || params.algorithm || 'hybrid_pipeline';
    const optimizationParamsOverride = params.optimization_params || {};
    // Garantir seed determinística — se a original tinha randomSeed null, fixamos em 42
    // (não há reproduzibilidade real sem seed). Caso contrário, replicamos a original.
    if (original.randomSeed != null) {
      optimizationParamsOverride.random_seed = original.randomSeed;
    } else if (optimizationParamsOverride.random_seed == null) {
      optimizationParamsOverride.random_seed = 42;
    }
    const cctParamsOverride = params.cct_params || {};
    const vspParamsOverride = params.vsp_params || {};

    return this.runOptimization(companyId, algorithm, undefined, {
      scenarioId: `replay-of-${inputFingerprint.slice(0, 12)}`,
      baselineScheduleId: original.baselineScheduleId,
      optimizationParamsOverride,
      cctParamsOverride,
      vspParamsOverride,
      skipTenantLock: true,
    });
  }

  /**
   * Retorna `{ original, replay, diff, status }` para um fingerprint dado.
   * `status` é 'ready' quando a replay COMPLETED, 'running' se ainda pendente,
   * 'not_started' se nenhuma replay existe.
   */
  async getReplayComparison(
    companyId: number,
    inputFingerprint: string,
  ): Promise<{
    original: any;
    replay: any;
    diff: any;
    status: string;
  }> {
    const original = await this.optimizationRunRepo.findOne({
      where: { companyId, inputFingerprint },
      order: { createdAt: 'DESC' },
    });
    if (!original) {
      throw new BadRequestException(
        `Nenhuma OptimizationRun com inputFingerprint=${inputFingerprint}.`,
      );
    }
    const replayScenarioId = `replay-of-${inputFingerprint.slice(0, 12)}`;
    const replayRun = await this.optimizationRunRepo.findOne({
      where: { companyId, scenarioId: replayScenarioId },
      order: { createdAt: 'DESC' },
    });

    const originalMetrics = this.extractRunMetrics(original.metrics);
    if (!replayRun) {
      return {
        original: originalMetrics,
        replay: null,
        diff: null,
        status: 'not_started',
      };
    }
    if (replayRun.status !== OptimizationRunStatus.COMPLETED) {
      return {
        original: originalMetrics,
        replay: { status: replayRun.status },
        diff: null,
        status: 'running',
      };
    }
    const replayMetrics = this.extractRunMetrics(replayRun.metrics);
    const diff: Record<string, any> = {};
    for (const key of Object.keys(originalMetrics)) {
      const o = originalMetrics[key];
      const r = replayMetrics[key];
      if (typeof o === 'number' && typeof r === 'number') {
        diff[key] = r - o;
      } else {
        diff[key] = r === o ? 'same' : { original: o, replay: r };
      }
    }
    return {
      original: originalMetrics,
      replay: replayMetrics,
      diff,
      status: 'ready',
    };
  }

  /**
   * Benchmark embarcado: gera viagens sintéticas para cada tamanho em `sizes`,
   * chama o optimizer diretamente (sem persistir no DB) e retorna timing + qualidade.
   * Útil para SRE validar performance do solver sem CLI.
   */
  async runBenchmark(
    sizes: number[],
    algorithm = 'branch_and_price',
    seed = 42,
    timeBudgetS = 30,
  ): Promise<{ results: any[]; timestamp: string }> {
    const results: any[] = [];
    const vehicleTypes = [
      { id: 1, name: 'Standard', passenger_capacity: 60, fixed_cost: 800.0 },
    ];

    for (const n of sizes) {
      // Viagens uniformes entre 06:00 (360min) e 20:00 (1200min), duration=40min, dist=10km
      const daySpan = 840; // 1200 - 360
      const interval = Math.floor(daySpan / n);
      const trips = Array.from({ length: n }, (_, i) => {
        const start = 360 + i * interval;
        return {
          id: i + 1,
          line_id: (i % 5) + 1,
          start_time: start,
          end_time: start + 40,
          duration: 40,
          origin_id: (i % 2) + 1,
          destination_id: ((i + 1) % 2) + 1,
          distance_km: 10.0,
        };
      });

      const t0 = Date.now();
      let result: any = null;
      let error: string | null = null;
      try {
        const { data } = await axios.post(
          `${this.OPTIMIZER_URL}/optimize/`,
          {
            trips,
            vehicle_types: vehicleTypes,
            algorithm,
            time_budget_s: timeBudgetS,
          },
          {
            headers: this.getOptimizerHeaders(),
            timeout: (timeBudgetS + 30) * 1000,
          },
        );
        result = data;
      } catch (e: any) {
        error = e?.response?.data?.detail ?? e?.message ?? 'unknown error';
      }
      const elapsedS = (Date.now() - t0) / 1000;
      results.push({
        n,
        algorithm,
        seed,
        blocks: result?.vehicles ?? null,
        totalCost: result?.total_cost ?? null,
        elapsedS: Number(elapsedS.toFixed(2)),
        error,
      });
    }
    return { results, timestamp: new Date().toISOString() };
  }

  /** Sumarização das métricas que importam para comparação de cenários. */
  private extractRunMetrics(result: any): Record<string, any> {
    if (!result || typeof result !== 'object') return {};
    const fairness = result.cost_breakdown?.csp?.fairness ?? null;
    return {
      totalCost: Number(result.total_cost ?? 0),
      numVehicles: Number(result.vehicles ?? 0),
      numDuties: Number(result.crew ?? result.meta?.roster_count ?? 0),
      totalTrips: Number(result.total_trips ?? 0),
      unassignedTrips: Number(result.unassigned_trips ?? 0),
      cctViolations: Number(result.cct_violations ?? 0),
      hardIssueCount: Number(
        result.solver_explanation?.issues?.hard_count ?? 0,
      ),
      softIssueCount: Number(
        result.solver_explanation?.issues?.soft_count ?? 0,
      ),
      algorithm: result.vsp_algorithm ?? null,
      fairnessGini: fairness?.work_time?.gini ?? null,
      fairnessCv: fairness?.work_time?.cv ?? null,
    };
  }

  async aiChat(metrics: any, question: string) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada.');

    try {
      // Busca os parâmetros reais configurados para esta empresa
      const params = await this.paramRepo.findOne({ where: { companyId } });
      const cctParams = this.buildCctParams(params);

      const { data } = await axios.post(
        `${this.OPTIMIZER_URL}/optimize/chat`,
        {
          metrics: {
            ...metrics,
            current_parameters: cctParams, // Agora a IA sabe suas regras atuais!
          },
          question,
        },
        {
          headers: this.getOptimizerHeaders(),
          timeout: 70000,
        },
      );
      return data;
    } catch (error) {
      this.logger.error(`Erro no chat de IA: ${error.message}`);
      return {
        answer:
          'O serviço de IA está temporariamente indisponível. Tente novamente em instantes.',
        status: 'error',
      };
    }
  }

  private pollOptimizerTask(
    taskId: string,
    scheduleId: number,
    companyId: number,
    context: Record<string, any> = {},
  ) {
    const maxConsecutiveErrors = 12;
    const pollIntervalMs = 5000;
    const requestedBudgetSeconds = Number(
      context?.optimizationParams?.time_budget_s ??
        context?.vspParams?.time_budget_s ??
        120,
    );
    const celeryHardLimitSeconds = 1500;
    const backendPollingGraceSeconds = 120;
    const computedMaxAttempts = Math.ceil(
      ((Math.max(requestedBudgetSeconds, celeryHardLimitSeconds) +
        backendPollingGraceSeconds) *
        1000) /
        pollIntervalMs,
    );
    const maxAttempts = Number.isFinite(
      Number(context?.pollingMaxAttemptsOverride),
    )
      ? Math.max(1, Number(context.pollingMaxAttemptsOverride))
      : computedMaxAttempts;
    let attempts = 0;
    let consecutiveErrors = 0;
    let done = false;
    let nextTimer: ReturnType<typeof setTimeout> | null = null;

    const clearNextTimer = () => {
      if (nextTimer) {
        clearTimeout(nextTimer);
        nextTimer = null;
      }
    };

    const scheduleNextPoll = () => {
      if (done) return;
      if (attempts >= maxAttempts) {
        done = true;
        clearNextTimer();
        this.persistFailure(scheduleId, companyId, {
          error_type: 'timeout',
          error_code: 'OPTIMIZER_POLLING_TIMEOUT',
          message: 'Timeout controlado aguardando conclusão do Celery.',
          details: {
            attempts,
            task_id: taskId,
            requested_budget_seconds: requestedBudgetSeconds,
            celery_hard_limit_seconds: celeryHardLimitSeconds,
          },
          task_id: taskId,
          context,
        }).catch((error) => {
          this.logger.error(
            `Erro ao persistir timeout do schedule ${scheduleId}: ${error.message}. Schedule pode estar em estado inconsistente.`,
          );
        });
        this.gateway.notifyOptimizationStale(companyId, { scheduleId, taskId });
        this.gateway.notifyOptimizationFailed(
          companyId,
          'Timeout controlado aguardando conclusão do Celery.',
        );
        return;
      }

      nextTimer = setTimeout(() => {
        // Fire-and-forget: capturamos qualquer erro inesperado para evitar
        // unhandledPromiseRejection (mata o processo Node em --unhandled-rejections=strict).
        runPoll().catch((err) => {
          this.logger.error(
            `[OPT-POLL-UNHANDLED] scheduleId=${scheduleId} taskId=${taskId} error=${(err as Error).message}`,
          );
        });
      }, pollIntervalMs);
    };

    const runPoll = async () => {
      if (done) return;
      attempts++;
      try {
        const { data } = await axios.get(
          `${this.OPTIMIZER_URL}/optimize/status/${taskId}`,
          {
            headers: this.getOptimizerHeaders(),
            timeout: 10000,
          },
        );

        consecutiveErrors = 0; // Reset error counter on success

        if (data.status === 'completed') {
          done = true;
          clearNextTimer();
          const persistedStatus = await this.persistResults(
            scheduleId,
            companyId,
            data.result,
            context,
          );
          // Invalidar cache para que o usuário veja o novo resultado imediatamente
          this.scheduleCache.delete(companyId);
          // Atualizar OptimizationRun (FASE 3 scenario tracking) — fire-and-forget
          // para não atrasar a notificação Socket.io e não introduzir microtasks extras
          // que quebram timing de testes existentes.
          void this.finalizeOptimizationRun(context, {
            status:
              persistedStatus === 'failed'
                ? OptimizationRunStatus.FAILED
                : OptimizationRunStatus.COMPLETED,
            metrics: this.extractRunMetrics(data.result),
            errorMessage:
              persistedStatus === 'failed'
                ? this.extractInvalidResultMessage(data.result)
                : null,
          });
          // Enviamos apenas um sinal de conclusão leve via Socket.io para evitar OOM no envio.
          // O Frontend buscará os dados completos via API (fetchData).
          if (persistedStatus === 'failed') {
            const message = this.extractInvalidResultMessage(data.result);
            this.gateway.notifyOptimizationFailed(companyId, message);
          } else {
            this.gateway.notifyOptimizationFinished(companyId, scheduleId, {
              status: 'completed',
            });
          }
        } else if (data.status === 'failed') {
          done = true;
          clearNextTimer();
          const errMsg =
            data.message ||
            data.error?.message ||
            data.error?.error_message ||
            'Erro no motor de otimização.';
          await this.persistFailure(scheduleId, companyId, {
            error_type: data.error_type ?? data.error?.error_type ?? 'business',
            error_code:
              data.error_code ?? data.error?.error_code ?? 'OPTIMIZER_FAILED',
            message: errMsg,
            details: data.details ?? data.error?.details ?? data.error ?? {},
            task_id: taskId,
            context,
          });
          this.gateway.notifyOptimizationFailed(companyId, errMsg);
        } else {
          this.gateway.notifyOptimizationProgress(companyId, {
            scheduleId,
            taskId,
            progressPct: data.progress_pct ?? null,
            phase: data.phase ?? null,
            phaseLabel: data.phase_label ?? null,
          });
        }

        if (!done) {
          scheduleNextPoll();
        }
      } catch (error) {
        if (done) return;
        const businessError = error?.response?.data?.detail;
        const businessType =
          businessError?.error_type ?? businessError?.error?.error_type;
        if (businessType === 'business') {
          done = true;
          clearNextTimer();
          const errMsg =
            businessError.message ||
            businessError.error?.message ||
            'Erro de negócio no solver.';
          await this.persistFailure(scheduleId, companyId, {
            error_type: 'business',
            error_code:
              businessError.error_code ??
              businessError.error?.error_code ??
              businessError.code ??
              'OPTIMIZER_BUSINESS_ERROR',
            message: errMsg,
            details:
              businessError.details ??
              businessError.error?.details ??
              businessError,
            task_id: taskId,
            context,
          });
          this.gateway.notifyOptimizationFailed(companyId, errMsg);
          return;
        }
        consecutiveErrors++;
        this.logger.warn(
          `Erro no polling do task ${taskId} (${consecutiveErrors}/${maxConsecutiveErrors}): ${error.message}`,
        );

        if (consecutiveErrors >= maxConsecutiveErrors) {
          done = true;
          clearNextTimer();
          this.logger.error(`Falha permanente no polling do task ${taskId}`);
          await this.persistFailure(scheduleId, companyId, {
            error_type: 'network',
            error_code: 'OPTIMIZER_COMMUNICATION_ERROR',
            message: 'Erro de comunicação com o solver.',
            details: { attempts, consecutiveErrors, last_error: error.message },
            task_id: taskId,
            context,
          });
          this.gateway.notifyOptimizationFailed(
            companyId,
            'Erro de comunicação com o solver.',
          );
          return;
        }

        if (!done) {
          scheduleNextPoll();
        }
      }
    };

    runPoll().catch((err) => {
      this.logger.error(
        `[OPT-POLL-UNHANDLED-INIT] scheduleId=${scheduleId} taskId=${taskId} error=${(err as Error).message}`,
      );
    });
  }

  private async persistFailure(
    scheduleId: number,
    companyId: number,
    failure: {
      error_type?: string;
      error_code?: string;
      message?: string;
      details?: any;
      task_id?: string;
      context?: Record<string, any>;
    },
  ): Promise<void> {
    const maxRetries = 3;
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const schedule = await this.scheduleRepo.findOne({
          where: { id: scheduleId, companyId },
        });
        let elapsedMs: number | null = null;
        try {
          const rows = await this.dataSource.query(
            'SELECT EXTRACT(EPOCH FROM (now() - "createdAt")) * 1000 AS elapsed_ms FROM schedules WHERE id = $1 AND "companyId" = $2',
            [scheduleId, companyId],
          );
          elapsedMs =
            rows?.[0]?.elapsed_ms !== undefined
              ? Number(rows[0].elapsed_ms)
              : null;
        } catch {
          elapsedMs = null;
        }
        const context = failure.context || {};
        const details = failure.details || {};
        const hardIssues = Array.isArray(details.issues)
          ? details.issues
          : Array.isArray(details.diagnostics?.issues)
            ? details.diagnostics.issues
            : [];
        const metadata = {
          ...(schedule?.metadata || {}),
          status: 'failed',
          error_type: failure.error_type || 'business',
          error_code: failure.error_code || 'OPTIMIZER_FAILED',
          error_message: failure.message || 'Erro no motor de otimização.',
          error_details: details,
          task_id: failure.task_id,
          algorithm: context.algorithm ?? details.algorithm ?? null,
          failed_at: new Date().toISOString(),
          elapsed_ms: elapsedMs,
          resolved_params: {
            cct_params: context.cctParams ?? null,
            vsp_params: context.vspParams ?? null,
            optimization_params: context.optimizationParams ?? null,
          },
          hard_constraint_report: hardIssues.length
            ? {
                ok: false,
                issues: hardIssues,
              }
            : (details.hard_constraint_report ?? null),
          performance: {
            ...(details.performance || {}),
            backend_elapsed_ms: elapsedMs,
          },
          run_snapshot: details.run_snapshot ?? null,
        };

        await this.scheduleRepo.update(
          { id: scheduleId, companyId },
          {
            status: ScheduleStatus.FAILED,
            totalCost: 0,
            cctViolations: hardIssues.length,
            metadata: metadata,
          },
        );
        this.scheduleCache.delete(companyId);
        // Sincroniza OptimizationRun (FASE 3 scenario tracking) com a falha — fire-and-forget
        void this.finalizeOptimizationRun(context, {
          status: OptimizationRunStatus.FAILED,
          errorMessage:
            failure.message ?? failure.error_code ?? 'Falha na otimização',
          metrics: null,
        });
        this.logger.log(
          `✓ Falha persistida com sucesso para Schedule ${scheduleId} (tentativa ${attempt}/${maxRetries})`,
        );
        return; // Sucesso
      } catch (error) {
        lastError = error as Error;
        this.logger.warn(
          `Erro ao persistir falha do schedule ${scheduleId} (tentativa ${attempt}/${maxRetries}): ${error.message}`,
        );

        if (attempt < maxRetries) {
          await new Promise((resolve) => setTimeout(resolve, 1000 * attempt)); // Backoff exponencial
        }
      }
    }

    // Se chegou aqui, esgotou todas as tentativas
    this.logger.error(
      `CRÍTICO: Falha permanente ao persistir erro do schedule ${scheduleId} após ${maxRetries} tentativas. ` +
        `Último erro: ${lastError?.message}. Schedule pode estar em estado INCONSISTENTE.`,
    );
  }

  private async persistResults(
    scheduleId: number,
    companyId: number,
    result: any,
    context: Record<string, any> = {},
  ): Promise<'completed' | 'failed'> {
    this.logger.log(
      `Persistindo resultados para Schedule ${scheduleId}. Blocks: ${(result.blocks || []).length}, Duties: ${(result.duties || []).length}`,
    );

    try {
      return await this.dataSource.transaction(async (manager) => {
        const solverExplanation = this.summarizeSolverExplanation(
          result.solver_explanation ?? null,
        );
        const operationalQuality = this.extractOperationalQualityMetadata(
          result,
          context,
        );
        const sourceMeta = this.pickFirstObject(
          [
            result?.meta,
            result?.result?.meta,
            result?.result?.result?.meta,
            result?.metadata,
            result?.result?.metadata,
            result?.result?.result?.metadata,
          ],
          false,
        );
        this.logger.log(
          `[OP-QUALITY] persistResults source ${JSON.stringify({
            schedule_id: scheduleId,
            has_chosen_scenario: operationalQuality.chosen_scenario !== null,
            has_operational_quality_decision:
              operationalQuality.operational_quality_decision !== null,
            result_keys: this.listObjectKeys(result),
            meta_keys: this.listObjectKeys(sourceMeta),
          })}`,
        );
        const hardIssues = Array.isArray(solverExplanation?.issues?.hard)
          ? solverExplanation.issues.hard
          : [];
        const softIssues = Array.isArray(solverExplanation?.issues?.soft)
          ? solverExplanation.issues.soft
          : [];
        const hardIssueCount = Number(
          solverExplanation?.issues?.hard_count ?? hardIssues.length ?? 0,
        );
        const softIssueCount = Number(
          solverExplanation?.issues?.soft_count ?? softIssues.length ?? 0,
        );
        const reportedViolations = Math.max(
          Number(result.cct_violations ?? 0),
          hardIssues.length,
        );
        const hardConstraintReport =
          result.meta?.hard_constraint_report ?? null;
        const outputReport = hardConstraintReport?.output ?? null;
        // Defesa em profundidade: solver pode retornar solver_explanation.status='feasible'
        // (ou ausente) mas ainda ter hard_issue_count > 0. Visto no benchmark 2026-05-11
        // em hybrid_pipeline easy/N=1000 que retornou cost menor com 392 violações hard.
        // Tratar como FAILED — solução não é válida para operação real.
        const invalidCompleted =
          solverExplanation?.status === 'hard_violation' ||
          outputReport?.ok === false ||
          hardIssueCount > 0;
        const finalStatus = invalidCompleted
          ? ScheduleStatus.FAILED
          : ScheduleStatus.COMPLETED;

        const BATCH_SIZE = 500;

        // 1. Salvar Blocos (Veículos) em lotes
        const blocksRaw = result.blocks || [];
        for (let i = 0; i < blocksRaw.length; i += BATCH_SIZE) {
          const chunk = blocksRaw.slice(i, i + BATCH_SIZE);
          const blocks = chunk.map((b: any) =>
            manager.create(BlockAssignment, {
              companyId,
              scheduleId,
              blockId: b.block_id ?? b.id ?? 0,
              tripIds: (b.trips || []).map((t: any) =>
                typeof t === 'number' ? t : t.id,
              ),
              cost: b.total_cost ?? b.activation_cost ?? 0,
              // CORREÇÃO: Apenas os campos essenciais, sem usar "...b"
              metadata: {
                start_time: b.start_time,
                end_time: b.end_time,
                activation_cost: b.activation_cost,
                deadhead_minutes: b.deadhead_minutes,
                idle_minutes: b.idle_minutes,
                start_depot_id: b.start_depot_id,
                end_depot_id: b.end_depot_id,
              },
            }),
          );
          await manager.save(BlockAssignment, blocks);
        }

        // 2. Salvar Duties (Motoristas) em lotes
        const dutiesRaw = result.duties || [];
        for (let i = 0; i < dutiesRaw.length; i += BATCH_SIZE) {
          const chunk = dutiesRaw.slice(i, i + BATCH_SIZE);
          const duties = chunk.map((d: any) => {
            const dutyTripIds = Array.isArray(d.trip_ids)
              ? d.trip_ids
              : (d.trips || []).map((t: any) =>
                  typeof t === 'number' ? t : (t.trip_id ?? t.id),
                );
            return manager.create(DutyAssignment, {
              companyId,
              scheduleId,
              dutyId: d.duty_id ?? d.id ?? 0,
              tripIds: dutyTripIds
                .filter(
                  (id: any) => Number.isFinite(Number(id)) && Number(id) > 0,
                )
                .map((id: any) => Number(id)),
              cost: d.total_cost ?? 0,
              // CORREÇÃO: Apenas os campos essenciais, sem usar "...d"
              metadata: {
                work_time: d.work_time,
                spread_time: d.spread_time,
                start_time: d.start_time,
                end_time: d.end_time,
                work_cost: d.work_cost,
                guaranteed_cost: d.guaranteed_cost,
                waiting_cost: d.waiting_cost,
                overtime_cost: d.overtime_cost,
                overtime_minutes: d.overtime_minutes,
                long_unpaid_break_penalty: d.long_unpaid_break_penalty,
                nocturnal_extra: d.nocturnal_extra_cost ?? d.nocturnal_extra,
                holiday_extra: d.holiday_extra_cost ?? d.holiday_extra,
                cct_penalties: d.cct_penalties_cost ?? d.cct_penalties,
                shift_violations: d.shift_violations,
                rest_violations: d.rest_violations,
                duty_time_segments:
                  d.meta?.duty_time_segments ?? d.segments ?? null,
                operational_time_report:
                  d.meta?.operational_time_report ?? null,
                quality_metrics: d.meta?.quality_metrics ?? null,
              },
            });
          });
          await manager.save(DutyAssignment, duties);
        }

        // 3. Atualizar Header do Schedule
        const scheduleMetadata: Record<string, any> = {
          solver_explanation: solverExplanation,
          hard_issue_count: hardIssueCount,
          soft_issue_count: softIssueCount,
          unassigned_trips: result.unassigned_trips ?? 0,
          cost_breakdown: this.summarizeCostBreakdown(
            result.cost_breakdown ?? {},
          ),
          phase_summary:
            result.phase_summary ?? result.meta?.phase_summary ?? null,
          trip_group_audit: this.summarizeTripGroupAudit(
            result.trip_group_audit ?? result.meta?.trip_group_audit ?? null,
          ),
          reproducibility:
            result.reproducibility ?? result.meta?.reproducibility ?? null,
          performance: result.performance ?? result.meta?.performance ?? null,
          hard_constraint_report: result.meta?.hard_constraint_report ?? null,
          operational_time_reports:
            result.operational_time_reports ??
            result.meta?.operational_time_reports ??
            null,
          operational_kpis: result.meta?.operational_kpis ?? null,
          resolved_params: result.meta?.input ?? null,
          run_snapshot:
            result.meta?.run_snapshot ??
            result.meta?.input?.run_snapshot ??
            null,
          num_vehicles: result.vehicles ?? 0,
          num_duties: result.crew ?? (result.meta?.roster_count || 0),
          roster_count: result.meta?.roster_count ?? 0,
          total_trips: result.total_trips ?? 0,
          algorithm: result.vsp_algorithm ?? '',
          // BUG-01 fix (auditoria 2026-05-17): expor fallback do solver para que o
          // operador saiba quando o algoritmo escolhido não rodou (ex: MCNF→Greedy
          // por timeout/infeasibility). Sem isso, cliente paga por "ILP" e recebe greedy.
          solver_warnings: this.collectSolverWarnings(result, sourceMeta),
          operational_quality_mode: operationalQuality.operational_quality_mode,
          chosen_scenario: operationalQuality.chosen_scenario,
          rejected_scenarios: operationalQuality.rejected_scenarios,
          justification: operationalQuality.justification,
          trade_offs: operationalQuality.trade_offs,
          operational_quality_decision:
            operationalQuality.operational_quality_decision,
        };

        if (invalidCompleted) {
          scheduleMetadata.status = 'failed';
          scheduleMetadata.error_type = 'business';
          scheduleMetadata.error_code = 'HARD_CONSTRAINT_OUTPUT';
          scheduleMetadata.error_message =
            this.extractInvalidResultMessage(result);
        }

        await manager.update(Schedule, scheduleId, {
          status: finalStatus,
          totalCost: result.total_cost ?? 0,
          cctViolations: reportedViolations,
          metadata: scheduleMetadata as any,
        });
        return finalStatus === ScheduleStatus.FAILED ? 'failed' : 'completed';
      });
    } catch (err: any) {
      this.logger.error(
        `persistResults FALHOU para Schedule ${scheduleId}: ${err.message}`,
        err.stack,
      );
      throw err;
    }
  }

  async reassignTrip(
    companyId: number,
    scheduleId: number,
    tripId: number,
    targetBlockId: number,
  ) {
    return this.dataSource.transaction(async (manager) => {
      // 1. Buscar a viagem e os blocos envolvidos
      const trip = await manager.findOne(Trip, {
        where: { id: tripId, companyId },
      });
      const sourceBlock = await manager
        .createQueryBuilder(BlockAssignment, 'b')
        .where('b.scheduleId = :scheduleId', { scheduleId })
        .andWhere('b.companyId = :companyId', { companyId })
        .andWhere(':tripId = ANY(b.tripIds)', { tripId })
        .getOne();
      const targetBlock = await manager.findOne(BlockAssignment, {
        where: { id: targetBlockId, scheduleId, companyId },
      });

      if (!trip || !targetBlock) {
        throw new InternalServerErrorException(
          'Viagem ou Bloco de destino não encontrado.',
        );
      }

      // 2. Rule Checker: Sobreposição e Viabilidade
      const violations: string[] = [];
      const targetTrips: Trip[] = await manager.find(Trip, {
        where: { id: In(targetBlock.tripIds) },
      });

      // Validar sobreposição temporal no bloco de destino
      for (const t of targetTrips) {
        if (trip.startTime < t.endTime && trip.endTime > t.startTime) {
          violations.push(
            `Sobreposição temporal com Viagem ${t.tripId || t.id}.`,
          );
        }
      }

      // 4. Sincronização com Motor Python (What-If) para recálculo de custo real
      const companyParams = await manager.findOne(CompanyParameters, {
        where: { companyId },
      });
      const allBlocks = await manager.find(BlockAssignment, {
        where: { scheduleId, companyId },
      });

      const whatIfPayload = {
        blocks: allBlocks.map((b) => ({
          id: b.blockId,
          vehicle_type_id: 1, // Padrao
          trips: b.metadata?.trips || [],
        })),
        source_block_id: sourceBlock?.blockId || 0,
        target_block_id: targetBlock.blockId,
        trip_ids: [tripId],
        target_index: 0, // O motor resolve o sort cronológico internamente
        optimization_params: {
          cost_vehicle: companyParams?.cost_vehicle ?? DEFAULT_COST_VEHICLE,
          vehicle_fixed_cost: companyParams?.vehicle_fixed_cost ?? null,
          cost_km: companyParams?.cost_km ?? DEFAULT_COST_KM,
          cost_duty: companyParams?.cost_duty ?? DEFAULT_COST_DUTY,
          driver_cost_per_minute: companyParams?.driver_cost_per_minute ?? 0.0,
          collector_cost_per_minute:
            companyParams?.collector_cost_per_minute ?? 0.0,
        },
      };

      try {
        const { data: whatIfResult } = await axios.post(
          `${this.OPTIMIZER_URL}/api/v1/evaluate-delta`,
          whatIfPayload,
          {
            headers: this.getOptimizerHeaders(),
          },
        );

        // 5. Atualizar custos persistidos no banco
        if (whatIfResult.status === 'ok') {
          // Atualizar custo individual de cada bloco alterado
          for (const bResp of whatIfResult.blocks) {
            await manager.update(
              BlockAssignment,
              { scheduleId, blockId: bResp.block_id, companyId },
              {
                cost: bResp.total_cost,
                metadata: {
                  ...(allBlocks.find((b) => b.blockId === bResp.block_id)
                    ?.metadata || {}),
                  ...bResp,
                },
              },
            );
          }

          // Atualizar custo total do Schedule (KPI Global)
          const totalCost = whatIfResult.cost_breakdown?.total || 0;
          await manager.update(Schedule, scheduleId, { totalCost });
        }

        // CORREÇÃO: Limpar o cache para forçar a re-hidratação no próximo request
        this.scheduleCache.delete(companyId);

        return {
          isValid: violations.length === 0,
          violations,
          scheduleId,
          costBreakdown: whatIfResult.cost_breakdown,
        };
      } catch (_error) {
        // CORREÇÃO: Limpar o cache para forçar a re-hidratação no próximo request
        this.scheduleCache.delete(companyId);

        return {
          isValid: violations.length === 0,
          violations,
          scheduleId,
          warning: 'Recálculo de custo via motor Python indisponível.',
        };
      }
    });
  }

  async evaluateDelta(frontendPayload: any) {
    const { blocks, move } = frontendPayload;

    let source_block_id: number | null = null;
    for (const block of blocks) {
      const bId = block.block_id ?? block.id;
      const trips = block.trips || [];
      if (trips.some((t: any) => (t.id ?? t.tripId) === move.trip_id)) {
        source_block_id = bId;
        break;
      }
    }

    if (source_block_id === null) {
      return {
        isValid: false,
        violations: [`Viagem ${move.trip_id} não encontrada nos blocos`],
        blocks: [],
        totalCost: null,
        deltaCost: null,
      };
    }

    const pythonBlocks = blocks.map((b: any) => ({
      id: b.block_id ?? b.id, // Python whatif.py lê 'id', não 'block_id'
      trips: (b.trips || []).map((t: any) => ({
        id: t.id ?? t.tripId,
        start_time: t.start_time ?? t.startTime,
        end_time: t.end_time ?? t.endTime,
        line_id: this.resolveLineId(
          t.line_id ?? t.lineId,
          t.line_code ?? t.lineCode,
          0,
        ),
        origin_id: t.origin_id ?? t.originId ?? 0,
        destination_id: t.destination_id ?? t.destinationId ?? 0,
        duration: t.duration ?? 0,
        distance_km: t.distance_km ?? t.distanceKm ?? 0,
        trip_group_id: t.trip_group_id ?? null,
        direction: t.direction ?? null,
      })),
      vehicle_type_id: b.vehicle_type_id ?? null,
    }));

    const pythonPayload = {
      blocks: pythonBlocks,
      trip_ids: [move.trip_id],
      source_block_id,
      target_block_id: move.to_block_id,
      target_index: 0,
    };

    try {
      const { data } = await axios.post(
        `${this.OPTIMIZER_URL}/api/v1/evaluate-delta`,
        pythonPayload,
        {
          headers: this.getOptimizerHeaders(),
          timeout: 15000,
        },
      );
      return {
        isValid: true,
        violations: [],
        totalCost: data.cost_breakdown?.total ?? 0,
        deltaCost: 0,
        blocks: data.blocks,
      };
    } catch (error: any) {
      const detail =
        error.response?.data?.detail ||
        'Movimento viola restrições operacionais';
      return {
        isValid: false,
        violations: [detail],
        blocks: [],
        totalCost: null,
        deltaCost: null,
      };
    }
  }

  async evaluateBaseline(frontendPayload: any) {
    const { blocks } = frontendPayload;

    const pythonBlocks = (blocks || []).map((b: any) => ({
      id: b.block_id ?? b.id,
      trips: (b.trips || []).map((t: any) => ({
        id: t.id ?? t.tripId,
        start_time: t.start_time ?? t.startTime,
        end_time: t.end_time ?? t.endTime,
        line_id: this.resolveLineId(
          t.line_id ?? t.lineId,
          t.line_code ?? t.lineCode,
          0,
        ),
        origin_id: t.origin_id ?? t.originId ?? 0,
        destination_id: t.destination_id ?? t.destinationId ?? 0,
        duration: t.duration ?? 0,
        distance_km: t.distance_km ?? t.distanceKm ?? 0,
        trip_group_id: t.trip_group_id ?? null,
        direction: t.direction ?? null,
      })),
      vehicle_type_id: b.vehicle_type_id ?? null,
    }));

    try {
      const { data } = await axios.post(
        `${this.OPTIMIZER_URL}/api/v1/evaluate-baseline`,
        { blocks: pythonBlocks },
        {
          headers: this.getOptimizerHeaders(),
          timeout: 15000,
        },
      );
      return {
        totalCost: data.cost_breakdown?.total ?? data.total_cost ?? 0,
        costBreakdown: data.cost_breakdown ?? null,
        blocks: data.blocks ?? [],
      };
    } catch (error: any) {
      const detail =
        error.response?.data?.detail || 'Erro ao calcular baseline';
      return {
        totalCost: null,
        costBreakdown: null,
        blocks: [],
        error: detail,
      };
    }
  }

  private buildCctParams(
    params: CompanyParameters | null,
  ): Record<string, any> {
    const runtimeParams = normalizeLegacyCompanyParameters(params).normalized;

    if (!runtimeParams) {
      return {
        max_work_minutes: 480,
        max_shift_minutes: 720,
        meal_break_minutes: 60,
        enforce_trip_groups_hard: true,
        operator_single_vehicle_only: true,
        apply_cct: true,
        strict_hard_validation: true,
        strict_union_rules: true,
      };
    }

    // Envia para o Python APENAS campos com valor preenchido (non-null).
    // Isso permite que o solver use seus defaults internos para campos nao configurados.
    const cctFields: (keyof CompanyParameters)[] = [
      'max_shift_minutes',
      'max_work_minutes',
      'min_work_minutes',
      'min_shift_minutes',
      'overtime_limit_minutes',
      'max_driving_minutes',
      'min_break_minutes',
      'connection_tolerance_minutes',
      'mandatory_break_after_minutes',
      'split_break_first_minutes',
      'split_break_second_minutes',
      'meal_break_minutes',
      'inter_shift_rest_minutes',
      'weekly_rest_minutes',
      'reduced_weekly_rest_minutes',
      'allow_reduced_weekly_rest',
      'daily_driving_limit_minutes',
      'extended_daily_driving_limit_minutes',
      'max_extended_driving_days_per_week',
      'weekly_driving_limit_minutes',
      'fortnight_driving_limit_minutes',
      'min_layover_minutes',
      'pullout_minutes',
      'pullback_minutes',
      'pullout_counts_in_driver_shift',
      'pullback_counts_in_driver_shift',
      'idle_time_is_paid',
      'waiting_time_pay_pct',
      'min_guaranteed_work_minutes',
      'max_unpaid_break_minutes',
      'max_total_unpaid_break_minutes',
      'long_unpaid_break_limit_minutes',
      'long_unpaid_break_penalty_weight',
      'allow_relief_points',
      'enforce_same_depot_start_end',
      'fairness_weight',
      'fairness_target_work_minutes',
      'fairness_tolerance_minutes',
      'operator_change_terminals_only',
      'enforce_trip_groups_hard',
      'operator_pairing_hard',
      'trip_group_keep_bonus',
      'sunday_off_weight',
      'holiday_extra_pct',
      'enforce_single_line_duty',
      'operator_single_vehicle_only',
      'nocturnal_start_hour',
      'nocturnal_end_hour',
      'nocturnal_factor',
      'nocturnal_extra_pct',
      'apply_cct',
      'strict_hard_validation',
      'strict_union_rules',
      'terminal_location_ids',
      'goal_weights',
      'dynamic_rules',
      'enforce_min_interval',
      'strict_zero_gap_validation',
      'strict_operational_mode',
      'strict_hard_constraints',
      'strict_gps_validation',
      'strict_terminal_sync_validation',
      'group_infeasibility_mode',
    ];

    const result: Record<string, any> = {};
    for (const field of cctFields) {
      const value = runtimeParams[field];
      if (value !== null && value !== undefined) {
        result[field] = value;
      }
    }

    // Fallbacks obrigatorios
    if (!result.max_work_minutes)
      result.max_work_minutes = runtimeParams.max_driving_time_minutes || 480;
    if (
      !result.max_driving_minutes &&
      runtimeParams.max_driving_time_minutes !== null &&
      runtimeParams.max_driving_time_minutes !== undefined
    ) {
      result.max_driving_minutes = runtimeParams.max_driving_time_minutes;
    }
    if (!result.max_shift_minutes)
      result.max_shift_minutes = runtimeParams.max_shift_minutes || 720;
    if (!result.meal_break_minutes)
      result.meal_break_minutes = runtimeParams.meal_break_minutes || 60;

    if (result.enforce_min_interval === undefined) {
      result.enforce_min_interval = true;
    }

    if (result.enforce_min_interval && result.min_break_minutes === undefined) {
      result.min_break_minutes = runtimeParams.min_break_minutes ?? 30;
    }

    if (result.min_layover_minutes === undefined) {
      result.min_layover_minutes =
        runtimeParams.min_layover_minutes ?? result.min_break_minutes ?? 30;
    }

    if (runtimeParams.force_round_trip) {
      result.enforce_trip_groups_hard = true;
      result.operator_pairing_hard = true;
    }
    if (runtimeParams.allow_vehicle_swap === false) {
      result.operator_single_vehicle_only = true;
    }
    if (result.apply_cct === undefined) result.apply_cct = true;
    if (result.strict_hard_validation === undefined)
      result.strict_hard_validation = true;
    if (result.strict_union_rules === undefined)
      result.strict_union_rules = true;

    return result;
  }

  private buildVspParams(
    params: CompanyParameters | null,
    cctParams: Record<string, any> = {},
  ): Record<string, any> {
    if (!params) {
      return {
        force_round_trip: true,
        allow_vehicle_swap: true,
        preferred_pair_window_minutes: 30,
        preserve_preferred_pairs: true,
      };
    }

    const vspFields: (keyof CompanyParameters)[] = [
      'time_budget_s',
      'random_seed',
      'max_vehicle_shift_minutes',
      'max_vehicles',
      'ilp_timeout_seconds',
      'min_layover_minutes',
      'deadhead_cost_per_minute',
      'idle_cost_per_minute',
      'strict_zero_gap_validation',
      'strict_operational_mode',
      'strict_hard_constraints',
      'allow_multi_line_block',
      'allow_vehicle_split_shifts',
      'split_shift_min_gap_minutes',
      'split_shift_max_gap_minutes',
      'max_simultaneous_chargers',
      'enable_column_generation',
      'pricing_enabled',
      'use_set_covering',
      'min_workpiece_minutes',
      'max_workpiece_minutes',
      'min_trips_per_piece',
      'max_trips_per_piece',
      'peak_energy_cost_per_kwh',
      'offpeak_energy_cost_per_kwh',
      'preferred_pair_window_minutes',
      'preserve_preferred_pairs',
      'pair_break_penalty',
      'paired_trip_bonus',
      'max_connection_cost_for_reuse_ratio',
      'max_candidate_successors_per_task',
      'max_generated_columns',
      'max_pricing_iterations',
      'max_pricing_additions',
      'vehicle_idle_gap_behavior',
      'vehicle_idle_gap_threshold_minutes',
      'goal_weights',
      'group_infeasibility_mode',
    ];

    const result: Record<string, any> = {
      force_round_trip: params.force_round_trip ?? true,
      allow_vehicle_swap: params.allow_vehicle_swap ?? true,
      fixed_vehicle_activation_cost:
        params.vehicle_fixed_cost ?? DEFAULT_VEHICLE_FIXED_COST,
      preferred_pair_window_minutes: params.preferred_pair_window_minutes ?? 30,
      preserve_preferred_pairs: params.preserve_preferred_pairs ?? true,
      vehicle_idle_gap_behavior:
        params.vehicle_idle_gap_behavior ?? 'solver_decides',
    };

    for (const field of vspFields) {
      const value = params[field];
      if (value !== null && value !== undefined) {
        result[field] = value;
      }
    }

    if (
      cctParams.connection_tolerance_minutes !== undefined &&
      result.connection_tolerance_minutes === undefined
    ) {
      result.connection_tolerance_minutes =
        cctParams.connection_tolerance_minutes;
    }
    if (
      params.paired_trip_bonus !== null &&
      params.paired_trip_bonus !== undefined
    ) {
      result.paired_trip_bonus = params.paired_trip_bonus;
    } else if (
      params.trip_group_keep_bonus !== null &&
      params.trip_group_keep_bonus !== undefined
    ) {
      result.paired_trip_bonus = params.trip_group_keep_bonus;
    }
    if (
      cctParams.strict_hard_validation !== undefined &&
      result.strict_hard_validation === undefined
    ) {
      result.strict_hard_validation = cctParams.strict_hard_validation;
    }
    if (
      cctParams.enforce_same_depot_start_end !== undefined &&
      result.same_depot_required === undefined
    ) {
      result.same_depot_required = Boolean(
        cctParams.enforce_same_depot_start_end,
      );
    }
    if (
      cctParams.max_shift_minutes !== undefined &&
      result.max_vehicle_shift_minutes === undefined
    ) {
      result.max_vehicle_shift_minutes = cctParams.max_shift_minutes;
    }

    const enforceMinInterval = cctParams.enforce_min_interval !== false;
    result.enforce_min_interval = enforceMinInterval;
    result.min_break_minutes =
      cctParams.min_break_minutes ?? params.min_break_minutes ?? 30;

    const baseLayover =
      params.min_layover_minutes ?? cctParams.min_layover_minutes ?? 8;

    result.min_layover_minutes = enforceMinInterval
      ? Math.max(baseLayover, result.min_break_minutes)
      : baseLayover;

    if (cctParams.enforce_trip_groups_hard || cctParams.operator_pairing_hard) {
      result.force_round_trip = true;
      result.preserve_preferred_pairs = true;
    }
    if (cctParams.operator_single_vehicle_only) {
      result.allow_vehicle_swap = false;
    }

    return result;
  }

  private buildVehicleTypesPayload(
    vehicleTypes: VehicleType[],
    params: CompanyParameters | null,
  ): any[] {
    // If we have vehicle types in the database, use them
    if (vehicleTypes && vehicleTypes.length > 0) {
      return vehicleTypes.map((vt) => ({
        id: vt.id,
        name: vt.name,
        passenger_capacity: vt.capacity,
        cost_per_km: 1.0, // Default, can be enhanced
        cost_per_hour: 10.0, // Default, can be enhanced
        fixed_cost:
          vt.costPerDay ||
          Number(params?.vehicle_fixed_cost || DEFAULT_VEHICLE_FIXED_COST),
        is_electric: false, // Default
        battery_capacity_kwh: 0.0,
        minimum_soc: 0.15,
        charge_rate_kw: 0.0,
        energy_cost_per_kwh: 0.0,
      }));
    }

    // Fallback to default vehicle type if none exist in database
    return [
      {
        id: 1,
        name: 'Padrao',
        passenger_capacity: 40,
        cost_per_km: 1.0,
        cost_per_hour: 10.0,
        fixed_cost: Number(
          params?.vehicle_fixed_cost || DEFAULT_VEHICLE_FIXED_COST,
        ),
        is_electric: false,
        battery_capacity_kwh: 0.0,
        minimum_soc: 0.15,
        charge_rate_kw: 0.0,
        energy_cost_per_kwh: 0.0,
      },
    ];
  }

  /**
   * Coleta warnings estruturados do solver para expor ao operador.
   * BUG-01 fix (auditoria 2026-05-17): fallback do MCNF→Greedy ou de qualquer ILP
   * para heurística DEVE aparecer aqui — sem isso o cliente acha que está usando
   * "ILP ótimo" quando na verdade está usando greedy.
   */
  private collectSolverWarnings(
    result: any,
    sourceMeta: any,
  ): Array<{
    code: string;
    severity: 'INFO' | 'WARN' | 'CRITICAL';
    message: string;
    detail?: any;
  }> {
    const warnings: Array<{
      code: string;
      severity: 'INFO' | 'WARN' | 'CRITICAL';
      message: string;
      detail?: any;
    }> = [];

    const metaCandidates = [
      result?.meta,
      sourceMeta,
      result?.vsp?.meta,
      result?.result?.meta,
    ].filter((m) => m && typeof m === 'object');

    for (const meta of metaCandidates) {
      if (meta.fallback_used) {
        warnings.push({
          code: 'SOLVER_FALLBACK',
          severity: 'CRITICAL',
          message:
            `Solver primário (${meta.original_solver ?? '?'}) falhou e foi substituído por ` +
            `fallback (${meta.fallback_solver ?? '?'}). Solução pode ser subótima. ` +
            `Razão: ${meta.fallback_reason ?? 'não especificada'}.`,
          detail: {
            original_solver: meta.original_solver ?? null,
            fallback_solver: meta.fallback_solver ?? null,
            fallback_reason: meta.fallback_reason ?? null,
          },
        });
      }
      if (meta.timetable_slack?.pvr_reduction_pct !== undefined) {
        warnings.push({
          code: 'TIMETABLE_SLACK_APPLIED',
          severity: 'INFO',
          message: `Timetable slack ajustou ${meta.timetable_slack.trips_adjusted} viagens (PVR -${meta.timetable_slack.pvr_reduction_pct?.toFixed?.(1) ?? 0}%)`,
          detail: meta.timetable_slack,
        });
      }
      const perf = meta.performance;
      if (perf?.vsp_metaheuristics_skipped) {
        warnings.push({
          code: 'METAHEURISTICS_SKIPPED',
          severity: 'WARN',
          message:
            'Metaheurísticas (SA/Tabu/Genetic) puladas por scale guard. ' +
            `Para forçar, ajuste force_vsp_metaheuristics=true. ` +
            `(trips=${perf.vsp_metaheuristics_skipped.trip_count}, ` +
            `blocks=${perf.vsp_metaheuristics_skipped.block_count})`,
          detail: perf.vsp_metaheuristics_skipped,
        });
      }
    }
    return warnings;
  }

  private extractInvalidResultMessage(result: any): string {
    const solverStatus =
      result?.solver_explanation?.status ??
      result?.meta?.solver_explanation?.status;
    const outputReport = result?.meta?.hard_constraint_report?.output;
    const hardCount = Number(
      result?.solver_explanation?.issues?.hard_count ?? 0,
    );
    if (solverStatus === 'hard_violation') {
      return 'Resultado inválido: solver_explanation.status=hard_violation.';
    }
    if (outputReport?.ok === false) {
      return 'Resultado inválido: hard_constraint_report.output.ok=false.';
    }
    if (hardCount > 0) {
      return `Resultado inválido: ${hardCount} restrição(ões) hard violada(s). Solver retornou solução numericamente mais barata mas inviável.`;
    }
    return 'Resultado inválido persistido como falha por validação final.';
  }

  async getOptimizeStatus(companyId: number) {
    const schedule = await this.scheduleRepo.findOne({
      where: { companyId },
      order: { createdAt: 'DESC' },
    });
    if (!schedule)
      return {
        status: 'idle',
        scheduleId: null,
        startedAt: null,
        totalCost: null,
        cctViolations: 0,
      };
    return {
      status: schedule.status,
      scheduleId: schedule.id,
      startedAt: schedule.createdAt,
      totalCost: schedule.totalCost ?? null,
      cctViolations: schedule.cctViolations ?? 0,
    };
  }

  /**
   * Certificado de otimalidade — lê o resultado persistido em
   * schedule.metadata.cost_breakdown.optimality. Retorna 404 se não houver
   * (otimização antiga, anterior ao certifier). Multi-tenant via companyId.
   */
  async getOptimalityCertificate(companyId: number, scheduleId: number) {
    const schedule = await this.scheduleRepo.findOne({
      where: { id: scheduleId, companyId },
    });
    if (!schedule) {
      throw new NotFoundException(`Schedule ${scheduleId} não encontrado.`);
    }
    const meta: Record<string, unknown> =
      (schedule.metadata as Record<string, unknown>) ?? {};
    const costBreakdown = (meta.cost_breakdown ?? {}) as Record<string, unknown>;
    const optimality = costBreakdown.optimality as
      | Record<string, unknown>
      | undefined;
    if (!optimality) {
      throw new NotFoundException(
        `Certificado de otimalidade indisponível para schedule ${scheduleId}.`,
      );
    }
    return {
      scheduleId,
      totalCost: schedule.totalCost ?? null,
      ...optimality,
    };
  }

  async getLatestSchedule(companyId: number) {
    const cached = this.scheduleCache.get(companyId);
    const now = Date.now();
    if (cached) {
      if (now - cached.timestamp < this.CACHE_TTL_MS) {
        return cached.data; // Cache válido
      } else {
        this.scheduleCache.delete(companyId); // CORREÇÃO: Remove ativamente da RAM se expirou
      }
    }

    const schedule = await this.scheduleRepo.findOne({
      where: { companyId },
      order: { createdAt: 'DESC' },
    });

    if (!schedule) return null;

    const [blocks, duties] = await Promise.all([
      this.dataSource.getRepository(BlockAssignment).find({
        where: { scheduleId: schedule.id, companyId },
        order: { blockId: 'ASC' },
      }),
      this.dataSource.getRepository(DutyAssignment).find({
        where: { scheduleId: schedule.id, companyId },
        order: { dutyId: 'ASC' },
      }),
    ]);

    // Hidratar trips completos dentro de cada block
    const allTripIds = blocks.flatMap((b) => b.tripIds || []);
    const uniqueTripIds = [...new Set(allTripIds)];
    const tripMap = new Map<number, Trip>();

    if (uniqueTripIds.length > 0) {
      const CHUNK_SIZE = 1000;
      const trips: Trip[] = [];

      // Busca em lotes e apenas com colunas necessárias para reduzir memória.
      for (let i = 0; i < uniqueTripIds.length; i += CHUNK_SIZE) {
        const chunk = uniqueTripIds.slice(i, i + CHUNK_SIZE);
        const chunkTrips = await this.tripRepo.find({
          where: { id: In(chunk) },
          select: {
            id: true,
            tripId: true,
            lineId: true,
            lineCode: true,
            pairId: true,
            tripGroupId: true,
            direction: true,
            startTime: true,
            endTime: true,
            originId: true,
            destinationId: true,
            distanceKm: true,
            duration: true,
          },
        });
        trips.push(...chunkTrips);
      }

      trips.forEach((t) => tripMap.set(t.id, t));
    }

    const hydratedBlocks = blocks
      .map((block) => {
        const meta = block.metadata || {};
        const st = meta.start_time ?? 0;
        const et = meta.end_time ?? 0;

        const hydratedTrips = (block.tripIds || [])
          .map((id) => tripMap.get(id))
          .filter((t): t is Trip => !!t)
          .map((t) => ({
            id: t.id,
            trip_id: t.tripId,
            start_time: Number(t.startTime),
            end_time:
              Number(t.endTime) < Number(t.startTime)
                ? Number(t.endTime) + 1440
                : Number(t.endTime),
            line_id: this.resolveLineId(t.lineId, t.lineCode, null),
            line_code: t.lineCode ?? null,
            trip_group_id: t.tripGroupId
              ? Number(t.tripGroupId)
              : t.pairId
                ? parseInt(t.pairId.replace(/\D/g, ''), 10) || null
                : null,
            origin_id: Number(t.originId),
            destination_id: Number(t.destinationId),
            duration: Number(t.duration),
            distance_km: Number(t.distanceKm),
            direction: t.direction ?? null,
            pair_id: t.pairId ?? null,
          }))
          .sort((a, b) => a.start_time - b.start_time);

        return {
          id: block.id,
          block_id: block.blockId,
          scheduleId: block.scheduleId,
          companyId: block.companyId,
          start_time: st,
          end_time: et,
          total_cost: Number(block.cost),
          trips: hydratedTrips,
          // Limpeza agressiva: enviamos apenas o necessário para o Gantt
          metadata: {
            activation_cost: meta.activation_cost,
            deadhead_minutes: meta.deadhead_minutes,
            idle_minutes: meta.idle_minutes,
            start_depot_id: meta.start_depot_id,
            end_depot_id: meta.end_depot_id,
            start_buffer_minutes: meta.start_buffer_minutes ?? 0,
            end_buffer_minutes: meta.end_buffer_minutes ?? 0,
            // ...meta // Comentado para evitar carregar dumps pesados do solver no Gantt
          },
        };
      })
      .sort((a, b) => (a.block_id || 0) - (b.block_id || 0));

    const tripDetailsById = new Map<number, any>();
    hydratedBlocks.forEach((block) => {
      (block.trips || []).forEach((trip: any, index: number) => {
        const detailedTrip = {
          ...trip,
          source_trip_id: trip.id,
          public_trip_id: trip.trip_id ?? trip.id,
          block_id: block.block_id,
          vehicle_id: block.block_id,
          sequence_in_block: index + 1,
        };
        const sourceTripId = this.toPositiveInteger(trip.id);
        if (sourceTripId != null) {
          tripDetailsById.set(sourceTripId, detailedTrip);
        }
        const publicTripId = this.toPositiveInteger(trip.trip_id);
        if (publicTripId != null && !tripDetailsById.has(publicTripId)) {
          tripDetailsById.set(publicTripId, detailedTrip);
        }
      });
    });

    // Monta resultSummary a partir do metadata salvo
    const meta = schedule.metadata || {};
    const rawMeta = meta.meta || {};
    const resolvedParams = meta.resolved_params ?? rawMeta.input ?? null;
    const fallbackFailedMessage = 'Falha sem erro estruturado persistido.';
    const effectiveErrorType =
      schedule.status === ScheduleStatus.FAILED
        ? (meta.error_type ?? 'unknown')
        : (meta.error_type ?? null);
    const effectiveErrorCode =
      schedule.status === ScheduleStatus.FAILED
        ? (meta.error_code ?? 'UNKNOWN_FAILURE')
        : (meta.error_code ?? null);
    const effectiveErrorMessage =
      schedule.status === ScheduleStatus.FAILED
        ? (meta.error_message ?? fallbackFailedMessage)
        : (meta.error_message ?? null);
    const operationalQuality = this.extractOperationalQualityMetadata(meta);
    const hardIssueCount =
      meta.hard_issue_count ??
      (((meta.solver_explanation || {}).issues || {}).hard || []).length;
    const softIssueCount =
      meta.soft_issue_count ??
      (((meta.solver_explanation || {}).issues || {}).soft || []).length;
    const tripGroupAudit = meta.trip_group_audit ?? null;
    const lightMetadata = {
      input: resolvedParams,
      solver_version: meta.solver_version ?? rawMeta.solver_version ?? null,
    };
    const resultSummary = {
      status: schedule.status,
      error_type: effectiveErrorType,
      error_code: effectiveErrorCode,
      error_message: effectiveErrorMessage,
      error_details: meta.error_details ?? null,
      num_vehicles: meta.num_vehicles ?? 0,
      vehicles: meta.num_vehicles ?? 0,
      num_crew: meta.num_duties ?? 0,
      crew: meta.num_duties ?? 0,
      total_cost: schedule.totalCost ?? meta.cost_breakdown?.total ?? 0,
      totalCost: schedule.totalCost ?? 0,
      cct_violations: schedule.cctViolations ?? 0,
      cctViolations: schedule.cctViolations ?? 0,
      total_trips: meta.total_trips ?? uniqueTripIds.length,
      rosterCount: meta.roster_count ?? 0,
      unassigned_trips: meta.unassigned_trips ?? [],
      hardIssueCount,
      softIssueCount,
      hasHardViolations: hardIssueCount > 0,
      solverStatus: (meta.solver_explanation || {}).status ?? null,
      costBreakdown: this.summarizeCostBreakdown(meta.cost_breakdown ?? null),
      solverExplanation: null, // meta.solver_explanation ?? null, // Removido do polling por ser muito pesado
      phaseSummary: null, // meta.phase_summary ?? null,
      tripGroupAudit,
      trip_group_audit: tripGroupAudit,
      reproducibility: null,
      performance: meta.performance ?? null,
      hardConstraintReport: meta.hard_constraint_report ?? null,
      operationalQualityMode: operationalQuality.operational_quality_mode,
      operational_quality_mode: operationalQuality.operational_quality_mode,
      chosenScenario: operationalQuality.chosen_scenario,
      chosen_scenario: operationalQuality.chosen_scenario,
      rejectedScenarios: operationalQuality.rejected_scenarios,
      rejected_scenarios: operationalQuality.rejected_scenarios,
      justification: operationalQuality.justification,
      tradeOffs: operationalQuality.trade_offs,
      trade_offs: operationalQuality.trade_offs,
      operationalQualityDecision:
        operationalQuality.operational_quality_decision,
      operational_quality_decision:
        operationalQuality.operational_quality_decision,
      partial_result: meta.partial_result ?? null,
      metadata: lightMetadata,
      meta: lightMetadata,
      runSnapshot: meta.run_snapshot ?? null,
      // blocks: hydratedBlocks, // REMOVIDO: Já enviado na raiz do objeto finalResult
      duties: duties.map((d) => {
        const dm = d.metadata || {};
        const dutyId = d.dutyId;
        const dutyTripIds = Array.isArray(d.tripIds)
          ? d.tripIds
              .map((tripId) => this.toPositiveInteger(tripId))
              .filter((tripId): tripId is number => tripId != null)
          : [];
        const dutyTimeSegments = this.normalizeDutyTimeSegments(
          dm.duty_time_segments ?? [],
          tripDetailsById,
        );
        const detailedTripAssignments = this.buildDetailedDutyTripAssignments(
          dutyId,
          dutyTripIds,
          dutyTimeSegments,
          tripDetailsById,
        );
        return {
          duty_id: dutyId,
          work_time: dm.work_time ?? 0,
          spread_time: dm.spread_time ?? 0,
          start_time: dm.start_time ?? 0,
          end_time: dm.end_time ?? 0,
          total_cost: d.cost ?? 0,
          work_cost: dm.work_cost ?? 0,
          overtime_cost: dm.overtime_cost ?? 0,
          overtime_minutes: dm.overtime_minutes ?? 0,
          shift_violations: dm.shift_violations ?? 0,
          rest_violations: dm.rest_violations ?? 0,
          duty_time_segments: dutyTimeSegments,
          operational_time_report: dm.operational_time_report ?? null,
          quality_metrics: dm.quality_metrics ?? null,
          detailed_trip_assignments: detailedTripAssignments,
          trip_ids: dutyTripIds,
        };
      }),
    };

    const hydratedDuties = resultSummary.duties;

    const finalResult = {
      id: schedule.id,
      companyId: schedule.companyId,
      status: schedule.status,
      totalCost: Number(schedule.totalCost),
      cctViolations: Number(schedule.cctViolations),
      error_type: effectiveErrorType,
      error_code: effectiveErrorCode,
      error_message: effectiveErrorMessage,
      hard_constraint_report: meta.hard_constraint_report ?? null,
      performance: meta.performance ?? null,
      partial_result: meta.partial_result ?? null,
      run_snapshot: meta.run_snapshot ?? null,
      hardIssueCount,
      hard_issue_count: hardIssueCount,
      softIssueCount,
      soft_issue_count: softIssueCount,
      tripGroupAudit,
      trip_group_audit: tripGroupAudit,
      solver_explanation: meta.solver_explanation ?? null,
      operational_quality_mode: operationalQuality.operational_quality_mode,
      chosen_scenario: operationalQuality.chosen_scenario,
      rejected_scenarios: operationalQuality.rejected_scenarios,
      justification: operationalQuality.justification,
      trade_offs: operationalQuality.trade_offs,
      operational_quality_decision:
        operationalQuality.operational_quality_decision,
      createdAt: schedule.createdAt,
      updatedAt: schedule.updatedAt,
      blocks: hydratedBlocks,
      duties: hydratedDuties,
      resultSummary,
      rosterCount: Number(meta.roster_count || 0),
      totalBlocks: blocks.length,
      totalTrips: uniqueTripIds.length,
    };

    // 4. Salvar no Cache antes de retornar
    this.scheduleCache.set(companyId, {
      data: finalResult,
      timestamp: Date.now(),
    });

    return finalResult;
  }

  private normalizeDutyTimeSegments(
    rawSegments: any[],
    tripDetailsById: Map<number, any>,
  ): Record<string, any>[] {
    if (!Array.isArray(rawSegments) || rawSegments.length === 0) {
      return [];
    }

    const segments = rawSegments.map((segment) => {
      const type = String(segment?.type ?? segment?.event_type ?? 'unknown');
      const tripIds = Array.isArray(segment?.trip_ids)
        ? segment.trip_ids
            .map((tripId: unknown) => this.toPositiveInteger(tripId))
            .filter((tripId): tripId is number => tripId != null)
        : [];
      const tripDetails = this.sortOperationalTrips(
        tripIds
          .map((tripId) => tripDetailsById.get(tripId))
          .filter((trip): trip is Record<string, any> => !!trip),
      );
      const inferredBlockId = this.resolveSegmentBlockId(segment, tripDetails);
      const directions = [
        ...new Set(tripDetails.map((trip) => trip.direction).filter(Boolean)),
      ];
      const tripGroupIds = [
        ...new Set(
          tripDetails
            .map((trip) => this.toPositiveInteger(trip.trip_group_id))
            .filter((value): value is number => value != null),
        ),
      ];
      const tripCount = tripIds.length;
      const bundleEventType =
        type === 'commercial_trip' && tripCount > 1
          ? 'commercial_trip_bundle'
          : type;
      const eventScope =
        typeof segment?.event_scope === 'string' &&
        segment.event_scope.trim().length > 0
          ? segment.event_scope.trim()
          : type === 'commercial_trip' || type === 'deadhead'
            ? 'driver_vehicle'
            : 'driver';
      const normalizedSegment: Record<string, any> = {
        ...segment,
        type,
        event_type: type,
        block_id: inferredBlockId,
        vehicle_id: inferredBlockId,
        event_scope: eventScope,
        trip_ids: tripIds,
        trip_count: tripCount,
        trip_directions: directions,
        trip_group_ids: tripGroupIds,
      };

      if (bundleEventType !== type) {
        normalizedSegment.bundle_event_type = bundleEventType;
        normalizedSegment.explanation =
          normalizedSegment.explanation ??
          `Segmento operacional agrupado com ${tripCount} viagens reais.`;
      }

      return normalizedSegment;
    });

    // Gap/boundary types already have driver_vehicle_change emitted by the Python solver before them.
    // Only non-gap commercial segments could ever need a synthetic insertion as a safety net.
    const GAP_SEGMENT_TYPES = new Set([
      'driver_idle',
      'idle',
      'normal_break',
      'mandatory_rest',
      'duty_start',
      'duty_end',
      'pullout',
      'pullback',
    ]);

    const normalizedSegments: Record<string, any>[] = [];
    segments.forEach((segment, index) => {
      const segmentType = String(
        segment.type ?? segment.event_type ?? 'unknown',
      );
      const fromBlockId = this.toPositiveInteger(segment.from_block_id);
      const toBlockId = this.toPositiveInteger(segment.to_block_id);
      if (
        fromBlockId != null &&
        toBlockId != null &&
        fromBlockId !== toBlockId &&
        segmentType !== 'driver_vehicle_change' &&
        !GAP_SEGMENT_TYPES.has(segmentType)
      ) {
        normalizedSegments.push(
          this.buildDriverVehicleChangeSegment(segment, fromBlockId, toBlockId),
        );
      }

      normalizedSegments.push(segment);

      const nextSegment = segments[index + 1];
      if (!nextSegment) {
        return;
      }
      const nextType = String(
        nextSegment.type ?? nextSegment.event_type ?? 'unknown',
      );
      if (segmentType !== 'commercial_trip' || nextType !== 'commercial_trip') {
        return;
      }

      const currentBlockId = this.toPositiveInteger(segment.block_id);
      const nextBlockId = this.toPositiveInteger(nextSegment.block_id);
      const currentEnd = Number(segment.end ?? segment.start ?? 0);
      const nextStart = Number(nextSegment.start ?? currentEnd);
      if (
        currentBlockId != null &&
        nextBlockId != null &&
        currentBlockId !== nextBlockId &&
        nextStart <= currentEnd
      ) {
        normalizedSegments.push(
          this.buildDriverVehicleChangeSegment(
            segment,
            currentBlockId,
            nextBlockId,
          ),
        );
      }
    });

    return normalizedSegments;
  }

  private buildDetailedDutyTripAssignments(
    dutyId: number,
    dutyTripIds: number[],
    dutyTimeSegments: Record<string, any>[],
    tripDetailsById: Map<number, any>,
  ): Record<string, any>[] {
    const detailedTrips: Record<string, any>[] = [];
    const seenTripIds = new Set<number>();

    const appendTrip = (
      trip: Record<string, any>,
      segmentSequence: number | null,
      sequenceInBundle: number,
      bundleTripCount: number,
      bundleType: string,
    ) => {
      const sourceTripId = this.toPositiveInteger(
        trip.source_trip_id ?? trip.id,
      );
      if (sourceTripId == null || seenTripIds.has(sourceTripId)) {
        return;
      }
      seenTripIds.add(sourceTripId);
      detailedTrips.push({
        ...trip,
        trip_id: trip.trip_id ?? trip.id,
        duty_id: dutyId,
        driver_id: dutyId,
        event_scope: 'trip',
        sequence_in_duty: detailedTrips.length + 1,
        segment_sequence: segmentSequence,
        sequence_in_bundle: sequenceInBundle,
        bundle_trip_count: bundleTripCount,
        bundle_event_type: bundleType,
        is_paired: bundleTripCount > 1,
      });
    };

    dutyTimeSegments.forEach((segment, index) => {
      const segmentType = String(
        segment.type ?? segment.event_type ?? 'unknown',
      );
      if (segmentType !== 'commercial_trip') {
        return;
      }
      const segmentTrips = this.sortOperationalTrips(
        (segment.trip_ids || [])
          .map((tripId: unknown) => this.toPositiveInteger(tripId))
          .filter((tripId): tripId is number => tripId != null)
          .map((tripId) => tripDetailsById.get(tripId))
          .filter((trip): trip is Record<string, any> => !!trip),
      );
      segmentTrips.forEach((trip, tripIndex) => {
        appendTrip(
          trip,
          index + 1,
          tripIndex + 1,
          segmentTrips.length,
          String(
            segment.bundle_event_type ?? segment.type ?? 'commercial_trip',
          ),
        );
      });
    });

    this.sortOperationalTrips(
      dutyTripIds
        .map((tripId) => tripDetailsById.get(tripId))
        .filter((trip): trip is Record<string, any> => !!trip),
    ).forEach((trip) => {
      appendTrip(trip, null, 1, 1, 'commercial_trip');
    });

    return detailedTrips;
  }

  private buildDriverVehicleChangeSegment(
    segment: Record<string, any>,
    fromBlockId: number,
    toBlockId: number,
  ) {
    const timestamp = Number(segment.start ?? segment.end ?? 0);
    return {
      type: 'driver_vehicle_change',
      event_type: 'driver_vehicle_change',
      event_scope: 'driver',
      start: timestamp,
      end: timestamp,
      duration: 0,
      location:
        segment.location ??
        segment.location_start ??
        segment.location_end ??
        null,
      from_block_id: fromBlockId,
      to_block_id: toBlockId,
      from_vehicle_id: fromBlockId,
      to_vehicle_id: toBlockId,
      explanation:
        'Motorista troca de veículo entre blocos distintos da mesma jornada.',
    };
  }

  private resolveSegmentBlockId(
    segment: Record<string, any>,
    tripDetails: Record<string, any>[],
  ): number | null {
    const explicitBlockId = this.toPositiveInteger(segment.block_id);
    if (explicitBlockId != null) {
      return explicitBlockId;
    }

    const fromBlockId = this.toPositiveInteger(segment.from_block_id);
    if (fromBlockId != null) {
      return fromBlockId;
    }

    const toBlockId = this.toPositiveInteger(segment.to_block_id);
    if (toBlockId != null) {
      return toBlockId;
    }

    for (const trip of tripDetails) {
      const tripBlockId = this.toPositiveInteger(
        trip.block_id ?? trip.vehicle_id,
      );
      if (tripBlockId != null) {
        return tripBlockId;
      }
    }

    return null;
  }

  private sortOperationalTrips(
    trips: Record<string, any>[],
  ): Record<string, any>[] {
    return [...trips].sort((left, right) => {
      const startDiff =
        Number(left.start_time ?? 0) - Number(right.start_time ?? 0);
      if (startDiff !== 0) {
        return startDiff;
      }

      const endDiff = Number(left.end_time ?? 0) - Number(right.end_time ?? 0);
      if (endDiff !== 0) {
        return endDiff;
      }

      return Number(left.id ?? 0) - Number(right.id ?? 0);
    });
  }

  private summarizeTripGroupPayload(trips: Trip[]): Record<string, number> {
    const grouped = new Map<number, Set<number>>();
    for (const trip of trips) {
      const groupId = this.normalizeTripGroupId(trip.tripGroupId);
      if (groupId === null) continue;
      grouped.set(groupId, grouped.get(groupId) || new Set<number>());
      grouped.get(groupId)?.add(Number(trip.id));
    }

    let groupCount = 0;
    let groupedTripCount = 0;
    let maxGroupSize = 0;
    for (const ids of grouped.values()) {
      if (ids.size < 2) continue;
      groupCount += 1;
      groupedTripCount += ids.size;
      if (ids.size > maxGroupSize) {
        maxGroupSize = ids.size;
      }
    }

    return {
      group_count: groupCount,
      grouped_trip_count: groupedTripCount,
      max_group_size: maxGroupSize,
    };
  }

  private normalizeTripGroupId(value: unknown): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed === 0) {
      return null;
    }
    return parsed;
  }

  private resolveLineId(
    lineId: unknown,
    lineCode: unknown,
    fallback: number | null,
  ): number | null {
    const numericLineId = this.toPositiveInteger(lineId);
    if (numericLineId !== null) {
      return numericLineId;
    }

    const numericLineCode = this.parseLineCode(lineCode);
    if (numericLineCode !== null) {
      return numericLineCode;
    }

    return fallback;
  }

  private toPositiveInteger(value: unknown): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }

    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return null;
    }

    const normalized = Math.round(parsed);
    return normalized > 0 ? normalized : null;
  }

  private parseLineCode(value: unknown): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }

    // eslint-disable-next-line @typescript-eslint/no-base-to-string
    const digits = String(value).replace(/\D/g, '');
    if (!digits) {
      return null;
    }

    const parsed = Number(digits);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  private resolveRequestedOperationalQualityMode(
    override: unknown,
    persistedValue: unknown,
  ): 'strict' | 'balanced' | 'optimized' | null {
    const normalizedOverride = this.normalizeOperationalQualityMode(override);
    const overrideWasProvided =
      override !== null &&
      override !== undefined &&
      // eslint-disable-next-line @typescript-eslint/no-base-to-string
      String(override).trim() !== '';
    if (overrideWasProvided) {
      return normalizedOverride;
    }
    return this.normalizeOperationalQualityMode(persistedValue) ?? 'balanced';
  }

  private normalizeOperationalQualityMode(
    value: unknown,
  ): 'strict' | 'balanced' | 'optimized' | null {
    if (value === null || value === undefined) {
      return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-base-to-string
    const normalized = String(value).trim().toLowerCase();
    if (
      normalized === 'strict' ||
      normalized === 'balanced' ||
      normalized === 'optimized'
    ) {
      return normalized;
    }
    return null;
  }

  private extractOperationalQualityMetadata(
    source: any,
    context: Record<string, any> = {},
  ): {
    operational_quality_mode: 'strict' | 'balanced' | 'optimized';
    chosen_scenario: string | null;
    rejected_scenarios: any[];
    justification: string[];
    trade_offs: string[];
    operational_quality_decision: Record<string, any> | null;
  } {
    const containers = [
      source,
      source?.meta,
      source?.result,
      source?.result?.meta,
      source?.result?.result,
      source?.result?.result?.meta,
      source?.metadata,
      source?.result?.metadata,
      source?.result?.result?.metadata,
      source?.resultSummary,
      source?.resultSummary?.meta,
      source?.resultSummary?.metadata,
    ].filter((item) => item && typeof item === 'object');
    const populatedDecision = this.pickFirstObject(
      containers.map((item) => item.operational_quality_decision),
      true,
    );
    const chosenScenario = this.pickFirstString([
      ...containers.map((item) => item.chosen_scenario),
      populatedDecision?.chosen_scenario,
    ]);
    const rejectedScenarios = this.pickFirstArray(
      [
        ...containers.map((item) => item.rejected_scenarios),
        populatedDecision?.rejected_scenarios,
      ],
      [],
    );
    const justification = this.pickFirstArray(
      [
        ...containers.map((item) => item.justification),
        populatedDecision?.justification,
      ],
      [],
    ) as string[];
    const tradeOffs = this.pickFirstArray(
      [
        ...containers.map((item) => item.trade_offs),
        populatedDecision?.trade_offs,
      ],
      [],
    ) as string[];
    const resolvedMode =
      this.normalizeOperationalQualityMode(
        populatedDecision?.mode ??
          this.pickFirstString([
            ...containers.map((item) => item.operational_quality_mode),
            context?.optimizationParams?.operational_quality_mode,
            context?.request_metadata?.operational_quality_mode,
          ]),
      ) ?? 'balanced';
    const decision =
      populatedDecision ??
      (chosenScenario ||
      rejectedScenarios.length ||
      justification.length ||
      tradeOffs.length
        ? {
            mode: resolvedMode,
            chosen_scenario: chosenScenario,
            rejected_scenarios: rejectedScenarios,
            justification,
            trade_offs: tradeOffs,
          }
        : null);

    return {
      operational_quality_mode: resolvedMode,
      chosen_scenario: chosenScenario,
      rejected_scenarios: rejectedScenarios,
      justification,
      trade_offs: tradeOffs,
      operational_quality_decision: decision,
    };
  }

  private listObjectKeys(value: unknown): string[] {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return [];
    }
    return Object.keys(value as Record<string, any>);
  }

  private pickFirstString(values: unknown[]): string | null {
    for (const value of values) {
      if (typeof value === 'string' && value.trim() !== '') {
        return value;
      }
    }
    return null;
  }

  private pickFirstArray(values: unknown[], fallback: any[]): any[] {
    for (const value of values) {
      if (Array.isArray(value) && value.length > 0) {
        return value;
      }
    }
    for (const value of values) {
      if (Array.isArray(value)) {
        return value;
      }
    }
    return fallback;
  }

  private pickFirstObject(
    values: unknown[],
    requireKeys = false,
  ): Record<string, any> | null {
    for (const value of values) {
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        continue;
      }
      if (
        !requireKeys ||
        Object.keys(value as Record<string, any>).length > 0
      ) {
        return value as Record<string, any>;
      }
    }
    return null;
  }

  private summarizeCostBreakdown(costBreakdown: any) {
    if (!costBreakdown || typeof costBreakdown !== 'object') return {};

    const summary: Record<string, any> = {};
    for (const [key, value] of Object.entries(costBreakdown)) {
      if (key === 'total') {
        summary[key] = value;
        continue;
      }
      if (key === 'shares' && value && typeof value === 'object') {
        summary[key] = { ...value };
        continue;
      }
      if (!value || typeof value !== 'object') continue;
      summary[key] = Object.fromEntries(
        Object.entries(value).filter(
          ([bucketKey]) => bucketKey !== 'blocks' && bucketKey !== 'duties',
        ),
      );
    }
    return summary;
  }

  private summarizeSolverExplanation(explanation: any) {
    if (!explanation || typeof explanation !== 'object') return null;

    const hard = Array.isArray(explanation?.issues?.hard)
      ? explanation.issues.hard
      : [];
    const soft = Array.isArray(explanation?.issues?.soft)
      ? explanation.issues.soft
      : [];
    const trimIssue = (issue: any) => {
      if (!issue || typeof issue !== 'object') return issue;
      return {
        raw: issue.raw ?? null,
        code: issue.code ?? null,
        severity: issue.severity ?? null,
        phase: issue.phase ?? null,
        message: issue.message ?? null,
        refs: Array.isArray(issue.refs) ? issue.refs.slice(0, 3) : [],
      };
    };

    return {
      status: explanation.status ?? null,
      headline: explanation.headline ?? null,
      summary: Array.isArray(explanation.summary)
        ? explanation.summary.slice(0, 5)
        : [],
      issues: {
        hard: hard.slice(0, this.DETAIL_LIMIT).map(trimIssue),
        soft: soft.slice(0, this.DETAIL_LIMIT).map(trimIssue),
        hard_count: Number(explanation?.issues?.hard_count ?? hard.length ?? 0),
        soft_count: Number(explanation?.issues?.soft_count ?? soft.length ?? 0),
      },
      recommendations: Array.isArray(explanation.recommendations)
        ? explanation.recommendations.slice(0, 5)
        : [],
    };
  }

  private summarizeTripGroupAudit(audit: any) {
    if (!audit || typeof audit !== 'object') return null;
    return {
      groups_total: audit.groups_total ?? null,
      groups_fully_assigned: audit.groups_fully_assigned ?? null,
      same_block_groups: audit.same_block_groups ?? null,
      same_duty_groups: audit.same_duty_groups ?? null,
      same_roster_groups: audit.same_roster_groups ?? null,
      split_groups: audit.split_groups ?? null,
      missing_groups: audit.missing_groups ?? null,
      same_roster_ratio: audit.same_roster_ratio ?? null,
      sample_splits: Array.isArray(audit.sample_splits)
        ? audit.sample_splits.slice(0, this.DETAIL_LIMIT)
        : [],
    };
  }

  async rosteringWeekly(body: any) {
    const { data } = await axios.post(
      `${this.OPTIMIZER_URL}/optimize/rostering/weekly`,
      body,
      { headers: this.getOptimizerHeaders(), timeout: 120000 },
    );
    return data;
  }
}
