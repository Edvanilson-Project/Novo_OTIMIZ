import { Injectable, NotFoundException, ConflictException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import * as bcrypt from 'bcrypt';
import { User } from '../database/entities/user.entity';

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private readonly repo: Repository<User>,
  ) {}

  findAll(): Promise<User[]> {
    return this.repo.find({ order: { name: 'ASC' } });
  }

  async findOne(id: number): Promise<User> {
    const user = await this.repo.findOne({ where: { id } });
    if (!user) throw new NotFoundException(`Usuário ${id} não encontrado`);
    return user;
  }

  async create(dto: Record<string, any>): Promise<User> {
    const exists = await this.repo.findOne({ where: { email: dto.email } });
    if (exists) throw new ConflictException('Já existe um usuário com este e-mail');

    const passwordHash = dto.password ? await bcrypt.hash(dto.password, 10) : '';
    const entity = this.repo.create({
      name: dto.name,
      email: dto.email,
      passwordHash,
      role: dto.role ?? 'operator',
      companyId: dto.companyId ?? null,
      isActive: dto.status === 'inactive' ? false : true,
    });
    return this.repo.save(entity);
  }

  async update(id: number, dto: Record<string, any>): Promise<User> {
    const user = await this.findOne(id);
    if (dto.name !== undefined) user.name = dto.name;
    if (dto.email !== undefined) user.email = dto.email;
    if (dto.password) user.passwordHash = await bcrypt.hash(dto.password, 10);
    if (dto.role !== undefined) user.role = dto.role;
    if (dto.companyId !== undefined) user.companyId = dto.companyId;
    if (dto.status !== undefined) user.isActive = dto.status !== 'inactive';
    return this.repo.save(user);
  }

  async remove(id: number): Promise<void> {
    const user = await this.findOne(id);
    await this.repo.remove(user);
  }
}
