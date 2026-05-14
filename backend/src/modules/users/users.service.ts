import { Injectable, NotFoundException, ConflictException, ForbiddenException, BadRequestException, UnprocessableEntityException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import * as bcrypt from 'bcrypt';
import { User, UserRole } from '../database/entities/user.entity';
import { TenantContext } from '../../common/context/tenant-context';

const ALLOWED_ROLES = Object.values(UserRole);

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private readonly repo: Repository<User>,
    private readonly tenantContext: TenantContext,
  ) {}

  private requireCompanyId(): number {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) {
      throw new ForbiddenException('Empresa não identificada no contexto autenticado.');
    }
    return companyId;
  }

  findAll(): Promise<User[]> {
    const companyId = this.requireCompanyId();
    return this.repo.find({ where: { companyId }, order: { name: 'ASC' } });
  }

  async findOne(id: number): Promise<User> {
    const companyId = this.requireCompanyId();
    const user = await this.repo.findOne({ where: { id, companyId } });
    if (!user) throw new NotFoundException(`Usuário ${id} não encontrado`);
    return user;
  }

  async create(dto: Record<string, any>): Promise<User> {
    const companyId = this.requireCompanyId();
    if (dto.companyId !== undefined && Number(dto.companyId) !== companyId) {
      throw new BadRequestException('CompanyId divergente do tenant autenticado.');
    }
    const exists = await this.repo.findOne({ where: { email: dto.email, companyId } });
    if (exists) throw new ConflictException('Já existe um usuário com este e-mail nesta empresa');

    if (dto.role !== undefined && !ALLOWED_ROLES.includes(dto.role)) {
      throw new UnprocessableEntityException(`Role inválida: ${dto.role}`);
    }
    const passwordHash = dto.password ? await bcrypt.hash(dto.password, 10) : '';
    const entity = this.repo.create({
      name: dto.name,
      email: dto.email,
      passwordHash,
      role: dto.role ?? UserRole.OPERATOR,
      companyId,
      isActive: dto.status === 'inactive' ? false : true,
    });
    return this.repo.save(entity);
  }

  async update(id: number, dto: Record<string, any>): Promise<User> {
    const user = await this.findOne(id);
    if (dto.companyId !== undefined && Number(dto.companyId) !== user.companyId) {
      throw new BadRequestException('Não é permitido transferir usuário para outra empresa.');
    }
    if (dto.name !== undefined) user.name = dto.name;
    if (dto.email !== undefined) user.email = dto.email;
    if (dto.password) user.passwordHash = await bcrypt.hash(dto.password, 10);
    if (dto.role !== undefined) {
      if (!ALLOWED_ROLES.includes(dto.role)) {
        throw new UnprocessableEntityException(`Role inválida: ${dto.role}`);
      }
      user.role = dto.role;
    }
    if (dto.status !== undefined) user.isActive = dto.status !== 'inactive';
    return this.repo.save(user);
  }

  async remove(id: number): Promise<void> {
    const user = await this.findOne(id);
    await this.repo.remove(user);
  }
}
