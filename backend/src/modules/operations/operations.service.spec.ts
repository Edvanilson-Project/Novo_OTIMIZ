import { BadRequestException, NotFoundException } from '@nestjs/common';
import { OperationsService } from './operations.service';

function makeTripRepo(trips: any[] = []) {
  return {
    find: jest.fn().mockResolvedValue(trips),
    findOne: jest.fn().mockResolvedValue(trips[0] ?? null),
    create: jest.fn((d: any) => d),
    save: jest.fn((d: any) =>
      Promise.resolve(
        Array.isArray(d)
          ? d.map((x, i) => ({ id: i + 1, ...x }))
          : { id: 1, ...d },
      ),
    ),
    remove: jest.fn().mockResolvedValue(undefined),
  } as any;
}

function makeDriverRepo(drivers: any[] = []) {
  return {
    find: jest.fn().mockResolvedValue(drivers),
    findOne: jest.fn().mockResolvedValue(drivers[0] ?? null),
    create: jest.fn((d: any) => d),
    save: jest.fn((d: any) =>
      Promise.resolve(
        Array.isArray(d)
          ? d.map((x, i) => ({ id: i + 1, ...x }))
          : { id: 1, ...d },
      ),
    ),
    remove: jest.fn().mockResolvedValue(undefined),
  } as any;
}

function makeTenant(id: number | null = 16) {
  return { getCompanyId: jest.fn().mockReturnValue(id) } as any;
}

