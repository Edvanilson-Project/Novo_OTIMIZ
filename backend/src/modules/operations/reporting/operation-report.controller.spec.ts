import { Test, TestingModule } from '@nestjs/testing';
import { OperationReportController } from './operation-report.controller';
import { OperationReportGeneratorService } from './operation-report-generator.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';

describe('OperationReportController', () => {
  let controller: OperationReportController;
  let service: jest.Mocked<Partial<OperationReportGeneratorService>>;

  beforeEach(async () => {
    service = {
      generateReport: jest.fn().mockResolvedValue({ scheduleId: 1, kpis: {} }),
      getHistoricalReports: jest.fn().mockResolvedValue([{ id: 1 }]),
      compareReports: jest.fn().mockResolvedValue({ delta: {} }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [OperationReportController],
      providers: [{ provide: OperationReportGeneratorService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
      .compile();

    controller = module.get(OperationReportController);
  });

  it('generateReport calls service with scheduleId', async () => {
    const result = await controller.generateReport(42);
    expect(service.generateReport).toHaveBeenCalledWith(42);
    expect(result).toMatchObject({ scheduleId: 1 });
  });

  it('getHistoricalReports returns list', async () => {
    const result = await controller.getHistoricalReports(1, 30);
    expect(service.getHistoricalReports).toHaveBeenCalledWith(1, 30);
    expect(result).toHaveLength(1);
  });

  it('compareReports passes parsed dates', async () => {
    await controller.compareReports(1, '2026-01-01', '2026-01-31');
    expect(service.compareReports).toHaveBeenCalledWith(
      1,
      new Date('2026-01-01'),
      new Date('2026-01-31'),
    );
  });
});
