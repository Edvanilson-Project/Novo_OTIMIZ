import { BadRequestException } from '@nestjs/common';
import { OperationsController } from './operations.controller';
import {
  RunOptimizationDto,
  ReassignTripDto,
  CreateTripDto,
  CreateDriverDto,
} from './dto/operations.dto';

function makeController(
  optimizationService: Partial<any> = {},
  operationsService: Partial<any> = {},
  companyId: number | undefined = 16,
) {
  const controller = new OperationsController(
    operationsService as any,
    optimizationService as any,
    { getCompanyId: jest.fn().mockReturnValue(companyId) } as any,
  );
  (controller as any).logger = { warn: jest.fn(), log: jest.fn(), error: jest.fn() };
  return controller;
}

describe('OperationsController', () => {
  // ── runOptimization ──────────────────────────────────────────────────────

  it('runOptimization encaminha algorithm e mode para o service', async () => {
    const runOptimization = jest.fn().mockResolvedValue({ scheduleId: 10, taskId: 'task-10' });
    const controller = makeController({ runOptimization });
    const dto: RunOptimizationDto = { algorithm: 'hybrid_pipeline', operational_quality_mode: 'strict' };

    await controller.runOptimization(dto);
    expect(runOptimization).toHaveBeenCalledWith(16, 'hybrid_pipeline', 'strict', { depotIds: undefined });
  });

  it('runOptimization passa depot_ids para o service', async () => {
    const runOptimization = jest.fn().mockResolvedValue({ scheduleId: 11 });
    const controller = makeController({ runOptimization });
    const dto: RunOptimizationDto = { depot_ids: [1, 2] };

    await controller.runOptimization(dto);
    expect(runOptimization).toHaveBeenCalledWith(16, undefined, undefined, { depotIds: [1, 2] });
  });

  it('runOptimization bloqueia companyId divergente do tenant', async () => {
    const controller = makeController({ runOptimization: jest.fn() });
    const dto: RunOptimizationDto = { companyId: 99 };

    await expect(controller.runOptimization(dto)).rejects.toBeInstanceOf(BadRequestException);
  });

  it('runOptimization lança BadRequestException sem tenant', async () => {
    const controller = new OperationsController(
      { runOptimization: jest.fn() } as any,
      {} as any,
      { getCompanyId: jest.fn().mockReturnValue(null) } as any,
    );
    (controller as any).logger = { warn: jest.fn(), log: jest.fn(), error: jest.fn() };
    await expect(controller.runOptimization({})).rejects.toBeInstanceOf(BadRequestException);
  });

  // ── reassignTrip ─────────────────────────────────────────────────────────

  it('reassignTrip delega para optimizationService', async () => {
    const reassignTrip = jest.fn().mockResolvedValue({ ok: true });
    const controller = makeController({ reassignTrip });
    const dto: ReassignTripDto = { scheduleId: 5, tripId: 10, targetBlockId: 3 };

    await controller.reassignTrip(dto);
    expect(reassignTrip).toHaveBeenCalledWith(16, 5, 10, 3);
  });

  // ── trips CRUD ───────────────────────────────────────────────────────────

  it('getTrips usa defaults de paginação quando sem query params', async () => {
    const getTrips = jest.fn().mockResolvedValue([]);
    const controller = makeController({}, { getTrips });

    await controller.getTrips(undefined as any, undefined as any);
    expect(getTrips).toHaveBeenCalledWith(1, 500, 16);
  });

  it('getTrips respeita limites de paginação (max 1000)', async () => {
    const getTrips = jest.fn().mockResolvedValue([]);
    const controller = makeController({}, { getTrips });

    await controller.getTrips('1', '9999');
    expect(getTrips).toHaveBeenCalledWith(1, 1000, 16);
  });

  it('createTrip delega para operationsService', async () => {
    const createTrip = jest.fn().mockResolvedValue({ id: 42 });
    const controller = makeController({}, { createTrip });
    const dto: CreateTripDto = {
      startTime: 480,
      endTime: 540,
      originId: 1,
      destinationId: 2,
    };

    await controller.createTrip(dto);
    expect(createTrip).toHaveBeenCalledWith(dto, 16);
  });

  // ── uploadFile ───────────────────────────────────────────────────────────

  it('uploadFile lança BadRequestException quando tipo inválido', async () => {
    const controller = makeController({}, { processUpload: jest.fn() });
    const fakeFile = { buffer: Buffer.from(''), originalname: 'test.csv', mimetype: 'text/csv' };

    await expect(controller.uploadFile(fakeFile, 'vehicles')).rejects.toBeInstanceOf(BadRequestException);
  });

  it('uploadFile lança BadRequestException quando sem arquivo', async () => {
    const controller = makeController({}, { processUpload: jest.fn() });

    await expect(controller.uploadFile(undefined as any, 'trips')).rejects.toBeInstanceOf(BadRequestException);
  });

  // ── drivers CRUD ─────────────────────────────────────────────────────────

  it('createDriver delega para operationsService', async () => {
    const createDriver = jest.fn().mockResolvedValue({ id: 7 });
    const controller = makeController({}, { createDriver });
    const dto: CreateDriverDto = { driverId: 'D001', name: 'João Silva' };

    await controller.createDriver(dto);
    expect(createDriver).toHaveBeenCalledWith(dto, 16);
  });

  it('deleteDriver delega para operationsService', async () => {
    const deleteDriver = jest.fn().mockResolvedValue({ affected: 1 });
    const controller = makeController({}, { deleteDriver });

    await controller.deleteDriver(42);
    expect(deleteDriver).toHaveBeenCalledWith(42, 16);
  });
});
