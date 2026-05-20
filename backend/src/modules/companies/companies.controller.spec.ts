import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { CompaniesController } from './companies.controller';
import { CompaniesService } from './companies.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { TenantContext } from '../../common/context/tenant-context';

describe('CompaniesController', () => {
  let controller: CompaniesController;
  let service: jest.Mocked<Partial<CompaniesService>>;

  beforeEach(async () => {
    service = {
      findAll: jest
        .fn()
        .mockResolvedValue([{ id: 1, name: 'Empresa A', slug: 'empresa-a' }]),
      findOne: jest.fn().mockResolvedValue({ id: 1, name: 'Empresa A' }),
      create: jest.fn().mockResolvedValue({ id: 2, name: 'Empresa B' }),
      update: jest.fn().mockResolvedValue({ id: 1, name: 'Updated' }),
      remove: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [CompaniesController],
      providers: [
        { provide: CompaniesService, useValue: service },
        { provide: TenantContext, useValue: { getCompanyId: () => null } },
      ],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(CompaniesController);
  });

  it('findAll returns list', async () => {
    expect(await controller.findAll()).toHaveLength(1);
  });

  it('findOne returns company', async () => {
    expect(await controller.findOne(1)).toMatchObject({ id: 1 });
  });

  it('findOne propagates NotFoundException', async () => {
    (service.findOne as jest.Mock).mockRejectedValue(new NotFoundException());
    await expect(controller.findOne(999)).rejects.toThrow(NotFoundException);
  });

  it('create calls service.create with body', async () => {
    const body = { name: 'Empresa B', slug: 'empresa-b' };
    const result = await controller.create(body);
    expect(service.create).toHaveBeenCalledWith(body);
    expect(result).toMatchObject({ id: 2 });
  });

  it('update calls service.update', async () => {
    await controller.update(1, { name: 'Updated' });
    expect(service.update).toHaveBeenCalledWith(1, { name: 'Updated' });
  });

  it('remove calls service.remove', async () => {
    await controller.remove(1);
    expect(service.remove).toHaveBeenCalledWith(1);
  });
});
