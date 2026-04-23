import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import { AuditLog, AuditAction } from '../database/entities/audit-log.entity';

export interface LogPayload {
  userId?: number;
  companyId?: number;
  userEmail?: string;
  action: AuditAction;
  entity: string;
  entityId?: string | number;
  payload?: Record<string, any>;
}

@Injectable()
export class AuditService {
  constructor(
    @InjectRepository(AuditLog)
    private readonly repo: Repository<AuditLog>,
  ) {}

  async log(data: LogPayload): Promise<void> {
    const entry = this.repo.create({
      ...data,
      entityId: data.entityId != null ? String(data.entityId) : undefined,
    });
    await this.repo.save(entry).catch(() => {});
  }

  async findByCompany(
    companyId: number,
    opts: { entity?: string; days?: number; page?: number; limit?: number } = {},
  ) {
    const { entity, days = 30, page = 1, limit = 50 } = opts;
    const since = new Date();
    since.setDate(since.getDate() - days);

    const where: any = { companyId, createdAt: MoreThanOrEqual(since) };
    if (entity) where.entity = entity;

    const [items, total] = await this.repo.findAndCount({
      where,
      order: { createdAt: 'DESC' },
      take: limit,
      skip: (page - 1) * limit,
    });

    return { items, total, page, limit, pages: Math.ceil(total / limit) };
  }
}
