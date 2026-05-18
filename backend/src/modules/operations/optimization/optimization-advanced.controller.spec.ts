import { Test, TestingModule } from '@nestjs/testing';
import { OptimizationAdvancedController } from './optimization-advanced.controller';
import { ScenarioEvaluatorService } from './scenario-evaluator.service';
import { WhatIfSimulatorService } from './whatif-simulator.service';
import { OptimizationService } from '../optimization.service';
import { TenantContext } from '../../../common/context/tenant-context';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';

describe('OptimizationAdvancedController', () => {
  let controller: OptimizationAdvancedController;
  let scenarioSvc: jest.Mocked<Partial<ScenarioEvaluatorService>>;
  let whatIfSvc: jest.Mocked<Partial<WhatIfSimulatorService>>;
  let optimizationSvc: jest.Mocked<Partial<OptimizationService>>;

  beforeEach(async () => {
    scenarioSvc = {
      generateScenarios: jest.fn().mockResolvedValue([{ scenarioId: 'S1' }]),
      getScenarioRun: jest.fn().mockResolvedValue({
        id: 1,
        scenarioId: 'S1',
        status: 'completed',
        algorithm: 'greedy',
        metrics: {},
        errorMessage: null,
        durationMs: 100,
        resultScheduleId: 2,
        inputFingerprint: 'abc',
        createdAt: new Date(),
        completedAt: new Date(),
      }),
    };
    whatIfSvc = {
      simulateVehicleTypeChange: jest.fn().mockReturnValue({ delta: {} }),
    };
    optimizationSvc = {
      replayRun: jest
        .fn()
        .mockResolvedValue({ optimizationRunId: 5, status: 'running' }),
      getReplayComparison: jest.fn().mockResolvedValue({
        original: { totalCost: 10000 },
        replay: { totalCost: 9800 },
        diff: { totalCost: -200 },
        status: 'ready',
      }),
      runBenchmark: jest.fn().mockResolvedValue({
        results: [{ n: 100, elapsedS: 0.5, blocks: 20 }],
        timestamp: '2026-05-16T00:00:00.000Z',
      }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [OptimizationAdvancedController],
      providers: [
        { provide: ScenarioEvaluatorService, useValue: scenarioSvc },
        { provide: WhatIfSimulatorService, useValue: whatIfSvc },
        { provide: OptimizationService, useValue: optimizationSvc },
        { provide: TenantContext, useValue: { getCompanyId: () => 1 } },
      ],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(OptimizationAdvancedController);
  });

  it('generateScenarios calls scenarioEvaluator', async () => {
    const result = await controller.generateScenarios(10);
    expect(scenarioSvc.generateScenarios).toHaveBeenCalledWith(10);
    expect(result).toHaveLength(1);
  });

  it('listScenarios calls same service', async () => {
    await controller.listScenarios(10);
    expect(scenarioSvc.generateScenarios).toHaveBeenCalledWith(10);
  });

  it('getScenarioRun returns formatted run', async () => {
    const result = await controller.getScenarioRun(10, 'S1');
    expect(scenarioSvc.getScenarioRun).toHaveBeenCalledWith(10, 'S1');
    expect(result).toMatchObject({ scenarioId: 'S1', status: 'completed' });
  });

  it('getScenarioRun returns null when not found', async () => {
    (scenarioSvc.getScenarioRun as jest.Mock).mockResolvedValue(null);
    const result = await controller.getScenarioRun(10, 'MISSING');
    expect(result).toBeNull();
  });

  it('replayRun delegates to optimizationService', async () => {
    const result = await controller.replayRun('fp123');
    expect(optimizationSvc.replayRun).toHaveBeenCalledWith(1, 'fp123');
    expect(result).toMatchObject({ status: 'running' });
  });

  it('getReplayComparison returns diff with status ready', async () => {
    const result = await controller.getReplayComparison('fp123');
    expect(optimizationSvc.getReplayComparison).toHaveBeenCalledWith(
      1,
      'fp123',
    );
    expect(result).toMatchObject({
      status: 'ready',
      diff: { totalCost: -200 },
    });
  });

  it('runBenchmark uses default sizes when not provided', async () => {
    await controller.runBenchmark({});
    expect(optimizationSvc.runBenchmark).toHaveBeenCalledWith(
      [100, 500, 1000],
      undefined,
      undefined,
      undefined,
    );
  });

  it('runBenchmark passes provided sizes and algorithm', async () => {
    await controller.runBenchmark({
      sizes: [50, 200],
      algorithm: 'greedy',
      seed: 7,
    });
    expect(optimizationSvc.runBenchmark).toHaveBeenCalledWith(
      [50, 200],
      'greedy',
      7,
      undefined,
    );
  });
});
