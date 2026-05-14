import { Controller, Get, Query, ParseIntPipe, UseGuards, BadRequestException } from '@nestjs/common';
import { ReportsService } from './reports.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { TenantContext } from '../../common/context/tenant-context';

@Controller('reports')
@UseGuards(JwtAuthGuard)
export class ReportsController {
  constructor(
    private readonly reportsService: ReportsService,
    private readonly tenantContext: TenantContext,
  ) {}

  @Get('kpis')
  getKpis() {
    return this.reportsService.getKpisByCompany(this._requireCompany());
  }

  @Get('history')
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
  compare(
    @Query('run1', ParseIntPipe) run1: number,
    @Query('run2', ParseIntPipe) run2: number,
  ) {
    return this.reportsService.compareOptimizations(run1, run2, this._requireCompany());
  }

  private _requireCompany(): number {
    const id = this.tenantContext.getCompanyId();
    if (!id) throw new BadRequestException('Empresa não identificada no contexto.');
    return id;
  }
}
