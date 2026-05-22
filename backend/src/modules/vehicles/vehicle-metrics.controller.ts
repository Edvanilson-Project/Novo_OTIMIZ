import {
  Controller,
  Get,
  Param,
  ParseIntPipe,
  UseGuards,
} from '@nestjs/common';
import { VehicleMetricsService } from './vehicle-metrics.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('vehicles/metrics')
@UseGuards(JwtAuthGuard)
export class VehicleMetricsController {
  constructor(private readonly service: VehicleMetricsService) {}

  @Get('all')
  getAllMetrics() {
    return this.service.getAllVehiclesMetrics();
  }

  @Get(':vehicleId')
  getVehicleMetrics(@Param('vehicleId', ParseIntPipe) vehicleId: number) {
    return this.service.getVehicleMetrics(vehicleId);
  }
}
