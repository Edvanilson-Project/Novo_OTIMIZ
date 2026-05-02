import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { VehicleMaintenance } from '../database/entities/vehicle-maintenance.entity';
import { VehicleAvailabilityWindow } from '../database/entities/vehicle-availability-window.entity';
import { VehiclesController } from './vehicles.controller';
import { VehiclesService } from './vehicles.service';
import { VehicleMaintenanceController } from './vehicle-maintenance.controller';
import { VehicleMaintenanceService } from './vehicle-maintenance.service';
import { VehicleMetricsService } from './vehicle-metrics.service';
import { VehicleMetricsController } from './vehicle-metrics.controller';
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [
    TypeOrmModule.forFeature([Vehicle, VehicleType, VehicleMaintenance, VehicleAvailabilityWindow]),
    JwtModule.register({}),
  ],
  controllers: [VehiclesController, VehicleMaintenanceController, VehicleMetricsController],
  providers: [VehiclesService, VehicleMaintenanceService, VehicleMetricsService, TenantContext],
  exports: [VehiclesService, VehicleMaintenanceService, VehicleMetricsService],
})
export class VehiclesModule {}
