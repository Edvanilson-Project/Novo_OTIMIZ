import {
  Controller, Get, Post, Patch, Delete,
  Param, Body, ParseIntPipe, UseGuards, HttpCode, HttpStatus,
  Header, Res,
} from '@nestjs/common';
import type { Response } from 'express';
import { CustomReportsService, SUPPORTED_METRICS } from './custom-reports.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('custom-reports')
@UseGuards(JwtAuthGuard)
export class CustomReportsController {
  constructor(private readonly service: CustomReportsService) {}

  @Get('metrics')
  listSupportedMetrics() {
    return { metrics: SUPPORTED_METRICS };
  }

  @Get()
  findAll() {
    return this.service.findAll();
  }

  @Get(':id')
  findOne(@Param('id', ParseIntPipe) id: number) {
    return this.service.findOne(id);
  }

  @Post()
  create(@Body() body: Record<string, any>) {
    return this.service.create(body);
  }

  @Patch(':id')
  update(@Param('id', ParseIntPipe) id: number, @Body() body: Record<string, any>) {
    return this.service.update(id, body);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.service.remove(id);
  }

  @Post('preview')
  preview(@Body() body: Record<string, any>) {
    return this.service.preview(body.metrics, body.filters ?? {});
  }

  @Get(':id/run')
  run(@Param('id', ParseIntPipe) id: number) {
    return this.service.run(id);
  }

  @Get(':id/export.csv')
  @Header('Content-Type', 'text/csv; charset=utf-8')
  async exportCsv(@Param('id', ParseIntPipe) id: number, @Res() res: Response) {
    const payload = await this.service.run(id);
    const csv = this.service.toCsv(payload);
    res.setHeader('Content-Disposition', `attachment; filename="report-${id}.csv"`);
    res.send(csv);
  }

  @Get(':id/export.pdf')
  async exportPdf(@Param('id', ParseIntPipe) id: number, @Res() res: Response) {
    const report = await this.service.findOne(id);
    const payload = await this.service.run(id);
    const pdf = await this.service.toPdf(report, payload);
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="report-${id}.pdf"`);
    res.send(pdf);
  }
}
