import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import { Logger } from '@nestjs/common';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
import { Trip } from '../database/entities/trip.entity';

/**
 * Serviço de validação independente de soluções
 * Não depende do otimizador - apenas auditando o resultado final
 */

export interface ValidationError {
  type: string;
  severity: 'CRITICAL' | 'HIGH' | 'WARNING';
  vehicleId?: number;
  dutyId?: number;
  tripIds?: number[];
  detail: string;
  suggestedFix?: string;
}

export interface ValidationResult {
  valid: boolean;
  errorCount: number;
  warningCount: number;
  errors: ValidationError[];
  warnings: ValidationError[];
  stats: ValidationStats;
}

export interface ValidationStats {
  totalTrips: number;
  allocatedTrips: number;
  unallocatedTrips: number;
  allocationPercentage: number;
  totalVehicles: number;
  totalDuties: number;
  totalOperatorHours: number;
  avgDutyHours: number;
}

/**
 * Shapes flexíveis: blocos/jornadas/viagens chegam ao validator com aliases
 * camelCase (frontend) e snake_case (solver Python), e às vezes campos
 * inflated via `...metadata`. Por isso usamos shape permissivo + narrowing.
 */
export interface BlockInput {
  blockId?: number;
  vehicleId?: number;
  items?: TripInBlock[];
  trips?: TripInBlock[];
  [key: string]: unknown;
}

export interface TripInBlock {
  tripId?: number;
  id?: number;
  startTime?: number;
  endTime?: number;
  [key: string]: unknown;
}

export interface DutyInput {
  dutyId?: number;
  duty_id?: number;
  id?: number;
  startTime?: number;
  endTime?: number;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface TripInput {
  id?: number;
  startTime?: number;
  endTime?: number;
  [key: string]: unknown;
}

export type ValidationParams = Record<string, unknown>;

@Injectable()
export class SolutionValidatorService {
  private readonly logger = new Logger(SolutionValidatorService.name);
  private readonly toleranceMinutes = 5;

  constructor(
    @InjectRepository(BlockAssignment)
    private readonly blockRepo: Repository<BlockAssignment>,
    @InjectRepository(DutyAssignment)
    private readonly dutyRepo: Repository<DutyAssignment>,
    @InjectRepository(Trip)
    private readonly tripRepo: Repository<Trip>,
  ) {}

  /**
   * Valida uma solução completa (blocos + jornadas)
   */
  validate(
    blocks: BlockInput[],
    duties: DutyInput[],
    trips: TripInput[],
    params: ValidationParams = {},
  ): ValidationResult {
    const errors: ValidationError[] = [];
    const warnings: ValidationError[] = [];

    // 1. Detectar sobreposição de horário
    errors.push(...this.checkTimeOverlaps(blocks));

    // 2. Validar gaps entre viagens
    errors.push(...this.checkDeadheadGaps(blocks));

    // 3. Validar jornada máxima
    errors.push(...this.checkMaxShift(duties, params));

    // 4. Validar posição de almoço
    warnings.push(...this.checkMealBreakPosition(duties, params));

    // 5. Calcular estatísticas
    const stats = this.calculateStats(blocks, duties, trips);

    const isValid = errors.length === 0;

    return {
      valid: isValid,
      errorCount: errors.length,
      warningCount: warnings.length,
      errors,
      warnings,
      stats,
    };
  }

  /**
   * Detecta sobreposição: duas viagens no mesmo veículo ao mesmo tempo
   */
  private checkTimeOverlaps(blocks: BlockInput[]): ValidationError[] {
    const errors: ValidationError[] = [];

    for (const block of blocks) {
      const vehicleId = block.blockId || block.vehicleId;
      const trips = block.items || block.trips || [];

      // Ordenar por hora de início
      const sorted = [...trips].sort(
        (a, b) => (a.startTime || 0) - (b.startTime || 0),
      );

      // Verificar cada par consecutivo
      for (let i = 0; i < sorted.length - 1; i++) {
        const trip1 = sorted[i];
        const trip2 = sorted[i + 1];

        const end1 = trip1.endTime;
        const start2 = trip2.startTime;

        if (end1 && start2 && end1 > start2) {
          errors.push({
            type: 'TIME_OVERLAP',
            severity: 'CRITICAL',
            vehicleId,
            tripIds: [trip1.tripId ?? 0, trip2.tripId ?? 0],
            detail: `Trip ${trip1.tripId} ends at ${end1}, Trip ${trip2.tripId} starts at ${start2}`,
            suggestedFix: 'Reorder trips or assign to different vehicle',
          });
        }
      }
    }

    return errors;
  }

  /**
   * Valida gaps entre viagens (deadhead time)
   */
  private checkDeadheadGaps(blocks: BlockInput[]): ValidationError[] {
    const errors: ValidationError[] = [];

    for (const block of blocks) {
      const vehicleId = block.blockId || block.vehicleId;
      const trips = block.items || block.trips || [];

      const sorted = [...trips].sort(
        (a, b) => (a.startTime || 0) - (b.startTime || 0),
      );

      for (let i = 0; i < sorted.length - 1; i++) {
        const trip1 = sorted[i];
        const trip2 = sorted[i + 1];

        const end1 = trip1.endTime;
        const start2 = trip2.startTime;

        if (end1 && start2) {
          const gap = start2 - end1;
          if (gap < this.toleranceMinutes) {
            errors.push({
              type: 'INSUFFICIENT_DEADHEAD',
              severity: 'HIGH',
              vehicleId,
              tripIds: [trip1.tripId ?? 0, trip2.tripId ?? 0],
              detail: `Gap ${gap}min < required ${this.toleranceMinutes}min`,
              suggestedFix:
                'Increase gap between trips or assign to different vehicle',
            });
          }
        }
      }
    }

    return errors;
  }

