import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { ScenarioEvaluatorService } from './scenario-evaluator.service';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';
import {
  OptimizationRun,
  OptimizationRunStatus,
} from '../../database/entities/optimization-run.entity';
import { TenantContext } from '../../../common/context/tenant-context';
import { OptimizationService } from '../optimization.service';

const COMPLETED_RUN = (
  id: number,
  scenarioId: string,
  totalCost: number,
  vehicles: number,
): OptimizationRun =>
  ({
    id,
    companyId: 16,
    scenarioId,
    baselineScheduleId: 1,
    resultScheduleId: id + 100,
    inputFingerprint: `hash-${id}`,
    params: {},
    algorithm: 'vcsp_pulp',
    randomSeed: 42,
    status: OptimizationRunStatus.COMPLETED,
    metrics: {
      totalCost,
      numVehicles: vehicles,
      numDuties: vehicles + 1,
      totalTrips: 100,
      unassignedTrips: 0,
      cctViolations: 0,
      hardIssueCount: 0,
      softIssueCount: 0,
    },
    errorMessage: null,
    durationMs: 60000,
    createdAt: new Date('2026-05-11T12:00:00Z'),
    updatedAt: new Date('2026-05-11T12:01:00Z'),
    completedAt: new Date('2026-05-11T12:01:00Z'),
  }) as any;

