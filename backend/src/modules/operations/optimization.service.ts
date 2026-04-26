import { Injectable, Logger, InternalServerErrorException, ConflictException, BadRequestException, OnModuleInit } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource, In } from 'typeorm';
import axios from 'axios';
import { Trip } from '../database/entities/trip.entity';
import { Driver } from '../database/entities/driver.entity';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { Schedule, ScheduleStatus } from '../database/entities/schedule.entity';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
import { OptimizationGateway } from './optimization.gateway';
import { ConfigService } from '@nestjs/config';
import { TenantContext } from '../../common/context/tenant-context';

@Injectable()
export class OptimizationService implements OnModuleInit {
  private readonly logger = new Logger(OptimizationService.name);
  private scheduleCache = new Map<number, { data: any; timestamp: number }>();
  private readonly CACHE_TTL_MS = 15000;
  private readonly OPTIMIZER_URL = process.env.OPTIMIZER_URL || 'http://localhost:8000';
  private readonly INTERNAL_KEY: string;
  private readonly DETAIL_LIMIT = 10;

  constructor(
    @InjectRepository(Trip) private tripRepo: Repository<Trip>,
    @InjectRepository(Driver) private driverRepo: Repository<Driver>,
    @InjectRepository(CompanyParameters) private paramRepo: Repository<CompanyParameters>,
    @InjectRepository(Schedule) private scheduleRepo: Repository<Schedule>,
    private dataSource: DataSource,
    private gateway: OptimizationGateway,
    private configService: ConfigService,
    private tenantContext: TenantContext,
  ) {
    this.INTERNAL_KEY = this.configService.get<string>('INTERNAL_OPTIMIZER_KEY') || 'internal-key-123456';
  }

  async onModuleInit() {
    const stale = await this.scheduleRepo.update(
      { status: ScheduleStatus.PROCESSING },
      { status: ScheduleStatus.FAILED },
    );
    if (stale.affected && stale.affected > 0) {
      this.logger.warn(`Cleared ${stale.affected} stale PROCESSING lock(s) on startup`);
    }
  }

