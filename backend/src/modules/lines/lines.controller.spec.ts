import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { LinesController } from './lines.controller';
import { LinesService } from './lines.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('LinesController', () => {
  let controller: LinesController;
  let service: jest.Mocked<Partial<LinesService>>;

  beforeEach(async () => {
    service = {
      findAll: jest.fn().mockResolvedValue([{ id: 1, lineId: 'L1', name: 'Linha 1' }]),
      findOne: jest.fn().mockResolvedValue({ id: 1, lineId: 'L1', name: 'Linha 1' }),
      create: jest.fn().mockResolvedValue({ id: 2, lineId: 'L2', name: 'Linha 2' }),
      update: jest.fn().mockResolvedValue({ id: 1, name: 'Updated' }),
      remove: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [LinesController],
      providers: [{ provide: LinesService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
      .compile();

    controller = module.get(LinesController);
  });

  it('findAll returns list', async () => {
    const result = await controller.findAll();
    expect(service.findAll).toHaveBeenCalled();
    expect(result).toHaveLength(1);
  });

  it('findOne returns line', async () => {
    const result = await controller.findOne(1);
    expect(service.findOne).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({ id: 1 });
  });

  it('findOne propagates NotFoundException', async () => {
    (service.findOne as jest.Mock).mockRejectedValue(new NotFoundException());
    await expect(controller.findOne(999)).rejects.toThrow(NotFoundException);
  });

  it('create calls service.create', async () => {
    const body = { lineId: 'L2', name: 'Linha 2' };
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
});
