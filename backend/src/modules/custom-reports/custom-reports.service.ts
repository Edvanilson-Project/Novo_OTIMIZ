import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import PDFDocument from 'pdfkit';
import {
  CustomReport,
  CustomReportFormat,
} from '../database/entities/custom-report.entity';
import { Schedule, ScheduleStatus } from '../database/entities/schedule.entity';
import { Trip } from '../database/entities/trip.entity';
import { Line } from '../database/entities/line.entity';
import { TenantContext } from '../../common/context/tenant-context';
import type {
  CreateCustomReportDto,
  CustomReportFilters,
  CustomReportPayload,
  RecentRunSummary,
  UpdateCustomReportDto,
} from './custom-reports.dto';

export const SUPPORTED_METRICS = [
  'totalRuns',
  'completedRuns',
  'failedRuns',
  'successRate',
  'totalTrips',
  'totalLines',
  'avgVehicles',
  'avgCrew',
  'avgCost',
  'trend7d',
  'recentRuns',
] as const;

export type SupportedMetric = (typeof SUPPORTED_METRICS)[number];

@Injectable()
export class CustomReportsService {
  constructor(
    @InjectRepository(CustomReport)
    private readonly reportRepo: Repository<CustomReport>,
    @InjectRepository(Schedule)
    private readonly scheduleRepo: Repository<Schedule>,
    @InjectRepository(Trip)
    private readonly tripRepo: Repository<Trip>,
    @InjectRepository(Line)
    private readonly lineRepo: Repository<Line>,
    private readonly tenantContext: TenantContext,
  ) {}

  private companyId(): number {
    const id = this.tenantContext.getCompanyId();
    if (!id)
      throw new BadRequestException('Empresa não identificada no contexto.');
    return id;
  }

  async findAll(): Promise<CustomReport[]> {
    return this.reportRepo.find({
      where: { companyId: this.companyId() },
      order: { updatedAt: 'DESC' },
    });
  }

  async findOne(id: number): Promise<CustomReport> {
    const report = await this.reportRepo.findOne({
      where: { id, companyId: this.companyId() },
    });
    if (!report) throw new NotFoundException(`Relatório ${id} não encontrado`);
    return report;
  }

  /**
   * Aceita `Partial` porque a validação primária do shape vem do ValidationPipe
   * (decorators no DTO). O service ainda valida runtime (metrics não-vazia) para
   * suportar chamadas internas que bypassam o pipe.
   */
  async create(dto: Partial<CreateCustomReportDto>): Promise<CustomReport> {
    this.validateMetrics(dto.metrics);
    const entity = this.reportRepo.create({
      companyId: this.companyId(),
      name: dto.name,
      description: dto.description ?? null,
      ownerUserId: dto.ownerUserId ?? null,
      metrics: dto.metrics,
      filters: dto.filters ?? {},
      format: dto.format ?? CustomReportFormat.JSON,
    });
    return this.reportRepo.save(entity);
  }

  async update(id: number, dto: UpdateCustomReportDto): Promise<CustomReport> {
    const report = await this.findOne(id);
    if (dto.metrics !== undefined) this.validateMetrics(dto.metrics);
    Object.assign(report, {
      name: dto.name ?? report.name,
      description: dto.description ?? report.description,
      metrics: dto.metrics ?? report.metrics,
      filters: dto.filters ?? report.filters,
      format: dto.format ?? report.format,
    });
    return this.reportRepo.save(report);
  }

  async remove(id: number): Promise<void> {
    const report = await this.findOne(id);
    await this.reportRepo.remove(report);
  }

  async run(id: number): Promise<CustomReportPayload> {
    const report = await this.findOne(id);
    return this.execute(
      report.metrics as SupportedMetric[],
      report.filters as CustomReportFilters,
    );
  }

  async preview(
    metrics: string[],
    filters: CustomReportFilters,
  ): Promise<CustomReportPayload> {
    this.validateMetrics(metrics);
    return this.execute(metrics as SupportedMetric[], filters ?? {});
  }

