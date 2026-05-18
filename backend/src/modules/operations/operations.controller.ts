import {
  Controller,
  Post,
  Get,
  Patch,
  Delete,
  Param,
  ParseIntPipe,
  Query,
  UseInterceptors,
  UploadedFile,
  Body,
  UseGuards,
  BadRequestException,
  Logger,
} from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { FileInterceptor } from '@nestjs/platform-express';
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiBearerAuth,
  ApiBody,
  ApiQuery,
  ApiConsumes,
} from '@nestjs/swagger';
import { OperationsService } from './operations.service';
import { OptimizationService } from './optimization.service';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@ApiTags('operations')
@ApiBearerAuth('JWT')
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
  @Throttle({ medium: { ttl: 300_000, limit: 5 } })
  @ApiOperation({
    summary: 'Iniciar otimização de escala',
    description:
      'Envia job assíncrono ao optimizer. Retorna taskId para polling de status.',
  })
  @ApiBody({
    schema: {
      example: {
        algorithm: 'hybrid_pipeline',
        operational_quality_mode: 'balanced',
        depot_ids: [1, 2],
      },
    },
  })
  @ApiResponse({
    status: 201,
    description: 'Otimização iniciada — retorna { taskId }.',
  })
  @ApiResponse({
    status: 400,
    description: 'CompanyId divergente ou payload inválido.',
  })
  @ApiResponse({
    status: 429,
    description: 'Rate limit: máximo 5 otimizações por 5 minutos.',
  })
  async runOptimization(
    @Body() body: Record<string, any>,
    @Body('algorithm') algorithm?: string,
    @Body('companyId') requestedCompanyId?: number,
    @Body('operational_quality_mode') operationalQualityMode?: string,
    @Body('depot_ids') depotIds?: number[],
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');

    if (
      requestedCompanyId !== undefined &&
      requestedCompanyId !== null &&
      Number(requestedCompanyId) !== Number(companyId)
    ) {
      this.logger.warn(
        `optimization_tenant_mismatch_blocked requested=${requestedCompanyId} tenant=${companyId}`,
      );
      throw new BadRequestException(
        `CompanyId divergente do tenant autenticado. requested=${requestedCompanyId} tenant=${companyId}`,
      );
    }

    const requestedOperationalQualityMode =
      body?.operational_quality_mode ??
      body?.operationalQualityMode ??
      operationalQualityMode;

    this.logger.log(
      `optimization_request_received company_id=${companyId} algorithm=${algorithm ?? 'default'} requested_operational_quality_mode=${requestedOperationalQualityMode ?? 'null'}`,
    );

    const rawDepotIds = depotIds ?? body?.depot_ids;
    const resolvedDepotIds = Array.isArray(rawDepotIds)
      ? rawDepotIds.map(Number).filter(Boolean)
      : undefined;

    return this.optimizationService.runOptimization(
      companyId,
      algorithm,
      requestedOperationalQualityMode,
      {
        depotIds: resolvedDepotIds,
      },
    );
  }

  @Post('chat')
  async aiChat(@Body() body: { metrics: any; question: string }) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.aiChat(body.metrics, body.question);
  }

  @Patch('reassign-trip')
  async reassignTrip(
    @Body('scheduleId') scheduleId: number,
    @Body('tripId') tripId: number,
    @Body('targetBlockId') targetBlockId: number,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.reassignTrip(
      companyId,
      scheduleId,
      tripId,
      targetBlockId,
    );
  }

  @Post('evaluate-delta')
  async evaluateDelta(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.evaluateDelta(body);
  }

  @Post('evaluate-baseline')
  async evaluateBaseline(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.evaluateBaseline(body);
  }

  @Get('optimize/status')
  @ApiOperation({
    summary: 'Status da última otimização',
    description:
      'Retorna status (processing|completed|failed|idle), scheduleId e totalCost da otimização mais recente.',
  })
  @ApiResponse({
    status: 200,
    description:
      'Status da otimização: idle | processing | completed | failed.',
  })
  async getOptimizeStatus() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.getOptimizeStatus(companyId);
  }

  @Get('latest-schedule')
  @ApiOperation({
    summary: 'Buscar última escala otimizada',
    description: 'Retorna o schedule mais recente com blocks, duties e trips.',
  })
  @ApiResponse({
    status: 200,
    description: 'Schedule completo com blocos e jornadas.',
  })
  async getLatestSchedule() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.getLatestSchedule(companyId);
  }

  @Post('upload')
  @UseInterceptors(FileInterceptor('file'))
  @ApiOperation({ summary: 'Upload de CSV de viagens ou motoristas' })
  @ApiConsumes('multipart/form-data')
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        file: { type: 'string', format: 'binary' },
        type: { type: 'string', enum: ['trips', 'drivers'] },
      },
    },
  })
  @ApiResponse({ status: 201, description: 'Arquivo processado com sucesso.' })
  async uploadFile(
    @UploadedFile()
    file: { buffer: Buffer; originalname: string; mimetype: string },
    @Body('type') type: 'trips' | 'drivers',
  ) {
    if (!file) throw new BadRequestException('Nenhum arquivo enviado');
    if (!['trips', 'drivers'].includes(type))
      throw new BadRequestException('Tipo de dado inválido');

    return this.operationsService.processUpload(file.buffer, type);
  }

  @Get('trips')
  @ApiOperation({ summary: 'Listar viagens do tenant' })
  @ApiQuery({ name: 'page', required: false, example: 1 })
  @ApiQuery({ name: 'limit', required: false, example: 500 })
  @ApiResponse({ status: 200, description: 'Lista paginada de viagens.' })
  async getTrips(@Query('page') page: string, @Query('limit') limit: string) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.getTrips(
      parseInt(page || '1'),
      parseInt(limit || '500'),
      companyId,
    );
  }

  @Post('trips')
  async createTrip(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.createTrip(body, companyId);
  }

  @Patch('trips/:id')
  async updateTrip(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: Record<string, any>,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.updateTrip(id, body, companyId);
  }

  @Delete('trips/:id')
  async deleteTrip(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.deleteTrip(id, companyId);
  }

  @Delete('trips')
  async clearAllTrips() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.clearAllTrips(companyId);
  }

  @Get('drivers')
  async getDrivers() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.getDrivers(companyId);
  }

  @Post('drivers')
  async createDriver(@Body() body: Record<string, any>) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.createDriver(body, companyId);
  }

  @Patch('drivers/:id')
  async updateDriver(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: Record<string, any>,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.updateDriver(id, body, companyId);
  }

  @Delete('drivers/:id')
  async deleteDriver(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.deleteDriver(id, companyId);
  }
}
