import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { VehicleMetricsService } from './vehicle-metrics.service';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleMaintenance, MaintenanceStatus } from '../database/entities/vehicle-maintenance.entity';
import { TenantContext } from '../../common/context/tenant-context';

describe('VehicleMetricsService', () => {
  let service: VehicleMetricsService;
  let vehicleRepo: any;
  let maintenanceRepo: any;
  let tenantContext: any;

  beforeEach(async () => {
    vehicleRepo = {
      findOne: jest.fn(),
      find: jest.fn(),
    };

    maintenanceRepo = {
      find: jest.fn(),
    };

    tenantContext = {
      getCompanyId: jest.fn().mockReturnValue(1),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        VehicleMetricsService,
        {
          provide: getRepositoryToken(Vehicle),
          useValue: vehicleRepo,
        },
        {
          provide: getRepositoryToken(VehicleMaintenance),
          useValue: maintenanceRepo,
        },
        {
          provide: TenantContext,
          useValue: tenantContext,
        },
      ],
    }).compile();

    service = module.get<VehicleMetricsService>(VehicleMetricsService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('getVehicleMetrics', () => {
    it('should calculate metrics for active vehicle', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-001',
        isActive: true,
        odometer: 150000,
        type: { id: 1, costPerDay: 800 },
      };

      const maintenance = [
        {
          maintenanceDate: new Date(new Date().getTime() - 30 * 24 * 60 * 60 * 1000),
        },
      ];

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue(maintenance);

      const result = await service.getVehicleMetrics(1);

      expect(result.vehicleId).toBe(1);
      expect(result.vehicleLabel).toBe('BUS-001');
      expect(result.healthScore).toBeGreaterThan(80);
      expect(result.maintenanceStatus).toBe('good');
    });

    it('should penalize inactive vehicles', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-002',
        isActive: false,
        odometer: 100000,
        type: { costPerDay: 800 },
      };

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue([]);

      const result = await service.getVehicleMetrics(1);

      expect(result.healthScore).toBeLessThan(60);
      expect(result.issues).toContain('Veículo inativo');
    });

    it('should detect overdue maintenance', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-003',
        isActive: true,
        odometer: 200000,
        type: { costPerDay: 800 },
      };

      const oldMaintenance = [
        {
          maintenanceDate: new Date(new Date().getTime() - 200 * 24 * 60 * 60 * 1000),
        },
      ];

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue(oldMaintenance);

      const result = await service.getVehicleMetrics(1);

      expect(result.healthScore).toBeLessThan(70);
      expect(result.maintenanceStatus).toBe('warning');
      expect(result.issues.length).toBeGreaterThan(0);
    });

    it('should flag high odometer vehicles', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-004',
        isActive: true,
        odometer: 450000,
        type: { costPerDay: 800 },
      };

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue([]);

      const result = await service.getVehicleMetrics(1);

      expect(result.healthScore).toBeLessThan(70);
      expect(result.issues.some((i) => i.includes('Quilometragem'))).toBe(true);
    });

    it('should provide recommendations', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-005',
        isActive: true,
        odometer: 350000,
        type: { costPerDay: 800 },
      };

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue([]);

      const result = await service.getVehicleMetrics(1);

      expect(result.recommendations.length).toBeGreaterThan(0);
    });
  });

  describe('getAllVehiclesMetrics', () => {
    it('should calculate metrics for all vehicles', async () => {
      const vehicles = [
        {
          id: 1,
          vehicleId: 'BUS-001',
          isActive: true,
          odometer: 100000,
          type: { costPerDay: 800 },
        },
        {
          id: 2,
          vehicleId: 'COACH-001',
          isActive: true,
          odometer: 200000,
          type: { costPerDay: 1200 },
        },
      ];

      vehicleRepo.find.mockResolvedValue(vehicles);
      maintenanceRepo.find.mockResolvedValue([]);

      // Mock the repository calls for each vehicle
      vehicleRepo.findOne
        .mockResolvedValueOnce(vehicles[0])
        .mockResolvedValueOnce(vehicles[1]);

      const result = await service.getAllVehiclesMetrics();

      expect(result.length).toBe(2);
      expect(result[0].vehicleLabel).toBe('BUS-001');
      expect(result[1].vehicleLabel).toBe('COACH-001');
    });
  });

  describe('health score calculation', () => {
    it('should calculate good health score (>80)', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-001',
        isActive: true,
        odometer: 100000,
        type: { costPerDay: 800 },
      };

      const recentMaintenance = [
        {
          maintenanceDate: new Date(),
        },
      ];

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue(recentMaintenance);

      const result = await service.getVehicleMetrics(1);

      expect(result.healthScore).toBeGreaterThanOrEqual(80);
      expect(result.maintenanceStatus).toBe('good');
    });

    it('should calculate warning health score (60-80)', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-001',
        isActive: true,
        odometer: 250000,
        type: { costPerDay: 800 },
      };

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue([]);

      const result = await service.getVehicleMetrics(1);

      expect(result.healthScore).toBeGreaterThanOrEqual(60);
      expect(result.healthScore).toBeLessThan(80);
      expect(result.maintenanceStatus).toBe('warning');
    });

    it('should calculate critical health score (<60)', async () => {
      const vehicle = {
        id: 1,
        vehicleId: 'BUS-001',
        isActive: false,
        odometer: 500000,
        type: { costPerDay: 800 },
      };

      vehicleRepo.findOne.mockResolvedValue(vehicle);
      maintenanceRepo.find.mockResolvedValue([]);

      const result = await service.getVehicleMetrics(1);

      expect(result.healthScore).toBeLessThan(60);
      expect(result.maintenanceStatus).toBe('critical');
    });
  });
});
