import { Controller, Post, Get, Patch, Delete, Param, ParseIntPipe, Query, UseInterceptors, UploadedFile, Body, UseGuards, BadRequestException, Logger } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { FileInterceptor } from '@nestjs/platform-express';
import { OperationsService } from './operations.service';
import { OptimizationService } from './optimization.service';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('operations')
@UseGuards(JwtAuthGuard)
export class OperationsController {
  private readonly logger = new Logger(OperationsController.name);

  constructor(
    private readonly operationsService: OperationsService,
    private readonly optimizationService: OptimizationService,
    private readonly tenantContext: TenantContext,
  ) {}

  @Post('optimize')
  // Otimização é cara em CPU (60-300s por run). Limitamos a 5 runs/5min por tenant
  // (não por IP, mas no nível controller — throttle global de 30 req/s ainda aplica).
  @Throttle({ medium: { ttl: 300_000, limit: 5 } })
  async runOptimization(
    @Body() body: Record<string, any>,
    @Body('algorithm') algorithm?: string,
    @Body('companyId') requestedCompanyId?: number,
    @Body('operational_quality_mode') operationalQualityMode?: string,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');

    if (
      requestedCompanyId !== undefined
      && requestedCompanyId !== null
      && Number(requestedCompanyId) !== Number(companyId)
    ) {
      this.logger.warn(
        `optimization_tenant_mismatch_blocked requested=${requestedCompanyId} tenant=${companyId}`,
      );
      throw new BadRequestException(
        `CompanyId divergente do tenant autenticado. requested=${requestedCompanyId} tenant=${companyId}`,
      );
    }

    const requestedOperationalQualityMode =
      body?.operational_quality_mode
      ?? body?.operationalQualityMode
      ?? operationalQualityMode;

    this.logger.log(
      `optimization_request_received company_id=${companyId} algorithm=${algorithm ?? 'default'} requested_operational_quality_mode=${requestedOperationalQualityMode ?? 'null'}`,
    );

    return this.optimizationService.runOptimization(companyId, algorithm, requestedOperationalQualityMode);
  }

  @Post('chat')
  async aiChat(@Body() body: { metrics: any; question: string }) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.aiChat(body.metrics, body.question);
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

  @Post('evaluate-baseline')
  async evaluateBaseline(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.evaluateBaseline(body);
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
    @UploadedFile() file: { buffer: Buffer; originalname: string; mimetype: string },
    @Body('type') type: 'trips' | 'drivers',
  ) {
    if (!file) throw new BadRequestException('Nenhum arquivo enviado');
    if (!['trips', 'drivers'].includes(type)) throw new BadRequestException('Tipo de dado inválido');

    return this.operationsService.processUpload(file.buffer, type);
  }

  @Get('trips')
  async getTrips(@Query('page') page: string, @Query('limit') limit: string) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.getTrips(parseInt(page || '1'), parseInt(limit || '500'), companyId);
  }

  @Post('trips')
  async createTrip(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.createTrip(body, companyId);
  }

  @Patch('trips/:id')
  async updateTrip(@Param('id', ParseIntPipe) id: number, @Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.updateTrip(id, body, companyId);
  }

  @Delete('trips/:id')
  async deleteTrip(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.deleteTrip(id, companyId);
  }

  @Delete('trips')
  async clearAllTrips() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.clearAllTrips(companyId);
  }

  @Get('drivers')
  async getDrivers() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.getDrivers(companyId);
  }

  @Post('drivers')
  async createDriver(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.createDriver(body, companyId);
  }

  @Patch('drivers/:id')
  async updateDriver(@Param('id', ParseIntPipe) id: number, @Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.updateDriver(id, body, companyId);
  }

  @Delete('drivers/:id')
  async deleteDriver(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.deleteDriver(id, companyId);
  }
}
