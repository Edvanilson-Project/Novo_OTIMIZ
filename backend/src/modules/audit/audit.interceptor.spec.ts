import { of } from 'rxjs';
import { AuditInterceptor } from './audit.interceptor';
import { AuditAction } from '../database/entities/audit-log.entity';

function makeAuditService() {
  return { log: jest.fn().mockResolvedValue(undefined) } as any;
}

function makeContext(
  method: string,
  path: string,
  user?: any,
  body?: any,
): any {
  const req = { method, path, url: path, user, body };
  return {
    switchToHttp: jest
      .fn()
      .mockReturnValue({ getRequest: jest.fn().mockReturnValue(req) }),
  };
}

function makeHandler() {
  return { handle: jest.fn().mockReturnValue(of({ ok: true })) } as any;
}

describe('AuditInterceptor', () => {
  let interceptor: AuditInterceptor;
  let auditService: ReturnType<typeof makeAuditService>;

  beforeEach(() => {
    auditService = makeAuditService();
    interceptor = new AuditInterceptor(auditService);
  });

  it('does not log for GET requests', (done) => {
    const ctx = makeContext('GET', '/api/v1/operations/trips');
    const next = makeHandler();
    interceptor.intercept(ctx, next).subscribe(() => {
      expect(auditService.log).not.toHaveBeenCalled();
      done();
    });
  });

  it('logs CREATE action for POST requests', (done) => {
    const user = { id: 1, companyId: 16, email: 'a@test.com' };
    const ctx = makeContext('POST', '/api/v1/operations/trips', user, {
      data: 1,
    });
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ action: AuditAction.CREATE }),
      );
      done();
    });
  });

  it('logs UPDATE action for PATCH requests', (done) => {
    const ctx = makeContext('PATCH', '/api/v1/operations/trips/5');
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ action: AuditAction.UPDATE }),
      );
      done();
    });
  });

  it('logs UPDATE action for PUT requests', (done) => {
    const ctx = makeContext('PUT', '/api/v1/operations/trips/5');
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ action: AuditAction.UPDATE }),
      );
      done();
    });
  });

  it('logs DELETE action for DELETE requests', (done) => {
    const ctx = makeContext('DELETE', '/api/v1/operations/trips/42');
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ action: AuditAction.DELETE }),
      );
      done();
    });
  });

  it('extracts entity and entityId from path', (done) => {
    const ctx = makeContext('DELETE', '/api/v1/operations/trips/42');
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ entityId: '42' }),
      );
      done();
    });
  });

  it('does not include entityId when last segment is not numeric', (done) => {
    const ctx = makeContext('POST', '/api/v1/operations/trips');
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ entityId: undefined }),
      );
      done();
    });
  });

  it('does not include body payload for DELETE', (done) => {
    const ctx = makeContext('DELETE', '/api/v1/trips/5', undefined, {
      secret: true,
    });
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ payload: undefined }),
      );
      done();
    });
  });

  it('includes body payload for POST', (done) => {
    const body = { tripId: 101 };
    const ctx = makeContext('POST', '/api/v1/trips', undefined, body);
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ payload: body }),
      );
      done();
    });
  });

  it('passes user info to audit log', (done) => {
    const user = { id: 7, companyId: 33, email: 'user@test.com' };
    const ctx = makeContext('POST', '/api/v1/trips', user);
    interceptor.intercept(ctx, makeHandler()).subscribe(() => {
      expect(auditService.log).toHaveBeenCalledWith(
        expect.objectContaining({
          userId: 7,
          companyId: 33,
          userEmail: 'user@test.com',
        }),
      );
      done();
    });
  });
});
