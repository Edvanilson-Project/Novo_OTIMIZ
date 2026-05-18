import { AuditService } from './audit.service';
import { AuditAction } from '../database/entities/audit-log.entity';

function makeRepo() {
  return {
    create: jest.fn((d: any) => d),
    save: jest.fn().mockResolvedValue(undefined),
    findAndCount: jest.fn().mockResolvedValue([[], 0]),
  } as any;
}

describe('AuditService', () => {
  let service: AuditService;
  let repo: ReturnType<typeof makeRepo>;

  beforeEach(() => {
    repo = makeRepo();
    service = new AuditService(repo);
  });

  describe('log', () => {
    it('persists an audit entry', async () => {
      await service.log({
        userId: 1,
        companyId: 16,
        action: AuditAction.CREATE,
        entity: 'Trip',
        entityId: 42,
      });
      expect(repo.save).toHaveBeenCalled();
      const created = repo.create.mock.calls[0][0];
      expect(created.entityId).toBe('42');
    });

    it('handles missing optional fields gracefully', async () => {
      await service.log({
        action: AuditAction.READ,
        entity: 'Schedule',
      });
      expect(repo.save).toHaveBeenCalled();
    });

    it('logs error and does not throw when save fails', async () => {
      repo.save.mockRejectedValue(new Error('DB timeout'));
      await expect(
        service.log({
          action: AuditAction.DELETE,
          entity: 'Driver',
          entityId: 5,
        }),
      ).resolves.not.toThrow();
    });
  });

  describe('findByCompany', () => {
    it('returns paginated audit logs', async () => {
      repo.findAndCount.mockResolvedValue([[{ id: 1 }], 1]);
      const result = await service.findByCompany(16, { page: 1, limit: 10 });
      expect(result.total).toBe(1);
      expect(result.items).toHaveLength(1);
      expect(result.pages).toBe(1);
    });

    it('filters by entity when provided', async () => {
      await service.findByCompany(16, { entity: 'Trip' });
      const [where] = repo.findAndCount.mock.calls[0];
      expect(where.where.entity).toBe('Trip');
    });

    it('uses defaults for missing options', async () => {
      await service.findByCompany(16);
      const [opts] = repo.findAndCount.mock.calls[0];
      expect(opts.take).toBe(50);
      expect(opts.skip).toBe(0);
    });

    it('returns correct page info', async () => {
      repo.findAndCount.mockResolvedValue([[], 105]);
      const result = await service.findByCompany(16, { page: 2, limit: 50 });
      expect(result.page).toBe(2);
      expect(result.pages).toBe(3);
    });
  });
});
