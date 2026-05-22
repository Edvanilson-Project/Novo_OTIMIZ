import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Schedule } from '../../database/entities/schedule.entity';
import { OptimizationService } from '../optimization.service';
import { TenantContext } from '../../../common/context/tenant-context';

export interface WhatIfScenario {
  type:
    | 'vehicle_type_change'
    | 'time_shift'
    | 'trip_removal'
    | 'trip_addition'
    | 'parameter_change';
  description: string;
  affectedElements: string[];
}

export interface WhatIfResult {
  scenario: WhatIfScenario;
  originalCost: number;
  newCost: number;
  costDifference: number;
  costDifferencePercent: number;
  feasible: boolean;
  warnings: string[];
  recommendations: string[];
  /**
   * Quando true, o resultado foi calculado por fórmula escalar (sem chamar o motor
   * de otimização). Útil pra estimativas rápidas — não substitui reotimização real.
   * Frontend deve sinalizar visualmente (banner amarelo) quando isHeuristic=true.
   */
  isHeuristic: boolean;
}

/**
 * Resultado de reotimização real (não-heurística). Retorna a OptimizationRun
 * enfileirada — frontend deve pollear via /optimization-advanced/scenarios/:id/run/:scenarioId
 * (ou listScenarios) até status=completed.
 */
export interface WhatIfRunResult {
  optimizationRunId: number;
  scheduleId: number;
  scenarioId: string;
  status: string;
  inputFingerprint: string;
  algorithm: string;
}

@Injectable()
export class WhatIfSimulatorService {
  constructor(
    @InjectRepository(Schedule) private scheduleRepo: Repository<Schedule>,
    private optimizationService: OptimizationService,
    private tenantContext: TenantContext,
  ) {}
  simulateVehicleTypeChange(
    originalCost: number,
    fromTypeId: number,
    toTypeId: number,
    fromTypeCost: number,
    toTypeCost: number,
    tripCount: number,
  ): WhatIfResult {
    const costDifference = (toTypeCost - fromTypeCost) * tripCount;
    const newCost = originalCost + costDifference;
    const percent =
      originalCost > 0 ? (costDifference / originalCost) * 100 : 0;

    return {
      scenario: {
        type: 'vehicle_type_change',
        description: `Mudança de tipo de veículo`,
        affectedElements: [`${tripCount} viagens`, 'Custo operacional'],
      },
      originalCost,
      newCost,
      costDifference,
      costDifferencePercent: percent,
      feasible:
        originalCost > 0 ? newCost <= originalCost * 1.2 : costDifference <= 0,
      warnings:
        percent > 10
          ? [`Custo aumentará em ${Math.abs(percent).toFixed(1)}%`]
          : [],
      recommendations:
        percent > 0
          ? [`Considere revisar utilização do veículo mais caro`]
          : [
              `Mudança resultará em economias de R$ ${Math.abs(costDifference).toFixed(2)}`,
            ],
      isHeuristic: true, // cálculo escalar; reotimização real exige refator de payload de trips
    };
  }

  simulateTimeShift(
    originalCost: number,
    shiftMinutes: number,
    tripCount: number,
  ): WhatIfResult {
    // Time shift can affect deadhead, idle costs
    const estimatedImpact = (shiftMinutes / 60) * 0.5 * tripCount; // ~0.5 cost per hour
    const costDifference = estimatedImpact;
    const newCost = originalCost + costDifference;

    return {
      scenario: {
        type: 'time_shift',
        description: `Adiamento de ${Math.abs(shiftMinutes)} minutos`,
        affectedElements: [`${tripCount} viagens`, 'Tempos de deadhead'],
      },
      originalCost,
      newCost,
      costDifference,
      costDifferencePercent:
        originalCost > 0 ? (costDifference / originalCost) * 100 : 0,
      feasible: shiftMinutes >= -120 && shiftMinutes <= 120, // ±2 hours
      warnings:
        Math.abs(shiftMinutes) > 60
          ? [`Adiamento > 1h pode afetar conexões`]
          : [],
      recommendations:
        shiftMinutes < 0
          ? [`Antecipação pode reduzir custos de idle`]
          : [`Adiamento deve ser coordenado com próximas viagens`],
      isHeuristic: true,
    };
  }

  simulateTripRemoval(
    originalCost: number,
    tripCost: number,
    vehicleFixedCost: number,
    vehicleUsageCount: number,
  ): WhatIfResult {
    // Removing a trip reduces cost, but might still need vehicle
    const costSavings =
      vehicleUsageCount > 1 ? tripCost : tripCost + vehicleFixedCost;
    const newCost = originalCost - costSavings;

    return {
      scenario: {
        type: 'trip_removal',
        description: `Remoção de 1 viagem`,
        affectedElements: ['1 viagem', 'Possível redução de veículo'],
      },
      originalCost,
      newCost,
      costDifference: -costSavings,
      costDifferencePercent:
        originalCost > 0 ? (-costSavings / originalCost) * 100 : 0,
      feasible: false, // Trip removal is not feasible for operational schedules
      warnings: [`Remoção de viagem não é recomendada`],
      recommendations: [`Avaliar se viagem é essencial antes de remover`],
      isHeuristic: true,
    };
  }