describe('OperationsService', () => {
  let service: OperationsService;
  let tripRepo: ReturnType<typeof makeTripRepo>;
  let driverRepo: ReturnType<typeof makeDriverRepo>;
  let tenant: ReturnType<typeof makeTenant>;

  beforeEach(() => {
    tripRepo = makeTripRepo();
    driverRepo = makeDriverRepo();
    tenant = makeTenant(16);
    service = new OperationsService(tripRepo, driverRepo, tenant);
  });

  // ── getTrips ──────────────────────────────────────────────────────────────

  describe('getTrips', () => {
    it('returns trips with default pagination', async () => {
      tripRepo.find.mockResolvedValue([{ id: 1, tripId: 10, companyId: 16 }]);
      const result = await service.getTrips();
      expect(result).toHaveLength(1);
      expect(tripRepo.find).toHaveBeenCalledWith(
        expect.objectContaining({ skip: 0, take: 100 }),
      );
    });

    it('applies companyId filter when provided', async () => {
      await service.getTrips(1, 50, 16);
      expect(tripRepo.find).toHaveBeenCalledWith(
        expect.objectContaining({ where: { companyId: 16 } }),
      );
    });

    it('omits where clause when companyId not provided', async () => {
      await service.getTrips(1, 50);
      expect(tripRepo.find).toHaveBeenCalledWith(
        expect.objectContaining({ where: undefined }),
      );
    });
  });

  // ── getDrivers ────────────────────────────────────────────────────────────

  describe('getDrivers', () => {
    it('returns drivers sorted by name', async () => {
      driverRepo.find.mockResolvedValue([{ id: 1, driverId: 'M001' }]);
      const result = await service.getDrivers(16);
      expect(result).toHaveLength(1);
      expect(driverRepo.find).toHaveBeenCalledWith(
        expect.objectContaining({ order: { name: 'ASC' } }),
      );
    });
  });

  // ── deleteTrip ────────────────────────────────────────────────────────────

  describe('deleteTrip', () => {
    it('removes existing trip', async () => {
      tripRepo.findOne.mockResolvedValue({ id: 5, companyId: 16 });
      const result = await service.deleteTrip(5, 16);
      expect(tripRepo.remove).toHaveBeenCalled();
      expect(result).toMatchObject({ deleted: true, id: 5 });
    });

    it('throws NotFoundException when trip not found', async () => {
      tripRepo.findOne.mockResolvedValue(null);
      await expect(service.deleteTrip(999, 16)).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  // ── deleteDriver ──────────────────────────────────────────────────────────

  describe('deleteDriver', () => {
    it('removes existing driver', async () => {
      driverRepo.findOne.mockResolvedValue({ id: 3, companyId: 16 });
      const result = await service.deleteDriver(3, 16);
      expect(driverRepo.remove).toHaveBeenCalled();
      expect(result).toMatchObject({ deleted: true });
    });

    it('throws NotFoundException when driver not found', async () => {
      driverRepo.findOne.mockResolvedValue(null);
      await expect(service.deleteDriver(404, 16)).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  // ── clearAllTrips ─────────────────────────────────────────────────────────

  describe('clearAllTrips', () => {
    it('removes all trips for company', async () => {
      tripRepo.find.mockResolvedValue([{ id: 1 }, { id: 2 }]);
      const result = await service.clearAllTrips(16);
      expect(result.deleted).toBe(2);
      expect(tripRepo.remove).toHaveBeenCalled();
    });
  });

  // ── processUpload — too large ─────────────────────────────────────────────

  describe('processUpload file size guard', () => {
    it('throws when file exceeds 10MB', async () => {
      const oversized = Buffer.alloc(11 * 1024 * 1024);
      await expect(service.processUpload(oversized, 'trips')).rejects.toThrow(
        BadRequestException,
      );
    });

    it('throws when tenant not identified', async () => {
      tenant.getCompanyId.mockReturnValue(null);
      const buf = Buffer.from('tripId,startTime,endTime\n1,480,540');
      await expect(service.processUpload(buf, 'trips')).rejects.toThrow(
        BadRequestException,
      );
    });
  });

  // ── processUpload — CSV trips ────────────────────────────────────────────

  describe('processUpload — CSV trips', () => {
    const validCsv = `tripId,lineCode,startTime,endTime,originId,destinationId\n101,L1,480,540,1,2\n102,L1,550,610,2,1`;

    it('persists valid CSV trips and returns inserted count', async () => {
      const result = await service.processUpload(
        Buffer.from(validCsv),
        'trips',
      );
      expect(tripRepo.save).toHaveBeenCalled();
      expect(result).toMatchObject({ inserted: 2 });
    });

    it('throws when CSV is empty (header only)', async () => {
      const empty = Buffer.from('tripId,lineCode,startTime,endTime\n');
      await expect(service.processUpload(empty, 'trips')).rejects.toThrow(
        BadRequestException,
      );
    });

    it('throws when all rows have invalid times', async () => {
      const bad = Buffer.from(
        'tripId,lineCode,startTime,endTime\n101,L1,invalid,also_bad',
      );
      await expect(service.processUpload(bad, 'trips')).rejects.toThrow(
        BadRequestException,
      );
    });

    it('parses HH:MM startTime and endTime correctly', async () => {
      const csv = `tripId,lineCode,startTime,endTime,originId,destinationId\n201,L2,08:00,09:30,1,2`;
      await service.processUpload(Buffer.from(csv), 'trips');
      const saved = tripRepo.save.mock.calls[0][0];
      expect(saved[0].startTime).toBe(480);
      expect(saved[0].endTime).toBe(570);
    });

    it('parses integer minute times correctly', async () => {
      const csv = `tripId,lineCode,startTime,endTime,originId,destinationId\n301,L3,600,660,3,4`;
      await service.processUpload(Buffer.from(csv), 'trips');
      const saved = tripRepo.save.mock.calls[0][0];
      expect(saved[0].startTime).toBe(600);
      expect(saved[0].endTime).toBe(660);
    });

    it('collects partial errors when some rows are invalid', async () => {
      const csv = `tripId,lineCode,startTime,endTime,originId,destinationId
101,L1,480,540,1,2
102,L1,bad,bad,2,1`;
      const result = await service.processUpload(Buffer.from(csv), 'trips');
      expect(result.inserted).toBe(1);
      expect(result.skipped).toBe(1);
    });
  });

  // ── processUpload — CSV drivers ──────────────────────────────────────────

  describe('processUpload — CSV drivers', () => {
    const validDriverCsv = `driverId,name,role\nM001,João,Motorista\nM002,Maria,Cobrador`;

    it('persists valid CSV drivers', async () => {
      const result = await service.processUpload(
        Buffer.from(validDriverCsv),
        'drivers',
      );
      expect(driverRepo.save).toHaveBeenCalled();
      expect(result.inserted).toBe(2);
    });

    it('throws when all rows lack driverId', async () => {
      const bad = Buffer.from('name,role\nJoão,Motorista');
      await expect(service.processUpload(bad, 'drivers')).rejects.toThrow(
        BadRequestException,
      );
    });

    it('skips rows missing name but saves rows with driverId+name', async () => {
      const csv = `driverId,name,role\nM001,João,Motorista\nM002,,Cobrador`;
      const result = await service.processUpload(Buffer.from(csv), 'drivers');
      expect(result.inserted).toBe(1);
      expect(result.skipped).toBe(1);
    });
  });

  // ── createTrip ────────────────────────────────────────────────────────────

  describe('createTrip', () => {
    it('creates a trip with valid times', async () => {
      const result = await service.createTrip(
        { startTime: 480, endTime: 540 },
        16,
      );
      expect(tripRepo.save).toHaveBeenCalled();
      expect(result).toBeTruthy();
    });

    it('throws when startTime missing', async () => {
      await expect(service.createTrip({ endTime: 540 }, 16)).rejects.toThrow(
        BadRequestException,
      );
    });

    it('throws when endTime missing', async () => {
      await expect(service.createTrip({ startTime: 480 }, 16)).rejects.toThrow(
        BadRequestException,
      );
    });
  });

  // ── createDriver ──────────────────────────────────────────────────────────

  describe('createDriver', () => {
    it('creates driver with required fields', async () => {
      await service.createDriver({ driverId: 'M001', name: 'João' }, 16);
      expect(driverRepo.save).toHaveBeenCalled();
    });

    it('throws when driverId missing', async () => {
      await expect(service.createDriver({ name: 'João' }, 16)).rejects.toThrow(
        BadRequestException,
      );
    });

    it('throws when name missing', async () => {
      await expect(
        service.createDriver({ driverId: 'M001' }, 16),
      ).rejects.toThrow(BadRequestException);
    });
  });

  // ── updateDriver ──────────────────────────────────────────────────────────

  describe('updateDriver', () => {
    it('updates existing driver fields', async () => {
      driverRepo.findOne.mockResolvedValue({
        id: 3,
        companyId: 16,
        driverId: 'M001',
        name: 'Old',
      });
      await service.updateDriver(3, { name: 'New Name', role: 'Cobrador' }, 16);
      expect(driverRepo.save).toHaveBeenCalled();
    });

    it('throws NotFoundException when driver not found', async () => {
      driverRepo.findOne.mockResolvedValue(null);
      await expect(
        service.updateDriver(999, { name: 'x' }, 16),
      ).rejects.toThrow(NotFoundException);
    });
  });

  // ── updateTrip ────────────────────────────────────────────────────────────

  describe('updateTrip', () => {
    it('updates trip startTime and endTime', async () => {
      tripRepo.findOne.mockResolvedValue({
        id: 1,
        companyId: 16,
        startTime: 480,
        endTime: 540,
      });
      await service.updateTrip(1, { startTime: 500, endTime: 560 }, 16);
      expect(tripRepo.save).toHaveBeenCalled();
    });

    it('throws BadRequestException when endTime < startTime', async () => {
      tripRepo.findOne.mockResolvedValue({
        id: 1,
        companyId: 16,
        startTime: 480,
        endTime: 540,
      });
      await expect(
        service.updateTrip(1, { startTime: 600, endTime: 500 }, 16),
      ).rejects.toThrow(BadRequestException);
    });

    it('throws NotFoundException when trip not found', async () => {
      tripRepo.findOne.mockResolvedValue(null);
      await expect(
        service.updateTrip(999, { startTime: 480, endTime: 540 }, 16),
      ).rejects.toThrow(NotFoundException);
    });
  });
});
