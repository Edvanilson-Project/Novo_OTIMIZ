import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { TerminalsController } from './terminals.controller';
import { TerminalsService } from './terminals.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('TerminalsController', () => {
  let controller: TerminalsController;
  let service: jest.Mocked<Partial<TerminalsService>>;

  beforeEach(async () => {
    service = {
      findAll: jest.fn().mockResolvedValue([{ id: 1, name: 'T1' }, { id: 2, name: 'T2', isDepot: true }]),
      findDepots: jest.fn().mockResolvedValue([{ id: 2, name: 'T2', isDepot: true }]),
      findOne: jest.fn().mockResolvedValue({ id: 1, name: 'T1' }),
      create: jest.fn().mockResolvedValue({ id: 2, name: 'T2' }),
      update: jest.fn().mockResolvedValue({ id: 1, name: 'Updated' }),
      remove: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [TerminalsController],
      providers: [{ provide: TerminalsService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
      .compile();

    controller = module.get(TerminalsController);
  });

  it('findAll returns list', async () => {
    const result = await controller.findAll();
    expect(service.findAll).toHaveBeenCalled();
    expect(result).toHaveLength(2);
  });

  it('findOne returns terminal', async () => {
    const result = await controller.findOne(1);
    expect(service.findOne).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({ id: 1 });
  });

  it('findOne propagates NotFoundException', async () => {
    (service.findOne as jest.Mock).mockRejectedValue(new NotFoundException());
    await expect(controller.findOne(999)).rejects.toThrow(NotFoundException);
  });

  it('create calls service.create', async () => {
    const body = { name: 'T2', terminalId: 'T2' };
    const result = await controller.create(body);
    expect(service.create).toHaveBeenCalledWith(body);
    expect(result).toMatchObject({ id: 2 });
  });

  it('update calls service.update', async () => {
    const result = await controller.update(1, { name: 'Updated' });
    expect(service.update).toHaveBeenCalledWith(1, { name: 'Updated' });
    expect(result).toMatchObject({ name: 'Updated' });
  });

  it('remove calls service.remove', async () => {
    await controller.remove(1);
    expect(service.remove).toHaveBeenCalledWith(1);
  });

  it('findDepots returns only depot terminals', async () => {
    const result = await controller.findDepots();
    expect(service.findDepots).toHaveBeenCalled();
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ isDepot: true });
  });
});
