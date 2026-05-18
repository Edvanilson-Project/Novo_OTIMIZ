import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { AuditController } from './audit.controller';
import { AuditService } from './audit.service';
import { TenantContext } from '../../common/context/tenant-context';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('AuditController', () => {
  let controller: AuditController;
  let service: jest.Mocked<Partial<AuditService>>;
  let tenantCtx: { getCompanyId: jest.Mock };

  beforeEach(async () => {
    service = {
      findByCompany: jest.fn().mockResolvedValue({ data: [], total: 0 }),
    };
    tenantCtx = { getCompanyId: jest.fn().mockReturnValue(1) };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [AuditController],
      providers: [
        { provide: AuditService, useValue: service },
        { provide: TenantContext, useValue: tenantCtx },
      ],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(AuditController);
  });

  it('find calls service with defaults', async () => {
    const result = await controller.find();
    expect(service.findByCompany).toHaveBeenCalledWith(1, {
      entity: undefined,
      days: 30,
      page: 1,
      limit: 50,
    });
    expect(result).toMatchObject({ data: [], total: 0 });
  });

  it('find passes query params parsed as numbers', async () => {
    await controller.find('trips', '7', '2', '20');
    expect(service.findByCompany).toHaveBeenCalledWith(1, {
      entity: 'trips',
      days: 7,
      page: 2,
      limit: 20,
    });
  });

  it('throws BadRequestException when no company in context', () => {
    tenantCtx.getCompanyId.mockReturnValue(null);
    expect(() => controller.find()).toThrow(BadRequestException);
  });
});