  /**
   * Valida jornada máxima do operador
   */
  private checkMaxShift(
    duties: DutyInput[],
    params: ValidationParams,
  ): ValidationError[] {
    const errors: ValidationError[] = [];
    const maxShift = (params.maxShiftMinutes as number | undefined) ?? 600;

    for (const duty of duties) {
      const start = duty.startTime;
      const end = duty.endTime;

      if (start && end) {
        const spread = end - start;
        if (spread > maxShift) {
          errors.push({
            type: 'MAX_SHIFT_EXCEEDED',
            severity: 'HIGH',
            dutyId: duty.dutyId || duty.id,
            detail: `Duty spread ${spread}min > max ${maxShift}min`,
            suggestedFix: 'Reduce duty spread or split into multiple duties',
          });
        }
      }
    }

    return errors;
  }

  /**
   * Verifica se jornadas longas têm folga suficiente para intervalo de almoço.
   * Usa metadata.work_time e metadata.spread_time armazenados na DutyAssignment.
   */
  private checkMealBreakPosition(
    duties: DutyInput[],
    params: ValidationParams,
  ): ValidationError[] {
    const warnings: ValidationError[] = [];
    const mealBreakMinutes =
      (params.meal_break_minutes as number | undefined) ??
      (params.mealBreakMinutes as number | undefined) ??
      30;
    const mealBreakThreshold =
      (params.meal_break_threshold as number | undefined) ?? 360; // 6h

    for (const duty of duties) {
      const meta = (duty.metadata ?? (duty as Record<string, unknown>)) as Record<string, unknown>;
      const workTime = Number(meta.work_time ?? meta.workTime ?? 0);
      const spreadTime = Number(meta.spread_time ?? meta.spreadTime ?? 0);

      if (workTime <= mealBreakThreshold) continue;

      const availableBreak = spreadTime - workTime;
      if (availableBreak < mealBreakMinutes) {
        warnings.push({
          type: 'MEAL_BREAK_INSUFFICIENT',
          severity: 'WARNING',
          dutyId: duty.dutyId ?? duty.duty_id ?? duty.id,
          detail: `Jornada de ${workTime}min (>${mealBreakThreshold}min) com apenas ${availableBreak}min de folga — abaixo dos ${mealBreakMinutes}min de intervalo de almoço`,
          suggestedFix: 'Aumentar a folga entre viagens ou dividir a jornada',
        });
      }
    }

    return warnings;
  }

  /**
   * Carrega blocos/jornadas/viagens do banco e valida o schedule salvo.
   */
  async validateScheduleById(
    scheduleId: number,
    companyId: number,
  ): Promise<ValidationResult> {
    const [blocks, duties] = await Promise.all([
      this.blockRepo.find({
        where: { scheduleId, companyId },
        order: { blockId: 'ASC' },
      }),
      this.dutyRepo.find({
        where: { scheduleId, companyId },
        order: { dutyId: 'ASC' },
      }),
    ]);

    if (!blocks.length && !duties.length) {
      throw new NotFoundException(
        `Schedule ${scheduleId} não encontrado ou sem dados para a empresa ${companyId}`,
      );
    }

    const allTripIds = [
      ...new Set([
        ...blocks.flatMap((b) => b.tripIds ?? []),
        ...duties.flatMap((d) => d.tripIds ?? []),
      ]),
    ];

    const trips = allTripIds.length
      ? await this.tripRepo.find({
          where: { id: In(allTripIds) },
          select: {
            id: true,
            startTime: true,
            endTime: true,
            duration: true,
            originId: true,
            destinationId: true,
          },
        })
      : [];

    // Normaliza para o formato que validate() espera
    const blocksDto = blocks.map((b) => ({
      blockId: b.blockId,
      trips: (b.tripIds ?? []).map((id) => {
        const t = trips.find((tr) => tr.id === id);
        return t
          ? {
              tripId: t.id,
              startTime: Number(t.startTime),
              endTime: Number(t.endTime),
            }
          : { tripId: id };
      }),
      ...(b.metadata ?? {}),
    }));

    const dutiesDto = duties.map((d) => ({
      dutyId: d.dutyId,
      metadata: d.metadata ?? {},
      ...(d.metadata ?? {}),
    }));

    const params = {}; // usa defaults do serviço
    return this.validate(
      blocksDto,
      dutiesDto,
      trips.map((t) => ({
        id: t.id,
        startTime: t.startTime,
        endTime: t.endTime,
      })),
      params,
    );
  }

  /**
   * Calcula estatísticas da solução
   */
  private calculateStats(
    blocks: BlockInput[],
    duties: DutyInput[],
    trips: TripInput[],
  ): ValidationStats {
    const allocated = new Set();
    for (const block of blocks) {
      const items = block.items || block.trips || [];
      for (const trip of items) {
        const tripId = trip.tripId || trip.id;
        if (tripId) allocated.add(tripId);
      }
    }

    const totalTrips = trips.length;
    const totalOperatorHours = duties.reduce((sum, duty) => {
      const start = duty.startTime;
      const end = duty.endTime;
      return sum + (start && end ? (end - start) / 60 : 0);
    }, 0);

    return {
      totalTrips,
      allocatedTrips: allocated.size,
      unallocatedTrips: totalTrips - allocated.size,
      allocationPercentage:
        totalTrips > 0 ? (allocated.size / totalTrips) * 100 : 0,
      totalVehicles: blocks.length,
      totalDuties: duties.length,
      totalOperatorHours: Math.round(totalOperatorHours * 100) / 100,
      avgDutyHours:
        duties.length > 0
          ? Math.round((totalOperatorHours / duties.length) * 100) / 100
          : 0,
    };
  }
}
