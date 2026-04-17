import { Controller, Post, Get, Patch, Query, UseInterceptors, UploadedFile, Body, UseGuards, BadRequestException } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { OperationsService } from './operations.service';
import { OptimizationService } from './optimization.service';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('operations')
@UseGuards(JwtAuthGuard)
export class OperationsController {
  constructor(
    private readonly operationsService: OperationsService,
    private readonly optimizationService: OptimizationService,
    private readonly tenantContext: TenantContext,
  ) {}

  @Post('optimize')
  async runOptimization() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.runOptimization(companyId);
  }

  @Patch('reassign-trip')
  async reassignTrip(
    @Body('scheduleId') scheduleId: number,
    @Body('tripId') tripId: number,
    @Body('targetBlockId') targetBlockId: number,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.reassignTrip(companyId, scheduleId, tripId, targetBlockId);
  }

  @Post('evaluate-delta')
  async evaluateDelta(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.evaluateDelta(body);
  }

  @Get('latest-schedule')
  async getLatestSchedule() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.getLatestSchedule(companyId);
  }

  @Post('upload')
  @UseInterceptors(FileInterceptor('file'))
  async uploadFile(
    @UploadedFile() file: Express.Multer.File,
    @Body('type') type: 'trips' | 'drivers',
  ) {
    if (!file) throw new BadRequestException('Nenhum arquivo enviado');
    if (!['trips', 'drivers'].includes(type)) throw new BadRequestException('Tipo de dado inválido');

    return this.operationsService.processUpload(file.buffer, type);
  }

  @Get('trips')
  async getTrips(@Query('page') page: string, @Query('limit') limit: string) {
    return this.operationsService.getTrips(parseInt(page || '1'), parseInt(limit || '100'));
  }

  @Get('drivers')
  async getDrivers() {
    return this.operationsService.getDrivers();
  }
}
