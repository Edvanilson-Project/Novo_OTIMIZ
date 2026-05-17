/**
 * GTFS import — dados reais de Salvador (SUNT / LabIA-UFBA).
 *
 * Fonte: https://github.com/LabIA-UFBA/SUNT (CC-BY 4.0)
 * Dataset: Salvador Urban Network Transportation, março 2024–2025.
 * 5 rotas reais do sistema de ônibus de Salvador-BA.
 *
 * Este teste valida o ciclo completo: ZIP → parse → DB (mocked) → resultado.
 */
import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GtfsImportService } from './gtfs-import.service';
import { Terminal } from '../database/entities/terminal.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { TenantContext } from '../../common/context/tenant-context';
// eslint-disable-next-line @typescript-eslint/no-require-imports
const AdmZip = require('adm-zip');

// ── Dados reais SUNT / LabIA-UFBA ────────────────────────────────────────────

// Stops reais de Salvador (linhas Sussuarana × Barra e adjacentes)
// Os dois últimos (44784470, 44784471) estão na rota real mas não no sample SUNT —
// adicionados com coordenadas aproximadas da Av. Ulysses Guimarães para completar a viagem.
const SUNT_STOPS = `stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station
43968810_S,R. São Cristóvão 2 - Sussuarana Salvador - BA 41213-430 Brasil,-12.931565284729,-38.444393157959,1,
43968810,R. São Cristóvão 2 - Sussuarana Salvador - BA 41213-430 Brasil,-12.931565284729,-38.444393157959,0,43968810_S
47566106_S,Av. Ulysses Guimarães 4067 - Sussuarana Salvador - BA 41213-000 Brasil,-12.93385887146,-38.4467735290527,1,
47566106,Av. Ulysses Guimarães 4067 - Sussuarana Salvador - BA 41213-000 Brasil,-12.93385887146,-38.4467735290527,0,47566106_S
44782337,Av. Ulysses Guimarães 4314-4322 - Novo Horizonte Salvador - BA 41218-700 Brasil,-12.9351501464844,-38.4405784606934,0,
44784470,Av. Ulysses Guimarães (ponto intermediário) - Salvador - BA,-12.9362,-38.4418,0,
44784471,Av. Ulysses Guimarães (terminal) - Nova Sussuarana Salvador - BA,-12.9371,-38.4430,0,
`;

// Rotas reais: 5 linhas do sistema STCO/Salvador
const SUNT_ROUTES = `route_id,agency_id,route_short_name,route_long_name,route_type
4089,1,1230,Sussuarana x Barra R1.,3
4450,1,1321,São Marcos x Barroquinha,3
4518,1,1103,Alto do Cruzeiro/Pernambués x Shop.Bela Vista/Term Ac.Norte,3
4523,1,1405,Estação Pirajá x Cajazeiras 8,3
4524,1,1137,Pernambués x Barra,3
`;

// Viagens reais da linha 1230 (Sussuarana x Barra)
const SUNT_TRIPS = `route_id,service_id,trip_id,direction_id,block_id,shape_id
4089,26082_D_1046761,1046761_D_1_0,0,4089_001M,26082_I
4089,26082_D_1046761,1046761_D_1_1,1,4089_001M,26082_V
4089,26082_D_1046761,1046761_D_2_0,0,4089_002M,26082_I
4089,26082_D_1046761,1046761_D_2_1,1,4089_002M,26082_V
4089,26082_D_1046761,1046761_D_3_0,0,4089_002T,26082_I
`;

// Stop-times reais da viagem 1046761_D_1_0 (partida 08:30 de Sussuarana)
const SUNT_STOP_TIMES = `trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type
1046761_D_1_0,08:30:00,08:30:00,43968810,1,0,0
1046761_D_1_0,08:31:41,08:31:41,47566106,2,0,0
1046761_D_1_0,08:33:49,08:33:49,44782337,3,0,0
1046761_D_1_0,08:34:55,08:34:55,44784470,4,0,0
1046761_D_1_0,08:35:44,08:35:44,44784471,5,0,0
`;

