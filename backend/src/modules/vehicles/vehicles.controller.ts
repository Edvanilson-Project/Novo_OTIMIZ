import {
  Controller, Get, Post, Patch, Delete,
  Param, Body, ParseIntPipe, UseGuards, HttpCode, HttpStatus,
} from '@nestjs/common';
import { VehiclesService } from './vehicles.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('vehicles')
@UseGuards(JwtAuthGuard)
export class VehiclesController {
  constructor(private readonly service: VehiclesService) {}

  // Vehicle Type endpoints
  @Get('types')
  findAllVehicleTypes() {
    return this.service.findAllVehicleTypes();
  }

  @Get('types/:id')
  findOneVehicleType(@Param('id', ParseIntPipe) id: number) {
    return this.service.findOneVehicleType(id);
  }

  @Post('types')
  createVehicleType(@Body() body: Record<string, any>) {
    return this.service.createVehicleType(body);
  }

  @Patch('types/:id')
  updateVehicleType(@Param('id', ParseIntPipe) id: number, @Body() body: Record<string, any>) {
    return this.service.updateVehicleType(id, body);
  }

  @Delete('types/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  removeVehicleType(@Param('id', ParseIntPipe) id: number) {
    return this.service.removeVehicleType(id);
  }

  // Vehicle endpoints
  @Get()
  findAllVehicles() {
    return this.service.findAllVehicles();
  }

  @Get('active')
  getActiveVehicles() {
    return this.service.getActiveVehicles();
  }

  @Get('by-type/:typeId')
  getVehiclesByType(@Param('typeId', ParseIntPipe) typeId: number) {
    return this.service.getVehiclesByType(typeId);
  }

  @Get(':id')
  findOneVehicle(@Param('id', ParseIntPipe) id: number) {
    return this.service.findOneVehicle(id);
  }

  @Post()
  createVehicle(@Body() body: Record<string, any>) {
    return this.service.createVehicle(body);
  }

  @Patch(':id')
  updateVehicle(@Param('id', ParseIntPipe) id: number, @Body() body: Record<string, any>) {
    return this.service.updateVehicle(id, body);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  removeVehicle(@Param('id', ParseIntPipe) id: number) {
    return this.service.removeVehicle(id);
  }
}
