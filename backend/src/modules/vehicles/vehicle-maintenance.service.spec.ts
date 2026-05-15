import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { BadRequestException, NotFoundException } from '@nestjs/common';
import { VehicleMaintenanceService } from './vehicle-maintenance.service';
import { VehicleMaintenance, MaintenanceStatus } from '../database/entities/vehicle-maintenance.entity';
import { VehicleAvailabilityWindow } from '../database/entities/vehicle-availability-window.entity';
import { TenantContext } from '../../common/context/tenant-context';

describe('VehicleMaintenanceService', () => {
  let service: VehicleMaintenanceService;
  let maintenanceRepo: any;
  let availabilityRepo: any;
  let tenantContext: any;

  beforeEach(async () => {
    maintenanceRepo = {
      find: jest.fn(),
      findOne: jest.fn(),
      create: jest.fn(),
      save: jest.fn(),
      remove: jest.fn(),
    };

    availabilityRepo = {
      find: jest.fn(),
      findOne: jest.fn(),
      create: jest.fn(),
      save: jest.fn(),
      remove: jest.fn(),
    };

    tenantContext = {
      getCompanyId: jest.fn().mockReturnValue(1),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        VehicleMaintenanceService,
        {
          provide: getRepositoryToken(VehicleMaintenance),
          useValue: maintenanceRepo,
        },
        {
          provide: getRepositoryToken(VehicleAvailabilityWindow),
          useValue: availabilityRepo,
        },
        {
          provide: TenantContext,
          useValue: tenantContext,
        },
      ],
    }).compile();

    service = module.get<VehicleMaintenanceService>(VehicleMaintenanceService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('scheduleMaintenance', () => {
    it('should schedule maintenance successfully', async () => {
      const vehicleId = 1;
      const futureDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000); // +30 dias
      const data = {
        maintenanceDate: futureDate.toISOString(),
        maintenanceType: 'preventive',
        estimatedDurationHours: 4,
        cost: 500,
      };

      maintenanceRepo.findOne.mockResolvedValue(null);
      maintenanceRepo.create.mockReturnValue({
        vehicleId,
        ...data,
      });
      maintenanceRepo.save.mockResolvedValue({
        id: 1,
        vehicleId,
        ...data,
      });

      const result = await service.scheduleMaintenance(vehicleId, data);

      expect(result).toBeDefined();
      expect(result.vehicleId).toBe(vehicleId);
      expect(maintenanceRepo.save).toHaveBeenCalled();
    });

    it('should throw error if maintenance date is in the past', async () => {
      const vehicleId = 1;
      const data = {
        maintenanceDate: new Date('2020-05-15').toISOString(),
      };

      await expect(service.scheduleMaintenance(vehicleId, data)).rejects.toThrow(
        BadRequestException,
      );
    });

    it('should throw error if maintenance already scheduled', async () => {
      const vehicleId = 1;
      const data = {
        maintenanceDate: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      };

      maintenanceRepo.findOne.mockResolvedValue({
        id: 1,
        vehicleId,
      });

      await expect(service.scheduleMaintenance(vehicleId, data)).rejects.toThrow(
        BadRequestException,
      );
    });
  });

  describe('getMaintenanceHistory', () => {
    it('should retrieve maintenance history', async () => {
      const vehicleId = 1;
      const history = [
        {
          id: 1,
          vehicleId,
          maintenanceDate: new Date('2026-05-10'),
        },
        {
          id: 2,
          vehicleId,
          maintenanceDate: new Date('2026-04-10'),
        },
      ];

      maintenanceRepo.find.mockResolvedValue(history);

      const result = await service.getMaintenanceHistory(vehicleId);

      expect(result).toEqual(history);
      expect(maintenanceRepo.find).toHaveBeenCalled();
    });
  });

  describe('checkVehicleAvailability', () => {
    it('should return available if no conflicts', async () => {
      const vehicleId = 1;
      const startTime = new Date('2026-05-15 08:00');
      const endTime = new Date('2026-05-15 12:00');

      availabilityRepo.find.mockResolvedValue([]);

      const result = await service.checkVehicleAvailability(vehicleId, startTime, endTime);

      expect(result.available).toBe(true);
      expect(result.conflicts).toHaveLength(0);
    });

    it('should detect conflicts', async () => {
      const vehicleId = 1;
      const startTime = new Date('2026-05-15 08:00');
      const endTime = new Date('2026-05-15 12:00');

      const conflict = {
        id: 1,
        vehicleId,
        startTime: new Date('2026-05-15 10:00'),
        endTime: new Date('2026-05-15 14:00'),
      };

      availabilityRepo.find.mockResolvedValue([conflict]);

      const result = await service.checkVehicleAvailability(vehicleId, startTime, endTime);

      expect(result.available).toBe(false);
      expect(result.conflicts).toHaveLength(1);
    });
  });

  describe('updateMaintenanceStatus', () => {
    it('should update maintenance status', async () => {
      const vehicleId = 1;
      const maintenanceId = 1;
      const maintenance = {
        id: maintenanceId,
        vehicleId,
        status: MaintenanceStatus.SCHEDULED,
      };

      maintenanceRepo.findOne.mockResolvedValue(maintenance);
      maintenanceRepo.save.mockResolvedValue({
        ...maintenance,
        status: MaintenanceStatus.COMPLETED,
      });

      const result = await service.updateMaintenanceStatus(
        vehicleId,
        maintenanceId,
        MaintenanceStatus.COMPLETED,
      );

      expect(result.status).toBe(MaintenanceStatus.COMPLETED);
      expect(maintenanceRepo.save).toHaveBeenCalled();
    });

    it('should throw error if maintenance not found', async () => {
      maintenanceRepo.findOne.mockResolvedValue(null);

      await expect(
        service.updateMaintenanceStatus(1, 999, MaintenanceStatus.COMPLETED),
      ).rejects.toThrow(NotFoundException);
    });
  });

  describe('cancelMaintenance', () => {
    it('should cancel scheduled maintenance', async () => {
      const vehicleId = 1;
      const maintenanceId = 1;
      const maintenance = {
        id: maintenanceId,
        vehicleId,
        status: MaintenanceStatus.SCHEDULED,
      };

      maintenanceRepo.findOne.mockResolvedValue(maintenance);
      maintenanceRepo.save.mockResolvedValue({
        ...maintenance,
        status: MaintenanceStatus.CANCELLED,
      });

      await service.cancelMaintenance(vehicleId, maintenanceId);

      expect(maintenanceRepo.save).toHaveBeenCalled();
    });

    it('should not cancel completed maintenance', async () => {
      const vehicleId = 1;
      const maintenanceId = 1;
      const maintenance = {
        id: maintenanceId,
        vehicleId,
        status: MaintenanceStatus.COMPLETED,
      };

      maintenanceRepo.findOne.mockResolvedValue(maintenance);

      await expect(service.cancelMaintenance(vehicleId, maintenanceId)).rejects.toThrow(
        BadRequestException,
      );
    });
  });

  describe('createAvailabilityWindow', () => {
    it('should create availability window', async () => {
      const vehicleId = 1;
      const data = {
        startTime: new Date('2026-05-15 08:00').toISOString(),
        endTime: new Date('2026-05-15 12:00').toISOString(),
        reason: 'maintenance',
      };

      availabilityRepo.create.mockReturnValue({
        vehicleId,
        ...data,
      });
      availabilityRepo.save.mockResolvedValue({
        id: 1,
        vehicleId,
        ...data,
      });

      const result = await service.createAvailabilityWindow(vehicleId, data);

      expect(result).toBeDefined();
      expect(result.vehicleId).toBe(vehicleId);
      expect(availabilityRepo.save).toHaveBeenCalled();
    });
  });

  describe('deleteAvailabilityWindow', () => {
    it('should delete availability window', async () => {
      const vehicleId = 1;
      const windowId = 1;
      const window = {
        id: windowId,
        vehicleId,
      };

      availabilityRepo.findOne.mockResolvedValue(window);
      availabilityRepo.remove.mockResolvedValue({});

      await service.deleteAvailabilityWindow(vehicleId, windowId);

      expect(availabilityRepo.remove).toHaveBeenCalled();
    });

    it('should throw error if window not found', async () => {
      availabilityRepo.findOne.mockResolvedValue(null);

      await expect(service.deleteAvailabilityWindow(1, 999)).rejects.toThrow(NotFoundException);
    });
  });
});