  simulateTripAddition(
    originalCost: number,
    newTripCost: number,
    willNeedNewVehicle: boolean,
    newVehicleFixedCost: number,
  ): WhatIfResult {
    const additionalCost = willNeedNewVehicle
      ? newTripCost + newVehicleFixedCost
      : newTripCost;
    const newCost = originalCost + additionalCost;

    return {
      scenario: {
        type: 'trip_addition',
        description: `Adição de 1 viagem`,
        affectedElements: [
          '1 nova viagem',
          ...(willNeedNewVehicle ? ['1 novo veículo'] : []),
        ],
      },
      originalCost,
      newCost,
      costDifference: additionalCost,
      costDifferencePercent:
        originalCost > 0 ? (additionalCost / originalCost) * 100 : 0,
      feasible: true,
      warnings: willNeedNewVehicle ? [`Requer novo veículo`] : [],
      recommendations: [
        `Viagem adicionada aumentará custo em R$ ${additionalCost.toFixed(2)}`,
      ],
      isHeuristic: true,
    };
  }

  simulateParameterChange(
    originalCost: number,
    parameter: string,
    oldValue: unknown,
    newValue: unknown,
  ): WhatIfResult {
    // Generic parameter change impact estimation
    let costMultiplier = 1.0;

    if (parameter === 'min_break_minutes') {
      // Longer breaks reduce efficiency
      const oldNum = Number(oldValue);
      const newNum = Number(newValue);
      costMultiplier = newNum > oldNum ? 1.02 : 0.98;
    } else if (parameter === 'vehicle_preference') {
      // Preference changes can shift costs
      costMultiplier = 1.01;
    }

    const newCost = originalCost * costMultiplier;
    const costDifference = newCost - originalCost;

    return {
      scenario: {
        type: 'parameter_change',
        description: `Mudança de parâmetro: ${parameter}`,
        affectedElements: [`${parameter}: ${oldValue} → ${newValue}`],
      },
      originalCost,
      newCost,
      costDifference,
      costDifferencePercent: parseFloat(
        ((costMultiplier - 1) * 100).toFixed(1),
      ),
      feasible: true,
      warnings:
        Math.abs(costMultiplier - 1) > 0.05
          ? [`Mudança pode impactar significativamente a operação`]
          : [],
      recommendations: [
        `Parâmetro será alterado em todas as futuras otimizações`,
      ],
      isHeuristic: true,
    };
  }

  /**
   * What-If REAL: enfileira uma OptimizationRun chamando o motor de otimização
   * com overrides em optimization_params/cct_params/vsp_params. Diferente dos
   * `simulate*` heurísticos, este caminho mede o impacto reotimizando o problema
   * inteiro. Retorna a run em status running — frontend deve pollear até completed.
   *
   * Limitação atual: não modifica o conjunto de trips (remoção/adição/shift exigem
   * refator do payload de trips no OptimizationService). Use para mudanças que
   * o optimizer já entende: time_budget_s, cct_violation_penalty, force_round_trip,
   * preferred_pair_window_minutes, paired_trip_bonus, cost_vehicle, cost_km, etc.
   */
  async runParameterChangeReal(
    baselineScheduleId: number,
    paramsOverride: Record<string, unknown>,
    label?: string,
    algorithm?: string,
  ): Promise<WhatIfRunResult> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new NotFoundException('Empresa não identificada.');
    const baseline = await this.scheduleRepo.findOne({
      where: { id: baselineScheduleId, companyId },
    });
    if (!baseline)
      throw new NotFoundException(
        `Schedule ${baselineScheduleId} não encontrado.`,
      );

    const scenarioId = `whatif-${label || 'param-change'}-${Date.now()}`;
    const submission = (await this.optimizationService.runOptimization(
      companyId,
      algorithm,
      undefined,
      {
        scenarioId,
        baselineScheduleId,
        optimizationParamsOverride: paramsOverride,
        skipTenantLock: true,
      },
    )) as {
      optimizationRunId: number;
      scheduleId: number;
      scenarioId?: string;
      inputFingerprint: string;
    };

    return {
      optimizationRunId: submission.optimizationRunId,
      scheduleId: submission.scheduleId,
      scenarioId: submission.scenarioId ?? scenarioId,
      status: 'running',
      inputFingerprint: submission.inputFingerprint,
      algorithm: algorithm ?? 'hybrid_pipeline',
    };
  }
}
