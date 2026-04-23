import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { ReportsService } from './reports.service';
import { ReportsController } from './reports.controller';
import { Schedule } from '../database/entities/schedule.entity';
import { Trip } from '../database/entities/trip.entity';
import { Line } from '../database/entities/line.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Schedule, Trip, Line]), JwtModule.register({})],
  controllers: [ReportsController],
  providers: [ReportsService, TenantContext],
  exports: [ReportsService],
})
export class ReportsModule {}