function makeSuntZip(): Buffer {
  const zip = new AdmZip();
  zip.addFile('stops.txt', Buffer.from(SUNT_STOPS, 'utf8'));
  zip.addFile('routes.txt', Buffer.from(SUNT_ROUTES, 'utf8'));
  zip.addFile('trips.txt', Buffer.from(SUNT_TRIPS, 'utf8'));
  zip.addFile('stop_times.txt', Buffer.from(SUNT_STOP_TIMES, 'utf8'));
  return zip.toBuffer();
}

// ─────────────────────────────────────────────────────────────────────────────

describe('GtfsImportService — dados reais SUNT Salvador', () => {
  let service: GtfsImportService;
  let terminalRepo: any;
  let lineRepo: any;
  let tripRepo: any;

  beforeEach(async () => {
    let terminalIdSeq = 1;
    let lineIdSeq = 100;

    terminalRepo = {
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((data: any) => data),
      save: jest.fn().mockImplementation(async (entity: any) => ({ id: terminalIdSeq++, ...entity })),
    };
    lineRepo = {
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((data: any) => data),
      save: jest.fn().mockImplementation(async (entity: any) => ({ id: lineIdSeq++, ...entity })),
    };
    tripRepo = {
      findOne: jest.fn().mockResolvedValue(null),
      create: jest.fn().mockImplementation((data: any) => data),
      save: jest.fn().mockImplementation(async (entity: any) => ({ id: 999, ...entity })),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GtfsImportService,
        { provide: getRepositoryToken(Terminal), useValue: terminalRepo },
        { provide: getRepositoryToken(Line), useValue: lineRepo },
        { provide: getRepositoryToken(Trip), useValue: tripRepo },
        { provide: TenantContext, useValue: { getCompanyId: jest.fn().mockReturnValue(42) } },
      ],
    }).compile();

    service = module.get(GtfsImportService);
  });

  it('importa 7 terminais reais de Salvador', async () => {
    const result = await service.importFromBuffer(makeSuntZip());
    // 7 stops.txt entries: 2 station parents (_S) + 5 regular stops
    expect(result.imported.terminals).toBe(7);
  });

  it('importa 5 linhas reais de Salvador', async () => {
    const result = await service.importFromBuffer(makeSuntZip());
    expect(result.imported.lines).toBe(5);
  });

  it('importa 1 viagem real (1046761_D_1_0: Sussuarana → Nova Sussuarana, 08:30)', async () => {
    const result = await service.importFromBuffer(makeSuntZip());
    // Apenas trip 1046761_D_1_0 tem stop_times → 1 viagem criada
    // As outras 4 viagens não têm stop_times → skipped (< 2 paradas)
    expect(result.imported.trips).toBe(1);
  });

  it('startTime e endTime calculados corretamente a partir de HH:MM:SS', async () => {
    await service.importFromBuffer(makeSuntZip());
    const savedTrip = tripRepo.save.mock.calls[0][0];
    // 08:30:00 → 8*60+30 = 510, 08:35:44 → 8*60+35 = 515 (trunca segundos)
    expect(savedTrip.startTime).toBe(510);
    expect(savedTrip.endTime).toBe(515);
    expect(savedTrip.duration).toBe(5);
  });

  it('viagem está no sentido IDA (direction_id=0)', async () => {
    await service.importFromBuffer(makeSuntZip());
    const savedTrip = tripRepo.save.mock.calls[0][0];
    expect(savedTrip.direction).toBe('IDA');
  });

  it('4 viagens sem stop_times são ignoradas sem erro (só 1 viagem importada)', async () => {
    // trips.txt tem 5 viagens mas stop_times.txt só tem paradas para 1046761_D_1_0.
    // As outras 4 não aparecem no stop_times → não são processadas → sem erro.
    const result = await service.importFromBuffer(makeSuntZip());
    expect(result.errors).toHaveLength(0);
    expect(result.imported.trips).toBe(1);
  });

  it('segunda importação do mesmo ZIP não cria duplicatas', async () => {
    // Simula que todos os registros já existem no DB
    terminalRepo.findOne.mockResolvedValue({ id: 1 });
    lineRepo.findOne.mockResolvedValue({ id: 100 });
    tripRepo.findOne.mockResolvedValue({ id: 999 });

    const result = await service.importFromBuffer(makeSuntZip());
    expect(result.imported.terminals).toBe(0);
    expect(result.imported.lines).toBe(0);
    expect(result.imported.trips).toBe(0);
    expect(result.skipped).toBeGreaterThan(0);
  });
});
