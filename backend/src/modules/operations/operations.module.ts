import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { MulterModule } from '@nestjs/platform-express';
import { OperationsController } from './operations.controller';
import { SolutionValidatorService } from './solution-validator.service';
import { SolutionValidatorController } from './solution-validator.controller';
import { OperationsService } from './operations.service';
import { OptimizationService } from './optimization.service';
import { OptimizationGateway } from './optimization.gateway';
import { OptimizationAdvancedController } from './optimization/optimization-advanced.controller';
import { ScenarioEvaluatorService } from './optimization/scenario-evaluator.service';
import { WhatIfSimulatorService } from './optimization/whatif-simulator.service';
import { OperationReportController } from './reporting/operation-report.controller';
import { OperationReportGeneratorService } from './reporting/operation-report-generator.service';
import {
  TripRepository,
  DriverRepository,
} from '../database/repositories/operations.repository';
import { Trip } from '../database/entities/trip.entity';
import { Driver } from '../database/entities/driver.entity';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { Schedule } from '../database/entities/schedule.entity';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { OptimizationRun } from '../database/entities/optimization-run.entity';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtModule } from '@nestjs/jwt';

@Module({
  imports: [
    TypeOrmModule.forFeature([
      Trip,
      Driver,
      CompanyParameters,
      Schedule,
      BlockAssignment,
      DutyAssignment,
      Vehicle,
      VehicleType,
      OptimizationRun,
      // OptimizationRun é importado acima e usado em reporting + scenario evaluator
    ]),
    MulterModule.register({
      limits: { fileSize: 10 * 1024 * 1024 },
    }),
    JwtModule.register({}),
  ],
  controllers: [
    OperationsController,
    SolutionValidatorController,
    OptimizationAdvancedController,
    OperationReportController,
  ],
  providers: [
    SolutionValidatorService,
    OperationsService,
    OptimizationService,
    OptimizationGateway,
    ScenarioEvaluatorService,
    WhatIfSimulatorService,
    OperationReportGeneratorService,
    TripRepository,
    DriverRepository,
    TenantContext,
  ],
  exports: [OperationsService, OptimizationService, SolutionValidatorService],
})
export class OperationsModule {}
