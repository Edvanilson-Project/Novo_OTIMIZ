import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { VehiclesController } from './vehicles.controller';
import { VehiclesService } from './vehicles.service';
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Vehicle, VehicleType]), JwtModule.register({})],
  controllers: [VehiclesController],
  providers: [VehiclesService, TenantContext],
  exports: [VehiclesService],
})
export class VehiclesModule {}
