import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { MulterModule } from '@nestjs/platform-express';
import { ConfigModule } from '@nestjs/config';
import { OperationsController } from './operations.controller';
import { SolutionValidatorService } from './solution-validator.service';
import { SolutionValidatorController } from './solution-validator.controller';
import { OperationsService } from './operations.service';
import { OptimizationService } from './optimization.service';
import { OptimizationGateway } from './optimization.gateway';
import { TripRepository, DriverRepository } from '../database/repositories/operations.repository';
import { Trip } from '../database/entities/trip.entity';
import { Driver } from '../database/entities/driver.entity';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { Schedule } from '../database/entities/schedule.entity';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
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
    ]),
    MulterModule.register({
      limits: { fileSize: 10 * 1024 * 1024 },
    }),
    JwtModule.register({}),
  ],
  controllers: [OperationsController, SolutionValidatorController],
  providers: [
    SolutionValidatorService,
    OperationsService,
    OptimizationService,
    OptimizationGateway,
    TripRepository,
    DriverRepository,
    TenantContext,
  ],
  exports: [OperationsService, OptimizationService, SolutionValidatorService],
})
export class OperationsModule {}
