/**
 * Vehicles HTTP E2E Tests — mock-service.
 *
 * Testa a camada HTTP do VehiclesController via supertest com NestJS TestingModule.
 * VehiclesService é mockado — não há dependência de banco de dados.
 *
 * Valida: status codes, formato de resposta, roteamento, ValidationPipe, auth override.
 *
 * Nota: o teste anterior usava SQLite que é incompatível com colunas `timestamp`
 * das entidades (tipo Postgres-only). Esta versão elimina essa dependência.
 */
import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
// eslint-disable-next-line @typescript-eslint/no-require-imports
const request = require('supertest');
import { VehiclesController } from './vehicles.controller';
import { VehiclesService } from './vehicles.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

const TYPE_FIXTURE = { id: 1, name: 'BUS', capacity: 60, costPerDay: 450, accessible: true, description: 'City bus', companyId: 1 };
const VEHICLE_FIXTURE = { id: 1, vehicleId: 'COACH-001', typeId: 1, depotId: 1, isActive: true, licensePlate: 'ABC-1234', companyId: 1 };

describe('Vehicles E2E — HTTP layer (mock-service)', () => {
  let app: INestApplication;
  let svc: jest.Mocked<Partial<VehiclesService>>;

  beforeAll(async () => {
    svc = {
      findAllVehicleTypes: jest.fn().mockResolvedValue([TYPE_FIXTURE]),
      findOneVehicleType: jest.fn().mockResolvedValue(TYPE_FIXTURE),
      createVehicleType: jest.fn().mockResolvedValue(TYPE_FIXTURE),
      updateVehicleType: jest.fn().mockResolvedValue({ ...TYPE_FIXTURE, name: 'COACH' }),
      removeVehicleType: jest.fn().mockResolvedValue(undefined),
      findAllVehicles: jest.fn().mockResolvedValue([VEHICLE_FIXTURE]),
      findOneVehicle: jest.fn().mockResolvedValue(VEHICLE_FIXTURE),
      createVehicle: jest.fn().mockResolvedValue(VEHICLE_FIXTURE),
      updateVehicle: jest.fn().mockResolvedValue({ ...VEHICLE_FIXTURE, licensePlate: 'XYZ-9999' }),
      removeVehicle: jest.fn().mockResolvedValue(undefined),
      getVehiclesByType: jest.fn().mockResolvedValue([VEHICLE_FIXTURE]),
      getActiveVehicles: jest.fn().mockResolvedValue([VEHICLE_FIXTURE]),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [VehiclesController],
      providers: [{ provide: VehiclesService, useValue: svc }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    app = module.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true }));
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  // ── Vehicle Types ──────────────────────────────────────────────────────────

  describe('GET /vehicles/types', () => {
    it('retorna lista de tipos com status 200', async () => {
      const res = await request(app.getHttpServer()).get('/vehicles/types').expect(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(res.body[0]).toMatchObject({ id: 1, name: 'BUS', capacity: 60 });
    });
  });

  describe('GET /vehicles/types/:id', () => {
    it('retorna tipo por id com status 200', async () => {
      const res = await request(app.getHttpServer()).get('/vehicles/types/1').expect(200);
      expect(res.body).toMatchObject({ id: 1, name: 'BUS' });
    });
  });

  describe('POST /vehicles/types', () => {
    it('cria tipo e retorna 201 com o objeto', async () => {
      const res = await request(app.getHttpServer())
        .post('/vehicles/types')
        .send({ name: 'BUS', capacity: 60, costPerDay: 450, accessible: true })
        .expect(201);
      expect(res.body).toMatchObject({ id: 1, name: 'BUS' });
      expect(svc.createVehicleType).toHaveBeenCalled();
    });
  });

  describe('PATCH /vehicles/types/:id', () => {
    it('atualiza tipo e retorna 200', async () => {
      const res = await request(app.getHttpServer())
        .patch('/vehicles/types/1')
        .send({ name: 'COACH' })
        .expect(200);
      expect(res.body).toMatchObject({ name: 'COACH' });
    });
  });

  describe('DELETE /vehicles/types/:id', () => {
    it('remove tipo e retorna 200', async () => {
      await request(app.getHttpServer()).delete('/vehicles/types/1').expect(res => expect(res.status).toBeLessThan(300));
      expect(svc.removeVehicleType).toHaveBeenCalledWith(1);
    });
  });

  // ── Vehicles ───────────────────────────────────────────────────────────────

  describe('GET /vehicles', () => {
    it('retorna lista de veículos com status 200', async () => {
      const res = await request(app.getHttpServer()).get('/vehicles').expect(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(res.body[0]).toMatchObject({ vehicleId: 'COACH-001' });
    });
  });

  describe('GET /vehicles/active', () => {
    it('retorna apenas veículos ativos', async () => {
      const res = await request(app.getHttpServer()).get('/vehicles/active').expect(200);
      expect(Array.isArray(res.body)).toBe(true);
      res.body.forEach((v: any) => expect(v.isActive).toBe(true));
    });
  });

  describe('GET /vehicles/by-type/:typeId', () => {
    it('retorna veículos filtrados por tipo', async () => {
      const res = await request(app.getHttpServer()).get('/vehicles/by-type/1').expect(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(svc.getVehiclesByType).toHaveBeenCalledWith(1);
    });
  });

  describe('GET /vehicles/:id', () => {
    it('retorna veículo por id', async () => {
      const res = await request(app.getHttpServer()).get('/vehicles/1').expect(200);
      expect(res.body).toMatchObject({ id: 1, vehicleId: 'COACH-001' });
    });
  });

  describe('POST /vehicles', () => {
    it('cria veículo e retorna 201', async () => {
      const res = await request(app.getHttpServer())
        .post('/vehicles')
        .send({ vehicleId: 'COACH-001', typeId: 1, depotId: 1, isActive: true, licensePlate: 'ABC-1234' })
        .expect(201);
      expect(res.body).toMatchObject({ vehicleId: 'COACH-001' });
      expect(svc.createVehicle).toHaveBeenCalled();
    });
  });

  describe('PATCH /vehicles/:id', () => {
    it('atualiza veículo e retorna 200', async () => {
      const res = await request(app.getHttpServer())
        .patch('/vehicles/1')
        .send({ licensePlate: 'XYZ-9999' })
        .expect(200);
      expect(res.body).toMatchObject({ licensePlate: 'XYZ-9999' });
    });
  });

  describe('DELETE /vehicles/:id', () => {
    it('remove veículo e retorna 200', async () => {
      await request(app.getHttpServer()).delete('/vehicles/1').expect(res => expect(res.status).toBeLessThan(300));
      expect(svc.removeVehicle).toHaveBeenCalledWith(1);
    });
  });
});
