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
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [
    TypeOrmModule.forFeature([Vehicle, VehicleType, VehicleMaintenance, VehicleAvailabilityWindow]),
    JwtModule.register({}),
  ],
  controllers: [VehiclesController, VehicleMaintenanceController],
  providers: [VehiclesService, VehicleMaintenanceService, TenantContext],
  exports: [VehiclesService, VehicleMaintenanceService],
})
export class VehiclesModule {}
