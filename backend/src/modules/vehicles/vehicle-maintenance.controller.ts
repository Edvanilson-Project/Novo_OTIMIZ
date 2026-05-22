import {
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Param,
  Body,
  ParseIntPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
  Query,
} from '@nestjs/common';
import { VehicleMaintenanceService } from './vehicle-maintenance.service';
import { MaintenanceStatus } from '../database/entities/vehicle-maintenance.entity';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('vehicles/:vehicleId/maintenance')
@UseGuards(JwtAuthGuard)
export class VehicleMaintenanceController {
  constructor(private readonly service: VehicleMaintenanceService) {}

  @Post()
  scheduleMaintenance(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Body() body: Record<string, unknown>,
  ) {
    return this.service.scheduleMaintenance(vehicleId, body);
  }

  @Get()
  getMaintenanceHistory(@Param('vehicleId', ParseIntPipe) vehicleId: number) {
    return this.service.getMaintenanceHistory(vehicleId);
  }

  @Patch(':maintenanceId')
  updateMaintenanceStatus(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Param('maintenanceId', ParseIntPipe) maintenanceId: number,
    @Body('status') status: string,
  ) {
    return this.service.updateMaintenanceStatus(
      vehicleId,
      maintenanceId,
      status as MaintenanceStatus,
    );
  }

  @Delete(':maintenanceId')
  @HttpCode(HttpStatus.NO_CONTENT)
  cancelMaintenance(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Param('maintenanceId', ParseIntPipe) maintenanceId: number,
  ) {
    return this.service.cancelMaintenance(vehicleId, maintenanceId);
  }

  @Get('availability/check')
  checkAvailability(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Query('startTime') startTime: string,
    @Query('endTime') endTime: string,
  ) {
    return this.service.checkVehicleAvailability(
      vehicleId,
      new Date(startTime),
      new Date(endTime),
    );
  }

  @Get('availability/periods')
  getUnavailablePeriods(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Query('startDate') startDate: string,
    @Query('endDate') endDate: string,
  ) {
    return this.service.getUnavailablePeriods(
      vehicleId,
      new Date(startDate),
      new Date(endDate),
    );
  }

  @Post('availability-windows')
  createAvailabilityWindow(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Body() body: Record<string, unknown>,
  ) {
    return this.service.createAvailabilityWindow(vehicleId, body);
  }

  @Delete('availability-windows/:windowId')
  @HttpCode(HttpStatus.NO_CONTENT)
  deleteAvailabilityWindow(
    @Param('vehicleId', ParseIntPipe) vehicleId: number,
    @Param('windowId', ParseIntPipe) windowId: number,
  ) {
    return this.service.deleteAvailabilityWindow(vehicleId, windowId);
  }
}
