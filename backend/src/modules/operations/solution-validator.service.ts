import { Injectable } from '@nestjs/common';
import { Logger } from '@nestjs/common';

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
  stats: {
    totalTrips: number;
    allocatedTrips: number;
    unallocatedTrips: number;
    allocationPercentage: number;
    totalVehicles: number;
    totalDuties: number;
    totalOperatorHours: number;
    avgDutyHours: number;
  };
}

@Injectable()
export class SolutionValidatorService {
  private readonly logger = new Logger(SolutionValidatorService.name);
  private readonly toleranceMinutes = 5;

  /**
   * Valida uma solução completa (blocos + jornadas)
   */
  validate(
    blocks: any[],
    duties: any[],
    trips: any[],
    params: Record<string, any> = {},
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
  private checkTimeOverlaps(blocks: any[]): ValidationError[] {
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
            tripIds: [trip1.tripId, trip2.tripId],
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
  private checkDeadheadGaps(blocks: any[]): ValidationError[] {
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
              tripIds: [trip1.tripId, trip2.tripId],
              detail: `Gap ${gap}min < required ${this.toleranceMinutes}min`,
              suggestedFix: 'Increase gap between trips or assign to different vehicle',
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
    duties: any[],
    params: Record<string, any>,
  ): ValidationError[] {
    const errors: ValidationError[] = [];
    const maxShift = params.maxShiftMinutes || 600;

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
   * Valida posição de almoço obrigatório
   */
  private checkMealBreakPosition(
    duties: any[],
    params: Record<string, any>,
  ): ValidationError[] {
    // TODO: Implementar quando tivermos estrutura de events detalhada
    return [];
  }

  /**
   * Calcula estatísticas da solução
   */
  private calculateStats(blocks: any[], duties: any[], trips: any[]): any {
    const allocated = new Set();
    for (const block of blocks) {
      const items = block.items || block.trips || [];
      for (const trip of items) {
        const tripId = trip.tripId || trip.id;
        if (tripId) allocated.add(tripId);
      }
    }

    const totalTrips = trips.length;
    const totalOperatorHours = duties.reduce(
      (sum, duty) => {
        const start = duty.startTime;
        const end = duty.endTime;
        return sum + (start && end ? (end - start) / 60 : 0);
      },
      0,
    );

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
