import {
  Controller,
  Get,
  Post,
  Param,
  Query,
  ParseIntPipe,
  UseGuards,
  Res,
} from '@nestjs/common';
import type { Response } from 'express';
import { OperationReportGeneratorService } from './operation-report-generator.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';

@Controller('operations/reporting')
@UseGuards(JwtAuthGuard)
export class OperationReportController {
  constructor(private reportGenerator: OperationReportGeneratorService) {}

  @Post('generate/:scheduleId')
  async generateReport(@Param('scheduleId', ParseIntPipe) scheduleId: number) {
    return this.reportGenerator.generateReport(scheduleId);
  }

  @Get('historical/:scheduleId')
  async getHistoricalReports(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Query('days') days: number = 30,
  ) {
    return this.reportGenerator.getHistoricalReports(scheduleId, days);
  }

  @Get('compare/:scheduleId')
  async compareReports(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Query('startDate') startDate: string,
    @Query('endDate') endDate: string,
  ) {
    return this.reportGenerator.compareReports(
      scheduleId,
      new Date(startDate),
      new Date(endDate),
    );
  }

  @Get('export-pdf/:scheduleId')
  async exportPDF(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Res() res: Response,
  ) {
    const pdf = await this.reportGenerator.generatePDFReport(scheduleId);
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="operacao_relatorio_${scheduleId}.pdf"`,
    );
    res.send(pdf);
  }

  @Get('export-excel/:scheduleId')
  async exportExcel(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
    @Res() res: Response,
  ) {
    const excel = await this.reportGenerator.generateExcelReport(scheduleId);
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
