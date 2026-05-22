import { NotFoundException } from '@nestjs/common';
import { ReportsService } from './reports.service';
import { ScheduleStatus } from '../database/entities/schedule.entity';

function makeScheduleRepo(runs: any[] = []) {
  return {
    count: jest.fn().mockResolvedValue(0),
    findOne: jest.fn().mockResolvedValue(runs[0] ?? null),
    find: jest.fn().mockResolvedValue(runs),
    findAndCount: jest.fn().mockResolvedValue([runs, runs.length]),
  } as any;
}

function makeTripRepo(count = 0) {
  return { count: jest.fn().mockResolvedValue(count) } as any;
}

function makeLineRepo(count = 0) {
  return { count: jest.fn().mockResolvedValue(count) } as any;
}

const completedRun = {
  id: 10,
  status: ScheduleStatus.COMPLETED,
  companyId: 16,
  referenceDate: '2026-01-01',
  createdAt: new Date(),
  updatedAt: new Date(),
  totalCost: 50000,
  cctViolations: 2,
  metadata: {
    num_vehicles: 10,
    num_crew: 20,
    algorithm: 'greedy',
    elapsed_ms: 1200,
  },
};

describe('ReportsService', () => {
  let service: ReportsService;
  let scheduleRepo: ReturnType<typeof makeScheduleRepo>;
  let tripRepo: ReturnType<typeof makeTripRepo>;
  let lineRepo: ReturnType<typeof makeLineRepo>;

  beforeEach(() => {
    scheduleRepo = makeScheduleRepo([completedRun]);
    tripRepo = makeTripRepo(100);
    lineRepo = makeLineRepo(5);
    service = new ReportsService(scheduleRepo, tripRepo, lineRepo);
  });

  // ── getKpisByCompany ──────────────────────────────────────────────────────

  describe('getKpisByCompany', () => {
    it('returns KPI object with required fields', async () => {
      scheduleRepo.count
        .mockResolvedValueOnce(10)
        .mockResolvedValueOnce(8)
        .mockResolvedValueOnce(2);
      scheduleRepo.count.mockResolvedValueOnce(3).mockResolvedValueOnce(5);
      scheduleRepo.find.mockResolvedValue([completedRun]);
      const result = await service.getKpisByCompany(16);
      expect(result).toHaveProperty('totalRuns');
      expect(result).toHaveProperty('completedRuns');
      expect(result).toHaveProperty('successRate');
      expect(result).toHaveProperty('totalTrips');
      expect(result).toHaveProperty('totalLines');
    });

    it('returns averages when runs have metadata', async () => {
      scheduleRepo.find.mockResolvedValue([completedRun]);
      const result = await service.getKpisByCompany(16);
      expect(result.averages).not.toBeNull();
      expect(result.averages?.vehicles).toBe(10);
    });

    it('returns null averages when no runs with data', async () => {
      scheduleRepo.find.mockResolvedValue([]);
      scheduleRepo.findOne.mockResolvedValue(null);
      const result = await service.getKpisByCompany(16);
      expect(result.averages).toBeNull();
      expect(result.lastOptimization).toBeNull();
    });

    it('returns trend7d null when prev7 is 0', async () => {
      scheduleRepo.count
        .mockResolvedValueOnce(0) // totalRuns
        .mockResolvedValueOnce(0) // completedRuns
        .mockResolvedValueOnce(0) // failedRuns
        .mockResolvedValueOnce(0) // last7
        .mockResolvedValueOnce(0); // prev7
      const result = await service.getKpisByCompany(16);
      expect(result.trend7d).toBeNull();
    });

    it('lastOptimization includes algorithm from metadata', async () => {
      scheduleRepo.findOne.mockResolvedValue(completedRun);
      const result = await service.getKpisByCompany(16);
      expect(result.lastOptimization?.algorithm).toBe('greedy');
    });
  });

  // ── getOptimizationHistory ────────────────────────────────────────────────

  describe('getOptimizationHistory', () => {
    it('returns paginated history', async () => {
      scheduleRepo.findAndCount.mockResolvedValue([[completedRun], 1]);
      const result = await service.getOptimizationHistory(16);
      expect(result.total).toBe(1);
      expect(result.items).toHaveLength(1);
      expect(result.pages).toBe(1);
    });

    it('maps metadata fields to items', async () => {
      scheduleRepo.findAndCount.mockResolvedValue([[completedRun], 1]);
      const result = await service.getOptimizationHistory(16);
      const item = result.items[0];
      expect(item.vehicles).toBe(10);
      expect(item.elapsedMs).toBe(1200);
    });

    it('uses custom days, page, and limit', async () => {
      scheduleRepo.findAndCount.mockResolvedValue([[], 0]);
      await service.getOptimizationHistory(16, 7, 2, 10);
      expect(scheduleRepo.findAndCount).toHaveBeenCalledWith(
        expect.objectContaining({ take: 10, skip: 10 }),
      );
    });
  });

  // ── compareOptimizations ─────────────────────────────────────────────────

  describe('compareOptimizations', () => {
    const run2 = {
      ...completedRun,
      id: 20,
      totalCost: 45000,
      cctViolations: 1,
      metadata: { num_vehicles: 8 },
    };

    it('returns delta between two runs', async () => {
      scheduleRepo.findOne
        .mockResolvedValueOnce(completedRun)
        .mockResolvedValueOnce(run2);
      const result = await service.compareOptimizations(10, 20, 16);
      expect(result.delta.vehicles).toBe(-2);
      expect(result.delta.cost).toBe(-5000);
    });

    it('throws NotFoundException when run1 not found', async () => {
      scheduleRepo.findOne.mockResolvedValueOnce(null);
      await expect(service.compareOptimizations(10, 20, 16)).rejects.toThrow(
        NotFoundException,
      );
    });

    it('throws NotFoundException when run2 not found', async () => {
      scheduleRepo.findOne
        .mockResolvedValueOnce(completedRun)
        .mockResolvedValueOnce(null);
      await expect(service.compareOptimizations(10, 20, 16)).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
