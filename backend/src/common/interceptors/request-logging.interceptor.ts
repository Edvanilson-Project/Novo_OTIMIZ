import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  Logger,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { MetricsService } from '../telemetry/metrics.service';

export const REQUEST_ID_HEADER = 'X-Request-ID';
export const CORRELATION_ID_HEADER = 'X-Correlation-ID';

/**
 * Injects requestId into every request/response and logs structured HTTP logs.
 * Logs format: JSON with requestId, method, path, statusCode, durationMs, userId, companyId, error.
 * Sanitizes: no Authorization, Cookie, tokens, passwords.
 */
@Injectable()
export class RequestLoggingInterceptor implements NestInterceptor {
  private readonly logger = new Logger(RequestLoggingInterceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const req = context.switchToHttp().getRequest<Request>();
    const res = context.switchToHttp().getResponse<Response>();

    // Generate or preserve request ID
    let requestId = req.headers[REQUEST_ID_HEADER.toLowerCase()] as string;
    if (!requestId) {
      requestId = req.headers[CORRELATION_ID_HEADER.toLowerCase()] as string;
    }
    if (!requestId) {
      requestId = uuidv4();
    }

    // Inject into request context for downstream code
    (req as any).requestId = requestId;

    // Add to response headers
    res.setHeader(REQUEST_ID_HEADER, requestId);
    res.setHeader(CORRELATION_ID_HEADER, requestId);

    const startTime = Date.now();
    const method = req.method;
    const path = req.path;

    return next.handle().pipe(
      tap(() => {
        const durationMs = Date.now() - startTime;
        const statusCode = res.statusCode;
        MetricsService.recordHttpRequest(method, path, statusCode, durationMs);
        this.logRequest(
          {
            requestId,
            method,
            path,
            statusCode,
            durationMs,
            userId: (req as any).user?.id,
            companyId: (req as any).user?.companyId,
            userAgent: req.get('user-agent'),
            ip: req.ip,
          },
          undefined,
        );
      }),
      catchError((error) => {
        const durationMs = Date.now() - startTime;
        const statusCode = res.statusCode || 500;
        MetricsService.recordHttpRequest(method, path, statusCode, durationMs);
        this.logRequest(
          {
            requestId,
            method,
            path,
            statusCode,
            durationMs,
            userId: (req as any).user?.id,
            companyId: (req as any).user?.companyId,
            userAgent: req.get('user-agent'),
            ip: req.ip,
          },
          error,
        );
        throw error;
      }),
    );
  }

  private logRequest(
    info: {
      requestId: string;
      method: string;
      path: string;
      statusCode: number;
      durationMs: number;
      userId?: number;
      companyId?: number;
      userAgent?: string;
      ip?: string;
    },
    error?: Error,
  ): void {
    // Determine log level
    const level = info.statusCode >= 500 ? 'error' : 'log';

    // Build structured log
    const logEntry = {
      timestamp: new Date().toISOString(),
      requestId: info.requestId,
      method: info.method,
      path: info.path,
      statusCode: info.statusCode,
      durationMs: info.durationMs,
      userId: info.userId,
      companyId: info.companyId,
      userAgent: info.userAgent,
      ip: info.ip,
      ...(error && {
        errorName: error.name,
        errorMessage: error.message,
      }),
    };

    // Output as JSON for structured logging compatibility (stdout → Docker logs)
    this.logger[level](JSON.stringify(logEntry));
  }
}
