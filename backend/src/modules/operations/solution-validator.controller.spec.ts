import { Test, TestingModule } from '@nestjs/testing';
import { SolutionValidatorController } from './solution-validator.controller';
import { SolutionValidatorService } from './solution-validator.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('SolutionValidatorController', () => {
  let controller: SolutionValidatorController;
  let service: jest.Mocked<Partial<SolutionValidatorService>>;

  beforeEach(async () => {
    service = {
      validate: jest.fn().mockReturnValue({ valid: true, errorCount: 0, errors: [], stats: {} }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [SolutionValidatorController],
      providers: [{ provide: SolutionValidatorService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
      .compile();

    controller = module.get(SolutionValidatorController);
  });

  it('validate calls service and returns result', () => {
    const body = { blocks: [{ blockId: 1 }], duties: [], trips: [{ id: 1 }], params: {} };
    const result = controller.validate(body);
    expect(service.validate).toHaveBeenCalledWith(body.blocks, body.duties, body.trips, body.params);
    expect(result).toMatchObject({ valid: true, errorCount: 0 });
  });

  it('validate with no params defaults to empty object', () => {
    controller.validate({ blocks: [], duties: [], trips: [] });
    expect(service.validate).toHaveBeenCalledWith([], [], [], {});
  });
});
