import { AsyncLocalStorage } from 'async_hooks';

/**
 * Request-scoped context for storing correlation/request IDs.
 * Used by RequestLoggingInterceptor to inject ID, and by HTTP clients to propagate it downstream.
 */
export interface RequestContextData {
  requestId?: string;
  companyId?: number;
}

const requestAsyncStorage = new AsyncLocalStorage<RequestContextData>();

export const RequestContext = {
  /**
   * Get the current request context (requestId, companyId).
   * Returns empty object if outside request scope.
   */
  get(): RequestContextData {
    return requestAsyncStorage.getStore() ?? {};
  },

  /**
   * Set the request context for the current async scope.
   * Called by RequestLoggingInterceptor.
   */
  set(data: RequestContextData): void {
    requestAsyncStorage.enterWith(data);
  },

  /**
   * Run a callback within a request context.
   * Used for testing or manual context setup.
   */
  async run<T>(data: RequestContextData, fn: () => Promise<T>): Promise<T> {
    return requestAsyncStorage.run(data, fn);
  },
};
