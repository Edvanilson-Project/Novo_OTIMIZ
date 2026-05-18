import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { ReportsController } from './reports.controller';
import { ReportsService } from './reports.service';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('ReportsController', () => {
  let controller: ReportsController;
  let service: jest.Mocked<Partial<ReportsService>>;
  let tenantCtx: { getCompanyId: jest.Mock };

  beforeEach(async () => {
    service = {
      getKpisByCompany: jest
        .fn()
        .mockResolvedValue({ totalTrips: 100, efficiency: 0.9 }),
      getOptimizationHistory: jest
        .fn()
        .mockResolvedValue({ data: [{ id: 1 }], total: 1 }),
      compareOptimizations: jest
        .fn()
        .mockResolvedValue({ delta: { cost: -500 } }),
    };
    tenantCtx = { getCompanyId: jest.fn().mockReturnValue(5) };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [ReportsController],
      providers: [
        { provide: ReportsService, useValue: service },
        { provide: TenantContext, useValue: tenantCtx },
      ],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(ReportsController);
  });

  it('getKpis calls service with companyId from context', async () => {
    const result = await controller.getKpis();
    expect(service.getKpisByCompany).toHaveBeenCalledWith(5);
    expect(result).toMatchObject({ totalTrips: 100 });
  });

  it('getHistory uses defaults when no query params', async () => {
    await controller.getHistory();
    expect(service.getOptimizationHistory).toHaveBeenCalledWith(5, 30, 1, 50);
  });

  it('getHistory parses query params as numbers', async () => {
    await controller.getHistory('7', '2', '10');
    expect(service.getOptimizationHistory).toHaveBeenCalledWith(5, 7, 2, 10);
  });

  it('compare calls service with both run ids and companyId', async () => {
    const result = await controller.compare(1, 2);
    expect(service.compareOptimizations).toHaveBeenCalledWith(1, 2, 5);
    expect(result).toMatchObject({ delta: { cost: -500 } });
  });

  it('compare throws BadRequestException when no company in context', () => {
    tenantCtx.getCompanyId.mockReturnValue(null);
    expect(() => controller.compare(1, 2)).toThrow(BadRequestException);
  });

  it('throws BadRequestException when no company in context', () => {
    tenantCtx.getCompanyId.mockReturnValue(null);
    expect(() => controller.getKpis()).toThrow(BadRequestException);
  });
});