  async runOptimization(companyId: number, algorithm?: string) {
    // 0. Tenant Lock: Verificar se já existe uma otimização em andamento
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
        `Schedule ${activeSchedule.id} preso em PROCESSING desde ${activeSchedule.createdAt}. Ignorando trava por timeout (1h).`,
      );
    }

    // 1. Criar registro inicial do Schedule
    const schedule = await this.scheduleRepo.save({
      companyId,
      status: ScheduleStatus.PROCESSING,
    });

    try {
      // 2. Coletar Dados para o Solver
      const [trips, drivers, params] = await Promise.all([
        this.tripRepo.find({ where: { companyId }, order: { startTime: 'ASC' } }),
        this.driverRepo.find({ where: { companyId } }),
        this.paramRepo.findOne({ where: { companyId } }),
      ]);

      if (!trips.length) throw new Error('Nenhuma viagem encontrada para otimização.');

      const cctParams = this.buildCctParams(params);
      const vspParams = this.buildVspParams(params, cctParams);
      const forceRoundTrip =
        Boolean(params?.force_round_trip) ||
        Boolean(cctParams.enforce_trip_groups_hard) ||
        Boolean(cctParams.operator_pairing_hard);
      const allowVehicleSwap = cctParams.operator_single_vehicle_only
        ? false
        : (params?.allow_vehicle_swap ?? true);

      // 3. Chamar API Python (FastAPI/Celery)
      const payload = {
        trips: trips.map((t) => {
          const st = Number(t.startTime);
          // Normaliza virada de meia-noite: se end < start, soma 1440
          const et = Number(t.endTime) < st ? Number(t.endTime) + 1440 : Number(t.endTime);
          // Deriva trip_group_id a partir do pairId (ex: "P097" → 97) para que
          // pares IDA-VOLTA com gap=0 sejam tratados como grupo forçado pelo optimizer.
          const tripGroupId = t.tripGroupId
            ? Number(t.tripGroupId)
            : t.pairId
              ? parseInt(t.pairId.replace(/\D/g, ''), 10) || null
              : null;
          return {
            id: t.id,
            line_id: this.resolveLineId(t.lineId, t.lineCode, 0),
            trip_group_id: tripGroupId,
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
          };
        }),
        vehicle_types: [
          {
            id: 1,
            name: 'Padrao',
            passenger_capacity: 40,
            cost_per_km: 1.0,
            cost_per_hour: 10.0,
            fixed_cost: Number(params?.vehicle_fixed_cost || 800),
          },
        ],
        cct_params: cctParams,
        optimization_params: {
          cost_vehicle: params?.cost_vehicle ?? 1000.0,
          cost_km: params?.cost_km ?? 1.0,
          cost_duty: params?.cost_duty ?? 500.0,
          force_round_trip: forceRoundTrip,
          allow_vehicle_swap: allowVehicleSwap,
        },
        vsp_params: vspParams,
        time_budget_s: params?.time_budget_s ?? null,
        algorithm: algorithm || 'hybrid_pipeline',
        company_id: companyId,
        run_id: schedule.id,
      };

      const { data: submitData } = await axios.post(`${this.OPTIMIZER_URL}/optimize/`, payload, {
        headers: { 'X-Internal-Key': this.INTERNAL_KEY },
      });
      const taskId = submitData.task_id;

      this.gateway.notifyOptimizationQueued(companyId, { scheduleId: schedule.id, taskId });

      // 4. Iniciar Polling no Backend (Processo em Background)
      this.pollOptimizerTask(taskId, schedule.id, companyId);

      return { scheduleId: schedule.id, taskId };
    } catch (error) {
      this.logger.error(`Falha ao iniciar otimização: ${error.message}`);
      await this.scheduleRepo.update(schedule.id, { status: ScheduleStatus.FAILED });
      throw new InternalServerErrorException(error.message);
    }
  }

  async aiChat(metrics: any, question: string) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada.');

    try {
      // Busca os parâmetros reais configurados para esta empresa
      const params = await this.paramRepo.findOne({ where: { companyId } });
      const cctParams = this.buildCctParams(params);

      const { data } = await axios.post(`${this.OPTIMIZER_URL}/optimize/chat`, {
        metrics: {
          ...metrics,
          current_parameters: cctParams, // Agora a IA sabe suas regras atuais!
        },
        question,
      }, {
        headers: { 'X-Internal-Key': this.INTERNAL_KEY },
        timeout: 70000,
      });
      return data;
    } catch (error) {
      this.logger.error(`Erro no chat de IA: ${error.message}`);
      return { answer: 'O serviço de IA está temporariamente indisponível. Tente novamente em instantes.', status: 'error' };
    }
  }

  private async pollOptimizerTask(taskId: string, scheduleId: number, companyId: number) {
    const maxAttempts = 120; // 10 minutos (5s * 120)
    const maxConsecutiveErrors = 12;
    const pollIntervalMs = 5000;
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
        void this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
        this.gateway.notifyOptimizationStale(companyId, { scheduleId, taskId });
        this.gateway.notifyOptimizationFailed(companyId, 'Timeout na otimização.');
        return;
      }

      nextTimer = setTimeout(() => {
        void runPoll();
      }, pollIntervalMs);
    };

    const runPoll = async () => {
      if (done) return;
      attempts++;
      try {
        const { data } = await axios.get(`${this.OPTIMIZER_URL}/optimize/status/${taskId}`, {
          headers: { 'X-Internal-Key': this.INTERNAL_KEY },
          timeout: 10000,
        });

        consecutiveErrors = 0; // Reset error counter on success

        if (data.status === 'completed') {
          done = true;
          clearNextTimer();
          await this.persistResults(scheduleId, companyId, data.result);
          // Invalidar cache para que o usuário veja o novo resultado imediatamente
          this.scheduleCache.delete(companyId);
          // Enviamos apenas um sinal de conclusão leve via Socket.io para evitar OOM no envio.
          // O Frontend buscará os dados completos via API (fetchData).
          this.gateway.notifyOptimizationFinished(companyId, scheduleId, { status: 'completed' });
        } else if (data.status === 'failed') {
          done = true;
          clearNextTimer();
          const errMsg = data.error?.message || data.error?.error_message || 'Erro no motor de otimização.';
          await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
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
        consecutiveErrors++;
        this.logger.warn(`Erro no polling do task ${taskId} (${consecutiveErrors}/${maxConsecutiveErrors}): ${error.message}`);

        if (consecutiveErrors >= maxConsecutiveErrors) {
          done = true;
          clearNextTimer();
          this.logger.error(`Falha permanente no polling do task ${taskId}`);
          await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
          this.gateway.notifyOptimizationFailed(companyId, 'Erro de comunicação com o solver.');
          return;
        }

        if (!done) {
          scheduleNextPoll();
        }
      }
    };

    void runPoll();
  }

  private async persistResults(scheduleId: number, companyId: number, result: any) {
    this.logger.log(`Persistindo resultados para Schedule ${scheduleId}. Blocks: ${(result.blocks||[]).length}, Duties: ${(result.duties||[]).length}`);

    try {
    await this.dataSource.transaction(async (manager) => {
      const solverExplanation = this.summarizeSolverExplanation(result.solver_explanation ?? null);
      const hardIssues = Array.isArray(solverExplanation?.issues?.hard) ? solverExplanation.issues.hard : [];
      const softIssues = Array.isArray(solverExplanation?.issues?.soft) ? solverExplanation.issues.soft : [];
      const hardIssueCount = Number(solverExplanation?.issues?.hard_count ?? hardIssues.length ?? 0);
      const softIssueCount = Number(solverExplanation?.issues?.soft_count ?? softIssues.length ?? 0);
      const reportedViolations = Math.max(Number(result.cct_violations ?? 0), hardIssues.length);

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
            tripIds: (b.trips || []).map((t: any) => (typeof t === 'number' ? t : t.id)),
            cost: b.total_cost ?? b.activation_cost ?? 0,
            // CORREÇÃO: Apenas os campos essenciais, sem usar "...b"
            metadata: {
              start_time: b.start_time,
              end_time: b.end_time,
              activation_cost: b.activation_cost,
              deadhead_minutes: b.deadhead_minutes,
              idle_minutes: b.idle_minutes,
              start_depot_id: b.start_depot_id,
              end_depot_id: b.end_depot_id
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
            : (d.trips || []).map((t: any) => (typeof t === 'number' ? t : (t.trip_id ?? t.id)));
          return manager.create(DutyAssignment, {
            companyId,
            scheduleId,
            dutyId: d.duty_id ?? d.id ?? 0,
            tripIds: dutyTripIds.filter((id: any) => Number.isFinite(Number(id)) && Number(id) > 0).map((id: any) => Number(id)),
            cost: d.total_cost ?? 0,
            // CORREÇÃO: Apenas os campos essenciais, sem usar "...d"
            metadata: {
              work_time: d.work_time,
              spread_time: d.spread_time,
              start_time: d.start_time,
              end_time: d.end_time,
              work_cost: d.work_cost,
              overtime_cost: d.overtime_cost,
              overtime_minutes: d.overtime_minutes,
              shift_violations: d.shift_violations,
              rest_violations: d.rest_violations
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
        cost_breakdown: this.summarizeCostBreakdown(result.cost_breakdown ?? {}),
        phase_summary: result.phase_summary ?? result.meta?.phase_summary ?? null,
        trip_group_audit: this.summarizeTripGroupAudit(result.trip_group_audit ?? result.meta?.trip_group_audit ?? null),
        reproducibility: result.reproducibility ?? result.meta?.reproducibility ?? null,
        performance: result.performance ?? result.meta?.performance ?? null,
        hard_constraint_report: result.meta?.hard_constraint_report ?? null,
        operational_kpis: result.meta?.operational_kpis ?? null,
        resolved_params: result.meta?.input ?? null,
        num_vehicles: result.vehicles ?? 0,
        num_duties: result.crew ?? 0,
        total_trips: result.total_trips ?? 0,
        algorithm: result.vsp_algorithm ?? '',
      };

      await manager.update(Schedule, scheduleId, {
        status: ScheduleStatus.COMPLETED,
        totalCost: result.total_cost ?? 0,
        cctViolations: reportedViolations,
        metadata: scheduleMetadata as any,
      });
    });
    } catch (err: any) {
      this.logger.error(`persistResults FALHOU para Schedule ${scheduleId}: ${err.message}`, err.stack);
      throw err;
    }
  }

  async reassignTrip(companyId: number, scheduleId: number, tripId: number, targetBlockId: number) {
    return this.dataSource.transaction(async (manager) => {
      // 1. Buscar a viagem e os blocos envolvidos
      const trip = await manager.findOne(Trip, { where: { id: tripId, companyId } });
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
        throw new InternalServerErrorException('Viagem ou Bloco de destino não encontrado.');
      }

      // 2. Rule Checker: Sobreposição e Viabilidade
      const violations: string[] = [];
      const targetTrips: Trip[] = await manager.find(Trip, {
        where: { id: In(targetBlock.tripIds) },
      });

      // Validar sobreposição temporal no bloco de destino
      for (const t of targetTrips) {
        if (trip.startTime < t.endTime && trip.endTime > t.startTime) {
          violations.push(`Sobreposição temporal com Viagem ${t.tripId || t.id}.`);
        }
      }

      // 4. Sincronização com Motor Python (What-If) para recálculo de custo real
      const companyParams = await manager.findOne(CompanyParameters, { where: { companyId } });
      const allBlocks = await manager.find(BlockAssignment, { where: { scheduleId, companyId } });
      
      const whatIfPayload = {
        blocks: allBlocks.map(b => ({
          id: b.blockId,
          vehicle_type_id: 1, // Padrao
          trips: b.metadata?.trips || [],
        })),
        source_block_id: sourceBlock?.blockId || 0,
        target_block_id: targetBlock.blockId,
        trip_ids: [tripId],
        target_index: 0, // O motor resolve o sort cronológico internamente
        optimization_params: {
          cost_vehicle: companyParams?.cost_vehicle ?? 1000.0,
          cost_km: companyParams?.cost_km ?? 1.0,
          cost_duty: companyParams?.cost_duty ?? 500.0,
        },
      };

      try {
        const { data: whatIfResult } = await axios.post(`${this.OPTIMIZER_URL}/api/v1/evaluate-delta`, whatIfPayload, {
          headers: { 'X-Internal-Key': this.INTERNAL_KEY },
        });
        
        // 5. Atualizar custos persistidos no banco
        if (whatIfResult.status === 'ok') {
          // Atualizar custo individual de cada bloco alterado
          for (const bResp of whatIfResult.blocks) {
            await manager.update(BlockAssignment, { scheduleId, blockId: bResp.block_id, companyId }, {
              cost: bResp.total_cost,
              metadata: { ... (allBlocks.find(b => b.blockId === bResp.block_id)?.metadata || {}), ...bResp }
            });
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
      } catch (error) {
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
      return { isValid: false, violations: [`Viagem ${move.trip_id} não encontrada nos blocos`], blocks: [], totalCost: null, deltaCost: null };
    }

    const pythonBlocks = blocks.map((b: any) => ({
      id: b.block_id ?? b.id,  // Python whatif.py lê 'id', não 'block_id'
      trips: (b.trips || []).map((t: any) => ({
        id: t.id ?? t.tripId,
        start_time: t.start_time ?? t.startTime,
        end_time: t.end_time ?? t.endTime,
        line_id: this.resolveLineId(t.line_id ?? t.lineId, t.line_code ?? t.lineCode, 0),
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
      const { data } = await axios.post(`${this.OPTIMIZER_URL}/api/v1/evaluate-delta`, pythonPayload, {
        headers: { 'X-Internal-Key': this.INTERNAL_KEY },
        timeout: 15000,
      });
      return {
        isValid: true,
        violations: [],
        totalCost: data.cost_breakdown?.total ?? 0,
        deltaCost: 0,
        blocks: data.blocks,
      };
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Movimento viola restrições operacionais';
      return { isValid: false, violations: [detail], blocks: [], totalCost: null, deltaCost: null };
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
        line_id: this.resolveLineId(t.line_id ?? t.lineId, t.line_code ?? t.lineCode, 0),
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
      const { data } = await axios.post(`${this.OPTIMIZER_URL}/api/v1/evaluate-baseline`, { blocks: pythonBlocks }, {
        headers: { 'X-Internal-Key': this.INTERNAL_KEY },
        timeout: 15000,
      });
      return {
        totalCost: data.cost_breakdown?.total ?? data.total_cost ?? 0,
        costBreakdown: data.cost_breakdown ?? null,
        blocks: data.blocks ?? [],
      };
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Erro ao calcular baseline';
      return { totalCost: null, costBreakdown: null, blocks: [], error: detail };
    }
  }

  private buildCctParams(params: CompanyParameters | null): Record<string, any> {
    if (!params) {
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
      'max_shift_minutes', 'max_work_minutes', 'min_work_minutes', 'min_shift_minutes',
      'overtime_limit_minutes', 'max_driving_minutes', 'min_break_minutes',
      'connection_tolerance_minutes', 'mandatory_break_after_minutes',
      'split_break_first_minutes', 'split_break_second_minutes', 'meal_break_minutes',
      'inter_shift_rest_minutes', 'weekly_rest_minutes', 'reduced_weekly_rest_minutes',
      'allow_reduced_weekly_rest', 'daily_driving_limit_minutes',
      'extended_daily_driving_limit_minutes', 'max_extended_driving_days_per_week',
      'weekly_driving_limit_minutes', 'fortnight_driving_limit_minutes',
      'min_layover_minutes', 'pullout_minutes', 'pullback_minutes',
      'idle_time_is_paid', 'waiting_time_pay_pct', 'min_guaranteed_work_minutes',
      'max_unpaid_break_minutes', 'max_total_unpaid_break_minutes',
      'long_unpaid_break_limit_minutes', 'long_unpaid_break_penalty_weight',
      'allow_relief_points', 'enforce_same_depot_start_end',
      'fairness_weight', 'fairness_target_work_minutes', 'fairness_tolerance_minutes',
      'operator_change_terminals_only', 'enforce_trip_groups_hard', 'operator_pairing_hard',
      'sunday_off_weight', 'holiday_extra_pct', 'enforce_single_line_duty',
      'operator_single_vehicle_only', 'nocturnal_start_hour', 'nocturnal_end_hour',
      'nocturnal_factor', 'nocturnal_extra_pct', 'apply_cct',
      'strict_hard_validation', 'strict_union_rules', 'terminal_location_ids',
      'goal_weights', 'dynamic_rules',
    ];

    const result: Record<string, any> = {};
    for (const field of cctFields) {
      const value = params[field];
      if (value !== null && value !== undefined) {
        result[field] = value;
      }
    }

    // Fallbacks obrigatorios
    if (!result.max_work_minutes) result.max_work_minutes = params.max_driving_time_minutes || 480;
    if (!result.max_shift_minutes) result.max_shift_minutes = params.max_shift_minutes || 720;
    if (!result.meal_break_minutes) result.meal_break_minutes = params.meal_break_minutes || 60;
    if (params.force_round_trip) {
      result.enforce_trip_groups_hard = true;
      result.operator_pairing_hard = true;
    }
    if (params.allow_vehicle_swap === false) {
      result.operator_single_vehicle_only = true;
    }
    if (result.apply_cct === undefined) result.apply_cct = true;
    if (result.strict_hard_validation === undefined) result.strict_hard_validation = true;
    if (result.strict_union_rules === undefined) result.strict_union_rules = true;

    return result;
  }

  private buildVspParams(params: CompanyParameters | null, cctParams: Record<string, any> = {}): Record<string, any> {
    if (!params) {
      return {
        force_round_trip: true,
        allow_vehicle_swap: true,
        preferred_pair_window_minutes: 30,
        preserve_preferred_pairs: true,
      };
    }

    const vspFields: (keyof CompanyParameters)[] = [
      'time_budget_s', 'random_seed', 'max_vehicle_shift_minutes', 'max_vehicles',
      'min_layover_minutes', 'deadhead_cost_per_minute', 'idle_cost_per_minute',
      'allow_multi_line_block', 'allow_vehicle_split_shifts',
      'split_shift_min_gap_minutes', 'split_shift_max_gap_minutes',
      'max_simultaneous_chargers', 'enable_column_generation', 'pricing_enabled',
      'use_set_covering', 'min_workpiece_minutes', 'max_workpiece_minutes',
      'min_trips_per_piece', 'max_trips_per_piece', 'peak_energy_cost_per_kwh',
      'offpeak_energy_cost_per_kwh', 'preferred_pair_window_minutes',
      'preserve_preferred_pairs', 'pair_break_penalty', 'paired_trip_bonus',
      'max_connection_cost_for_reuse_ratio', 'max_candidate_successors_per_task',
      'max_generated_columns', 'max_pricing_iterations', 'max_pricing_additions',
      'vehicle_idle_gap_behavior', 'vehicle_idle_gap_threshold_minutes',
      'goal_weights',
    ];

    const result: Record<string, any> = {
      force_round_trip: params.force_round_trip ?? true,
      allow_vehicle_swap: params.allow_vehicle_swap ?? true,
      fixed_vehicle_activation_cost: params.vehicle_fixed_cost ?? 800.0,
      preferred_pair_window_minutes: params.preferred_pair_window_minutes ?? 30,
      preserve_preferred_pairs: params.preserve_preferred_pairs ?? true,
      vehicle_idle_gap_behavior: params.vehicle_idle_gap_behavior ?? 'solver_decides',
    };

    for (const field of vspFields) {
      const value = params[field];
      if (value !== null && value !== undefined) {
        result[field] = value;
      }
    }

    if (cctParams.connection_tolerance_minutes !== undefined && result.connection_tolerance_minutes === undefined) {
      result.connection_tolerance_minutes = cctParams.connection_tolerance_minutes;
    }
    if (cctParams.strict_hard_validation !== undefined && result.strict_hard_validation === undefined) {
      result.strict_hard_validation = cctParams.strict_hard_validation;
    }
    if (cctParams.enforce_same_depot_start_end !== undefined && result.same_depot_required === undefined) {
      result.same_depot_required = Boolean(cctParams.enforce_same_depot_start_end);
    }
    if (cctParams.max_shift_minutes !== undefined && result.max_vehicle_shift_minutes === undefined) {
      result.max_vehicle_shift_minutes = cctParams.max_shift_minutes;
    }
    if (cctParams.min_layover_minutes !== undefined) {
      result.min_layover_minutes = cctParams.min_layover_minutes;
    }
    if (cctParams.min_break_minutes !== undefined) {
      result.min_layover_minutes = Math.max(
        Number(result.min_layover_minutes ?? 0),
        Number(cctParams.min_break_minutes),
      );
    }
    if (cctParams.enforce_trip_groups_hard || cctParams.operator_pairing_hard) {
      result.force_round_trip = true;
      result.preserve_preferred_pairs = true;
    }
    if (cctParams.operator_single_vehicle_only) {
      result.allow_vehicle_swap = false;
    }

    return result;
  }

  async getLatestSchedule(companyId: number) {
    const cached = this.scheduleCache.get(companyId);
    const now = Date.now();
    if (cached) {
      if ((now - cached.timestamp) < this.CACHE_TTL_MS) {
        return cached.data; // Cache válido
      } else {
        this.scheduleCache.delete(companyId); // CORREÇÃO: Remove ativamente da RAM se expirou
      }
    }

    const schedule = await this.scheduleRepo.findOne({
      where: { companyId, status: ScheduleStatus.COMPLETED },
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

    const hydratedBlocks = blocks.map((block) => {
      const meta = (block.metadata || {}) as any;
      const st = meta.start_time ?? 0;
      const et = meta.end_time ?? 0;
      
      const hydratedTrips = (block.tripIds || [])
        .map((id) => tripMap.get(id))
        .filter((t): t is Trip => !!t)
        .map((t) => ({
          id: t.id,
          trip_id: t.tripId,
          start_time: Number(t.startTime),
          end_time: Number(t.endTime) < Number(t.startTime) ? Number(t.endTime) + 1440 : Number(t.endTime),
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
          // ...meta // Comentado para evitar carregar dumps pesados do solver no Gantt
        },
      };
    }).sort((a, b) => (a.block_id || 0) - (b.block_id || 0));

    // Monta resultSummary a partir do metadata salvo
    const meta = (schedule.metadata || {}) as any;
    const rawMeta = (meta.meta || {}) as any;
    const resolvedParams = meta.resolved_params ?? rawMeta.input ?? null;
    const lightMetadata = {
      input: resolvedParams,
      solver_version: meta.solver_version ?? rawMeta.solver_version ?? null,
    };
    const resultSummary = {
      num_vehicles: meta.num_vehicles ?? 0,
      vehicles: meta.num_vehicles ?? 0,
      num_crew: meta.num_duties ?? 0,
      crew: meta.num_duties ?? 0,
      total_cost: schedule.totalCost ?? meta.cost_breakdown?.total ?? 0,
      totalCost: schedule.totalCost ?? 0,
      cct_violations: schedule.cctViolations ?? 0,
      cctViolations: schedule.cctViolations ?? 0,
      total_trips: meta.total_trips ?? uniqueTripIds.length,
      unassigned_trips: meta.unassigned_trips ?? [],
      hardIssueCount: meta.hard_issue_count ?? (((meta.solver_explanation || {}).issues || {}).hard || []).length,
      softIssueCount: meta.soft_issue_count ?? (((meta.solver_explanation || {}).issues || {}).soft || []).length,
      hasHardViolations: (((meta.solver_explanation || {}).issues || {}).hard || []).length > 0,
      solverStatus: (meta.solver_explanation || {}).status ?? null,
      costBreakdown: this.summarizeCostBreakdown(meta.cost_breakdown ?? null),
      solverExplanation: null, // meta.solver_explanation ?? null, // Removido do polling por ser muito pesado
      phaseSummary: null, // meta.phase_summary ?? null,
      tripGroupAudit: null, // meta.trip_group_audit ?? null,
      reproducibility: null,
      performance: null,
      hardConstraintReport: null,
      metadata: lightMetadata,
      meta: lightMetadata,
      // blocks: hydratedBlocks, // REMOVIDO: Já enviado na raiz do objeto finalResult
      duties: duties.map((d) => {
        const dm = (d.metadata || {}) as any;
        return {
          duty_id: d.dutyId,
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
          trip_ids: d.tripIds ?? [],
        };
      }),
    };

    const finalResult = {
      id: schedule.id,
      companyId: schedule.companyId,
      status: schedule.status,
      totalCost: Number(schedule.totalCost),
      cctViolations: Number(schedule.cctViolations),
      createdAt: schedule.createdAt,
      updatedAt: schedule.updatedAt,
      blocks: hydratedBlocks,
      resultSummary,
    };

    // 4. Salvar no Cache antes de retornar
    this.scheduleCache.set(companyId, { data: finalResult, timestamp: Date.now() });

    return finalResult;
  }

  private resolveLineId(lineId: unknown, lineCode: unknown, fallback: number | null): number | null {
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

    const digits = String(value).replace(/\D/g, '');
    if (!digits) {
      return null;
    }

    const parsed = Number(digits);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
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
        Object.entries(value).filter(([bucketKey]) => bucketKey !== 'blocks' && bucketKey !== 'duties')
      );
    }
    return summary;
  }

  private summarizeSolverExplanation(explanation: any) {
    if (!explanation || typeof explanation !== 'object') return null;

    const hard = Array.isArray(explanation?.issues?.hard) ? explanation.issues.hard : [];
    const soft = Array.isArray(explanation?.issues?.soft) ? explanation.issues.soft : [];
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
      summary: Array.isArray(explanation.summary) ? explanation.summary.slice(0, 5) : [],
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
      sample_splits: Array.isArray(audit.sample_splits) ? audit.sample_splits.slice(0, this.DETAIL_LIMIT) : [],
    };
  }
}