describe('ScenarioEvaluatorService (real optimizer integration)', () => {
  let service: ScenarioEvaluatorService;
  let scheduleRepo: any;
  let blockRepo: any;
  let optimizationRunRepo: any;
  let optimizationService: any;
  let tenantContext: any;

  beforeEach(async () => {
    scheduleRepo = {
      findOne: jest.fn(),
    };
    blockRepo = { find: jest.fn() };

    optimizationRunRepo = {
      createQueryBuilder: jest.fn(),
      findOne: jest.fn(),
      save: jest.fn(),
      update: jest.fn(),
    };

    optimizationService = {
      runOptimization: jest.fn(),
    };

    tenantContext = { getCompanyId: jest.fn().mockReturnValue(16) };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ScenarioEvaluatorService,
        { provide: getRepositoryToken(Schedule), useValue: scheduleRepo },
        { provide: getRepositoryToken(BlockAssignment), useValue: blockRepo },
        {
          provide: getRepositoryToken(OptimizationRun),
          useValue: optimizationRunRepo,
        },
        { provide: TenantContext, useValue: tenantContext },
        { provide: OptimizationService, useValue: optimizationService },
      ],
    }).compile();

    service = module.get<ScenarioEvaluatorService>(ScenarioEvaluatorService);
  });

  describe('generateScenarios', () => {
    it('returns 4 scenarios: baseline current + 3 optimizer-backed', async () => {
      scheduleRepo.findOne.mockResolvedValue({
        id: 1,
        totalCost: 1000,
        cctViolations: 0,
        blocks: [{}, {}, {}],
        createdAt: new Date(),
      });
      // no completed runs in TTL, no in-flight: each ensure call enqueues a new run
      optimizationRunRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });
      optimizationRunRepo.findOne.mockResolvedValue(null);
      let runIdCounter = 100;
      optimizationService.runOptimization.mockImplementation(
        (_cid: number, _algo: string, _mode: any, opts: any) => {
          const id = ++runIdCounter;
          optimizationRunRepo.findOne.mockResolvedValueOnce({
            id,
            scenarioId: opts.scenarioId,
            status: OptimizationRunStatus.RUNNING,
            algorithm: _algo,
            resultScheduleId: id + 1000,
            metrics: null,
            errorMessage: null,
            inputFingerprint: `hash-${id}`,
            createdAt: new Date(),
            completedAt: null,
          });
          return {
            scheduleId: id + 1000,
            taskId: `task-${id}`,
            optimizationRunId: id,
          };
        },
      );

      const scenarios = await service.generateScenarios(1);

      expect(scenarios).toHaveLength(4);
      expect(scenarios.map((s) => s.id)).toEqual([
        'current',
        'cost-optimized',
        'service-optimized',
        'maintenance-aware',
      ]);
      expect(scenarios[0].status).toBe('baseline');
      expect(optimizationService.runOptimization).toHaveBeenCalledTimes(3);
      const cfg = optimizationService.runOptimization.mock.calls[0];
      expect(cfg[1]).toBe('vcsp_pulp'); // cost-optimized algorithm
      expect(cfg[3].scenarioId).toBe('cost-optimized');
      expect(cfg[3].skipTenantLock).toBe(true);
    });

    it('reuses recent completed run (idempotency within TTL)', async () => {
      scheduleRepo.findOne.mockResolvedValue({
        id: 1,
        totalCost: 5000,
        cctViolations: 0,
        blocks: [],
        createdAt: new Date(),
      });
      // For cost-optimized: completed run exists
      const completedRun = COMPLETED_RUN(50, 'cost-optimized', 4500, 10);
      const qb = (matches: any) => ({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(matches),
      });
      optimizationRunRepo.createQueryBuilder
        .mockReturnValueOnce(qb(completedRun))
        .mockReturnValueOnce(qb(null))
        .mockReturnValueOnce(qb(null));
      optimizationRunRepo.findOne.mockResolvedValue(null);
      optimizationService.runOptimization.mockResolvedValue({
        scheduleId: 999,
        taskId: 'task-x',
        optimizationRunId: 51,
      });
      optimizationRunRepo.findOne
        .mockResolvedValueOnce(null) // service-optimized in-flight check
        .mockResolvedValueOnce({
          id: 51,
          scenarioId: 'service-optimized',
          status: OptimizationRunStatus.RUNNING,
          metrics: null,
          errorMessage: null,
          resultScheduleId: 999,
          inputFingerprint: 'h51',
          algorithm: 'mcnf',
          createdAt: new Date(),
          completedAt: null,
        })
        .mockResolvedValueOnce(null) // maintenance-aware in-flight check
        .mockResolvedValueOnce({
          id: 52,
          scenarioId: 'maintenance-aware',
          status: OptimizationRunStatus.RUNNING,
          metrics: null,
          errorMessage: null,
          resultScheduleId: 1000,
          inputFingerprint: 'h52',
          algorithm: 'hybrid_pipeline',
          createdAt: new Date(),
          completedAt: null,
        });

      const scenarios = await service.generateScenarios(1);

      const costOptimized = scenarios.find((s) => s.id === 'cost-optimized')!;
      expect(costOptimized.status).toBe(OptimizationRunStatus.COMPLETED);
      expect(costOptimized.totalCost).toBe(4500);
      expect(costOptimized.optimizationRunId).toBe(50);
      // Only service-optimized + maintenance-aware get enqueued (cost was reused)
      expect(optimizationService.runOptimization).toHaveBeenCalledTimes(2);
    });

    it('reports in-flight scenarios as RUNNING without re-enqueueing', async () => {
      scheduleRepo.findOne.mockResolvedValue({
        id: 1,
        totalCost: 1000,
        cctViolations: 0,
        blocks: [],
        createdAt: new Date(),
      });
      const qbEmpty = () => ({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });
      optimizationRunRepo.createQueryBuilder.mockImplementation(qbEmpty);
      // Every in-flight check returns a RUNNING run
      const runningRun = {
        id: 77,
        status: OptimizationRunStatus.RUNNING,
        metrics: null,
        errorMessage: null,
        resultScheduleId: 1001,
        inputFingerprint: 'pending',
        algorithm: 'vcsp_pulp',
        createdAt: new Date(),
        completedAt: null,
      };
      optimizationRunRepo.findOne.mockResolvedValue(runningRun);

      const scenarios = await service.generateScenarios(1);

      for (const s of scenarios.slice(1)) {
        expect(s.status).toBe(OptimizationRunStatus.RUNNING);
      }
      expect(optimizationService.runOptimization).not.toHaveBeenCalled();
    });
  });

  describe('compareScenarios', () => {
    it('computes real diff between two completed scenarios', async () => {
      scheduleRepo.findOne.mockResolvedValue({
        id: 1,
        totalCost: 5000,
        cctViolations: 2,
        blocks: [{}, {}, {}, {}, {}],
        createdAt: new Date(),
      });
      const completed = COMPLETED_RUN(60, 'cost-optimized', 4500, 4);
      const qbCompleted = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(completed),
      };
      const qbEmpty = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      };
      optimizationRunRepo.createQueryBuilder
        .mockReturnValueOnce(qbCompleted)
        .mockReturnValueOnce(qbEmpty)
        .mockReturnValueOnce(qbEmpty);
      optimizationRunRepo.findOne.mockResolvedValue(null);
      optimizationService.runOptimization.mockResolvedValue({
        scheduleId: 999,
        taskId: 'task',
        optimizationRunId: 61,
      });
      optimizationRunRepo.findOne.mockResolvedValueOnce({
        id: 61,
        scenarioId: 'service-optimized',
        status: OptimizationRunStatus.RUNNING,
        metrics: null,
        errorMessage: null,
        resultScheduleId: 999,
        inputFingerprint: 'pending',
        algorithm: 'mcnf',
        createdAt: new Date(),
        completedAt: null,
      });

      const result = await service.compareScenarios(
        1,
        'current',
        'cost-optimized',
      );

      expect(result.savings).toBe(500); // 5000 - 4500
      expect(result.savingsPercent).toBe(10);
      expect(result.differences.some((d) => d.includes('Veículos'))).toBe(true);
      expect(result.differences.some((d) => d.includes('Custo'))).toBe(true);
    });

    it('throws when scenario id is unknown', async () => {
      scheduleRepo.findOne.mockResolvedValue({
        id: 1,
        totalCost: 1000,
        cctViolations: 0,
        blocks: [],
        createdAt: new Date(),
      });
      optimizationRunRepo.createQueryBuilder.mockReturnValue({
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        getOne: jest.fn().mockResolvedValue(null),
      });
      optimizationRunRepo.findOne.mockResolvedValue(null);
      optimizationService.runOptimization.mockResolvedValue({
        scheduleId: 999,
        taskId: 'task',
        optimizationRunId: 70,
      });
      optimizationRunRepo.findOne.mockResolvedValue({
        id: 70,
        status: OptimizationRunStatus.RUNNING,
        metrics: null,
        errorMessage: null,
        resultScheduleId: 999,
        inputFingerprint: 'p',
        algorithm: 'vcsp_pulp',
        createdAt: new Date(),
        completedAt: null,
      });

      await expect(
        service.compareScenarios(1, 'current', 'unknown-scenario'),
      ).rejects.toThrow();
    });
  });
});
