import { AsyncLocalStorage } from 'node:async_hooks';
import { EntityManager } from 'typeorm';

const als = new AsyncLocalStorage<EntityManager>();

export const RlsQueryRunnerContext = {
  run<T>(manager: EntityManager, fn: () => T): T {
    return als.run(manager, fn) as T;
  },

  getManager(): EntityManager | undefined {
    return als.getStore();
  },
};
