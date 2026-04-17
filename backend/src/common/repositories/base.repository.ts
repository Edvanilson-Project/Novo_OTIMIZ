import { Repository, FindManyOptions, FindOneOptions, ObjectLiteral, FindOptionsWhere } from 'typeorm';
import { TenantContext } from '../context/tenant-context';

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

  async find(options?: FindManyOptions<T>): Promise<T[]> {
    return super.find(this.applyTenantFilter(options));
  }

  async findOne(options: FindOneOptions<T>): Promise<T | null> {
    return super.findOne(this.applyTenantFilter(options));
  }

  async count(options?: FindManyOptions<T>): Promise<number> {
    return super.count(this.applyTenantFilter(options));
  }

  // Adicionar outros métodos conforme necessário (ex: findAndCount)
  async findAndCount(options?: FindManyOptions<T>): Promise<[T[], number]> {
    return super.findAndCount(this.applyTenantFilter(options));
  }
}
