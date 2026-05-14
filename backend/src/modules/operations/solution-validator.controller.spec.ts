import { ForbiddenException } from '@nestjs/common';
import { SolutionValidatorController } from './solution-validator.controller';

const MOCK_RESULT = { valid: true, errorCount: 0, warningCount: 0, errors: [], warnings: [], stats: {} };

function makeController(companyId: number | null) {
  const service = {
    validate: jest.fn().mockReturnValue(MOCK_RESULT),
    validateScheduleById: jest.fn().mockResolvedValue(MOCK_RESULT),
  };
  const tenantCtx = { getCompanyId: jest.fn().mockReturnValue(companyId) };
  const ctrl = new SolutionValidatorController(service as any, tenantCtx as any);
  return { ctrl, service, tenantCtx };
}

describe('SolutionValidatorController', () => {
  it('validate calls service and returns result', () => {
    const { ctrl, service } = makeController(7);
    const body = { blocks: [{ blockId: 1 }], duties: [], trips: [{ id: 1 }], params: {} };
    const result = ctrl.validate(body);
    expect(service.validate).toHaveBeenCalledWith(body.blocks, body.duties, body.trips, body.params);
    expect(result).toMatchObject({ valid: true, errorCount: 0 });
  });

  it('validate with no params defaults to empty object', () => {
    const { ctrl, service } = makeController(7);
    ctrl.validate({ blocks: [], duties: [], trips: [] });
    expect(service.validate).toHaveBeenCalledWith([], [], [], {});
  });

  it('validateSchedule calls validateScheduleById with scheduleId and companyId', async () => {
    const { ctrl, service } = makeController(7);
    const result = await ctrl.validateSchedule(42);
    expect(service.validateScheduleById).toHaveBeenCalledWith(42, 7);
    expect(result).toMatchObject({ valid: true });
  });

  it('validateSchedule throws ForbiddenException when no companyId in context', async () => {
    const { ctrl } = makeController(null);
    await expect(ctrl.validateSchedule(1)).rejects.toBeInstanceOf(ForbiddenException);
  });
});
