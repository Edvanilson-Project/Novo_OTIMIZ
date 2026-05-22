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
import { OperationsService, type RawRow } from './operations.service';
import { OptimizationService } from './optimization.service';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import {
  RunOptimizationDto,
  ReassignTripDto,
  AiChatDto,
  CreateTripDto,
  UpdateTripDto,
  CreateDriverDto,
  UpdateDriverDto,
  RosteringWeeklyDto,
  EvaluateBaselineDto,
  EvaluateDeltaPayloadDto,
} from './dto/operations.dto';

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
    description: 'Envia job assíncrono ao optimizer. Retorna taskId para polling de status.',
  })
  @ApiResponse({ status: 201, description: 'Otimização iniciada — retorna { taskId }.' })
  @ApiResponse({ status: 400, description: 'CompanyId divergente ou payload inválido.' })
  @ApiResponse({ status: 429, description: 'Rate limit: máximo 5 otimizações por 5 minutos.' })
  async runOptimization(@Body() body: RunOptimizationDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');

    if (
      body.companyId !== undefined &&
      body.companyId !== null &&
      Number(body.companyId) !== Number(companyId)
    ) {
      this.logger.warn(
        `optimization_tenant_mismatch_blocked requested=${body.companyId} tenant=${companyId}`,
      );
      throw new BadRequestException(
        `CompanyId divergente do tenant autenticado. requested=${body.companyId} tenant=${companyId}`,
      );
    }

    const resolvedDepotIds = Array.isArray(body.depot_ids)
      ? body.depot_ids.map(Number).filter(Boolean)
      : undefined;

    return this.optimizationService.runOptimization(
      companyId,
      body.algorithm,
      body.operational_quality_mode,
      { depotIds: resolvedDepotIds },
    );
  }

  @Post('chat')
  @ApiOperation({ summary: 'Chat com IA sobre métricas de otimização' })
  async aiChat(@Body() body: AiChatDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.aiChat(body.metrics, body.question);
  }

  @Post('rostering/weekly')
  @ApiOperation({ summary: 'Rostering semanal de motoristas' })
  async rosteringWeekly(@Body() body: RosteringWeeklyDto) {
    return this.optimizationService.rosteringWeekly(body);
  }

  @Patch('reassign-trip')
  @ApiOperation({ summary: 'Reatribuir viagem para outro bloco' })
  async reassignTrip(@Body() body: ReassignTripDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.reassignTrip(
      companyId,
      body.scheduleId,
      body.tripId,
      body.targetBlockId,
    );
  }

  @Post('evaluate-delta')
  @ApiOperation({ summary: 'Avaliar delta de custo de reatribuição de viagem' })
  async evaluateDelta(@Body() body: EvaluateDeltaPayloadDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.evaluateDelta(body);
  }

  @Post('evaluate-baseline')
  @ApiOperation({ summary: 'Avaliar custo baseline do schedule atual' })
  async evaluateBaseline(@Body() body: EvaluateBaselineDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.evaluateBaseline(body);
  }

  @Get('optimize/status')
  @ApiOperation({
    summary: 'Status da última otimização',
    description: 'Retorna status (processing|completed|failed|idle), scheduleId e totalCost.',
  })
  async getOptimizeStatus() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.getOptimizeStatus(companyId);
  }

  @Get('latest-schedule')
  @ApiOperation({ summary: 'Buscar última escala otimizada' })
  async getLatestSchedule() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.getLatestSchedule(companyId);
  }

  @Get('schedules/:id/optimality')
  @ApiOperation({
    summary: 'Certificado de otimalidade do schedule',
    description:
      'Retorna LB (best-of Bodin & Golden + Lagrangian + Bundle), UB (veículos usados) e gap percentual.',
  })
  async getOptimalityCertificate(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.optimizationService.getOptimalityCertificate(companyId, id);
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
  async uploadFile(
    @UploadedFile()
    file: { buffer: Buffer; originalname: string; mimetype: string },
    @Body('type') type: string,
  ) {
    if (!file) throw new BadRequestException('Nenhum arquivo enviado');
    if (!['trips', 'drivers'].includes(type))
      throw new BadRequestException('Tipo de dado inválido: deve ser "trips" ou "drivers"');
    return this.operationsService.processUpload(file.buffer, type as 'trips' | 'drivers');
  }

  @Get('trips')
  @ApiOperation({ summary: 'Listar viagens do tenant' })
  @ApiQuery({ name: 'page', required: false, example: 1 })
  @ApiQuery({ name: 'limit', required: false, example: 500 })
  async getTrips(
    @Query('page') page: string,
    @Query('limit') limit: string,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    const pageNum = Math.max(1, parseInt(page || '1', 10) || 1);
    const limitNum = Math.min(1000, Math.max(1, parseInt(limit || '500', 10) || 500));
    return this.operationsService.getTrips(pageNum, limitNum, companyId);
  }

  @Post('trips')
  @ApiOperation({ summary: 'Criar viagem' })
  async createTrip(@Body() body: CreateTripDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    // DTO já validado pelo ValidationPipe; service normaliza shape via RawRow.
    return this.operationsService.createTrip(
      body as unknown as RawRow,
      companyId,
    );
  }

  @Patch('trips/:id')
  @ApiOperation({ summary: 'Atualizar viagem' })
  async updateTrip(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: UpdateTripDto,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.updateTrip(
      id,
      body as unknown as RawRow,
      companyId,
    );
  }

  @Delete('trips/:id')
  @ApiOperation({ summary: 'Remover viagem' })
  async deleteTrip(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.deleteTrip(id, companyId);
  }

  @Delete('trips')
  @ApiOperation({ summary: 'Limpar todas as viagens do tenant' })
  async clearAllTrips() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.clearAllTrips(companyId);
  }

  @Get('drivers')
  @ApiOperation({ summary: 'Listar motoristas do tenant' })
  async getDrivers() {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.getDrivers(companyId);
  }

  @Post('drivers')
  @ApiOperation({ summary: 'Criar motorista' })
  async createDriver(@Body() body: CreateDriverDto) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.createDriver(
      body as unknown as RawRow,
      companyId,
    );
  }

  @Patch('drivers/:id')
  @ApiOperation({ summary: 'Atualizar motorista' })
  async updateDriver(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: UpdateDriverDto,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.updateDriver(
      id,
      body as unknown as RawRow,
      companyId,
    );
  }

  @Delete('drivers/:id')
  @ApiOperation({ summary: 'Remover motorista' })
  async deleteDriver(@Param('id', ParseIntPipe) id: number) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return this.operationsService.deleteDriver(id, companyId);
  }
}
