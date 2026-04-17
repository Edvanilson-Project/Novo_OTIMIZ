import { AsyncLocalStorage } from 'node:async_hooks';
import { Injectable, Scope } from '@nestjs/common';

export interface TenantStore {
  companyId: number;
}

@Injectable({ scope: Scope.DEFAULT })
export class TenantContext {
  private static readonly als = new AsyncLocalStorage<TenantStore>();

  static run(store: TenantStore, callback: () => void) {
    return this.als.run(store, callback);
  }

  getCompanyId(): number | undefined {
    const store = TenantContext.als.getStore();
    return store?.companyId;
  }

  getStore(): TenantStore | undefined {
    return TenantContext.als.getStore();
  }
}
