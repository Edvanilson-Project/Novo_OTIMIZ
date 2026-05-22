import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { VehiclesController } from './vehicles.controller';
import { VehiclesService } from './vehicles.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('VehiclesController', () => {
  let controller: VehiclesController;
  let service: jest.Mocked<Partial<VehiclesService>>;

  beforeEach(async () => {
    service = {
      findAllVehicleTypes: jest
        .fn()
        .mockResolvedValue([{ id: 1, name: 'BUS' }]),
      findOneVehicleType: jest.fn().mockResolvedValue({ id: 1, name: 'BUS' }),
      createVehicleType: jest.fn().mockResolvedValue({ id: 2, name: 'MINI' }),
      updateVehicleType: jest
        .fn()
        .mockResolvedValue({ id: 1, name: 'Updated' }),
      removeVehicleType: jest.fn().mockResolvedValue(undefined),
      findAllVehicles: jest
        .fn()
        .mockResolvedValue([{ id: 10, vehicleId: 'V1' }]),
      getActiveVehicles: jest.fn().mockResolvedValue([{ id: 10 }]),
      getVehiclesByType: jest.fn().mockResolvedValue([]),
      findOneVehicle: jest.fn().mockResolvedValue({ id: 10 }),
      createVehicle: jest.fn().mockResolvedValue({ id: 11 }),
      updateVehicle: jest
        .fn()
        .mockResolvedValue({ id: 10, vehicleId: 'Updated' }),
      removeVehicle: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [VehiclesController],
      providers: [{ provide: VehiclesService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(VehiclesController);
  });

  describe('vehicle types', () => {
    it('findAllVehicleTypes returns list', async () => {
      expect(await controller.findAllVehicleTypes()).toHaveLength(1);
    });

    it('findOneVehicleType returns type', async () => {
      expect(await controller.findOneVehicleType(1)).toMatchObject({ id: 1 });
      expect(service.findOneVehicleType).toHaveBeenCalledWith(1);
    });

    it('findOneVehicleType propagates NotFoundException', async () => {
      (service.findOneVehicleType as jest.Mock).mockRejectedValue(
        new NotFoundException(),
      );
      await expect(controller.findOneVehicleType(999)).rejects.toThrow(
        NotFoundException,
      );
    });

    it('createVehicleType calls service', async () => {
      const body = { name: 'MINI', capacity: 20, costPerDay: 100 };
      expect(await controller.createVehicleType(body)).toMatchObject({ id: 2 });
      expect(service.createVehicleType).toHaveBeenCalledWith(body);
    });

    it('updateVehicleType calls service', async () => {
      await controller.updateVehicleType(1, { name: 'Updated' });
      expect(service.updateVehicleType).toHaveBeenCalledWith(1, {
        name: 'Updated',
      });
    });

    it('removeVehicleType calls service', async () => {
      await controller.removeVehicleType(1);
      expect(service.removeVehicleType).toHaveBeenCalledWith(1);
    });
  });

  describe('vehicles', () => {
    it('findAllVehicles returns list', async () => {
      expect(await controller.findAllVehicles()).toHaveLength(1);
    });

    it('getActiveVehicles filters active', async () => {
      expect(await controller.getActiveVehicles()).toHaveLength(1);
    });

    it('getVehiclesByType calls service with typeId', async () => {
      await controller.getVehiclesByType(5);
      expect(service.getVehiclesByType).toHaveBeenCalledWith(5);
    });

    it('findOneVehicle propagates NotFoundException', async () => {
      (service.findOneVehicle as jest.Mock).mockRejectedValue(
        new NotFoundException(),
      );
      await expect(controller.findOneVehicle(999)).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
