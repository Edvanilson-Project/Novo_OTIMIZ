import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  Logger,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { DataSource } from 'typeorm';
import { TenantContext } from '../context/tenant-context';
import { RlsQueryRunnerContext } from '../context/rls-query-runner.context';

/**
 * Wraps each HTTP request in a PostgreSQL transaction that sets
 * `app.current_company_id` via SET LOCAL, activating the RLS policies
 * created by migration 1716300000000-AddRowLevelSecurity.
 *
 * BaseRepository checks RlsQueryRunnerContext for the transaction EntityManager
 * and routes queries through it so they run on the same connection.
 *
 * Services using @InjectRepository directly are NOT covered by this interceptor
 * but are protected by ORM-level companyId filtering in service code.
 */
@Injectable()
export class RlsTenantInterceptor implements NestInterceptor {
  private readonly logger = new Logger(RlsTenantInterceptor.name);

  constructor(
    private readonly dataSource: DataSource,
    private readonly tenantContext: TenantContext,
  ) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const companyId = this.tenantContext.getCompanyId();

    if (!companyId) {
      return next.handle();
    }

    return new Observable(subscriber => {
      const queryRunner = this.dataSource.createQueryRunner();

      queryRunner
        .connect()
        .then(() => queryRunner.startTransaction())
        .then(() =>
          queryRunner.query(
            `SET LOCAL app.current_company_id = ${companyId}`,
          ),
        )
        .then(
          () =>
            new Promise<void>((resolve, reject) => {
              RlsQueryRunnerContext.run(queryRunner.manager, () => {
                next.handle().subscribe({
                  next: value => subscriber.next(value),
                  error: reject,
                  complete: resolve,
                });
              });
            }),
        )
        .then(
          async () => {
            // Success path: commit → release → complete
            await queryRunner.commitTransaction();
            try {
              await queryRunner.release();
            } catch {
              this.logger.warn('Failed to release RLS query runner');
            }
            subscriber.complete();
          },
          async (err: unknown) => {
            // Error path: rollback → release → error (release before notify)
            try {
              await queryRunner.rollbackTransaction();
            } catch {}
            try {
              await queryRunner.release();
            } catch {
              this.logger.warn('Failed to release RLS query runner');
            }
            subscriber.error(err);
          },
        );
    });
  }
}
