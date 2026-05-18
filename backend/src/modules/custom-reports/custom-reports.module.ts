import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { CustomReportsService } from './custom-reports.service';
import { CustomReportsController } from './custom-reports.controller';
import { CustomReport } from '../database/entities/custom-report.entity';
import { Schedule } from '../database/entities/schedule.entity';
import { Trip } from '../database/entities/trip.entity';
import { Line } from '../database/entities/line.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [
    TypeOrmModule.forFeature([CustomReport, Schedule, Trip, Line]),
    JwtModule.register({}),
  ],
  controllers: [CustomReportsController],
  providers: [CustomReportsService, TenantContext],
  exports: [CustomReportsService],
})
export class CustomReportsModule {}
