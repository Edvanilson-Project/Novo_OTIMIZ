import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { GtfsImportController } from './gtfs-import.controller';
import { GtfsImportService } from './gtfs-import.service';
import { Terminal } from '../database/entities/terminal.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Terminal, Line, Trip]), JwtModule.register({})],
  controllers: [GtfsImportController],
  providers: [GtfsImportService, TenantContext],
  exports: [GtfsImportService],
})
export class GtfsModule {}
