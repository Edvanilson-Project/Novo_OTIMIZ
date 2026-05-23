import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { OperationReportGeneratorService } from './operation-report-generator.service';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';
import { DutyAssignment } from '../../database/entities/duty-assignment.entity';
import { Trip } from '../../database/entities/trip.entity';
import {
  OptimizationRun,
  OptimizationRunStatus,
} from '../../database/entities/optimization-run.entity';

const baselineSchedule = (overrides: any = {}) => ({
  id: 1,
  totalCost: 5000,
  cctViolations: 0,
  createdAt: new Date('2026-05-10T08:00:00Z'),
  blocks: [
    { vehicleId: 1, tripIds: [1, 2, 3], cost: 1500 },
    { vehicleId: 1, tripIds: [4, 5], cost: 1300 },
    { vehicleId: 2, tripIds: [6, 7], cost: 1200 },
  ],
  ...overrides,
});

const completedRun = (overrides: any = {}): OptimizationRun => ({
  id: 10,
  companyId: 16,
  scenarioId: 'cost-optimized',
  baselineScheduleId: 1,
  resultScheduleId: 100,
  inputFingerprint: 'fp-10',
  params: {},
  algorithm: 'vcsp_pulp',
  randomSeed: 42,
  status: OptimizationRunStatus.COMPLETED,
  metrics: {
    totalCost: 4500,
    numVehicles: 10,
    numDuties: 12,
    totalTrips: 100,
    unassignedTrips: 0,
    cctViolations: 0,
    hardIssueCount: 0,
    softIssueCount: 0,
  },
  errorMessage: null,
  durationMs: 60000,
  createdAt: new Date('2026-05-10T10:00:00Z'),
  updatedAt: new Date('2026-05-10T10:01:00Z'),
  completedAt: new Date('2026-05-10T10:01:00Z'),
  ...overrides,
});

