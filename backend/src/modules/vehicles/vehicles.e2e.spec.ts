import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe, CanActivate, Injectable } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { APP_GUARD } from '@nestjs/core';
import * as request from 'supertest';
import { VehiclesModule } from './vehicles.module';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleMaintenance } from '../database/entities/vehicle-maintenance.entity';
import { VehicleAvailabilityWindow } from '../database/entities/vehicle-availability-window.entity';
import { Terminal } from '../database/entities/terminal.entity';
import { BlockAssignment } from '../database/entities/block-assignment.entity';
import { Schedule } from '../database/entities/schedule.entity';
import { DutyAssignment } from '../database/entities/duty-assignment.entity';
import { OptimizationRun } from '../database/entities/optimization-run.entity';
import { AuditLog } from '../database/entities/audit-log.entity';
import { Company } from '../database/entities/company.entity';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { CustomReport } from '../database/entities/custom-report.entity';
import { Driver } from '../database/entities/driver.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { User } from '../database/entities/user.entity';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Injectable()
class MockAuthGuard implements CanActivate {
  canActivate(): boolean {
    return true;
  }
}

describe.skip('Vehicles E2E Tests', () => {
  jest.setTimeout(30000);
  let app: INestApplication;
  let moduleFixture: TestingModule;
  let vehicleTypeRepo: any;
  let vehicleRepo: any;
  let terminalRepo: any;

  beforeAll(async () => {
    moduleFixture = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'sqlite',
          database: ':memory:',
          entities: [
            VehicleType, Vehicle, VehicleMaintenance, VehicleAvailabilityWindow,
            Terminal, BlockAssignment, Schedule, DutyAssignment, OptimizationRun,
            AuditLog, Company, CompanyParameters, CustomReport, Driver, Line, Trip, User,
          ],
          synchronize: true,
        }),
        VehiclesModule,
      ],
      providers: [
        {
          provide: APP_GUARD,
          useClass: MockAuthGuard,
        },
      ],
    })
      .overrideGuard(JwtAuthGuard)
      .useClass(MockAuthGuard)
      .compile();

    app = moduleFixture.createNestApplication();
    app.useGlobalPipes(new ValidationPipe());
    await app.init();

    // Get repositories
    const dataSource = moduleFixture.get('DataSource');
    vehicleTypeRepo = dataSource.getRepository(VehicleType);
    vehicleRepo = dataSource.getRepository(Vehicle);
    terminalRepo = dataSource.getRepository(Terminal);

    // Create test terminal (depot)
    await terminalRepo.save({
      terminalId: 'MAIN',
      name: 'Main Depot',
      companyId: 1,
    });
  });

  afterAll(async () => {
    try {
      if (moduleFixture) {
        const dataSource = moduleFixture.get('DataSource');
        if (dataSource?.isInitialized) {
          await dataSource.destroy();
        }
      }
    } catch (e) {
      // Ignore cleanup errors
    }
    if (app) {
      await app.close();
    }
  }, 10000);

  describe('Vehicle Types API', () => {
    it('POST /vehicles/types - Should create a vehicle type', async () => {
      const response = await request(app.getHttpServer())
        .post('/vehicles/types')
        .set('Authorization', 'Bearer test-token')
        .send({
          name: 'BUS',
          capacity: 60,
          costPerDay: 450,
          accessible: true,
          description: 'Standard city bus',
        })
        .expect(201);

      expect(response.body).toHaveProperty('id');
      expect(response.body.name).toBe('BUS');
      expect(response.body.capacity).toBe(60);
      expect(response.body.costPerDay).toBe(450);
    });

    it('GET /vehicles/types - Should list all vehicle types', async () => {
      const response = await request(app.getHttpServer())
        .get('/vehicles/types')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      expect(response.body.length).toBeGreaterThan(0);
    });
  });

  describe('Vehicles API', () => {
    let createdTypeId: number;

    beforeAll(async () => {
      // Create vehicle type first
      const type = await vehicleTypeRepo.save({
        name: 'COACH',
        capacity: 50,
        costPerDay: 400,
        accessible: false,
        companyId: 1,
      });
      createdTypeId = type.id;
    });

    it('POST /vehicles - Should create a vehicle', async () => {
      const response = await request(app.getHttpServer())
        .post('/vehicles')
        .set('Authorization', 'Bearer test-token')
        .send({
          vehicleId: 'COACH-001',
          typeId: createdTypeId,
          depotId: 1,
          isActive: true,
          licensePlate: 'ABC-1234',
          odometer: 120000,
        })
        .expect(201);

      expect(response.body).toHaveProperty('id');
      expect(response.body.vehicleId).toBe('COACH-001');
      expect(response.body.typeId).toBe(createdTypeId);
    });

    it('GET /vehicles - Should list all vehicles', async () => {
      const response = await request(app.getHttpServer())
        .get('/vehicles')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
    });

    it('GET /vehicles/active - Should list active vehicles only', async () => {
      const response = await request(app.getHttpServer())
        .get('/vehicles/active')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      response.body.forEach((v: any) => {
        expect(v.isActive).toBe(true);
      });
    });

    it('GET /vehicles/by-type/:typeId - Should list vehicles by type', async () => {
      const response = await request(app.getHttpServer())
        .get(`/vehicles/by-type/${createdTypeId}`)
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
    });
  });
});
