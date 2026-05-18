import { Test, TestingModule } from '@nestjs/testing';
import { VehicleMetricsController } from './vehicle-metrics.controller';
import { VehicleMetricsService } from './vehicle-metrics.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('VehicleMetricsController', () => {
  let controller: VehicleMetricsController;
  let service: jest.Mocked<Partial<VehicleMetricsService>>;

  beforeEach(async () => {
    service = {
      getAllVehiclesMetrics: jest
        .fn()
        .mockResolvedValue([{ vehicleId: 1, utilizationPct: 80 }]),
      getVehicleMetrics: jest
        .fn()
        .mockResolvedValue({ vehicleId: 1, utilizationPct: 80 }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [VehicleMetricsController],
      providers: [{ provide: VehicleMetricsService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(VehicleMetricsController);
  });

  it('getAllMetrics returns list', async () => {
    const result = await controller.getAllMetrics();
    expect(service.getAllVehiclesMetrics).toHaveBeenCalled();
    expect(result).toHaveLength(1);
  });

  it('getVehicleMetrics returns metrics for specific vehicle', async () => {
    const result = await controller.getVehicleMetrics(1);
    expect(service.getVehicleMetrics).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({ vehicleId: 1 });
  });
});
