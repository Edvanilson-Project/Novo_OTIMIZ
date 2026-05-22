import { RequestContext } from './request-context';

describe('RequestContext', () => {
  afterEach(() => {
    // Context doesn't have a reset, but each test is isolated by async context
  });

  describe('set and get', () => {
    it('should store and retrieve requestId', async () => {
      const testData = { requestId: 'test-123-xyz', companyId: 42 };

      await RequestContext.run(testData, async () => {
        const context = RequestContext.get();
        expect(context.requestId).toBe('test-123-xyz');
        expect(context.companyId).toBe(42);
      });
    });

    it('should return empty object outside request context', () => {
      const context = RequestContext.get();
      // Outside of RequestContext.run, should be empty
      expect(context).toEqual({});
    });

    it('should isolate context between async scopes', async () => {
      const scope1 = { requestId: 'req-1', companyId: 1 };
      const scope2 = { requestId: 'req-2', companyId: 2 };

      const promise1 = RequestContext.run(scope1, async () => {
        // Simulate async work
        await new Promise((resolve) => setTimeout(resolve, 10));
        return RequestContext.get();
      });

      const promise2 = RequestContext.run(scope2, async () => {
        // Simulate async work
        await new Promise((resolve) => setTimeout(resolve, 10));
        return RequestContext.get();
      });

      const [result1, result2] = await Promise.all([promise1, promise2]);

      expect(result1.requestId).toBe('req-1');
      expect(result1.companyId).toBe(1);
      expect(result2.requestId).toBe('req-2');
      expect(result2.companyId).toBe(2);
    });

    it('should allow partial data (only requestId)', async () => {
      const testData = { requestId: 'test-456' };

      await RequestContext.run(testData, async () => {
        const context = RequestContext.get();
        expect(context.requestId).toBe('test-456');
        expect(context.companyId).toBeUndefined();
      });
    });
  });

  describe('enterWith (synchronous set)', () => {
    it('should set context synchronously', () => {
      RequestContext.set({ requestId: 'sync-test', companyId: 99 });
      const context = RequestContext.get();
      expect(context.requestId).toBe('sync-test');
      expect(context.companyId).toBe(99);
    });
  });
});
