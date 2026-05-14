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
import type { Response } from 'express';
import { OperationReportGeneratorService } from './operation-report-generator.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';
import { TenantContext } from '../../../common/context/tenant-context';

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
  async generateReport(@Param('scheduleId', ParseIntPipe) scheduleId: number) {
    return this.reportGenerator.generateReport(scheduleId, this.getCompanyId());
  }

  @Get('historical/:scheduleId')
  async getHistoricalReports(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Query('days', new ParseIntPipe({ optional: true })) days: number = 30,
  ) {
    return this.reportGenerator.getHistoricalReports(scheduleId, this.getCompanyId(), days);
  }

  @Get('compare/:scheduleId')
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
