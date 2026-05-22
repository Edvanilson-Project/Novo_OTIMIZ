/**
 * GTFS import — ciclo completo com dados reais de Salvador (SUNT / LabIA-UFBA).
 *
 * Fixtures: fixtures/sunt_salvador/*.txt
 *   stops.txt     — 2975 paradas reais do sistema de ônibus de Salvador-BA
 *   routes.txt    — 412 linhas reais (STCO, Integra Salvador)
 *   trips.txt     — 20 viagens da linha 1230 (Sussuarana × Barra R1)
 *   stop_times.txt — 41 paradas reais da viagem 1046761_D_1_0 (08:30→09:25)
 *
 * Fonte: github.com/LabIA-UFBA/SUNT (CC-BY 4.0, março 2024–2025)
 *
 * Este é o único teste que valida importação em escala de produção:
 *   2975 terminais + 412 linhas + 1 viagem completa (Sussuarana→Barra, 41 paradas, 55 min).
 */
import * as fs from 'fs';
import * as path from 'path';
import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GtfsImportService } from './gtfs-import.service';
import { Terminal } from '../database/entities/terminal.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { TenantContext } from '../../common/context/tenant-context';
// eslint-disable-next-line @typescript-eslint/no-require-imports
const AdmZip = require('adm-zip');

const FIXTURES = path.join(__dirname, 'fixtures', 'sunt_salvador');

function loadFixtureZip(): Buffer {
  const zip = new AdmZip();
  for (const f of ['stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt']) {
    zip.addFile(f, fs.readFileSync(path.join(FIXTURES, f)));
  }
  return zip.toBuffer();
}

describe('GtfsImportService — dados reais de Salvador em escala de produção', () => {
  let service: GtfsImportService;
  let terminalRepo: any;
  let lineRepo: any;
  let tripRepo: any;
  let terminalIdSeq: number;
  let lineIdSeq: number;

  beforeEach(async () => {
    terminalIdSeq = 1;
    lineIdSeq = 1;

    terminalRepo = {
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((d: any) => d),
      save: jest
        .fn()
        .mockImplementation((e: any) => ({ id: terminalIdSeq++, ...e })),
    };
    lineRepo = {
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((d: any) => d),
      save: jest
        .fn()
        .mockImplementation((e: any) => ({ id: lineIdSeq++, ...e })),
    };
    tripRepo = {
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((d: any) => d),
      save: jest.fn().mockImplementation((e: any) => ({ id: 1, ...e })),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GtfsImportService,
        { provide: getRepositoryToken(Terminal), useValue: terminalRepo },
        { provide: getRepositoryToken(Line), useValue: lineRepo },
        { provide: getRepositoryToken(Trip), useValue: tripRepo },
        {
          provide: TenantContext,
          useValue: { getCompanyId: jest.fn().mockReturnValue(1) },
        },
      ],
    }).compile();

    service = module.get(GtfsImportService);
  });

  it('importa 2975 terminais reais de Salvador', async () => {
    const result = await service.importFromBuffer(loadFixtureZip());
    expect(result.imported.terminals).toBe(2975);
  }, 30_000);

  it('importa 412 linhas reais de Salvador', async () => {
    const result = await service.importFromBuffer(loadFixtureZip());
    expect(result.imported.lines).toBe(412);
  }, 30_000);

  it('importa 1 viagem completa (1046761_D_1_0 — Sussuarana→Barra, 41 paradas)', async () => {
    const result = await service.importFromBuffer(loadFixtureZip());
    // Apenas trip 1046761_D_1_0 tem stop_times (as 19 restantes em trips.txt não têm)
    expect(result.imported.trips).toBe(1);
    expect(result.errors).toHaveLength(0);
  }, 30_000);

  it('viagem real dura 55 minutos (08:30→09:25)', async () => {
    await service.importFromBuffer(loadFixtureZip());
    const savedTrip = tripRepo.save.mock.calls[0][0];
    expect(savedTrip.startTime).toBe(510); // 8*60+30
    expect(savedTrip.endTime).toBe(565); // 9*60+25
    expect(savedTrip.duration).toBe(55);
  }, 30_000);

  it('viagem está no sentido IDA (direction_id=0)', async () => {
    await service.importFromBuffer(loadFixtureZip());
    const savedTrip = tripRepo.save.mock.calls[0][0];
    expect(savedTrip.direction).toBe('IDA');
  }, 30_000);

  it('segunda importação não cria duplicatas (idempotência)', async () => {
    terminalRepo.findOne.mockResolvedValue({ id: 1 });
    lineRepo.findOne.mockResolvedValue({ id: 1 });
    tripRepo.findOne.mockResolvedValue({ id: 1 });

    const result = await service.importFromBuffer(loadFixtureZip());
    expect(result.imported.terminals).toBe(0);
    expect(result.imported.lines).toBe(0);
    expect(result.imported.trips).toBe(0);
  }, 30_000);
});
