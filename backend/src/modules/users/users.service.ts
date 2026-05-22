import {
  Injectable,
  NotFoundException,
  ConflictException,
  ForbiddenException,
  BadRequestException,
  UnprocessableEntityException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import * as bcrypt from 'bcrypt';
import { User, UserRole } from '../database/entities/user.entity';
import { TenantContext } from '../../common/context/tenant-context';
import { AuditLog } from '../database/entities/audit-log.entity';

const ALLOWED_ROLES = Object.values(UserRole);

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private readonly repo: Repository<User>,
    private readonly tenantContext: TenantContext,
    private readonly dataSource: DataSource,
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

  async create(dto: Record<string, unknown>): Promise<User> {
    const companyId = this.requireCompanyId();
    if (dto.companyId !== undefined && Number(dto.companyId) !== companyId) {
      throw new BadRequestException('CompanyId divergente do tenant autenticado.');
    }
    const email = String(dto.email ?? '');
    const exists = await this.repo.findOne({ where: { email, companyId } });
    if (exists) throw new ConflictException('Já existe um usuário com este e-mail nesta empresa');

    const role = dto.role as UserRole | undefined;
    if (role !== undefined && !ALLOWED_ROLES.includes(role)) {
      throw new UnprocessableEntityException(`Role inválida: ${String(role)}`);
    }
    const passwordHash = dto.password
      ? await bcrypt.hash(String(dto.password), 10)
      : '';
    const entity = this.repo.create({
      name: String(dto.name ?? ''),
      email,
      passwordHash,
      role: role ?? UserRole.OPERATOR,
      companyId,
      isActive: dto.status === 'inactive' ? false : true,
    });
    return this.repo.save(entity);
  }

  async update(id: number, dto: Record<string, unknown>): Promise<User> {
    const user = await this.findOne(id);
    if (dto.companyId !== undefined && Number(dto.companyId) !== user.companyId) {
      throw new BadRequestException('Não é permitido transferir usuário para outra empresa.');
    }
    if (dto.name !== undefined) user.name = String(dto.name);
    if (dto.email !== undefined) user.email = String(dto.email);
    if (dto.password) user.passwordHash = await bcrypt.hash(String(dto.password), 10);
    if (dto.role !== undefined) {
      const role = dto.role as UserRole;
      if (!ALLOWED_ROLES.includes(role)) {
        throw new UnprocessableEntityException(`Role inválida: ${String(role)}`);
      }
      user.role = role;
    }
    if (dto.status !== undefined) user.isActive = dto.status !== 'inactive';
    return this.repo.save(user);
  }

  async remove(id: number): Promise<void> {
    const user = await this.findOne(id);
    await this.repo.remove(user);
  }

  // ── LGPD / Privacy ─────────────────────────────────────────────────────────

  /**
   * LGPD Art. 18 §2: direito de acesso — exporta todos os dados pessoais do usuário.
   */
  async exportMyData(userId: number): Promise<Record<string, unknown>> {
    const companyId = this.requireCompanyId();
    const user = await this.repo.findOne({
      where: { id: userId, companyId },
    });
    if (!user) throw new NotFoundException('Usuário não encontrado');

    // Gather related data — select only non-sensitive personal data
    const auditLogs = await this.dataSource
      .getRepository(AuditLog)
      .find({
        where: { userId, companyId },
        order: { createdAt: 'DESC' },
        take: 1000,
        select: ['id', 'action', 'entity', 'entityId', 'createdAt'],
      });

    return {
      exportedAt: new Date().toISOString(),
      profile: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
        isActive: user.isActive,
        createdAt: user.createdAt,
        updatedAt: user.updatedAt,
        lastLoginAt: user.lastLoginAt,
      },
      activityLog: auditLogs,
      dataRetentionPolicy: 'Dados retidos por 5 anos conforme exigência fiscal brasileira (Lei 12.682/2012).',
      gdprNote: 'Para exercer outros direitos LGPD (Art. 18), contate privacy@otimiz.com.br',
    };
  }

  /**
   * LGPD Art. 18 §6: direito ao esquecimento — anonimiza dados pessoais.
   * Dados de auditoria são mantidos (obrigação fiscal/legal) mas desvinculados do usuário.
   * A conta é desativada e dados identificáveis são removidos.
   */
  async anonymizeAccount(userId: number): Promise<void> {
    const companyId = this.requireCompanyId();
    const user = await this.repo.findOne({ where: { id: userId, companyId } });
    if (!user) throw new NotFoundException('Usuário não encontrado');

    await this.dataSource.transaction(async (manager) => {
      // Anonymize personal data — keep id for audit FK integrity
      await manager.update(User, { id: userId }, {
        email: `deleted_${userId}_${Date.now()}@anonymized.local`,
        name: 'Usuário removido',
        passwordHash: 'DELETED',
        isActive: false,
        refreshTokenHash: null,
        refreshTokenExpiresAt: null,
      });

      // Delete tokens (they reference email/identity)
      await manager.query(
        `DELETE FROM refresh_tokens WHERE "userId" = $1`,
        [userId],
      );
      await manager.query(
        `DELETE FROM password_reset_tokens WHERE "userId" = $1`,
        [userId],
      );
    });
  }
}
