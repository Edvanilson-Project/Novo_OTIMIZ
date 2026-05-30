import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Terminal } from '../database/entities/terminal.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Injectable()
export class TerminalsService {
  constructor(
    @InjectRepository(Terminal)
    private readonly repo: Repository<Terminal>,
    private readonly tenantContext: TenantContext,
  ) {}

  findAll(): Promise<Terminal[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.repo.find({ where: { companyId }, order: { name: 'ASC' } });
  }

  findDepots(): Promise<Terminal[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.repo.find({
      where: { companyId, isDepot: true },
      order: { name: 'ASC' },
    });
  }

  async findOne(id: number): Promise<Terminal> {
    const companyId = this.tenantContext.getCompanyId();
    const terminal = await this.repo.findOne({ where: { id, companyId } });
    if (!terminal) throw new NotFoundException(`Terminal ${id} não encontrado`);
    return terminal;
  }

  async create(dto: Record<string, unknown>): Promise<Terminal> {
    const companyId = this.tenantContext.getCompanyId();
    const terminalId: string =
      (dto['terminalId'] as string) ||
      'TER-' +
        String(dto['name'] || '')
          .toUpperCase()
          .replace(/[^A-Z0-9]/g, '')
          .slice(0, 6) +
        '-' +
        Math.floor(Math.random() * 900 + 100);
    const entity = this.repo.create({ ...(dto as Record<string, unknown>), companyId, terminalId });
    return this.repo.save(entity);
  }

  async update(id: number, dto: Record<string, unknown>): Promise<Terminal> {
    const terminal = await this.findOne(id);
    Object.assign(terminal, dto);
    return this.repo.save(terminal);
  }

  async remove(id: number): Promise<void> {
    const terminal = await this.findOne(id);
    await this.repo.remove(terminal);
  }
}
