import { BadRequestException } from '@nestjs/common';
import { OperationsController } from './operations.controller';

describe('OperationsController', () => {
  it('encaminha operational_quality_mode do body para o service', async () => {
    const optimizationService = {
      runOptimization: jest.fn().mockResolvedValue({ scheduleId: 10, taskId: 'task-10' }),
    };
    const controller = new OperationsController(
      {} as any,
      optimizationService as any,
      { getCompanyId: jest.fn().mockReturnValue(16) } as any,
    );
    (controller as any).logger = {
      warn: jest.fn(),
      log: jest.fn(),
    };

    await controller.runOptimization(
      {
        algorithm: 'hybrid_pipeline',
        operational_quality_mode: 'strict',
      },
      'hybrid_pipeline',
      undefined,
      'strict',
    );

    expect(optimizationService.runOptimization).toHaveBeenCalledWith(
      16,
      'hybrid_pipeline',
      'strict',
      { depotIds: undefined },
    );
  });

  it('usa fallback camelCase quando operational_quality_mode nao veio no body snake_case', async () => {
    const optimizationService = {
      runOptimization: jest.fn().mockResolvedValue({ scheduleId: 11, taskId: 'task-11' }),
    };
    const controller = new OperationsController(
      {} as any,
      optimizationService as any,
      { getCompanyId: jest.fn().mockReturnValue(16) } as any,
    );
    (controller as any).logger = {
      warn: jest.fn(),
      log: jest.fn(),
    };

    await controller.runOptimization(
      {
        algorithm: 'hybrid_pipeline',
        operationalQualityMode: 'optimized',
      },
      'hybrid_pipeline',
      undefined,
      undefined,
    );

    expect(optimizationService.runOptimization).toHaveBeenCalledWith(
      16,
      'hybrid_pipeline',
      'optimized',
      { depotIds: undefined },
    );
  });

  it('bloqueia companyId divergente do tenant', async () => {
    const controller = new OperationsController(
      {} as any,
      { runOptimization: jest.fn() } as any,
      { getCompanyId: jest.fn().mockReturnValue(16) } as any,
    );
    (controller as any).logger = {
      warn: jest.fn(),
      log: jest.fn(),
    };

    await expect(
      controller.runOptimization(
        {
          algorithm: 'hybrid_pipeline',
          companyId: 99,
        },
        'hybrid_pipeline',
        99,
        undefined,
      ),
    ).rejects.toBeInstanceOf(BadRequestException);
  });
});
