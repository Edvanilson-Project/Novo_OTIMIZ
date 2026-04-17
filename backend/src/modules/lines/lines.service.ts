import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Line } from '../database/entities/line.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Injectable()
export class LinesService {
  constructor(
    @InjectRepository(Line)
    private readonly repo: Repository<Line>,
    private readonly tenantContext: TenantContext,
  ) {}

  findAll(): Promise<Line[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.repo.find({ where: { companyId }, order: { name: 'ASC' } });
  }

  async findOne(id: number): Promise<Line> {
    const companyId = this.tenantContext.getCompanyId();
    const line = await this.repo.findOne({ where: { id, companyId } });
    if (!line) throw new NotFoundException(`Linha ${id} não encontrada`);
    return line;
  }

  async create(dto: Record<string, any>): Promise<Line> {
    const companyId = this.tenantContext.getCompanyId();
    const entity = this.repo.create({ ...dto, companyId });
    return this.repo.save(entity);
  }

  async update(id: number, dto: Record<string, any>): Promise<Line> {
    const line = await this.findOne(id);
    Object.assign(line, dto);
    return this.repo.save(line);
  }

  async remove(id: number): Promise<void> {
    const line = await this.findOne(id);
    await this.repo.remove(line);
  }
}
