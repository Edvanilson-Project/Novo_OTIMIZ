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
        id: 1, scenarioId: 'S1', status: 'completed', algorithm: 'greedy',
        metrics: {}, errorMessage: null, durationMs: 100, resultScheduleId: 2,
        inputFingerprint: 'abc', createdAt: new Date(), completedAt: new Date(),
      }),
    };
    whatIfSvc = {
      simulateVehicleTypeChange: jest.fn().mockReturnValue({ delta: {} }),
    };
    optimizationSvc = {
      replayRun: jest.fn().mockResolvedValue({}),
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
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
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
});
