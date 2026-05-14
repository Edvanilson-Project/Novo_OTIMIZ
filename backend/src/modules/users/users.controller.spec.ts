import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { UsersController } from './users.controller';
import { UsersService } from './users.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('UsersController', () => {
  let controller: UsersController;
  let service: jest.Mocked<Partial<UsersService>>;

  beforeEach(async () => {
    service = {
      findAll: jest.fn().mockResolvedValue([{ id: 1, email: 'a@b.com' }]),
      findOne: jest.fn().mockResolvedValue({ id: 1, email: 'a@b.com' }),
      create: jest.fn().mockResolvedValue({ id: 2, email: 'b@b.com' }),
      update: jest.fn().mockResolvedValue({ id: 1, email: 'updated@b.com' }),
      remove: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [UsersController],
      providers: [{ provide: UsersService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard).useValue({ canActivate: () => true })
      .compile();

    controller = module.get(UsersController);
  });

  it('findAll returns list', async () => {
    expect(await controller.findAll()).toHaveLength(1);
  });

  it('findOne returns user', async () => {
    const result = await controller.findOne(1);
    expect(service.findOne).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({ id: 1 });
  });

  it('findOne propagates NotFoundException', async () => {
    (service.findOne as jest.Mock).mockRejectedValue(new NotFoundException());
    await expect(controller.findOne(999)).rejects.toThrow(NotFoundException);
  });

  it('create calls service.create with body', async () => {
    const body = { email: 'b@b.com', password: 'secret' };
    const result = await controller.create(body);
    expect(service.create).toHaveBeenCalledWith(body);
    expect(result).toMatchObject({ id: 2 });
  });

  it('update calls service.update', async () => {
    await controller.update(1, { email: 'updated@b.com' });
    expect(service.update).toHaveBeenCalledWith(1, { email: 'updated@b.com' });
  });

  it('remove calls service.remove', async () => {
    await controller.remove(1);
    expect(service.remove).toHaveBeenCalledWith(1);
  });
});
