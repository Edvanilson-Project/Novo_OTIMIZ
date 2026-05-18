import { Test, TestingModule } from '@nestjs/testing';
import { VehicleMaintenanceController } from './vehicle-maintenance.controller';
import { VehicleMaintenanceService } from './vehicle-maintenance.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('VehicleMaintenanceController', () => {
  let controller: VehicleMaintenanceController;
  let service: jest.Mocked<Partial<VehicleMaintenanceService>>;

  beforeEach(async () => {
    service = {
      scheduleMaintenance: jest
        .fn()
        .mockResolvedValue({ id: 1, vehicleId: 10 }),
      getMaintenanceHistory: jest.fn().mockResolvedValue([{ id: 1 }]),
      updateMaintenanceStatus: jest
        .fn()
        .mockResolvedValue({ id: 1, status: 'completed' }),
      cancelMaintenance: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [VehicleMaintenanceController],
      providers: [{ provide: VehicleMaintenanceService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(VehicleMaintenanceController);
  });

  it('scheduleMaintenance calls service', async () => {
    const body = { maintenanceDate: '2026-06-01', estimatedDurationHours: 4 };
    const result = await controller.scheduleMaintenance(10, body);
    expect(service.scheduleMaintenance).toHaveBeenCalledWith(10, body);
    expect(result).toMatchObject({ vehicleId: 10 });
  });

  it('getMaintenanceHistory returns list', async () => {
    const result = await controller.getMaintenanceHistory(10);
    expect(service.getMaintenanceHistory).toHaveBeenCalledWith(10);
    expect(result).toHaveLength(1);
  });

  it('updateMaintenanceStatus calls service', async () => {
    const result = await controller.updateMaintenanceStatus(10, 1, 'completed');
    expect(service.updateMaintenanceStatus).toHaveBeenCalledWith(
      10,
      1,
      'completed',
    );
    expect(result).toMatchObject({ status: 'completed' });
  });

  it('cancelMaintenance calls service', async () => {
    await controller.cancelMaintenance(10, 1);
    expect(service.cancelMaintenance).toHaveBeenCalledWith(10, 1);
  });
});
