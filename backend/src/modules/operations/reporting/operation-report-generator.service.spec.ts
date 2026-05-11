import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { OperationReportGeneratorService } from './operation-report-generator.service';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';

describe('OperationReportGeneratorService', () => {
  let service: OperationReportGeneratorService;
  let scheduleRepo: any;
  let blockRepo: any;

  beforeEach(async () => {
    scheduleRepo = {
      findOne: jest.fn(),
    };

    blockRepo = {
      find: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OperationReportGeneratorService,
        {
          provide: getRepositoryToken(Schedule),
          useValue: scheduleRepo,
        },
        {
          provide: getRepositoryToken(BlockAssignment),
          useValue: blockRepo,
        },
      ],
    }).compile();

    service = module.get<OperationReportGeneratorService>(
      OperationReportGeneratorService,
    );
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('generateReport', () => {
    it('should generate a complete operation report', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [
          { vehicleId: 1 },
          { vehicleId: 1 },
          { vehicleId: 2 },
          { vehicleId: null },
          { vehicleId: null },
        ],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report).toBeDefined();
      expect(report.scheduleId).toBe(1);
      expect(report.metrics).toBeDefined();
      expect(report.metrics.totalTrips).toBe(5);
      expect(report.metrics.assignedTrips).toBe(3);
      expect(report.metrics.unassignedTrips).toBe(2);
    });

    it('should calculate metrics correctly', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [
          { vehicleId: 1 },
          { vehicleId: 1 },
          { vehicleId: 2 },
        ],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report.metrics.totalTrips).toBe(3);
      expect(report.metrics.assignedTrips).toBe(3);
      expect(report.metrics.unassignedTrips).toBe(0);
      expect(report.metrics.vehiclesUsed).toBe(2);
      expect(report.metrics.totalCost).toBeGreaterThan(0);
    });

    it('should identify unassigned trips issue', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [
          { vehicleId: 1 },
          { vehicleId: null },
          { vehicleId: null },
        ],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report.issues.some((i) => i.severity === 'critical')).toBe(true);
      expect(
        report.issues.some((i) => i.message.includes('não foram atribuídas'))
      ).toBe(true);
    });

    it('should flag low utilization', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [{ vehicleId: 1 }],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report.issues.some((i) => i.severity === 'warning')).toBe(true);
    });

    it('should include scenario comparison', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [
          { vehicleId: 1 },
          { vehicleId: 1 },
        ],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report.scenarioComparison).toBeDefined();
      expect(report.scenarioComparison.current).toBeDefined();
      expect(report.scenarioComparison.optimized).toBeDefined();
      expect(report.scenarioComparison.savings).toBeGreaterThan(0);
      expect(report.scenarioComparison.savingsPercent).toBeGreaterThan(0);
    });

    it('should throw error for non-existent schedule', async () => {
      scheduleRepo.findOne.mockResolvedValue(null);

      await expect(service.generateReport(999)).rejects.toThrow();
    });
  });

  describe('getHistoricalReports', () => {
    it('should return historical reports', async () => {
      const reports = await service.getHistoricalReports(1, 7);

      expect(Array.isArray(reports)).toBe(true);
      expect(reports.length).toBe(7);
    });

    it('should return correct number of days', async () => {
      const reports = await service.getHistoricalReports(1, 30);

      expect(reports.length).toBe(30);
    });

    it('should have varying costs in historical data', async () => {
      const reports = await service.getHistoricalReports(1, 10);

      const costs = reports.map((r) => r.metrics.totalCost);
      const uniqueCosts = new Set(costs);

      expect(uniqueCosts.size).toBeGreaterThan(1);
    });

    it('should maintain proper date ordering', async () => {
      const reports = await service.getHistoricalReports(1, 10);

      for (let i = 0; i < reports.length - 1; i++) {
        expect(reports[i].generatedAt.getTime()).toBeLessThanOrEqual(
          reports[i + 1].generatedAt.getTime(),
        );
      }
    });
  });

  describe('compareReports', () => {
    it('should compare reports within date range', async () => {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 7);
      const endDate = new Date();

      const comparison = await service.compareReports(1, startDate, endDate);

      expect(comparison).toBeDefined();
      expect(comparison.averageCost).toBeGreaterThan(0);
      expect(comparison.averageUtilization).toBeGreaterThan(0);
    });

    it('should calculate cost trend', async () => {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 30);
      const endDate = new Date();

      const comparison = await service.compareReports(1, startDate, endDate);

      expect(typeof comparison.costTrend).toBe('number');
    });

    it('should identify best and worst day', async () => {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 30);
      const endDate = new Date();

      const comparison = await service.compareReports(1, startDate, endDate);

      expect(comparison.bestDay).toBeDefined();
      expect(comparison.worstDay).toBeDefined();
      expect(comparison.bestDay.metrics.totalCost).toBeLessThanOrEqual(
        comparison.worstDay.metrics.totalCost,
      );
    });

    it('should return null for empty date range', async () => {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 60);
      const endDate = new Date();
      endDate.setDate(endDate.getDate() - 45);

      const comparison = await service.compareReports(1, startDate, endDate);

      expect(comparison).toBeNull();
    });
  });

  describe('Report Structure', () => {
    it('should have required report fields', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report).toHaveProperty('id');
      expect(report).toHaveProperty('scheduleId');
      expect(report).toHaveProperty('generatedAt');
      expect(report).toHaveProperty('period');
      expect(report).toHaveProperty('metrics');
      expect(report).toHaveProperty('scenarioComparison');
      expect(report).toHaveProperty('recommendations');
      expect(report).toHaveProperty('issues');
    });

    it('should have required metrics fields', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(report.metrics).toHaveProperty('totalTrips');
      expect(report.metrics).toHaveProperty('assignedTrips');
      expect(report.metrics).toHaveProperty('unassignedTrips');
      expect(report.metrics).toHaveProperty('totalCost');
      expect(report.metrics).toHaveProperty('costPerTrip');
      expect(report.metrics).toHaveProperty('vehiclesUsed');
      expect(report.metrics).toHaveProperty('averageUtilization');
    });

    it('should have valid recommendations', async () => {
      const mockSchedule = {
        id: 1,
        blocks: [{ vehicleId: 1 }],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const report = await service.generateReport(1);

      expect(Array.isArray(report.recommendations)).toBe(true);
      expect(report.recommendations.length).toBeGreaterThan(0);
      expect(typeof report.recommendations[0]).toBe('string');
    });
  });
});