  private validateMetrics(metrics: unknown): void {
    if (!Array.isArray(metrics) || metrics.length === 0) {
      throw new BadRequestException(
        'Campo `metrics` deve ser uma lista não-vazia.',
      );
    }
    for (const m of metrics) {
      if (!SUPPORTED_METRICS.includes(m as SupportedMetric)) {
        throw new BadRequestException(`Métrica não suportada: ${m}`);
      }
    }
  }

  private async execute(
    metrics: SupportedMetric[],
    filters: CustomReportFilters,
  ): Promise<CustomReportPayload> {
    const companyId = this.companyId();
    const dateRangeDays = Number(filters.dateRangeDays ?? 30);
    const result: CustomReportPayload = {
      generatedAt: new Date().toISOString(),
      filters: { dateRangeDays },
    };
    const wants = new Set(metrics);

    const sinceMain = new Date();
    sinceMain.setDate(sinceMain.getDate() - dateRangeDays);

    if (
      wants.has('totalRuns') ||
      wants.has('completedRuns') ||
      wants.has('failedRuns') ||
      wants.has('successRate')
    ) {
      const [total, completed, failed] = await Promise.all([
        this.scheduleRepo.count({
          where: { companyId, createdAt: MoreThanOrEqual(sinceMain) },
        }),
        this.scheduleRepo.count({
          where: {
            companyId,
            status: ScheduleStatus.COMPLETED,
            createdAt: MoreThanOrEqual(sinceMain),
          },
        }),
        this.scheduleRepo.count({
          where: {
            companyId,
            status: ScheduleStatus.FAILED,
            createdAt: MoreThanOrEqual(sinceMain),
          },
        }),
      ]);
      if (wants.has('totalRuns')) result.totalRuns = total;
      if (wants.has('completedRuns')) result.completedRuns = completed;
      if (wants.has('failedRuns')) result.failedRuns = failed;
      if (wants.has('successRate')) {
        result.successRate =
          total > 0 ? +((completed / total) * 100).toFixed(1) : 0;
      }
    }

    if (wants.has('totalTrips')) {
      result.totalTrips = await this.tripRepo.count({ where: { companyId } });
    }
    if (wants.has('totalLines')) {
      result.totalLines = await this.lineRepo.count({ where: { companyId } });
    }

    if (
      wants.has('avgVehicles') ||
      wants.has('avgCrew') ||
      wants.has('avgCost')
    ) {
      const recent = await this.scheduleRepo.find({
        where: {
          companyId,
          status: ScheduleStatus.COMPLETED,
          createdAt: MoreThanOrEqual(sinceMain),
        },
        order: { updatedAt: 'DESC' },
        take: 30,
      });
      let sumV = 0,
        sumC = 0,
        sumCost = 0,
        n = 0;
      for (const r of recent) {
        const meta: Record<string, unknown> =
          (r.metadata as Record<string, unknown>) || {};
        const v = (meta.num_vehicles ?? meta.vehicles) as number | undefined;
        const c = (meta.num_crew ?? meta.crew) as number | undefined;
        if (v != null || c != null) {
          sumV += v ?? 0;
          sumC += c ?? 0;
          sumCost += Number(r.totalCost) || 0;
          n++;
        }
      }
      if (wants.has('avgVehicles'))
        result.avgVehicles = n > 0 ? +(sumV / n).toFixed(1) : null;
      if (wants.has('avgCrew'))
        result.avgCrew = n > 0 ? +(sumC / n).toFixed(1) : null;
      if (wants.has('avgCost'))
        result.avgCost = n > 0 ? +(sumCost / n).toFixed(2) : null;
    }

    if (wants.has('trend7d')) {
      const d7 = new Date();
      d7.setDate(d7.getDate() - 7);
      const d14 = new Date();
      d14.setDate(d14.getDate() - 14);
      const [last7, prev14] = await Promise.all([
        this.scheduleRepo.count({
          where: {
            companyId,
            status: ScheduleStatus.COMPLETED,
            createdAt: MoreThanOrEqual(d7),
          },
        }),
        this.scheduleRepo.count({
          where: {
            companyId,
            status: ScheduleStatus.COMPLETED,
            createdAt: MoreThanOrEqual(d14),
          },
        }),
      ]);
      const prev7 = prev14 - last7;
      result.trend7d =
        prev7 > 0 ? +(((last7 - prev7) / prev7) * 100).toFixed(1) : null;
    }

    if (wants.has('recentRuns')) {
      const runs = await this.scheduleRepo.find({
        where: { companyId, createdAt: MoreThanOrEqual(sinceMain) },
        order: { createdAt: 'DESC' },
        take: 20,
      });
      result.recentRuns = runs.map((r): RecentRunSummary => {
        const meta: Record<string, unknown> =
          (r.metadata as Record<string, unknown>) || {};
        return {
          id: r.id,
          status: r.status,
          createdAt: r.createdAt,
          totalCost: r.totalCost,
          cctViolations: r.cctViolations,
          vehicles:
            ((meta.num_vehicles ?? meta.vehicles) as number | null) ?? null,
          crew: ((meta.num_crew ?? meta.crew) as number | null) ?? null,
          algorithm: (meta.algorithm as string | null) ?? null,
        };
      });
    }

    return result;
  }

