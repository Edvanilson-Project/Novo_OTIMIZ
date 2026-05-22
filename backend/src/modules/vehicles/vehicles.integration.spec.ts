/**
 * Vehicles Integration Tests — mock-based.
 *
 * Valida a lógica de negócio do VehiclesService com repositórios Jest,
 * sem depender de banco de dados real (SQLite ou Postgres).
 * Testa especialmente as relações VehicleType → Vehicle.
 */
import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { VehiclesService } from './vehicles.service';
import { TenantContext } from '../../common/context/tenant-context';

const COMPANY_ID = 1;

const TYPE_BUS: VehicleType = {
  id: 10,
  companyId: COMPANY_ID,
  name: 'TEST-BUS',
  capacity: 60,
  costPerDay: 500,
  accessible: true,
  description: 'Test bus type',
} as VehicleType;

const VEHICLE_001: Vehicle = {
  id: 1,
  companyId: COMPANY_ID,
  vehicleId: 'TEST-001',
  typeId: TYPE_BUS.id,
  depotId: 1,
  isActive: true,
  licensePlate: 'TEST-001',
  type: TYPE_BUS,
} as Vehicle;

const VEHICLE_002: Vehicle = {
  id: 2,
  companyId: COMPANY_ID,
  vehicleId: 'TEST-002',
  typeId: TYPE_BUS.id,
  depotId: 1,
  isActive: false,
  licensePlate: 'TEST-002',
  type: TYPE_BUS,
} as Vehicle;

describe('Vehicles Integration Tests (mock-based)', () => {
  let service: VehiclesService;
  let vehicleRepo: any;
  let vehicleTypeRepo: any;

  beforeEach(async () => {
    vehicleTypeRepo = {
      find: jest.fn().mockResolvedValue([TYPE_BUS]),
      findOne: jest
        .fn()
        .mockImplementation(({ where: { id, companyId } }: any) =>
          Promise.resolve(
            id === TYPE_BUS.id && companyId === COMPANY_ID ? TYPE_BUS : null,
          ),
        ),
      create: jest
        .fn()
        .mockImplementation((data: any) => ({ id: 99, ...data })),
      save: jest.fn().mockImplementation((e: any) => e),
      remove: jest.fn().mockResolvedValue(undefined),
    };

    vehicleRepo = {
      find: jest.fn().mockResolvedValue([VEHICLE_001, VEHICLE_002]),
      findOne: jest
        .fn()
        .mockImplementation(({ where: { id, companyId } }: any) =>
          Promise.resolve(
            id === VEHICLE_001.id && companyId === COMPANY_ID
              ? VEHICLE_001
              : null,
          ),
        ),
      create: jest
        .fn()
        .mockImplementation((data: any) => ({ id: 50, ...data })),
      save: jest.fn().mockImplementation((e: any) => e),
      remove: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        VehiclesService,
        { provide: getRepositoryToken(Vehicle), useValue: vehicleRepo },
        { provide: getRepositoryToken(VehicleType), useValue: vehicleTypeRepo },
        {
          provide: TenantContext,
          useValue: { getCompanyId: () => COMPANY_ID },
        },
      ],
    }).compile();

    service = module.get(VehiclesService);
  });

  describe('Vehicle Type Operations', () => {
    it('createVehicleType persists com companyId', async () => {
      const result = await service.createVehicleType({
        name: 'COACH',
        capacity: 45,
        costPerDay: 700,
        accessible: false,
      });
      expect(vehicleTypeRepo.create).toHaveBeenCalledWith(
        expect.objectContaining({ companyId: COMPANY_ID }),
      );
      expect(vehicleTypeRepo.save).toHaveBeenCalled();
      expect(result.name).toBe('COACH');
    });

    it('findOneVehicleType retorna tipo existente', async () => {
      const result = await service.findOneVehicleType(TYPE_BUS.id);
      expect(result.name).toBe('TEST-BUS');
      expect(result.capacity).toBe(60);
    });

    it('findOneVehicleType lança NotFoundException para id inexistente', async () => {
      await expect(service.findOneVehicleType(9999)).rejects.toThrow(
        NotFoundException,
      );
    });

    it('updateVehicleType aplica campos e salva', async () => {
      await service.updateVehicleType(TYPE_BUS.id, { capacity: 70 });
      expect(vehicleTypeRepo.save).toHaveBeenCalledWith(
        expect.objectContaining({ capacity: 70 }),
      );
    });
  });

  describe('Vehicle Operations — relação com VehicleType', () => {
    it('createVehicle persiste typeId e companyId', async () => {
      const result = await service.createVehicle({
        vehicleId: 'TEST-001',
        typeId: TYPE_BUS.id,
        depotId: 1,
        isActive: true,
        licensePlate: 'TT-001',
      });
      expect(vehicleRepo.create).toHaveBeenCalledWith(
        expect.objectContaining({
          companyId: COMPANY_ID,
          typeId: TYPE_BUS.id,
        }),
      );
      expect(result.typeId).toBe(TYPE_BUS.id);
    });

    it('findAllVehicles retorna veículos com relação type carregada', async () => {
      const vehicles = await service.findAllVehicles();
      expect(vehicles).toHaveLength(2);
      expect(vehicles[0].type).toBeDefined();
      expect(vehicles[0].type.id).toBe(TYPE_BUS.id);
      expect(vehicles[0].type.name).toBe('TEST-BUS');
    });

    it('getVehiclesByType filtra pelo typeId correto', async () => {
      vehicleRepo.find.mockResolvedValueOnce([VEHICLE_001]);
      const vehicles = await service.getVehiclesByType(TYPE_BUS.id);
      expect(vehicleRepo.find).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({ typeId: TYPE_BUS.id }),
        }),
      );
      expect(vehicles.every((v) => v.typeId === TYPE_BUS.id)).toBe(true);
    });

    it('getActiveVehicles retorna apenas veículos ativos', async () => {
      vehicleRepo.find.mockResolvedValueOnce([VEHICLE_001]); // isActive=true somente
      const active = await service.getActiveVehicles();
      expect(vehicleRepo.find).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({ isActive: true }),
        }),
      );
      expect(active.every((v) => v.isActive)).toBe(true);
    });

    it('findOneVehicle lança NotFoundException para id inexistente', async () => {
      await expect(service.findOneVehicle(9999)).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
