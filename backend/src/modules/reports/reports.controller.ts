import {
  Controller,
  Get,
  Query,
  ParseIntPipe,
  UseGuards,
  BadRequestException,
} from '@nestjs/common';
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiBearerAuth,
  ApiQuery,
} from '@nestjs/swagger';
import { ReportsService } from './reports.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { TenantContext } from '../../common/context/tenant-context';

@ApiTags('reports')
@ApiBearerAuth('JWT')
@Controller('reports')
@UseGuards(JwtAuthGuard)
export class ReportsController {
  constructor(
    private readonly reportsService: ReportsService,
    private readonly tenantContext: TenantContext,
  ) {}

  @Get('kpis')
  @ApiOperation({
    summary: 'KPIs globais da empresa',
    description:
      'Retorna totais, taxas e tendências de 7 dias das otimizações.\n\n⚠️ **DEPRECATED**: Use operationReportingApi endpoints instead.',
    deprecated: true,
  })
  @ApiResponse({
    status: 200,
    description:
      'KPIs: totalRuns, completedRuns, trend7d, averages, lastOptimization.',
  })
  getKpis() {
    return this.reportsService.getKpisByCompany(this._requireCompany());
  }

  @Get('history')
  @ApiOperation({
    summary: 'Histórico de otimizações',
    description: 'Paginado, últimos N dias.\n\n⚠️ **DEPRECATED**: Use GET /operations/schedules instead.',
    deprecated: true,
  })
  @ApiQuery({ name: 'days', required: false, example: 30 })
  @ApiQuery({ name: 'page', required: false, example: 1 })
  @ApiQuery({ name: 'limit', required: false, example: 50 })
  @ApiResponse({
    status: 200,
    description: 'Página de schedules com metadados.',
  })
  getHistory(
    @Query('days') days?: string,
    @Query('page') page?: string,
    @Query('limit') limit?: string,
  ) {
    return this.reportsService.getOptimizationHistory(
      this._requireCompany(),
      days ? +days : 30,
      page ? +page : 1,
      limit ? +limit : 50,
    );
  }

  @Get('compare')
  @ApiOperation({
    summary: 'Comparar duas otimizações',
    description:
      'Retorna delta de veículos, crew, custo e violações entre dois schedules do mesmo tenant.\n\n⚠️ **DEPRECATED**: No replacement endpoint; use operationReportingApi for detailed comparisons.',
    deprecated: true,
  })
  @ApiQuery({ name: 'run1', type: Number, example: 10 })
  @ApiQuery({ name: 'run2', type: Number, example: 12 })
  @ApiResponse({ status: 200, description: 'run1, run2 e delta de métricas.' })
  @ApiResponse({
    status: 404,
    description: 'Schedule não encontrado no tenant.',
  })
  compare(
    @Query('run1', ParseIntPipe) run1: number,
    @Query('run2', ParseIntPipe) run2: number,
  ) {
    return this.reportsService.compareOptimizations(
      run1,
      run2,
      this._requireCompany(),
    );
  }

  private _requireCompany(): number {
    const id = this.tenantContext.getCompanyId();
    if (!id)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return id;
  }
}
