import {
  Controller,
  Get,
  Post,
  Param,
  Query,
  ParseIntPipe,
  UseGuards,
  Res,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiBearerAuth, ApiParam, ApiQuery } from '@nestjs/swagger';
import type { Response } from 'express';
import { OperationReportGeneratorService } from './operation-report-generator.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';
import { TenantContext } from '../../../common/context/tenant-context';

@ApiTags('reporting')
@ApiBearerAuth('JWT')
@Controller('operations/reporting')
@UseGuards(JwtAuthGuard)
export class OperationReportController {
  constructor(
    private reportGenerator: OperationReportGeneratorService,
    private tenantContext: TenantContext,
  ) {}

  private getCompanyId(): number {
    const id = this.tenantContext.getCompanyId();
    if (!id) throw new ForbiddenException('Empresa não identificada no contexto autenticado.');
    return id;
  }

  @Post('generate/:scheduleId')
  @ApiOperation({ summary: 'Gerar relatório de operação', description: 'Computa KPIs, alertas e recomendações para a escala.' })
  @ApiParam({ name: 'scheduleId', type: Number })
  @ApiResponse({ status: 201, description: 'Relatório gerado com KPIs e alertas.' })
  @ApiResponse({ status: 403, description: 'Empresa não identificada.' })
  async generateReport(@Param('scheduleId', ParseIntPipe) scheduleId: number) {
    return this.reportGenerator.generateReport(scheduleId, this.getCompanyId());
  }

  @Get('historical/:scheduleId')
  @ApiOperation({ summary: 'Histórico de relatórios de otimização', description: 'Retorna runs de OptimizationRun dos últimos N dias.' })
  @ApiParam({ name: 'scheduleId', type: Number })
  @ApiQuery({ name: 'days', required: false, example: 30 })
  @ApiResponse({ status: 200, description: 'Lista de runs históricos com métricas.' })
  async getHistoricalReports(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Query('days', new ParseIntPipe({ optional: true })) days: number = 30,
  ) {
    return this.reportGenerator.getHistoricalReports(scheduleId, this.getCompanyId(), days);
  }

  @Get('compare/:scheduleId')
  @ApiOperation({ summary: 'Comparar relatórios por período', description: 'Compara métricas entre duas datas ISO.' })
  @ApiParam({ name: 'scheduleId', type: Number })
  @ApiQuery({ name: 'startDate', example: '2026-01-01' })
  @ApiQuery({ name: 'endDate', example: '2026-01-31' })
  @ApiResponse({ status: 200, description: 'Delta de KPIs entre os dois períodos.' })
  @ApiResponse({ status: 400, description: 'startDate ou endDate inválidos.' })
  async compareReports(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Query('startDate') startDate: string,
    @Query('endDate') endDate: string,
  ) {
    const start = new Date(startDate);
    const end = new Date(endDate);
    if (!startDate || isNaN(start.getTime())) {
      throw new BadRequestException('startDate inválida ou ausente (formato ISO esperado)');
    }
    if (!endDate || isNaN(end.getTime())) {
      throw new BadRequestException('endDate inválida ou ausente (formato ISO esperado)');
    }
    return this.reportGenerator.compareReports(
      scheduleId,
      this.getCompanyId(),
      start,
      end,
    );
  }

  @Get('export-pdf/:scheduleId')
  async exportPDF(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Res() res: Response,
  ) {
    const pdf = await this.reportGenerator.generatePDFReport(scheduleId, this.getCompanyId());
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="operacao_relatorio_${scheduleId}.pdf"`,
    );
    res.send(pdf);
  }

  @Get('duties/:scheduleId')
  @ApiOperation({ summary: 'Estatísticas de jornadas', description: 'Retorna Gini, P5/P95, violações e custo por jornada.' })
  @ApiParam({ name: 'scheduleId', type: Number })
  @ApiResponse({ status: 200, description: 'Resumo e detalhe por jornada com indicadores de equidade.' })
  async getDutyStats(@Param('scheduleId', ParseIntPipe) scheduleId: number) {
    return this.reportGenerator.getDutyStats(scheduleId, this.getCompanyId());
  }

  @Get('export-excel/:scheduleId')
  async exportExcel(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Res() res: Response,
  ) {
    const excel = await this.reportGenerator.generateExcelReport(scheduleId, this.getCompanyId());
    res.setHeader(
      'Content-Type',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    );
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="operacao_relatorio_${scheduleId}.xlsx"`,
    );
    res.send(excel);
  }
}
