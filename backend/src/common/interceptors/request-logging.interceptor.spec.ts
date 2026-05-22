import { RequestLoggingInterceptor, REQUEST_ID_HEADER, CORRELATION_ID_HEADER } from './request-logging.interceptor';
import { Logger } from '@nestjs/common';
import { of, throwError } from 'rxjs';
import { MetricsService } from '../telemetry/metrics.service';

describe('RequestLoggingInterceptor', () => {
  let interceptor: RequestLoggingInterceptor;
  let loggerSpy: jest.SpyInstance;

  const mockRequest = (headers: any = {}) => ({
    headers,
    method: 'GET',
    path: '/test',
    ip: '127.0.0.1',
    user: undefined,
    requestId: undefined as string | undefined,
    get: (name: string) => headers[name.toLowerCase()] || null,
  });

  const mockResponse = () => ({
    statusCode: 200,
    setHeader: jest.fn(),
  });

  beforeEach(() => {
    interceptor = new RequestLoggingInterceptor();
    loggerSpy = jest.spyOn(Logger.prototype, 'log').mockReturnValue();
    jest.spyOn(Logger.prototype, 'error').mockReturnValue();
    jest.spyOn(MetricsService, 'recordHttpRequest').mockReturnValue();
    MetricsService.reset();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('generates and preserves request IDs', () => {
    it('should generate a UUID if no request ID is provided', (done) => {
      const req = mockRequest();
      const res = mockResponse() as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        expect(req.requestId).toBeDefined();
        expect(req.requestId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-/i);
        expect(res.setHeader).toHaveBeenCalledWith(REQUEST_ID_HEADER, expect.any(String));
        done();
      });
    });

    it('should preserve X-Request-ID if provided', (done) => {
      const providedId = 'req-123-xyz';
      const req = mockRequest({ 'x-request-id': providedId });
      const res = mockResponse() as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        expect(req.requestId).toBe(providedId);
        expect(res.setHeader).toHaveBeenCalledWith(REQUEST_ID_HEADER, providedId);
        done();
      });
    });

    it('should fall back to X-Correlation-ID if X-Request-ID not provided', (done) => {
      const providedId = 'corr-123-xyz';
      const req = mockRequest({ 'x-correlation-id': providedId });
      const res = mockResponse() as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        expect(req.requestId).toBe(providedId);
        done();
      });
    });

    it('should add request ID to response headers', (done) => {
      const req = mockRequest();
      const res = mockResponse() as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        expect(res.setHeader).toHaveBeenCalledWith(REQUEST_ID_HEADER, req.requestId);
        expect(res.setHeader).toHaveBeenCalledWith(CORRELATION_ID_HEADER, req.requestId);
        done();
      });
    });
  });

  describe('logs structured requests', () => {
    it('should log successful request with requestId, method, path, statusCode, durationMs', (done) => {
      const req = mockRequest() as any;
      req.method = 'POST';
      req.path = '/api/v1/test';
      req.user = { id: 42, companyId: 1 };
      const res = { ...mockResponse(), statusCode: 201 } as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        const logged = loggerSpy.mock.calls[0]?.[0];
        expect(logged).toBeDefined();
        const logObj = JSON.parse(logged);
        expect(logObj.requestId).toBeDefined();
        expect(logObj.method).toBe('POST');
        expect(logObj.path).toBe('/api/v1/test');
        expect(logObj.statusCode).toBe(201);
        expect(logObj.durationMs).toBeGreaterThanOrEqual(0);
        expect(logObj.userId).toBe(42);
        expect(logObj.companyId).toBe(1);
        done();
      });
    });

    it('should not log Authorization or Cookie headers', (done) => {
      const req = mockRequest({ authorization: 'Bearer secret', cookie: 'session=abc' });
      const res = mockResponse() as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        const logged = loggerSpy.mock.calls[0]?.[0];
        expect(logged).not.toContain('secret');
        expect(logged).not.toContain('abc');
        done();
      });
    });
  });

  describe('records metrics', () => {
    it('should record HTTP request metrics on success', (done) => {
      const req = mockRequest() as any;
      req.method = 'GET';
      req.path = '/test';
      const res = mockResponse() as any;
      const next = { handle: () => of({}) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(() => {
        expect(MetricsService.recordHttpRequest).toHaveBeenCalledWith('GET', '/test', 200, expect.any(Number));
        done();
      });
    });

    it('should record HTTP request metrics on error', (done) => {
      const req = mockRequest() as any;
      req.method = 'POST';
      req.path = '/api/v1/create';
      const res = { ...mockResponse(), statusCode: 500 } as any;
      const error = new Error('Test error');
      const next = { handle: () => throwError(() => error) };
      const context = { switchToHttp: () => ({ getRequest: () => req, getResponse: () => res }) } as any;

      interceptor.intercept(context, next).subscribe(
        () => {},
        () => {
          expect(MetricsService.recordHttpRequest).toHaveBeenCalledWith('POST', '/api/v1/create', 500, expect.any(Number));
          done();
        },
      );
    });
  });
});
