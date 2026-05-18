import { NotFoundException } from '@nestjs/common';
import { LinesService } from './lines.service';

function makeRepo(line?: any) {
  return {
    find: jest.fn().mockResolvedValue(line ? [line] : []),
    findOne: jest.fn().mockResolvedValue(line ?? null),
    create: jest.fn((d: any) => d),
    save: jest.fn((d: any) => Promise.resolve({ id: 1, ...d })),
    remove: jest.fn().mockResolvedValue(undefined),
  } as any;
}

function makeTenant(id = 16) {
  return { getCompanyId: jest.fn().mockReturnValue(id) } as any;
}

describe('LinesService', () => {
  let service: LinesService;
  let repo: ReturnType<typeof makeRepo>;
  let tenant: ReturnType<typeof makeTenant>;

  beforeEach(() => {
    repo = makeRepo({ id: 1, name: 'L1', companyId: 16 });
    tenant = makeTenant(16);
    service = new LinesService(repo, tenant);
  });

  it('findAll returns lines for tenant', async () => {
    const result = await service.findAll();
    expect(result).toHaveLength(1);
    expect(repo.find).toHaveBeenCalledWith({
      where: { companyId: 16 },
      order: { name: 'ASC' },
    });
  });

  it('findOne returns line by id', async () => {
    const result = await service.findOne(1);
    expect(result.id).toBe(1);
  });

  it('findOne throws when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.findOne(99)).rejects.toThrow(NotFoundException);
  });

  it('create saves line with companyId', async () => {
    await service.create({ name: 'Nova Linha' });
    expect(repo.save).toHaveBeenCalled();
    const saved = repo.save.mock.calls[0][0];
    expect(saved.companyId).toBe(16);
  });

  it('update modifies and saves line', async () => {
    await service.update(1, { name: 'Updated' });
    expect(repo.save).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Updated' }),
    );
  });

  it('update throws when line not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.update(99, { name: 'x' })).rejects.toThrow(
      NotFoundException,
    );
  });

  it('remove deletes line', async () => {
    await service.remove(1);
    expect(repo.remove).toHaveBeenCalled();
  });

  it('remove throws when line not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.remove(99)).rejects.toThrow(NotFoundException);
  });
});
