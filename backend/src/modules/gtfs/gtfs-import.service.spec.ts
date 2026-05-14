import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GtfsImportService } from './gtfs-import.service';
import { Terminal } from '../database/entities/terminal.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { TenantContext } from '../../common/context/tenant-context';
// eslint-disable-next-line @typescript-eslint/no-require-imports
const AdmZip = require('adm-zip');

function makeZip(files: Record<string, string>): Buffer {
  const zip = new AdmZip();
  for (const [name, content] of Object.entries(files)) {
    zip.addFile(name, Buffer.from(content, 'utf8'));
  }
  return zip.toBuffer();
}

const STOPS_CSV = `stop_id,stop_name,stop_lat,stop_lon
T1,Terminal Alpha,10.0,-50.0
T2,Terminal Beta,11.0,-51.0
`;

const ROUTES_CSV = `route_id,route_short_name,route_long_name
R1,Linha 1,Linha Centro
`;

const TRIPS_CSV = `trip_id,route_id,direction_id
TRIP1,R1,0
`;

const STOP_TIMES_CSV = `trip_id,stop_id,departure_time,arrival_time,stop_sequence
TRIP1,T1,06:00:00,06:00:00,1
TRIP1,T2,06:30:00,06:30:00,2
`;

describe('GtfsImportService', () => {
  let service: GtfsImportService;
  let terminalRepo: any;
  let lineRepo: any;
  let tripRepo: any;
  let tenantCtx: any;

  beforeEach(async () => {
    const makeRepo = () => ({
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((data: any) => data),
      save: jest.fn().mockImplementation(async (entity: any) => ({ id: Math.floor(Math.random() * 1000) + 1, ...entity })),
    });

    terminalRepo = makeRepo();
    lineRepo = makeRepo();
    tripRepo = makeRepo();
    tenantCtx = { getCompanyId: jest.fn().mockReturnValue(1) };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GtfsImportService,
        { provide: getRepositoryToken(Terminal), useValue: terminalRepo },
        { provide: getRepositoryToken(Line), useValue: lineRepo },
        { provide: getRepositoryToken(Trip), useValue: tripRepo },
        { provide: TenantContext, useValue: tenantCtx },
      ],
    }).compile();

    service = module.get(GtfsImportService);
  });

  it('imports terminals, lines and trips from valid GTFS zip', async () => {
    const buf = makeZip({
      'stops.txt': STOPS_CSV,
      'routes.txt': ROUTES_CSV,
      'trips.txt': TRIPS_CSV,
      'stop_times.txt': STOP_TIMES_CSV,
    });
    const result = await service.importFromBuffer(buf);
    expect(result.imported.terminals).toBe(2);
    expect(result.imported.lines).toBe(1);
    expect(result.imported.trips).toBe(1);
    expect(result.errors).toHaveLength(0);
  });

  it('skips duplicate terminals (already in DB)', async () => {
    terminalRepo.findOne.mockResolvedValue({ id: 99, terminalId: 'T1', companyId: 1 });
    const buf = makeZip({
      'stops.txt': STOPS_CSV,
      'routes.txt': ROUTES_CSV,
      'trips.txt': TRIPS_CSV,
      'stop_times.txt': STOP_TIMES_CSV,
    });
    const result = await service.importFromBuffer(buf);
    expect(result.imported.terminals).toBe(0);
    expect(result.skipped).toBeGreaterThan(0);
  });

  it('throws BadRequestException for invalid ZIP buffer', async () => {
    await expect(service.importFromBuffer(Buffer.from('not a zip'))).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException when stops.txt is missing', async () => {
    const buf = makeZip({ 'routes.txt': ROUTES_CSV, 'trips.txt': TRIPS_CSV, 'stop_times.txt': STOP_TIMES_CSV });
    await expect(service.importFromBuffer(buf)).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException when no company in context', async () => {
    tenantCtx.getCompanyId.mockReturnValue(null);
    const buf = makeZip({ 'stops.txt': STOPS_CSV, 'routes.txt': ROUTES_CSV, 'trips.txt': TRIPS_CSV, 'stop_times.txt': STOP_TIMES_CSV });
    await expect(service.importFromBuffer(buf)).rejects.toThrow(BadRequestException);
  });

  it('skips trips where origin == destination (terminal loop)', async () => {
    const loopStopTimes = `trip_id,stop_id,departure_time,arrival_time,stop_sequence
TRIP1,T1,06:00:00,06:00:00,1
TRIP1,T1,06:30:00,06:30:00,2
`;
    // terminals T1 and T1 same id → loop, should skip
    terminalRepo.save
      .mockResolvedValueOnce({ id: 5 })
      .mockResolvedValueOnce({ id: 5 }); // same id both times
    const buf = makeZip({ 'stops.txt': STOPS_CSV, 'routes.txt': ROUTES_CSV, 'trips.txt': TRIPS_CSV, 'stop_times.txt': loopStopTimes });
    const result = await service.importFromBuffer(buf);
    expect(result.imported.trips).toBe(0);
  });

  it('converts HH:MM:SS correctly to minutes', async () => {
    const late = `trip_id,stop_id,departure_time,arrival_time,stop_sequence
TRIP1,T1,24:05:00,24:05:00,1
TRIP1,T2,24:50:00,24:50:00,2
`;
    const buf = makeZip({ 'stops.txt': STOPS_CSV, 'routes.txt': ROUTES_CSV, 'trips.txt': TRIPS_CSV, 'stop_times.txt': late });
    const result = await service.importFromBuffer(buf);
    // 24*60+5=1445 and 24*60+50=1490, endTime > startTime → trip created
    expect(result.imported.trips).toBe(1);
    const savedTrip = tripRepo.save.mock.calls[0][0];
    expect(savedTrip.startTime).toBe(1445);
    expect(savedTrip.endTime).toBe(1490);
  });
});