describe('OperationReportGeneratorService', () => {
  let service: OperationReportGeneratorService;
  let scheduleRepo: any;
  let blockRepo: any;
  let runRepo: any;
  let dutyRepo: any;
  let tripRepo: any;

  // Mock trips for utilization calculation
  const mockTrips = [
    { id: 1, startTime: 360, endTime: 420, duration: 60 }, // 6:00-7:00 = 60min
    { id: 2, startTime: 420, endTime: 480, duration: 60 }, // 7:00-8:00
    { id: 3, startTime: 480, endTime: 540, duration: 60 }, // 8:00-9:00
    { id: 4, startTime: 540, endTime: 600, duration: 60 }, // 9:00-10:00
    { id: 5, startTime: 600, endTime: 660, duration: 60 }, // 10:00-11:00
    { id: 6, startTime: 660, endTime: 720, duration: 60 }, // 11:00-12:00
    { id: 7, startTime: 720, endTime: 780, duration: 60 }, // 12:00-13:00
  ];

  beforeEach(async () => {
    scheduleRepo = { findOne: jest.fn() };
    blockRepo = { find: jest.fn() };
    runRepo = {
      findOne: jest.fn(),
      find: jest.fn(),
      createQueryBuilder: jest.fn(),
    };
    dutyRepo = { find: jest.fn() };
    tripRepo = { find: jest.fn().mockResolvedValue(mockTrips) };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OperationReportGeneratorService,
        { provide: getRepositoryToken(Schedule), useValue: scheduleRepo },
        { provide: getRepositoryToken(BlockAssignment), useValue: blockRepo },
        { provide: getRepositoryToken(OptimizationRun), useValue: runRepo },
        { provide: getRepositoryToken(DutyAssignment), useValue: dutyRepo },
        { provide: getRepositoryToken(Trip), useValue: tripRepo },
      ],
    }).compile();

    service = module.get(OperationReportGeneratorService);
  });

  describe('generateReport', () => {
    it('throws when schedule is missing', async () => {
      scheduleRepo.findOne.mockResolvedValue(null);
      await expect(service.generateReport(999, 16)).rejects.toThrow();
    });

    it('returns baseline-only report when no optimization run exists', async () => {
      scheduleRepo.findOne.mockResolvedValue(baselineSchedule());
      runRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });

      const report = await service.generateReport(1, 16);

      expect(report.scheduleId).toBe(1);
      expect(report.scenarioComparison.optimized).toBeNull();
      expect(report.scenarioComparison.savings).toBe(0);
      expect(report.sourceOptimizationRunId).toBeNull();
      expect(report.metrics.totalCost).toBe(5000);
      expect(report.metrics.totalTrips).toBe(7);
      expect(report.metrics.vehiclesUsed).toBe(2);
    });

    it('uses cheapest completed run as optimized comparison', async () => {
      scheduleRepo.findOne.mockResolvedValue(baselineSchedule());
      runRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(completedRun()),
      });

      const report = await service.generateReport(1, 16);

      expect(report.scenarioComparison.optimized).toBeTruthy();
      expect(report.scenarioComparison.optimized!.totalCost).toBe(4500);
      expect(report.scenarioComparison.savings).toBe(500); // 5000 - 4500
      expect(report.scenarioComparison.savingsPercent).toBeCloseTo(10, 5);
      expect(report.sourceOptimizationRunId).toBe(10);
      expect(report.algorithm).toBe('vcsp_pulp');
      expect(
        report.recommendations.some((r) => r.includes('cenário otimizado')),
      ).toBe(true);
    });

    it('emits critical issue when unassigned trips > 0', async () => {
      scheduleRepo.findOne.mockResolvedValue(
        baselineSchedule({
          blocks: [
            { vehicleId: 1, tripIds: [1, 2], cost: 500 },
            { vehicleId: null, tripIds: [3, 4], cost: 0 },
          ],
        }),
      );
      runRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });

      const report = await service.generateReport(1, 16);

      expect(report.metrics.unassignedTrips).toBe(2);
      expect(report.issues.some((i) => i.severity === 'critical')).toBe(true);
    });

    it('counts persisted block trips as assigned even when vehicleId is null', async () => {
      scheduleRepo.findOne.mockResolvedValue(
        baselineSchedule({
          metadata: {
            total_trips: 2,
            unassigned_trips: 0,
          },
          blocks: [
            { blockId: 1, vehicleId: null, tripIds: [1, 2], cost: 500 },
          ],
        }),
      );
      runRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });

      const report = await service.generateReport(1, 16);

      expect(report.metrics.assignedTrips).toBe(2);
      expect(report.metrics.unassignedTrips).toBe(0);
      expect(report.metrics.vehiclesUsed).toBe(1);
    });
  });

  describe('getHistoricalReports', () => {
    it('returns empty array when no runs in window (no fake data)', async () => {
      scheduleRepo.findOne.mockResolvedValue(baselineSchedule());
      runRepo.find.mockResolvedValue([]);

      const out = await service.getHistoricalReports(1, 16, 30);

      expect(out).toEqual([]);
    });

    it('groups runs by day picking best per day', async () => {
      scheduleRepo.findOne.mockResolvedValue(baselineSchedule());
      const day1Run1 = completedRun({
        id: 20,
        metrics: {
          totalCost: 4800,
          numVehicles: 11,
          totalTrips: 100,
          unassignedTrips: 0,
          cctViolations: 0,
        },
        completedAt: new Date('2026-05-09T08:00:00Z'),
      });
      const day1Run2 = completedRun({
        id: 21,
        metrics: {
          totalCost: 4600,
          numVehicles: 10,
          totalTrips: 100,
          unassignedTrips: 0,
          cctViolations: 0,
        },
        completedAt: new Date('2026-05-09T15:00:00Z'),
      });
      const day2Run = completedRun({
        id: 22,
        metrics: {
          totalCost: 4400,
          numVehicles: 9,
          totalTrips: 100,
          unassignedTrips: 0,
          cctViolations: 0,
        },
        completedAt: new Date('2026-05-10T12:00:00Z'),
      });
      runRepo.find.mockResolvedValue([day1Run1, day1Run2, day2Run]);

      const out = await service.getHistoricalReports(1, 16, 30);

      expect(out).toHaveLength(2);
      // Day 1: melhor é day1Run2 (4600 < 4800)
      expect(out[0].sourceOptimizationRunId).toBe(21);
      expect(out[0].metrics.totalCost).toBe(4600);
      // Day 2
      expect(out[1].sourceOptimizationRunId).toBe(22);
      expect(out[1].metrics.totalCost).toBe(4400);
    });
  });

  describe('generatePDFReport', () => {
    it('returns a Buffer that begins with PDF magic bytes', async () => {
      scheduleRepo.findOne.mockResolvedValue(baselineSchedule());
      runRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });

      const buf = await service.generatePDFReport(1, 16);

      expect(Buffer.isBuffer(buf)).toBe(true);
      expect(buf.slice(0, 4).toString()).toBe('%PDF');
    });
  });

  describe('generateExcelReport', () => {
    it('returns a Buffer that begins with XLSX magic bytes (PK zip header)', async () => {
      scheduleRepo.findOne.mockResolvedValue(baselineSchedule());
      runRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });

      const buf = await service.generateExcelReport(1, 16);

      expect(Buffer.isBuffer(buf)).toBe(true);
      // .xlsx is a ZIP — starts with PK\x03\x04
      expect(buf[0]).toBe(0x50); // P
      expect(buf[1]).toBe(0x4b); // K
    });
  });

  describe('compareReports', () => {
    it('returns null when no runs in window', async () => {
      runRepo.find.mockResolvedValue([]);
      const out = await service.compareReports(
        1,
        16,
        new Date('2026-05-01'),
        new Date('2026-05-11'),
      );
      expect(out).toBeNull();
    });

    it('returns real averages + best/worst day from runs', async () => {
      const runs = [
        completedRun({
          id: 30,
          metrics: {
            totalCost: 4500,
            numVehicles: 10,
            totalTrips: 100,
            unassignedTrips: 0,
            cctViolations: 0,
          },
        }),
        completedRun({
          id: 31,
          metrics: {
            totalCost: 4700,
            numVehicles: 11,
            totalTrips: 100,
            unassignedTrips: 0,
            cctViolations: 1,
          },
        }),
        completedRun({
          id: 32,
          metrics: {
            totalCost: 4300,
            numVehicles: 9,
            totalTrips: 100,
            unassignedTrips: 0,
            cctViolations: 0,
          },
        }),
      ];
      runRepo.find.mockResolvedValue(runs);

      const out = await service.compareReports(
        1,
        16,
        new Date('2026-05-01'),
        new Date('2026-05-11'),
      );

      expect(out).not.toBeNull();
      expect(out!.reportCount).toBe(3);
      expect(out!.averageCost).toBeCloseTo(4500, 0);
      expect(out!.averageViolations).toBeCloseTo(1 / 3, 4);
      expect(out!.bestDay.runId).toBe(32); // 4300 menor
      expect(out!.worstDay.runId).toBe(31); // 4700 maior
      expect(out!.costTrend).toBe(-200); // 4300 - 4500
    });
  });

  describe('getDutyStats', () => {
    const makeDuty = (
      dutyId: number,
      work_time: number,
      cost: number,
      overrides: any = {},
    ) => ({
      dutyId,
      tripIds: [1, 2],
      cost,
      metadata: {
        work_time,
        spread_time: work_time + 30,
        overtime_minutes: 0,
        rest_violations: 0,
        shift_violations: 0,
        ...overrides,
      },
    });

    it('throws NotFoundException when no duties exist', async () => {
      dutyRepo.find.mockResolvedValue([]);
      await expect(service.getDutyStats(1, 16)).rejects.toThrow();
    });

    it('returns correct summary for multiple duties', async () => {
      dutyRepo.find.mockResolvedValue([
        makeDuty(1, 300, 200),
        makeDuty(2, 420, 280),
        makeDuty(3, 480, 320),
      ]);

      const out = await service.getDutyStats(1, 16);

      expect(out.totalDuties).toBe(3);
      expect(out.duties).toHaveLength(3);
      expect(out.summary.minWorkMinutes).toBe(300);
      expect(out.summary.maxWorkMinutes).toBe(480);
      expect(out.summary.avgWorkMinutes).toBeCloseTo(400, 0);
      expect(out.summary.totalCost).toBeCloseTo(800, 0);
      expect(out.summary.giniWorkTime).toBeGreaterThanOrEqual(0);
      expect(out.summary.giniWorkTime).toBeLessThanOrEqual(1);
    });

    it('includes rest/shift violations in summary totals', async () => {
      dutyRepo.find.mockResolvedValue([
        makeDuty(1, 300, 100, { rest_violations: 2, shift_violations: 1 }),
        makeDuty(2, 360, 120, { rest_violations: 0, shift_violations: 0 }),
      ]);

      const out = await service.getDutyStats(1, 16);

      expect(out.summary.totalRestViolations).toBe(2);
      expect(out.summary.totalShiftViolations).toBe(1);
    });
  });
});
