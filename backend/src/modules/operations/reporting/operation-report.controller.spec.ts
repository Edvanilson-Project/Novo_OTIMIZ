import { ForbiddenException, BadRequestException } from '@nestjs/common';
import { OperationReportController } from './operation-report.controller';

const MOCK_REPORT = { scheduleId: 1, kpis: {} };

function makeController(companyId: number | null) {
  const service = {
    generateReport: jest.fn().mockResolvedValue(MOCK_REPORT),
    getHistoricalReports: jest.fn().mockResolvedValue([{ id: 1 }]),
    compareReports: jest.fn().mockResolvedValue({ delta: {} }),
    generatePDFReport: jest.fn().mockResolvedValue(Buffer.from('%PDF')),
    generateExcelReport: jest.fn().mockResolvedValue(Buffer.from('PK')),
  };
  const tenantCtx = { getCompanyId: jest.fn().mockReturnValue(companyId) };
  const ctrl = new OperationReportController(service as any, tenantCtx as any);
  return { ctrl, service, tenantCtx };
}

describe('OperationReportController', () => {
  it('generateReport passes scheduleId and companyId to service', async () => {
    const { ctrl, service } = makeController(7);
    const result = await ctrl.generateReport(42);
    expect(service.generateReport).toHaveBeenCalledWith(42, 7);
    expect(result).toMatchObject({ scheduleId: 1 });
  });

  it('generateReport throws ForbiddenException when no companyId', async () => {
    const { ctrl } = makeController(null);
    await expect(ctrl.generateReport(1)).rejects.toBeInstanceOf(
      ForbiddenException,
    );
  });

  it('getHistoricalReports passes scheduleId, companyId, days to service', async () => {
    const { ctrl, service } = makeController(7);
    const result = await ctrl.getHistoricalReports(1, 30);
    expect(service.getHistoricalReports).toHaveBeenCalledWith(1, 7, 30);
    expect(result).toHaveLength(1);
  });

  it('compareReports passes scheduleId, companyId, and parsed dates', async () => {
    const { ctrl, service } = makeController(7);
    await ctrl.compareReports(1, '2026-01-01', '2026-01-31');
    expect(service.compareReports).toHaveBeenCalledWith(
      1,
      7,
      new Date('2026-01-01'),
      new Date('2026-01-31'),
    );
  });

  it('compareReports throws ForbiddenException when no companyId', async () => {
    const { ctrl } = makeController(null);
    await expect(
      ctrl.compareReports(1, '2026-01-01', '2026-01-31'),
    ).rejects.toBeInstanceOf(ForbiddenException);
  });

  it('compareReports throws BadRequestException for missing startDate', async () => {
    const { ctrl } = makeController(7);
    await expect(
      ctrl.compareReports(1, '', '2026-01-31'),
    ).rejects.toBeInstanceOf(BadRequestException);
  });

  it('compareReports throws BadRequestException for invalid endDate', async () => {
    const { ctrl } = makeController(7);
    await expect(
      ctrl.compareReports(1, '2026-01-01', 'not-a-date'),
    ).rejects.toBeInstanceOf(BadRequestException);
  });
});
