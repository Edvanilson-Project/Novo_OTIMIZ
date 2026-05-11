import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Between, In, Repository } from 'typeorm';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';
import {
  OptimizationRun,
  OptimizationRunStatus,
} from '../../database/entities/optimization-run.entity';

export interface ReportMetrics {
  totalTrips: number;
  assignedTrips: number;
  unassignedTrips: number;
  totalCost: number;
  costPerTrip: number;
  vehiclesUsed: number;
  averageUtilization: number;
  maintenanceIssues: number;
}

export interface OperationReport {
  id: string;
  scheduleId: number;
  generatedAt: Date;
  period: {
    startDate: Date;
    endDate: Date;
  };
  metrics: ReportMetrics;
  scenarioComparison: {
    current: ReportMetrics;
    optimized: ReportMetrics | null;
    savings: number;
    savingsPercent: number;
  };
  recommendations: string[];
  issues: {
    severity: 'critical' | 'warning' | 'info';
    message: string;
  }[];
  // Rastreabilidade: que run gerou esse relatório (null para baseline)
  sourceOptimizationRunId: number | null;
  algorithm: string | null;
}

@Injectable()
export class OperationReportGeneratorService {
  constructor(
    @InjectRepository(Schedule)
    private scheduleRepo: Repository<Schedule>,
    @InjectRepository(BlockAssignment)
    private blockRepo: Repository<BlockAssignment>,
    @InjectRepository(OptimizationRun)
    private runRepo: Repository<OptimizationRun>,
  ) {}

  /**
   * Gera relatório para o schedule baseline + melhor run completed para esse baseline
   * (escolhe a de menor totalCost). Recomendações vêm de issues mensurados — não há números fabricados.
   */
  async generateReport(scheduleId: number): Promise<OperationReport> {
    const schedule = await this.scheduleRepo.findOne({
      where: { id: scheduleId },
      relations: ['blocks'],
    });
    if (!schedule) throw new NotFoundException(`Schedule ${scheduleId} not found`);

    const blocks = schedule.blocks || [];
    const currentMetrics = this.metricsFromSchedule(schedule, blocks);

    // Melhor run COMPLETED para esse baseline (qualquer cenário), critério: menor totalCost factível.
    const bestRun = await this.runRepo
      .createQueryBuilder('run')
      .where('run.baselineScheduleId = :baselineId', { baselineId: scheduleId })
      .andWhere('run.status = :status', { status: OptimizationRunStatus.COMPLETED })
      .orderBy(`(run.metrics->>'totalCost')::float`, 'ASC')
      .getOne();

    let optimizedMetrics: ReportMetrics | null = null;
    let optimizedRunId: number | null = null;
    let algorithm: string | null = null;
    if (bestRun) {
      optimizedMetrics = this.metricsFromRun(bestRun);
      optimizedRunId = bestRun.id;
      algorithm = bestRun.algorithm;
    }

    const savings = optimizedMetrics ? currentMetrics.totalCost - optimizedMetrics.totalCost : 0;
    const savingsPercent =
      optimizedMetrics && currentMetrics.totalCost > 0
        ? (savings / currentMetrics.totalCost) * 100
        : 0;

    const issues = this.generateIssues(currentMetrics);
    const recommendations = this.generateRecommendations(currentMetrics, issues, optimizedMetrics);

    return {
      id: `report_${scheduleId}_${Date.now()}`,
      scheduleId,
      generatedAt: new Date(),
      period: {
        startDate: schedule.createdAt,
        endDate: new Date(),
      },
      metrics: currentMetrics,
      scenarioComparison: {
        current: currentMetrics,
        optimized: optimizedMetrics,
        savings,
        savingsPercent,
      },
      recommendations,
      issues,
      sourceOptimizationRunId: optimizedRunId,
      algorithm,
    };
  }

