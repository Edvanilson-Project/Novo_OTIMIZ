import { Test, TestingModule } from '@nestjs/testing';
import { ParametersController } from './parameters.controller';
import { ParametersService } from './parameters.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('ParametersController', () => {
  let controller: ParametersController;
  let service: jest.Mocked<Partial<ParametersService>>;

  const mockParams = { id: 1, companyId: 1, maxWorkHours: 8, minRestHours: 11 } as any;

  beforeEach(async () => {
    service = {
      getParameters: jest.fn().mockResolvedValue(mockParams),
      updateParameters: jest.fn().mockResolvedValue({ ...mockParams, maxWorkHours: 10 }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [ParametersController],
      providers: [{ provide: ParametersService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
      .compile();

    controller = module.get(ParametersController);
  });

  it('getParameters returns current params', async () => {
    const result = await controller.getParameters();
    expect(service.getParameters).toHaveBeenCalled();
    expect(result).toMatchObject({ id: 1, maxWorkHours: 8 });
  });

  it('updateParameters calls service with partial data', async () => {
    const result = await controller.updateParameters({ maxWorkHours: 10 } as any);
    expect(service.updateParameters).toHaveBeenCalledWith({ maxWorkHours: 10 });
    expect(result).toMatchObject({ maxWorkHours: 10 });
  });
});
