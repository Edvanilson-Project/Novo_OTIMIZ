import {
  ConflictException,
  ForbiddenException,
  NotFoundException,
  BadRequestException,
  UnprocessableEntityException,
} from '@nestjs/common';
import { UsersService } from './users.service';
import { UserRole } from '../database/entities/user.entity';

jest.mock('bcrypt', () => ({
  hash: jest.fn().mockResolvedValue('hashed_pw'),
  compare: jest.fn(),
}));
import * as bcrypt from 'bcrypt';

function makeRepo(user?: any) {
  return {
    find: jest.fn().mockResolvedValue(user ? [user] : []),
    findOne: jest.fn().mockResolvedValue(user ?? null),
    create: jest.fn((d: any) => d),
    save: jest.fn((d: any) => Promise.resolve({ id: 1, ...d })),
    remove: jest.fn().mockResolvedValue(undefined),
  } as any;
}

function makeTenant(id: number | null = 16) {
  return { getCompanyId: jest.fn().mockReturnValue(id) } as any;
}

function makeDataSource() {
  const mgr = {
    update: jest.fn().mockResolvedValue({ affected: 1 }),
    query: jest.fn().mockResolvedValue([]),
  };
  return {
    getRepository: jest.fn().mockReturnValue({
      find: jest.fn().mockResolvedValue([]),
    }),
    transaction: jest.fn().mockImplementation((cb: (m: any) => Promise<void>) => cb(mgr)),
  } as any;
}

const baseUser = {
  id: 1,
  name: 'Ana',
  email: 'ana@test.com',
  companyId: 16,
  role: UserRole.OPERATOR,
};

describe('UsersService', () => {
  let service: UsersService;
  let repo: ReturnType<typeof makeRepo>;
  let tenant: ReturnType<typeof makeTenant>;

  beforeEach(() => {
    repo = makeRepo(baseUser);
    tenant = makeTenant(16);
    service = new UsersService(repo, tenant, makeDataSource());
  });

  // ── requireCompanyId ─────────────────────────────────────────────────────

  it('throws ForbiddenException when tenant not identified', () => {
    tenant.getCompanyId.mockReturnValue(null);
    expect(() => service.findAll()).toThrow(ForbiddenException);
  });

  // ── findAll ──────────────────────────────────────────────────────────────

  it('findAll returns users for tenant sorted by name', async () => {
    const result = await service.findAll();
    expect(result).toHaveLength(1);
    expect(repo.find).toHaveBeenCalledWith({
      where: { companyId: 16 },
      order: { name: 'ASC' },
    });
  });

  // ── findOne ──────────────────────────────────────────────────────────────

  it('findOne returns user by id', async () => {
    const result = await service.findOne(1);
    expect(result.id).toBe(1);
  });

  it('findOne throws NotFoundException when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.findOne(999)).rejects.toThrow(NotFoundException);
  });

  // ── create ───────────────────────────────────────────────────────────────

  it('create saves user with hashed password and default role', async () => {
    repo.findOne.mockResolvedValue(null);
    const result = await service.create({
      name: 'Bob',
      email: 'bob@test.com',
      password: 'secret',
    });
    expect(bcrypt.hash).toHaveBeenCalledWith('secret', 10);
    expect(result).toMatchObject({ name: 'Bob' });
  });

  it('create throws BadRequestException when password not provided', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(
      service.create({ name: 'Bob', email: 'bob@test.com' }),
    ).rejects.toThrow(BadRequestException);
  });

  it('create throws BadRequestException when password is blank', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(
      service.create({ name: 'Bob', email: 'bob@test.com', password: '   ' }),
    ).rejects.toThrow(BadRequestException);
  });

  it('create defaults role to OPERATOR', async () => {
    repo.findOne.mockResolvedValue(null);
    await service.create({ name: 'Bob', email: 'bob@test.com', password: 'secret' });
    const saved = repo.create.mock.calls[0][0];
    expect(saved.role).toBe(UserRole.OPERATOR);
  });

  it('create throws ConflictException when email already exists', async () => {
    repo.findOne.mockResolvedValue(baseUser);
    await expect(
      service.create({ name: 'Bob', email: 'ana@test.com', password: 'secret' }),
    ).rejects.toThrow(ConflictException);
  });

  it('create throws BadRequestException when companyId diverges', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(
      service.create({ name: 'Bob', email: 'b@t.com', password: 'secret', companyId: 99 }),
    ).rejects.toThrow(BadRequestException);
  });

  it('create throws UnprocessableEntityException for invalid role', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(
      service.create({ name: 'Bob', email: 'b@t.com', password: 'secret', role: 'god' }),
    ).rejects.toThrow(UnprocessableEntityException);
  });

  it('create sets isActive false when status is inactive', async () => {
    repo.findOne.mockResolvedValue(null);
    await service.create({ name: 'Bob', email: 'b@t.com', password: 'secret', status: 'inactive' });
    const saved = repo.create.mock.calls[0][0];
    expect(saved.isActive).toBe(false);
  });

  // ── update ───────────────────────────────────────────────────────────────

  it('update modifies name, email, and role', async () => {
    repo.findOne.mockResolvedValue({ ...baseUser });
    const result = await service.update(1, {
      name: 'Carlos',
      email: 'c@t.com',
      role: UserRole.COMPANY_ADMIN,
    });
    expect(repo.save).toHaveBeenCalled();
    expect(result).toBeTruthy();
  });

  it('update hashes password when provided', async () => {
    repo.findOne.mockResolvedValue({ ...baseUser, passwordHash: '' });
    await service.update(1, { password: 'newpass' });
    expect(bcrypt.hash).toHaveBeenCalledWith('newpass', 10);
  });

  it('update sets isActive from status field', async () => {
    repo.findOne.mockResolvedValue({ ...baseUser });
    await service.update(1, { status: 'inactive' });
    const saved = repo.save.mock.calls[0][0];
    expect(saved.isActive).toBe(false);
  });

  it('update throws BadRequestException when companyId transfer attempted', async () => {
    repo.findOne.mockResolvedValue({ ...baseUser, companyId: 16 });
    await expect(service.update(1, { companyId: 99 })).rejects.toThrow(
      BadRequestException,
    );
  });

  it('update throws UnprocessableEntityException for invalid role', async () => {
    repo.findOne.mockResolvedValue({ ...baseUser });
    await expect(service.update(1, { role: 'hacker' })).rejects.toThrow(
      UnprocessableEntityException,
    );
  });

  it('update throws NotFoundException when user not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.update(999, { name: 'x' })).rejects.toThrow(
      NotFoundException,
    );
  });

  // ── remove ───────────────────────────────────────────────────────────────

  it('remove deletes user', async () => {
    repo.findOne.mockResolvedValue(baseUser);
    await service.remove(1);
    expect(repo.remove).toHaveBeenCalledWith(baseUser);
  });

  it('remove throws NotFoundException when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.remove(404)).rejects.toThrow(NotFoundException);
  });
});