  toCsv(payload: CustomReportPayload): string {
    const flat: Array<[string, string]> = [];
    for (const [k, v] of Object.entries(payload)) {
      if (k === 'recentRuns' && Array.isArray(v)) continue;
      if (k === 'filters' && typeof v === 'object' && v !== null) {
        for (const [fk, fv] of Object.entries(v as Record<string, unknown>))
          flat.push([`filter.${fk}`, String(fv)]);
      } else {
        flat.push([k, v == null ? '' : String(v)]);
      }
    }
    let csv = 'metric,value\n';
    for (const [k, v] of flat) {
      csv += `${k},${this.csvEscape(v)}\n`;
    }
    if (Array.isArray(payload.recentRuns) && payload.recentRuns.length > 0) {
      const cols = Object.keys(payload.recentRuns[0]) as Array<
        keyof RecentRunSummary
      >;
      csv += `\nrecentRuns\n${cols.join(',')}\n`;
      for (const row of payload.recentRuns) {
        csv += cols.map((c) => this.csvEscape(row[c])).join(',') + '\n';
      }
    }
    return csv;
  }

  private csvEscape(value: unknown): string {
    if (value == null) return '';
    const s = typeof value === 'string' ? value : JSON.stringify(value);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }

  async toPdf(
    report: CustomReport,
    payload: CustomReportPayload,
  ): Promise<Buffer> {
    return new Promise((resolve, reject) => {
      const doc = new PDFDocument({ margin: 48, size: 'A4' });
      const chunks: Buffer[] = [];
      doc.on('data', (c: Buffer) => chunks.push(c));
      doc.on('end', () => resolve(Buffer.concat(chunks)));
      doc.on('error', reject);

      doc.fontSize(18).text(report.name, { align: 'left' });
      if (report.description) {
        doc
          .moveDown(0.3)
          .fontSize(10)
          .fillColor('#666')
          .text(report.description);
      }
      doc
        .moveDown(0.5)
        .fontSize(9)
        .fillColor('#888')
        .text(
          `Gerado em: ${new Date(payload.generatedAt ?? new Date()).toLocaleString('pt-BR')}`,
        )
        .text(`Janela: últimos ${payload.filters?.dateRangeDays ?? 30} dia(s)`);
      doc.moveDown(0.8);

      doc.fillColor('#000').fontSize(12).text('Métricas', { underline: true });
      doc.moveDown(0.3).fontSize(10);

      for (const [k, v] of Object.entries(payload)) {
        if (k === 'generatedAt' || k === 'filters' || k === 'recentRuns')
          continue;
        if (v == null) continue;
        doc.text(`${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`);
      }

      if (Array.isArray(payload.recentRuns) && payload.recentRuns.length > 0) {
        doc
          .moveDown(0.8)
          .fontSize(12)
          .text('Execuções recentes', { underline: true });
        doc.moveDown(0.3).fontSize(9);
        for (const r of payload.recentRuns) {
          const date = r.createdAt
            ? new Date(r.createdAt).toLocaleDateString('pt-BR')
            : '—';
          doc.text(
            `#${r.id} · ${date} · ${r.status} · ${r.vehicles ?? '—'} veíc · ${r.crew ?? '—'} crew · R$ ${r.totalCost ?? '—'} · ${r.algorithm ?? '—'}`,
          );
        }
      }

      doc.end();
    });
  }
}
