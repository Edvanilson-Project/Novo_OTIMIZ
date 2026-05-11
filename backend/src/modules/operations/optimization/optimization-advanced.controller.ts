import {
  Controller,
  Get,
  Post,
  Param,
  Body,
  ParseIntPipe,
  UseGuards,
} from '@nestjs/common';
import { ScenarioEvaluatorService } from './scenario-evaluator.service';
import { WhatIfSimulatorService } from './whatif-simulator.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';

@Controller('operations/optimization-advanced')
@UseGuards(JwtAuthGuard)
export class OptimizationAdvancedController {
  constructor(
    private scenarioEvaluator: ScenarioEvaluatorService,
    private whatIfSimulator: WhatIfSimulatorService,
  ) {}

  @Post('scenarios/:scheduleId')
  async generateScenarios(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
  ) {
    return this.scenarioEvaluator.generateScenarios(scheduleId);
  }

  // GET = leitura idempotente para polling. POST acima é o trigger inicial que pode enfileirar.
  @Get('scenarios/:scheduleId')
  async listScenarios(@Param('scheduleId', ParseIntPipe) scheduleId: number) {
    return this.scenarioEvaluator.generateScenarios(scheduleId);
  }

  @Get('scenarios/:scheduleId/run/:scenarioId')
  async getScenarioRun(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Param('scenarioId') scenarioId: string,
  ) {
    const run = await this.scenarioEvaluator.getScenarioRun(scheduleId, scenarioId);
    if (!run) return null;
    return {
      id: run.id,
      scenarioId: run.scenarioId,
      status: run.status,
      algorithm: run.algorithm,
      metrics: run.metrics,
      errorMessage: run.errorMessage,
      durationMs: run.durationMs,
      resultScheduleId: run.resultScheduleId,
      inputFingerprint: run.inputFingerprint,
      createdAt: run.createdAt,
      completedAt: run.completedAt,
    };
  }

  @Post('scenarios/:scheduleId/compare')
  async compareScenarios(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Body('scenario1Id') scenario1Id: string,
    @Body('scenario2Id') scenario2Id: string,
  ) {
    return this.scenarioEvaluator.compareScenarios(scheduleId, scenario1Id, scenario2Id);
  }

  @Post('whatif/vehicle-type-change')
  simulateVehicleTypeChange(
    @Body()
    body: {
      originalCost: number;
      fromTypeId: number;
      toTypeId: number;
      fromTypeCost: number;
      toTypeCost: number;
      tripCount: number;
    },
  ) {
    return this.whatIfSimulator.simulateVehicleTypeChange(
      body.originalCost,
      body.fromTypeId,
      body.toTypeId,
      body.fromTypeCost,
      body.toTypeCost,
      body.tripCount,
    );
  }

  @Post('whatif/time-shift')
  simulateTimeShift(
    @Body()
    body: {
      originalCost: number;
      shiftMinutes: number;
      tripCount: number;
    },
  ) {
    return this.whatIfSimulator.simulateTimeShift(
      body.originalCost,
      body.shiftMinutes,
      body.tripCount,
    );
  }

  @Post('whatif/trip-removal')
  simulateTripRemoval(
    @Body()
    body: {
      originalCost: number;
      tripCost: number;
      vehicleFixedCost: number;
      vehicleUsageCount: number;
    },
  ) {
    return this.whatIfSimulator.simulateTripRemoval(
      body.originalCost,
      body.tripCost,
      body.vehicleFixedCost,
      body.vehicleUsageCount,
    );
  }

  @Post('whatif/trip-addition')
  simulateTripAddition(
    @Body()
    body: {
      originalCost: number;
      newTripCost: number;
      willNeedNewVehicle: boolean;
      newVehicleFixedCost: number;
    },
  ) {
    return this.whatIfSimulator.simulateTripAddition(
      body.originalCost,
      body.newTripCost,
      body.willNeedNewVehicle,
      body.newVehicleFixedCost,
    );
  }

  @Post('whatif/parameter-change')
  simulateParameterChange(
    @Body()
    body: {
      originalCost: number;
      parameter: string;
      oldValue: any;
      newValue: any;
    },
  ) {
    return this.whatIfSimulator.simulateParameterChange(
      body.originalCost,
      body.parameter,
      body.oldValue,
      body.newValue,
    );
  }

  /**
   * What-If REAL: enfileira uma reotimização chamando o motor real com overrides.
   * Cobre mudanças que o optimizer entende nativamente (time_budget_s,
   * cct_violation_penalty, cost_vehicle, force_round_trip, etc.). Retorna run em status
   * running — frontend pode pollear via GET /scenarios/:scheduleId/run/:scenarioId.
   */
  @Post('whatif/run-real/:scheduleId')
  async runWhatIfReal(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Body()
    body: {
      paramsOverride: Record<string, any>;
      label?: string;
      algorithm?: string;
    },
  ) {
    return this.whatIfSimulator.runParameterChangeReal(
      scheduleId,
      body.paramsOverride || {},
      body.label,
      body.algorithm,
    );
  }
}
