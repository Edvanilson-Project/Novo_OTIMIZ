import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { AuditService } from './audit.service';
import { AuditAction } from '../database/entities/audit-log.entity';

const METHOD_ACTION: Record<string, AuditAction> = {
  POST: AuditAction.CREATE,
  PATCH: AuditAction.UPDATE,
  PUT: AuditAction.UPDATE,
  DELETE: AuditAction.DELETE,
};

function extractEntityFromPath(path: string): {
  entity: string;
  entityId?: string;
} {
  // e.g. /api/v1/operations/trips/42 → entity=trips, entityId=42
  const segments = path
    .replace(/^\/api\/v\d+\//, '')
    .split('/')
    .filter(Boolean);
  const entity = segments.slice(0, 2).join('/');
  const lastSegment = segments[segments.length - 1];
  const entityId = /^\d+$/.test(lastSegment) ? lastSegment : undefined;
  return { entity, entityId };
}

@Injectable()
export class AuditInterceptor implements NestInterceptor {
  constructor(private readonly auditService: AuditService) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const req = context.switchToHttp().getRequest();
    const method: string = req.method?.toUpperCase();
    const action = METHOD_ACTION[method];

    if (!action) return next.handle();

    const { entity, entityId } = extractEntityFromPath(
      req.path || req.url || '',
    );
    const user = req.user;

    return next.handle().pipe(
      tap(() => {
        void this.auditService.log({
          userId: user?.id,
          companyId: user?.companyId,
          userEmail: user?.email,
          action,
          entity,
          entityId,
          payload: method !== 'DELETE' ? req.body : undefined,
        });
      }),
    );
  }
}
