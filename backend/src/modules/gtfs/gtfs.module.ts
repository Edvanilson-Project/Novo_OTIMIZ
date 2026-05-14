import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { GtfsImportController } from './gtfs-import.controller';
import { GtfsImportService } from './gtfs-import.service';
import { Terminal } from '../database/entities/terminal.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Terminal, Line, Trip])],
  controllers: [GtfsImportController],
  providers: [GtfsImportService, TenantContext],
  exports: [GtfsImportService],
})
export class GtfsModule {}
