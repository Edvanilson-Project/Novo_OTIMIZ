import { Injectable } from '@nestjs/common';

export interface WhatIfScenario {
  type: 'vehicle_type_change' | 'time_shift' | 'trip_removal' | 'trip_addition' | 'parameter_change';
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
}

@Injectable()
export class WhatIfSimulatorService {
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
    const percent = (costDifference / originalCost) * 100;

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
      feasible: newCost <= originalCost * 1.2, // Allow 20% cost increase
      warnings:
        percent > 10
          ? [`Custo aumentará em ${Math.abs(percent).toFixed(1)}%`]
          : [],
      recommendations:
        percent > 0
          ? [`Considere revisar utilização do veículo mais caro`]
          : [`Mudança resultará em economias de ${Math.abs(percent).toFixed(1)}%`],
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
      costDifferencePercent: (costDifference / originalCost) * 100,
      feasible: shiftMinutes >= -120 && shiftMinutes <= 120, // ±2 hours
      warnings:
        Math.abs(shiftMinutes) > 60
          ? [`Adiamento > 1h pode afetar conexões`]
          : [],
      recommendations:
        shiftMinutes < 0
          ? [`Antecipação pode reduzir custos de idle`]
          : [`Adiamento deve ser coordenado com próximas viagens`],
    };
  }

  simulateTripRemoval(
    originalCost: number,
    tripCost: number,
    vehicleFixedCost: number,
    vehicleUsageCount: number,
  ): WhatIfResult {
    // Removing a trip reduces cost, but might still need vehicle
    const costSavings = vehicleUsageCount > 1 ? tripCost : tripCost + vehicleFixedCost;
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
      costDifferencePercent: (-costSavings / originalCost) * 100,
      feasible: false, // Trip removal is not feasible for operational schedules
      warnings: [`Remoção de viagem não é recomendada`],
      recommendations: [`Avaliar se viagem é essencial antes de remover`],
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
      costDifferencePercent: (additionalCost / originalCost) * 100,
      feasible: true,
      warnings: willNeedNewVehicle ? [`Requer novo veículo`] : [],
      recommendations: [`Viagem adicionada aumentará custo em R$ ${additionalCost.toFixed(2)}`],
    };
  }

  simulateParameterChange(
    originalCost: number,
    parameter: string,
    oldValue: any,
    newValue: any,
  ): WhatIfResult {
    // Generic parameter change impact estimation
    let costMultiplier = 1.0;

    if (parameter === 'min_break_minutes') {
      // Longer breaks reduce efficiency
      costMultiplier = newValue > oldValue ? 1.02 : 0.98;
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
      costDifferencePercent: parseFloat(((costMultiplier - 1) * 100).toFixed(1)),
      feasible: true,
      warnings:
        Math.abs(costMultiplier - 1) > 0.05
          ? [`Mudança pode impactar significativamente a operação`]
          : [],
      recommendations: [
        `Parâmetro será alterado em todas as futuras otimizações`,
      ],
    };
  }
}