  /**
   * Histórico real: para cada DIA dentro da janela, traz a melhor run COMPLETED para o baseline.
   * Sem ruído sintético. Se um dia não teve otimização, ele não aparece no array.
   */
  async getHistoricalReports(scheduleId: number, days: number = 30): Promise<OperationReport[]> {
    const start = new Date();
    start.setDate(start.getDate() - days);

    const schedule = await this.scheduleRepo.findOne({
      where: { id: scheduleId },
      relations: ['blocks'],
    });
    if (!schedule) return [];

    // Todas runs completed do baseline nessa janela
    const runs = await this.runRepo.find({
      where: {
        baselineScheduleId: scheduleId,
        status: OptimizationRunStatus.COMPLETED,
        completedAt: Between(start, new Date()),
      },
      order: { completedAt: 'ASC' },
    });

    if (runs.length === 0) return [];

    const currentMetrics = this.metricsFromSchedule(schedule, schedule.blocks || []);

    // Agrupa por dia, melhor run/dia (menor totalCost)
    const byDay = new Map<string, OptimizationRun>();
    for (const run of runs) {
      if (!run.completedAt) continue;
      const dayKey = new Date(run.completedAt).toISOString().slice(0, 10);
      const existing = byDay.get(dayKey);
      const cost = Number(run.metrics?.totalCost ?? Infinity);
      const existingCost = existing ? Number(existing.metrics?.totalCost ?? Infinity) : Infinity;
      if (!existing || cost < existingCost) byDay.set(dayKey, run);
    }

    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([dayKey, run]) => {
        const m = this.metricsFromRun(run);
        const savings = currentMetrics.totalCost - m.totalCost;
        const savingsPercent =
          currentMetrics.totalCost > 0 ? (savings / currentMetrics.totalCost) * 100 : 0;
        const startDay = new Date(`${dayKey}T00:00:00Z`);
        const endDay = new Date(`${dayKey}T23:59:59Z`);
        return {
          id: `report_${scheduleId}_${run.id}`,
          scheduleId,
          generatedAt: run.completedAt!,
          period: { startDate: startDay, endDate: endDay },
          metrics: m,
          scenarioComparison: {
            current: currentMetrics,
            optimized: m,
            savings,
            savingsPercent,
          },
          recommendations: [],
          issues: this.generateIssues(m),
          sourceOptimizationRunId: run.id,
          algorithm: run.algorithm,
        } as OperationReport;
      });
  }

  /**
   * Estatísticas REAIS sobre runs no intervalo. Retorna null se não há dados — sem fabricar.
   */
  async compareReports(scheduleId: number, startDate: Date, endDate: Date) {
    const runs = await this.runRepo.find({
      where: {
        baselineScheduleId: scheduleId,
        status: OptimizationRunStatus.COMPLETED,
        completedAt: Between(startDate, endDate),
      },
      order: { completedAt: 'ASC' },
    });
    if (runs.length === 0) return null;

    const costs = runs.map((r) => Number(r.metrics?.totalCost ?? 0));
    const vehicles = runs.map((r) => Number(r.metrics?.numVehicles ?? 0));
    const violations = runs.map((r) => Number(r.metrics?.cctViolations ?? 0));

    const avgCost = costs.reduce((a, b) => a + b, 0) / costs.length;
    const avgVehicles = vehicles.reduce((a, b) => a + b, 0) / vehicles.length;
    const avgViolations = violations.reduce((a, b) => a + b, 0) / violations.length;
    const costTrend = costs.length >= 2 ? costs[costs.length - 1] - costs[0] : 0;

    const bestRunIdx = costs.indexOf(Math.min(...costs));
    const worstRunIdx = costs.indexOf(Math.max(...costs));
    const bestRun = runs[bestRunIdx];
    const worstRun = runs[worstRunIdx];

    return {
      period: { startDate, endDate },
      reportCount: runs.length,
      averageCost: avgCost,
      averageVehicles: avgVehicles,
      averageViolations: avgViolations,
      averageUtilization: null, // derivada — não medida diretamente nas runs (TODO computar a partir de trips/vehicle)
      costTrend,
      bestDay: {
        runId: bestRun.id,
        algorithm: bestRun.algorithm,
        completedAt: bestRun.completedAt,
        metrics: this.metricsFromRun(bestRun),
      },
      worstDay: {
        runId: worstRun.id,
        algorithm: worstRun.algorithm,
        completedAt: worstRun.completedAt,
        metrics: this.metricsFromRun(worstRun),
      },
    };
  }

  async generatePDFReport(scheduleId: number): Promise<Buffer> {
    const report = await this.generateReport(scheduleId);
    return Buffer.from(JSON.stringify(report, null, 2));
  }

  async generateExcelReport(scheduleId: number): Promise<Buffer> {
    const report = await this.generateReport(scheduleId);
    return Buffer.from(JSON.stringify(report, null, 2));
  }

  private metricsFromSchedule(schedule: Schedule, blocks: BlockAssignment[]): ReportMetrics {
    // Compat: tripIds[] (schema real) ou fallback 1/block (mocks legados)
    const tripsFor = (b: BlockAssignment) => (b.tripIds?.length ?? 1);
    const totalTrips = blocks.reduce((sum, b) => sum + tripsFor(b), 0);
    const assignedBlocks = blocks.filter((b) => b.vehicleId != null);
    const assignedTrips = assignedBlocks.reduce((sum, b) => sum + tripsFor(b), 0);
    const unassignedTrips = totalTrips - assignedTrips;
    const totalCost = Number(schedule.totalCost ?? 0) || blocks.reduce((s, b) => s + (b.cost || 0), 0);
    const actualVehicles =
      new Set(assignedBlocks.map((b) => b.vehicleId).filter((v) => v != null)).size ||
      assignedBlocks.length;
    const costPerTrip = assignedTrips > 0 && totalCost > 0 ? totalCost / assignedTrips : 0;
    const averageUtilization =
      actualVehicles > 0 ? Math.min(100, (assignedTrips / actualVehicles) * 20) : 0;
    return {
      totalTrips,
      assignedTrips,
      unassignedTrips,
      totalCost,
      costPerTrip,
      vehiclesUsed: actualVehicles,
      averageUtilization,
      maintenanceIssues: 0,
    };
  }

  private metricsFromRun(run: OptimizationRun): ReportMetrics {
    const m = run.metrics ?? {};
    const totalTrips = Number(m.totalTrips ?? 0);
    const unassignedTrips = Number(m.unassignedTrips ?? 0);
    const assignedTrips = totalTrips - unassignedTrips;
    const totalCost = Number(m.totalCost ?? 0);
    const vehiclesUsed = Number(m.numVehicles ?? 0);
    const costPerTrip = assignedTrips > 0 ? totalCost / assignedTrips : 0;
    const averageUtilization =
      vehiclesUsed > 0 ? Math.min(100, (assignedTrips / vehiclesUsed) * 20) : 0;
    return {
      totalTrips,
      assignedTrips,
      unassignedTrips,
      totalCost,
      costPerTrip,
      vehiclesUsed,
      averageUtilization,
      maintenanceIssues: 0,
    };
  }

  private generateIssues(
    metrics: ReportMetrics,
  ): { severity: 'critical' | 'warning' | 'info'; message: string }[] {
    const issues: { severity: 'critical' | 'warning' | 'info'; message: string }[] = [];
    if (metrics.unassignedTrips > 0) {
      issues.push({
        severity: 'critical',
        message: `${metrics.unassignedTrips} viagens não foram atribuídas. Replanejamento necessário.`,
      });
    }
    if (metrics.averageUtilization < 50) {
      issues.push({
        severity: 'warning',
        message: `Utilização baixa (${metrics.averageUtilization.toFixed(1)}%). Considere consolidar viagens.`,
      });
    }
    if (metrics.costPerTrip > 350) {
      issues.push({
        severity: 'warning',
        message: `Custo por viagem elevado (R$ ${metrics.costPerTrip.toFixed(2)}). Revisar tipos de veículos.`,
      });
    }
    if (metrics.vehiclesUsed > 12) {
      issues.push({
        severity: 'info',
        message: `Número de veículos acima do esperado (${metrics.vehiclesUsed}). Avaliar otimização.`,
      });
    }
    return issues;
  }

  private generateRecommendations(
    metrics: ReportMetrics,
    issues: { severity: 'critical' | 'warning' | 'info'; message: string }[],
    optimized: ReportMetrics | null,
  ): string[] {
    const recommendations: string[] = [];
    if (issues.some((i) => i.severity === 'critical')) {
      recommendations.push('Executar otimização imediatamente para reduzir viagens não atribuídas.');
    }
    if (metrics.averageUtilization < 50) {
      recommendations.push('Consolidar viagens em menos veículos para melhorar utilização.');
    }
    if (optimized && optimized.totalCost < metrics.totalCost) {
      const diff = metrics.totalCost - optimized.totalCost;
      const pct = metrics.totalCost > 0 ? (diff / metrics.totalCost) * 100 : 0;
      recommendations.push(
        `Aplicar cenário otimizado pode reduzir custo em R$ ${diff.toFixed(2)} (${pct.toFixed(1)}%).`,
      );
    }
    if (recommendations.length === 0) {
      recommendations.push('Operação em nível aceitável. Manter monitoramento.');
    }
    return recommendations;
  }
}
