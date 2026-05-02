import { Test, TestingModule } from '@nestjs/testing';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { VehiclesService } from './vehicles.service';
import { TenantContext } from '../../common/context/tenant-context';

describe.skip('Vehicles Integration Tests (Database Relations)', () => {
  let service: VehiclesService;
  let module: TestingModule;

  // Note: These tests require a running PostgreSQL database
  // To run these tests, ensure DB_HOST, DB_USER, DB_PASSWORD, DB_NAME are set
  // They will use the real database, not mocks
  // Use .skip() to exclude from unit test suite. Run separately with:
  // npm test -- --testNamePattern="Integration Tests"

  beforeAll(async () => {
    module = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'postgres',
          host: process.env.DB_HOST || 'localhost',
          port: parseInt(process.env.DB_PORT || '5432'),
          username: process.env.DB_USER || 'postgres',
          password: process.env.DB_PASSWORD || 'postgres',
          database: process.env.DB_NAME || 'otimiz_db',
          entities: [Vehicle, VehicleType],
          synchronize: true,
          dropSchema: false, // Use false in integration tests to preserve data
        }),
        TypeOrmModule.forFeature([Vehicle, VehicleType]),
      ],
      providers: [
        VehiclesService,
        {
          provide: TenantContext,
          useValue: { getCompanyId: () => 1 },
        },
      ],
    }).compile();

    service = module.get<VehiclesService>(VehiclesService);
  });

  afterAll(async () => {
    await module.close();
  });

  describe('Vehicle Type Operations', () => {
    it('should create and retrieve vehicle type', async () => {
      const vehicleType = await service.createVehicleType({
        name: 'TEST-BUS',
        capacity: 60,
        costPerDay: 500,
        accessible: true,
        description: 'Test vehicle type',
      });

      expect(vehicleType).toBeDefined();
      expect(vehicleType.id).toBeDefined();
      expect(vehicleType.name).toBe('TEST-BUS');
      expect(vehicleType.capacity).toBe(60);

      const retrieved = await service.findOneVehicleType(vehicleType.id);
      expect(retrieved.name).toBe('TEST-BUS');
    });
  });

  describe('Vehicle Operations with Type Relationship', () => {
    let vehicleType: VehicleType;

    beforeAll(async () => {
      vehicleType = await service.createVehicleType({
        name: 'TEST-TYPE',
        capacity: 50,
        costPerDay: 400,
        accessible: false,
      });
    });

    it('should create vehicle with type relationship', async () => {
      const vehicle = await service.createVehicle({
        vehicleId: 'TEST-001',
        typeId: vehicleType.id,
        depotId: 1,
        isActive: true,
        licensePlate: 'TEST-001',
      });

      expect(vehicle).toBeDefined();
      expect(vehicle.typeId).toBe(vehicleType.id);
    });

    it('should retrieve vehicle with type relationship', async () => {
      const vehicles = await service.findAllVehicles();
      const testVehicle = vehicles.find(v => v.vehicleId === 'TEST-001');

      expect(testVehicle).toBeDefined();
      expect(testVehicle.type).toBeDefined();
      expect(testVehicle.type.id).toBe(vehicleType.id);
      expect(testVehicle.type.name).toBe('TEST-TYPE');
    });

    it('should get vehicles by type', async () => {
      const vehicles = await service.getVehiclesByType(vehicleType.id);
      expect(vehicles.length).toBeGreaterThan(0);
      expect(vehicles.some(v => v.vehicleId === 'TEST-001')).toBe(true);
    });
  });

  describe('Active Vehicles Filter', () => {
    it('should return only active vehicles', async () => {
      const activeVehicles = await service.getActiveVehicles();
      expect(activeVehicles.every(v => v.isActive === true)).toBe(true);
    });
  });
});
