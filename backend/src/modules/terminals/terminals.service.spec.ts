import { NotFoundException } from '@nestjs/common';
import { TerminalsService } from './terminals.service';

function makeRepo(terminal?: any) {
  return {
    find: jest.fn().mockResolvedValue(terminal ? [terminal] : []),
    findOne: jest.fn().mockResolvedValue(terminal ?? null),
    create: jest.fn((d: any) => d),
    save: jest.fn((d: any) => Promise.resolve({ id: 1, ...d })),
    remove: jest.fn().mockResolvedValue(undefined),
  } as any;
}

function makeTenant(id = 16) {
  return { getCompanyId: jest.fn().mockReturnValue(id) } as any;
}

describe('TerminalsService', () => {
  let service: TerminalsService;
  let repo: ReturnType<typeof makeRepo>;
  let tenant: ReturnType<typeof makeTenant>;

  const base = {
    id: 1,
    name: 'Terminal Central',
    companyId: 16,
    isDepot: false,
  };

  beforeEach(() => {
    repo = makeRepo(base);
    tenant = makeTenant(16);
    service = new TerminalsService(repo, tenant);
  });

  it('findAll returns terminals for tenant', async () => {
    const result = await service.findAll();
    expect(result).toHaveLength(1);
    expect(repo.find).toHaveBeenCalledWith({
      where: { companyId: 16 },
      order: { name: 'ASC' },
    });
  });

  it('findDepots returns only depots', async () => {
    await service.findDepots();
    expect(repo.find).toHaveBeenCalledWith({
      where: { companyId: 16, isDepot: true },
      order: { name: 'ASC' },
    });
  });

  it('findOne returns terminal by id', async () => {
    const result = await service.findOne(1);
    expect(result.id).toBe(1);
  });

  it('findOne throws NotFoundException when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.findOne(99)).rejects.toThrow(NotFoundException);
  });

  it('create saves terminal with companyId', async () => {
    await service.create({ name: 'Novo Terminal', isDepot: false });
    expect(repo.save).toHaveBeenCalled();
    const saved = repo.create.mock.calls[0][0];
    expect(saved.companyId).toBe(16);
    expect(saved.name).toBe('Novo Terminal');
  });

  it('update modifies terminal fields', async () => {
    repo.findOne.mockResolvedValue({ ...base });
    await service.update(1, { name: 'Updated' });
    expect(repo.save).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Updated' }),
    );
  });

  it('update throws NotFoundException when terminal not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.update(99, { name: 'x' })).rejects.toThrow(
      NotFoundException,
    );
  });

  it('remove deletes terminal', async () => {
    repo.findOne.mockResolvedValue(base);
    await service.remove(1);
    expect(repo.remove).toHaveBeenCalled();
  });

  it('remove throws NotFoundException when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.remove(99)).rejects.toThrow(NotFoundException);
  });
});
