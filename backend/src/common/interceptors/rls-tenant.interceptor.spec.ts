import { of, firstValueFrom, lastValueFrom } from 'rxjs';
import { RlsTenantInterceptor } from './rls-tenant.interceptor';
import { RlsQueryRunnerContext } from '../context/rls-query-runner.context';

function makeQueryRunner(overrides: Partial<any> = {}) {
  return {
    connect: jest.fn().mockResolvedValue(undefined),
    startTransaction: jest.fn().mockResolvedValue(undefined),
    query: jest.fn().mockResolvedValue(undefined),
    commitTransaction: jest.fn().mockResolvedValue(undefined),
    rollbackTransaction: jest.fn().mockResolvedValue(undefined),
    release: jest.fn().mockResolvedValue(undefined),
    manager: { getRepository: jest.fn() },
    ...overrides,
  };
}

function makeDataSource(qr: any) {
  return { createQueryRunner: jest.fn().mockReturnValue(qr) } as any;
}

function makeContext(): any {
  return {};
}

function makeHandler(value: any = { ok: true }) {
  return { handle: () => of(value) } as any;
}

describe('RlsTenantInterceptor', () => {
  it('skips transaction when no companyId in context', async () => {
    const qr = makeQueryRunner();
    const interceptor = new RlsTenantInterceptor(
      makeDataSource(qr),
      { getCompanyId: () => undefined } as any,
    );
    const result = await firstValueFrom(
      interceptor.intercept(makeContext(), makeHandler()),
    );
    expect(result).toEqual({ ok: true });
    expect(qr.connect).not.toHaveBeenCalled();
  });

  it('sets SET LOCAL with companyId when context present', async () => {
    const qr = makeQueryRunner();
    const interceptor = new RlsTenantInterceptor(
      makeDataSource(qr),
      { getCompanyId: () => 42 } as any,
    );
    await firstValueFrom(interceptor.intercept(makeContext(), makeHandler()));
    expect(qr.query).toHaveBeenCalledWith('SET LOCAL app.current_company_id = 42');
  });

  it('commits transaction on success', async () => {
    const qr = makeQueryRunner();
    const interceptor = new RlsTenantInterceptor(
      makeDataSource(qr),
      { getCompanyId: () => 1 } as any,
    );
    // lastValueFrom waits for complete, which fires after commitTransaction
    await lastValueFrom(interceptor.intercept(makeContext(), makeHandler()));
    expect(qr.commitTransaction).toHaveBeenCalled();
    expect(qr.rollbackTransaction).not.toHaveBeenCalled();
  });

  it('releases query runner even on error', async () => {
    const qr = makeQueryRunner();
    const interceptor = new RlsTenantInterceptor(
      makeDataSource(qr),
      { getCompanyId: () => 1 } as any,
    );
    const failingHandler = {
      handle: () => {
        throw new Error('handler error');
      },
    } as any;
    // release() is called before subscriber.error(), so it's done by the time this rejects
    await lastValueFrom(
      interceptor.intercept(makeContext(), failingHandler),
    ).catch(() => {});
    expect(qr.release).toHaveBeenCalled();
  });

  it('provides EntityManager via RlsQueryRunnerContext inside handler', async () => {
    const fakeManager = { getRepository: jest.fn() };
    const qr = makeQueryRunner({ manager: fakeManager });
    const interceptor = new RlsTenantInterceptor(
      makeDataSource(qr),
      { getCompanyId: () => 7 } as any,
    );

    let capturedManager: any;
    const capturingHandler = {
      handle: () => {
        capturedManager = RlsQueryRunnerContext.getManager();
        return of({ done: true });
      },
    } as any;

    await firstValueFrom(interceptor.intercept(makeContext(), capturingHandler));
    expect(capturedManager).toBe(fakeManager);
  });
});
