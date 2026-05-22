import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { Request, Response } from 'express';
import { captureException } from '../telemetry/sentry.setup';

@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(GlobalExceptionFilter.name);

  catch(exception: any, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const request = ctx.getRequest<Request>();

    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : HttpStatus.INTERNAL_SERVER_ERROR;

    // Log detalhado apenas no servidor
    this.logger.error(
      `[${request.method}] ${request.url} - Status: ${status} - Error: ${exception.message}`,
      exception.stack,
    );

    // Capture 5xx errors in Sentry (not 4xx — those are expected client errors)
    if (status >= 500) {
      captureException(exception, {
        url: request.url,
        method: request.method,
        status,
      });
    }

    // Resposta padrão e opaca para o cliente (Segurança Anti-vazamento)
    const isErrorHttp = exception instanceof HttpException;
    const message = isErrorHttp
      ? exception.getResponse()
      : 'Erro interno do servidor';

    response.status(status).json({
      statusCode: status,
      timestamp: new Date().toISOString(),
      path: request.url,
      message: typeof message === 'object' ? (message as any).message : message,
    });
  }
}
