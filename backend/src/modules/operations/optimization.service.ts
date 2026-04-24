import { Injectable, Logger, InternalServerErrorException, ConflictException, BadRequestException } from '@nestjs/common';
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
export class OptimizationService {
  private readonly logger = new Logger(OptimizationService.name);
  private readonly OPTIMIZER_URL = process.env.OPTIMIZER_URL || 'http://localhost:8000';
  private readonly INTERNAL_KEY: string;

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

      // 3. Chamar API Python (FastAPI/Celery)
      const payload = {
        trips: trips.map((t) => {
          const st = Number(t.startTime);
          // Normaliza virada de meia-noite: se end < start, soma 1440
          const et = Number(t.endTime) < st ? Number(t.endTime) + 1440 : Number(t.endTime);
          return {
            id: t.id,                     // sempre DB id para que persistResults possa fazer lookup
            line_id: Number(t.lineId) || 0,
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
        cct_params: this.buildCctParams(params),
        optimization_params: {
          cost_vehicle: params?.cost_vehicle ?? 1000.0,
          cost_km: params?.cost_km ?? 1.0,
          cost_duty: params?.cost_duty ?? 500.0,
        },
        vsp_params: {
          force_round_trip: params?.force_round_trip ?? true,
          allow_vehicle_swap: params?.allow_vehicle_swap ?? true,
          preferred_pair_window_minutes: params?.preferred_pair_window_minutes ?? 30,
          preserve_preferred_pairs: params?.preserve_preferred_pairs ?? true,
          vehicle_idle_gap_behavior: params?.vehicle_idle_gap_behavior ?? 'solver_decides',
          vehicle_idle_gap_threshold_minutes: params?.vehicle_idle_gap_threshold_minutes ?? null,
        },
        time_budget_s: params?.time_budget_s ?? null,
        algorithm: algorithm || 'hybrid_pipeline',
        company_id: companyId,
        run_id: schedule.id,
      };

      const { data: submitData } = await axios.post(`${this.OPTIMIZER_URL}/optimize/`, payload, {
        headers: { 'X-Internal-Key': this.INTERNAL_KEY },
      });
      const taskId = submitData.task_id;

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
    const maxAttempts = 60; // 5 minutos (5s * 60)
    let attempts = 0;
    let done = false; // Evita duplo processamento em caso de sobreposição de ticks

    const interval = setInterval(async () => {
      if (done) return;
      attempts++;
      try {
        const { data } = await axios.get(`${this.OPTIMIZER_URL}/optimize/status/${taskId}`, {
          headers: { 'X-Internal-Key': this.INTERNAL_KEY },
        });

        if (data.status === 'completed') {
          done = true;
          clearInterval(interval);
          await this.persistResults(scheduleId, companyId, data.result);
          this.gateway.notifyOptimizationFinished(companyId, scheduleId, data.result);
        } else if (data.status === 'failed') {
          done = true;
          clearInterval(interval);
          const errMsg = data.error?.message || data.error?.error_message || 'Erro no motor de otimização.';
          await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
          this.gateway.notifyOptimizationFailed(companyId, errMsg);
        } else if (attempts >= maxAttempts) {
          done = true;
          clearInterval(interval);
          await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
          this.gateway.notifyOptimizationFailed(companyId, 'Timeout na otimização.');
        }
      } catch (error) {
        if (done) return;
        done = true;
        this.logger.error(`Erro no polling do task ${taskId}: ${error.message}`);
        clearInterval(interval);
        await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
        this.gateway.notifyOptimizationFailed(companyId, 'Erro de comunicação com o solver.');
      }
    }, 5000);
  }

  private async persistResults(scheduleId: number, companyId: number, result: any) {
    this.logger.log(`Persistindo resultados para Schedule ${scheduleId}. Blocks: ${(result.blocks||[]).length}, Duties: ${(result.duties||[]).length}`);

    try {
    await this.dataSource.transaction(async (manager) => {
      // 1. Salvar Blocos (Veículos)
      const blocks = (result.blocks || []).map((b: any) =>
        manager.create(BlockAssignment, {
          companyId,
          scheduleId,
          blockId: b.block_id ?? b.id ?? 0,
          tripIds: (b.trips || []).map((t: any) => (typeof t === 'number' ? t : t.id)),
          cost: b.total_cost ?? b.activation_cost ?? 0,
          metadata: b,
        }),
      );
      await manager.save(BlockAssignment, blocks);

      // 2. Salvar Duties (Motoristas)
      const duties = (result.duties || []).map((d: any) =>
        manager.create(DutyAssignment, {
          companyId,
          scheduleId,
          dutyId: d.duty_id ?? d.id ?? 0,
          tripIds: (d.trips || []).map((t: any) => (typeof t === 'number' ? t : t.id)),
          cost: d.total_cost ?? 0,
          metadata: d,
        }),
      );
      await manager.save(DutyAssignment, duties);

      // 3. Atualizar Header do Schedule
      await manager.update(Schedule, scheduleId, {
        status: ScheduleStatus.COMPLETED,
        totalCost: result.total_cost ?? 0,
        cctViolations: result.cct_violations ?? 0,
        metadata: {
          solver_explanation: result.solver_explanation ?? null,
          unassigned_trips: result.unassigned_trips ?? 0,
          cost_breakdown: result.cost_breakdown ?? {},
          num_vehicles: result.vehicles ?? 0,
          num_duties: result.crew ?? 0,
          total_trips: result.total_trips ?? 0,
          algorithm: result.vsp_algorithm ?? '',
        },
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

        return {
          isValid: violations.length === 0,
          violations,
          scheduleId,
          costBreakdown: whatIfResult.cost_breakdown,
        };
      } catch (error) {
        this.logger.error(`Falha no What-If Python: ${error.message}`);
        // Fallback: Mantém os dados locais mas avisa sobre a falha no recálculo
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
        line_id: t.line_id ?? t.lineId ?? 0,
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
        line_id: t.line_id ?? t.lineId ?? 0,
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
      return { max_work_minutes: 480, max_shift_minutes: 720, meal_break_minutes: 60 };
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

    return result;
  }

  async getLatestSchedule(companyId: number) {
    const schedule = await this.scheduleRepo.findOne({
      where: { companyId, status: ScheduleStatus.COMPLETED },
      relations: ['blocks', 'duties'],
      order: { createdAt: 'DESC' },
    });

    if (!schedule) return null;

    // Hidratar trips completos dentro de cada block
    const allTripIds = schedule.blocks.flatMap((b) => b.tripIds || []);
    const uniqueTripIds = [...new Set(allTripIds)];
    const tripMap = new Map<number, Trip>();

    if (uniqueTripIds.length > 0) {
      const trips = await this.tripRepo.find({ where: { id: In(uniqueTripIds) } });
      trips.forEach((t) => tripMap.set(t.id, t));
    }

    const hydratedBlocks = schedule.blocks.map((block) => {
      const meta = (block.metadata || {}) as any;
      const st = meta.start_time ?? 0;
      const et = meta.end_time ?? 0;
      const hydratedTrips = (block.tripIds || [])
        .map((id) => tripMap.get(id))
        .filter((t): t is Trip => t !== undefined)
        .map((t) => ({
          id: t.id,
          trip_id: t.tripId,
          start_time: t.startTime,
          // normaliza virada de meia-noite para o frontend (end sempre > start)
          end_time: t.endTime < t.startTime ? t.endTime + 1440 : t.endTime,
          line_id: t.lineId ?? null,
          line_code: t.lineCode ?? null,
          origin_id: t.originId,
          destination_id: t.destinationId,
          duration: t.duration,
          distance_km: t.distanceKm,
          direction: t.direction ?? null,
          pair_id: t.pairId ?? null,
        }))
        .sort((a, b) => a.start_time - b.start_time);

      return {
        ...block,
        block_id: block.blockId,
        start_time: st,
        end_time: et,
        total_cost: block.cost,
        trips: hydratedTrips,
      };
    }).sort((a, b) => (a.block_id || 0) - (b.block_id || 0));

    // Monta resultSummary a partir do metadata salvo
    const meta = (schedule.metadata || {}) as any;
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
      costBreakdown: meta.cost_breakdown ?? null,
      solverExplanation: meta.solver_explanation ?? null,
      blocks: hydratedBlocks,
      duties: schedule.duties.map((d) => {
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

    return {
      ...schedule,
      blocks: hydratedBlocks,
      resultSummary,
    };
  }
}
