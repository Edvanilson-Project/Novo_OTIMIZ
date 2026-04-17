import { Injectable, Logger, InternalServerErrorException, ConflictException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource, Any, In } from 'typeorm';
import axios from 'axios';
import { Trip } from '../database/entities/trip.entity';
import { Driver } from '../database/entities/driver.entity';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { Schedule, ScheduleStatus } from '../database/entities/schedule.entity';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
import { OptimizationGateway } from './optimization.gateway';
import { ConfigService } from '@nestjs/config';

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
  ) {
    this.INTERNAL_KEY = this.configService.get<string>('INTERNAL_OPTIMIZER_KEY') || 'internal-key-123456';
  }

  async runOptimization(companyId: number) {
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
        trips: trips.map((t) => ({
          id: t.tripId || t.id,
          line_id: t.lineId,
          start_time: t.startTime,
          end_time: t.endTime,
          origin_id: t.originId,
          destination_id: t.destinationId,
          origin_latitude: t.originLatitude,
          origin_longitude: t.originLongitude,
          destination_latitude: t.destinationLatitude,
          destination_longitude: t.destinationLongitude,
          duration: t.duration,
          distance_km: t.distanceKm,
        })),
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
        algorithm: 'vcsp_pulp',
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

  private async pollOptimizerTask(taskId: string, scheduleId: number, companyId: number) {
    const maxAttempts = 60; // 5 minutos (5s * 60)
    let attempts = 0;

    const interval = setInterval(async () => {
      attempts++;
      try {
        const { data } = await axios.get(`${this.OPTIMIZER_URL}/optimize/status/${taskId}`, {
          headers: { 'X-Internal-Key': this.INTERNAL_KEY },
        });

        if (data.status === 'completed') {
          clearInterval(interval);
          await this.persistResults(scheduleId, companyId, data.result);
          this.gateway.notifyOptimizationFinished(companyId, scheduleId, data.result);
        } else if (data.status === 'failed') {
          clearInterval(interval);
          await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
          this.gateway.notifyOptimizationFailed(companyId, 'Erro no motor de otimização.');
        }

        if (attempts >= maxAttempts) {
          clearInterval(interval);
          await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
          this.gateway.notifyOptimizationFailed(companyId, 'Timeout na otimização.');
        }
      } catch (error) {
        this.logger.error(`Erro no polling do task ${taskId}: ${error.message}`);
        clearInterval(interval);
        await this.scheduleRepo.update(scheduleId, { status: ScheduleStatus.FAILED });
        this.gateway.notifyOptimizationFailed(companyId, 'Erro de comunicação com o solver.');
      }
    }, 5000);
  }

  private async persistResults(scheduleId: number, companyId: number, result: any) {
    this.logger.log(`Persistindo resultados para Schedule ${scheduleId}`);

    await this.dataSource.transaction(async (manager) => {
      // 1. Salvar Blocos (Veículos)
      const blocks = result.blocks.map((b) =>
        manager.create(BlockAssignment, {
          companyId,
          scheduleId,
          blockId: b.id,
          tripIds: b.trips,
          cost: b.total_cost || 0,
          metadata: b,
        }),
      );
      await manager.save(BlockAssignment, blocks);

      // 2. Salvar Duties (Motoristas)
      const duties = result.duties.map((d) =>
        manager.create(DutyAssignment, {
          companyId,
          scheduleId,
          dutyId: d.id,
          tripIds: d.trips,
          cost: d.total_cost || 0,
          metadata: d,
        }),
      );
      await manager.save(DutyAssignment, duties);

      // 3. Atualizar Header do Schedule
      await manager.update(Schedule, scheduleId, {
        status: ScheduleStatus.COMPLETED,
        totalCost: result.total_cost,
        cctViolations: result.cct_violations,
        metadata: {
          solver_explanation: result.solver_explanation,
          unassigned_trips: result.unassigned_trips,
        },
      });
    });
  }

  async reassignTrip(companyId: number, scheduleId: number, tripId: number, targetBlockId: number) {
    return this.dataSource.transaction(async (manager) => {
      // 1. Buscar a viagem e os blocos envolvidos
      const trip = await manager.findOne(Trip, { where: { id: tripId, companyId } });
      const sourceBlock = await manager.findOne(BlockAssignment, {
        where: { scheduleId, tripIds: Any([tripId]), companyId },
      });
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
        const { data: whatIfResult } = await axios.post(`${this.OPTIMIZER_URL}/evaluate-delta`, whatIfPayload, {
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
      id: b.block_id ?? b.id,
      trips: b.trips,
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
      const { data } = await axios.post(`${this.OPTIMIZER_URL}/evaluate-delta`, pythonPayload, {
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
    return this.scheduleRepo.findOne({
      where: { companyId, status: ScheduleStatus.COMPLETED },
      relations: ['blocks', 'duties'],
      order: { createdAt: 'DESC' },
    });
  }
}
