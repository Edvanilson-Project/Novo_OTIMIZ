import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import { Schedule, ScheduleStatus } from '../database/entities/schedule.entity';
import { Trip } from '../database/entities/trip.entity';
import { Line } from '../database/entities/line.entity';

@Injectable()
export class ReportsService {
  constructor(
    @InjectRepository(Schedule)
    private readonly scheduleRepo: Repository<Schedule>,
    @InjectRepository(Trip)
    private readonly tripRepo: Repository<Trip>,
    @InjectRepository(Line)
    private readonly lineRepo: Repository<Line>,
  ) {}

  async getKpisByCompany(companyId: number) {
    const [totalRuns, completedRuns, failedRuns] = await Promise.all([
      this.scheduleRepo.count({ where: { companyId } }),
      this.scheduleRepo.count({
        where: { companyId, status: ScheduleStatus.COMPLETED },
      }),
      this.scheduleRepo.count({
        where: { companyId, status: ScheduleStatus.FAILED },
      }),
    ]);

    const lastCompleted = await this.scheduleRepo.findOne({
      where: { companyId, status: ScheduleStatus.COMPLETED },
      order: { updatedAt: 'DESC' },
    });

    const [totalTrips, totalLines] = await Promise.all([
      this.tripRepo.count({ where: { companyId } }),
      this.lineRepo.count({ where: { companyId } }),
    ]);

    // Trend: últimos 7 dias vs 7 dias anteriores
    const now = new Date();
    const d7 = new Date(now);
    d7.setDate(d7.getDate() - 7);
    const d14 = new Date(now);
    d14.setDate(d14.getDate() - 14);

    const [last7, prev7] = await Promise.all([
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
    const trend7d =
      prev7 > 0
        ? (((last7 - (prev7 - last7)) / (prev7 - last7 || 1)) * 100).toFixed(1)
        : null;

    // Médias de veículos, crew e custo dos últimos 30 runs
    const recentRuns = await this.scheduleRepo.find({
      where: { companyId, status: ScheduleStatus.COMPLETED },
      order: { updatedAt: 'DESC' },
      take: 30,
    });

    let sumVehicles = 0,
      sumCrew = 0,
      sumCost = 0,
      countWithData = 0;
    for (const r of recentRuns) {
      const meta = r.metadata as Record<string, unknown> | null;
      const v = (meta?.num_vehicles ?? meta?.vehicles) as number | undefined;
      const c = (meta?.num_crew ?? meta?.crew) as number | undefined;
      if (v != null || c != null) {
        sumVehicles += v ?? 0;
        sumCrew += c ?? 0;
        sumCost += Number(r.totalCost) || 0;
        countWithData++;
      }
    }

    const meta = lastCompleted?.metadata as Record<string, unknown> | null;

    return {
      totalRuns,
      completedRuns,
      failedRuns,
      successRate:
        totalRuns > 0 ? ((completedRuns / totalRuns) * 100).toFixed(1) : '0',
      totalTrips,
      totalLines,
      trend7d,
      averages:
        countWithData > 0
          ? {
              vehicles: +(sumVehicles / countWithData).toFixed(1),
              crew: +(sumCrew / countWithData).toFixed(1),
              cost: +(sumCost / countWithData).toFixed(2),
            }
          : null,
      lastOptimization: lastCompleted
        ? {
            id: lastCompleted.id,
            date: lastCompleted.updatedAt,
            vehicles: meta?.num_vehicles ?? meta?.vehicles ?? null,
            crew: meta?.num_crew ?? meta?.crew ?? null,
            cost: lastCompleted.totalCost,
            cctViolations: lastCompleted.cctViolations,
            algorithm: meta?.algorithm ?? null,
          }
        : null,
    };
  }

  async getOptimizationHistory(
    companyId: number,
    days = 30,
    page = 1,
    limit = 50,
  ) {
    const since = new Date();
    since.setDate(since.getDate() - days);
    const [runs, total] = await this.scheduleRepo.findAndCount({
      where: { companyId, createdAt: MoreThanOrEqual(since) },
      order: { createdAt: 'DESC' },
      take: limit,
      skip: (page - 1) * limit,
    });

    const items = runs.map((r) => {
      const meta = r.metadata as Record<string, unknown> | null;
      return {
        id: r.id,
        status: r.status,
        referenceDate: r.referenceDate,
        createdAt: r.createdAt,
        totalCost: r.totalCost,
        cctViolations: r.cctViolations,
        vehicles: meta?.num_vehicles ?? meta?.vehicles ?? null,
        crew: meta?.num_crew ?? meta?.crew ?? null,
        algorithm: meta?.algorithm ?? null,
        elapsedMs: meta?.elapsed_ms ?? null,
      };
    });

    return { items, total, page, limit, pages: Math.ceil(total / limit) };
  }

  async compareOptimizations(
    runId1: number,
    runId2: number,
    companyId: number,
  ) {
    const [run1, run2] = await Promise.all([
      this.scheduleRepo.findOne({ where: { id: runId1, companyId } }),
      this.scheduleRepo.findOne({ where: { id: runId2, companyId } }),
    ]);

    if (!run1)
      throw new NotFoundException(`Schedule #${runId1} não encontrado`);
    if (!run2)
      throw new NotFoundException(`Schedule #${runId2} não encontrado`);

    const meta1 = run1.metadata as Record<string, unknown> | null;
    const meta2 = run2.metadata as Record<string, unknown> | null;

    const v1 = Number(meta1?.num_vehicles ?? meta1?.vehicles ?? 0);
    const v2 = Number(meta2?.num_vehicles ?? meta2?.vehicles ?? 0);
    const c1 = Number(meta1?.num_crew ?? meta1?.crew ?? 0);
    const c2 = Number(meta2?.num_crew ?? meta2?.crew ?? 0);

    return {
      run1: {
        id: run1.id,
        referenceDate: run1.referenceDate,
        vehicles: v1,
        crew: c1,
        cost: run1.totalCost,
        violations: run1.cctViolations,
        algorithm: meta1?.algorithm ?? null,
      },
      run2: {
        id: run2.id,
        referenceDate: run2.referenceDate,
        vehicles: v2,
        crew: c2,
        cost: run2.totalCost,
        violations: run2.cctViolations,
        algorithm: meta2?.algorithm ?? null,
      },
      delta: {
        vehicles: v2 - v1,
        crew: c2 - c1,
        cost: (Number(run2.totalCost) || 0) - (Number(run1.totalCost) || 0),
        violations: (run2.cctViolations || 0) - (run1.cctViolations || 0),
      },
    };
  }
}
