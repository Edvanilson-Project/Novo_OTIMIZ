import { Injectable, NotFoundException, ConflictException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Company } from '../database/entities/company.entity';

function slugify(text: string): string {
  return text
    .toString()
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\w-]+/g, '')
    .replace(/--+/g, '-');
}

@Injectable()
export class CompaniesService {
  constructor(
    @InjectRepository(Company)
    private readonly repo: Repository<Company>,
  ) {}

  findAll(): Promise<Company[]> {
    return this.repo.find({ order: { name: 'ASC' } });
  }

  async findOne(id: number): Promise<Company> {
    const company = await this.repo.findOne({ where: { id } });
    if (!company) throw new NotFoundException(`Empresa ${id} não encontrada`);
    return company;
  }

  async create(dto: Partial<Company>): Promise<Company> {
    const slug = slugify(dto.name ?? '');
    const existing = await this.repo.findOne({ where: { slug } });
    if (existing) throw new ConflictException('Já existe uma empresa com este nome');

    const entity = this.repo.create({ ...dto, slug, isActive: dto.isActive ?? true });
    return this.repo.save(entity);
  }

  async update(id: number, dto: Partial<Company>): Promise<Company> {
    const company = await this.findOne(id);
    if (dto.name && dto.name !== company.name) {
      company.slug = slugify(dto.name);
    }
    Object.assign(company, dto);
    return this.repo.save(company);
  }

  async remove(id: number): Promise<void> {
    const company = await this.findOne(id);
    await this.repo.remove(company);
  }
}
