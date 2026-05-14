import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { BadRequestException, NotFoundException } from '@nestjs/common';
import { CustomReportsService } from './custom-reports.service';
import { CustomReport, CustomReportFormat } from '../database/entities/custom-report.entity';
import { Schedule, ScheduleStatus } from '../database/entities/schedule.entity';
import { Trip } from '../database/entities/trip.entity';
import { Line } from '../database/entities/line.entity';
import { TenantContext } from '../../common/context/tenant-context';

describe('CustomReportsService', () => {
  let service: CustomReportsService;
  let reportRepo: any;
  let scheduleRepo: any;
  let tripRepo: any;
  let lineRepo: any;

  beforeEach(async () => {
    reportRepo = {
      find: jest.fn(),
      findOne: jest.fn(),
      create: jest.fn((dto) => ({ ...dto, id: 1 })),
      save: jest.fn((entity) => Promise.resolve({ ...entity, id: entity.id ?? 1 })),
      remove: jest.fn(),
    };
    scheduleRepo = { count: jest.fn(), find: jest.fn().mockResolvedValue([]) };
    tripRepo = { count: jest.fn() };
    lineRepo = { count: jest.fn() };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        CustomReportsService,
        { provide: getRepositoryToken(CustomReport), useValue: reportRepo },
        { provide: getRepositoryToken(Schedule), useValue: scheduleRepo },
        { provide: getRepositoryToken(Trip), useValue: tripRepo },
        { provide: getRepositoryToken(Line), useValue: lineRepo },
        { provide: TenantContext, useValue: { getCompanyId: () => 7 } },
      ],
    }).compile();

    service = module.get(CustomReportsService);
  });

  describe('create', () => {
    it('valida que metrics é lista não-vazia', async () => {
      await expect(service.create({ name: 'r1', metrics: [] })).rejects.toThrow(BadRequestException);
      await expect(service.create({ name: 'r1' })).rejects.toThrow(BadRequestException);
    });

    it('rejeita métrica não suportada', async () => {
      await expect(
        service.create({ name: 'r1', metrics: ['totalRuns', 'unknownMetric'] }),
      ).rejects.toThrow(/Métrica não suportada/);
    });

    it('cria template com defaults', async () => {
      const result = await service.create({ name: 'r1', metrics: ['totalRuns'] });
      expect(reportRepo.create).toHaveBeenCalledWith(
        expect.objectContaining({
          companyId: 7,
          name: 'r1',
          metrics: ['totalRuns'],
          filters: {},
          format: CustomReportFormat.JSON,
          ownerUserId: null,
        }),
      );
      expect(result.id).toBe(1);
    });
  });

  describe('findOne', () => {
    it('lança NotFound se não existir', async () => {
      reportRepo.findOne.mockResolvedValue(null);
      await expect(service.findOne(99)).rejects.toThrow(NotFoundException);
    });

    it('só retorna do próprio tenant', async () => {
      reportRepo.findOne.mockResolvedValue({ id: 1, companyId: 7, name: 'r' });
      const result = await service.findOne(1);
      expect(reportRepo.findOne).toHaveBeenCalledWith({ where: { id: 1, companyId: 7 } });
      expect(result.name).toBe('r');
    });
  });

  describe('preview / execute', () => {
    it('preview com totalRuns/completedRuns/successRate calcula corretamente', async () => {
      scheduleRepo.count
        .mockResolvedValueOnce(10) // total
        .mockResolvedValueOnce(7)  // completed
        .mockResolvedValueOnce(2); // failed

      const result = await service.preview(['totalRuns', 'completedRuns', 'failedRuns', 'successRate'], {
        dateRangeDays: 30,
      });

      expect(result.totalRuns).toBe(10);
      expect(result.completedRuns).toBe(7);
      expect(result.failedRuns).toBe(2);
      expect(result.successRate).toBe(70);
    });

    it('preview com totalTrips/totalLines', async () => {
      tripRepo.count.mockResolvedValue(150);
      lineRepo.count.mockResolvedValue(8);

      const result = await service.preview(['totalTrips', 'totalLines'], {});

      expect(result.totalTrips).toBe(150);
      expect(result.totalLines).toBe(8);
    });

    it('preview com avgVehicles/avgCrew/avgCost', async () => {
      scheduleRepo.find.mockResolvedValue([
        { metadata: { num_vehicles: 10, num_crew: 12 }, totalCost: '1000.00' },
        { metadata: { num_vehicles: 14, num_crew: 18 }, totalCost: '2000.00' },
      ]);

      const result = await service.preview(['avgVehicles', 'avgCrew', 'avgCost'], {});

      expect(result.avgVehicles).toBe(12);
      expect(result.avgCrew).toBe(15);
      expect(result.avgCost).toBe(1500);
    });

    it('successRate=0 quando nenhum run', async () => {
      scheduleRepo.count.mockResolvedValue(0);
      const result = await service.preview(['successRate'], {});
      expect(result.successRate).toBe(0);
    });
  });

  describe('toCsv', () => {
    it('produz cabeçalho metric,value e linha para escalar', () => {
      const csv = service.toCsv({ totalRuns: 10, successRate: 80 });
      expect(csv).toContain('metric,value');
      expect(csv).toContain('totalRuns,10');
      expect(csv).toContain('successRate,80');
    });

    it('escapa valores com vírgula', () => {
      const csv = service.toCsv({ note: 'a, b' });
      expect(csv).toContain('"a, b"');
    });

    it('serializa recentRuns como sub-tabela', () => {
      const csv = service.toCsv({
        totalRuns: 2,
        recentRuns: [
          { id: 1, status: 'completed' },
          { id: 2, status: 'failed' },
        ],
      });
      expect(csv).toContain('totalRuns,2');
      expect(csv).toContain('id,status');
      expect(csv).toContain('1,completed');
      expect(csv).toContain('2,failed');
    });
  });
});
