import {
  Repository,
  FindManyOptions,
  FindOneOptions,
  ObjectLiteral,
  FindOptionsWhere,
  EntityManager,
} from 'typeorm';
import { TenantContext } from '../context/tenant-context';
import { RlsQueryRunnerContext } from '../context/rls-query-runner.context';

export class BaseRepository<T extends ObjectLiteral> extends Repository<T> {
  private tenantContext = new TenantContext();

  private applyTenantFilter(options: any = {}): any {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) return options;

    if (!options.where) {
      options.where = { companyId } as unknown as FindOptionsWhere<T>;
    } else if (Array.isArray(options.where)) {
      options.where = options.where.map((w: any) => ({ ...w, companyId }));
    } else {
      options.where = { ...options.where, companyId };
    }

    return options;
  }

  // Returns the repo to use: transaction-bound (RLS active) or default.
  private activeRepo(): Repository<T> {
    const manager: EntityManager | undefined = RlsQueryRunnerContext.getManager();
    if (manager) {
      return manager.getRepository<T>(this.metadata.target as any);
    }
    return this;
  }

  async find(options?: FindManyOptions<T>): Promise<T[]> {
    const repo = this.activeRepo();
    const filtered = this.applyTenantFilter(options);
    return repo === this ? super.find(filtered) : repo.find(filtered);
  }

  async findOne(options: FindOneOptions<T>): Promise<T | null> {
    const repo = this.activeRepo();
    const filtered = this.applyTenantFilter(options);
    return repo === this ? super.findOne(filtered) : repo.findOne(filtered);
  }

  async count(options?: FindManyOptions<T>): Promise<number> {
    const repo = this.activeRepo();
    const filtered = this.applyTenantFilter(options);
    return repo === this ? super.count(filtered) : repo.count(filtered);
  }

  async findAndCount(options?: FindManyOptions<T>): Promise<[T[], number]> {
    const repo = this.activeRepo();
    const filtered = this.applyTenantFilter(options);
    return repo === this
      ? super.findAndCount(filtered)
      : repo.findAndCount(filtered);
  }
}
