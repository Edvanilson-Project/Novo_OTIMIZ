import { ConflictException, NotFoundException } from '@nestjs/common';
import { CompaniesService } from './companies.service';

function makeRepo(company?: any) {
  return {
    find: jest.fn().mockResolvedValue(company ? [company] : []),
    findOne: jest.fn().mockResolvedValue(company ?? null),
    create: jest.fn((d: any) => d),
    save: jest.fn((d: any) => Promise.resolve({ id: 1, ...d })),
    remove: jest.fn().mockResolvedValue(undefined),
  } as any;
}

describe('CompaniesService', () => {
  let service: CompaniesService;
  let repo: ReturnType<typeof makeRepo>;

  beforeEach(() => {
    repo = makeRepo({
      id: 1,
      name: 'Empresa A',
      slug: 'empresa-a',
      isActive: true,
    });
    service = new CompaniesService(repo);
  });

  // ── findAll ────────────────────────────────────────────────────────────────
  it('findAll returns companies sorted by name', async () => {
    const result = await service.findAll();
    expect(result).toHaveLength(1);
    expect(repo.find).toHaveBeenCalledWith({ order: { name: 'ASC' } });
  });

  // ── findOne ────────────────────────────────────────────────────────────────
  it('findOne returns company by id', async () => {
    const result = await service.findOne(1);
    expect(result.id).toBe(1);
  });

  it('findOne throws NotFoundException when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.findOne(999)).rejects.toThrow(NotFoundException);
  });

  // ── create ─────────────────────────────────────────────────────────────────
  it('create saves a new company with generated slug', async () => {
    repo.findOne.mockResolvedValue(null); // no conflict
    const result = await service.create({ name: 'Nova Empresa' });
    expect(repo.save).toHaveBeenCalled();
    expect(result).toMatchObject({ name: 'Nova Empresa' });
  });

  it('create slugifies the name correctly', async () => {
    repo.findOne.mockResolvedValue(null);
    await service.create({ name: 'Empresa São Paulo' });
    const saved = repo.create.mock.calls[0][0];
    expect(saved.slug).toBe('empresa-so-paulo');
  });

  it('create sets isActive to true by default', async () => {
    repo.findOne.mockResolvedValue(null);
    await service.create({ name: 'Nova' });
    const saved = repo.create.mock.calls[0][0];
    expect(saved.isActive).toBe(true);
  });

  it('create throws ConflictException when slug already exists', async () => {
    // findOne returns existing company (slug collision)
    repo.findOne.mockResolvedValue({
      id: 2,
      name: 'Empresa A',
      slug: 'empresa-a',
    });
    await expect(service.create({ name: 'Empresa A' })).rejects.toThrow(
      ConflictException,
    );
  });

  // ── update ─────────────────────────────────────────────────────────────────
  it('update modifies existing company', async () => {
    repo.findOne.mockResolvedValue({
      id: 1,
      name: 'Old Name',
      slug: 'old-name',
    });
    await service.update(1, { name: 'New Name' });
    expect(repo.save).toHaveBeenCalled();
  });

  it('update regenerates slug when name changes', async () => {
    repo.findOne.mockResolvedValue({ id: 1, name: 'Old', slug: 'old' });
    await service.update(1, { name: 'New Name Here' });
    const saved = repo.save.mock.calls[0][0];
    expect(saved.slug).toBe('new-name-here');
  });

  it('update throws NotFoundException when company not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.update(999, { name: 'x' })).rejects.toThrow(
      NotFoundException,
    );
  });

  // ── remove ─────────────────────────────────────────────────────────────────
  it('remove deletes existing company', async () => {
    repo.findOne.mockResolvedValue({ id: 1, name: 'A' });
    await service.remove(1);
    expect(repo.remove).toHaveBeenCalled();
  });

  it('remove throws NotFoundException when not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.remove(404)).rejects.toThrow(NotFoundException);
  });
});
