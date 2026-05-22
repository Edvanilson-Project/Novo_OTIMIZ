import { TenantContext } from './tenant-context';

describe('TenantContext', () => {
  let ctx: TenantContext;

  beforeEach(() => {
    ctx = new TenantContext();
  });

  it('getCompanyId returns undefined when no store is active', () => {
    expect(ctx.getCompanyId()).toBeUndefined();
  });

  it('getStore returns undefined when no store is active', () => {
    expect(ctx.getStore()).toBeUndefined();
  });

  it('getCompanyId returns companyId within run callback', (done) => {
    TenantContext.run({ companyId: 42 }, () => {
      expect(ctx.getCompanyId()).toBe(42);
      done();
    });
  });

  it('getStore returns full store within run callback', (done) => {
    TenantContext.run({ companyId: 16 }, () => {
      const store = ctx.getStore();
      expect(store).toEqual({ companyId: 16 });
      done();
    });
  });

  it('getCompanyId is undefined outside run callback after it finishes', async () => {
    await new Promise<void>((resolve) => {
      TenantContext.run({ companyId: 99 }, () => resolve());
    });
    expect(ctx.getCompanyId()).toBeUndefined();
  });
});
