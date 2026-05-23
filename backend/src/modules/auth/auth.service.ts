import {
  Injectable,
  UnauthorizedException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { InjectRepository } from '@nestjs/typeorm';
import { LessThan, Repository } from 'typeorm';
import { createHash } from 'crypto';
import { randomUUID } from 'crypto';
import * as bcrypt from 'bcrypt';
import { User } from '../database/entities/user.entity';
import { RefreshToken } from '../database/entities/refresh-token.entity';
import { PasswordResetToken } from '../database/entities/password-reset-token.entity';
import { EmailService } from '../email/email.service';

const REFRESH_TOKEN_TTL_DAYS = 7;
const RESET_TOKEN_TTL_MINUTES = 60;
const REFRESH_COOKIE = 'refresh_token';

// SHA-256 is sufficient for high-entropy UUIDs (128-bit random).
// bcrypt is for low-entropy values (passwords). Never use bcrypt for tokens.
function sha256(raw: string): string {
  return createHash('sha256').update(raw).digest('hex');
}

@Injectable()
export class AuthService {
  constructor(
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
    @InjectRepository(RefreshToken)
    private readonly refreshTokenRepo: Repository<RefreshToken>,
    @InjectRepository(PasswordResetToken)
    private readonly resetTokenRepo: Repository<PasswordResetToken>,
    private readonly jwtService: JwtService,
    private readonly emailService: EmailService,
  ) {}

  async login(email: string, pass: string, userAgent?: string) {
    const user = await this.userRepo.findOne({
      where: { email },
      select: ['id', 'email', 'passwordHash', 'companyId', 'name', 'role', 'isActive'],
    });

    if (!user || !user.isActive) {
      throw new UnauthorizedException('Credenciais inválidas');
    }

    const valid = await bcrypt.compare(pass, user.passwordHash);
    if (!valid) {
      throw new UnauthorizedException('Credenciais inválidas');
    }

    const [accessToken, refreshToken] = await Promise.all([
      this._signAccess(user),
      this._issueRefreshToken(user.id, userAgent),
    ]);

    // Prune expired refresh tokens for this user on login (keeps table lean)
    void this.refreshTokenRepo.delete({ userId: user.id, expiresAt: LessThan(new Date()) });

    await this.userRepo.update(user.id, { lastLoginAt: new Date() });

    return {
      access_token: accessToken,
      refresh_token: refreshToken,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        companyId: user.companyId,
        role: user.role,
      },
    };
  }

  async refresh(rawRefreshToken: string, userAgent?: string) {
    if (!rawRefreshToken) throw new UnauthorizedException('Refresh token ausente');

    // O(1) lookup via SHA-256 unique index
    const record = await this.refreshTokenRepo.findOne({
      where: { tokenHash: sha256(rawRefreshToken) },
      relations: ['user'],
    });

    if (!record || !record.user?.isActive) {
      throw new ForbiddenException('Refresh token inválido');
    }

    if (record.expiresAt < new Date()) {
      await this.refreshTokenRepo.delete(record.id);
      throw new ForbiddenException('Refresh token expirado');
    }

    // Rotate: delete old, issue new
    await this.refreshTokenRepo.delete(record.id);
    const newRefreshToken = await this._issueRefreshToken(record.userId, userAgent);

    return {
      access_token: await this._signAccess(record.user),
      refresh_token: newRefreshToken,
      user: {
        id: record.user.id,
        name: record.user.name,
        email: record.user.email,
        companyId: record.user.companyId,
        role: record.user.role,
      },
    };
  }

  async logout(rawRefreshToken: string | undefined): Promise<void> {
    if (!rawRefreshToken) return;
    await this.refreshTokenRepo.delete({ tokenHash: sha256(rawRefreshToken) });
  }

  // ── Password Reset ─────────────────────────────────────────────────────────

  async forgotPassword(email: string): Promise<void> {
    // Always respond with 200 — don't reveal whether email exists (prevents enumeration)
    const user = await this.userRepo.findOne({ where: { email, isActive: true } });
    if (!user) return;

    // Invalidate existing tokens for this user
    await this.resetTokenRepo.delete({ userId: user.id });

    const raw = randomUUID();
    const expiresAt = new Date();
    expiresAt.setMinutes(expiresAt.getMinutes() + RESET_TOKEN_TTL_MINUTES);

    await this.resetTokenRepo.insert({
      userId: user.id,
      tokenHash: sha256(raw),
      expiresAt,
      usedAt: null,
    });

    const frontendUrl = process.env.FRONTEND_URL ?? 'http://localhost:3000';
    const resetUrl = `${frontendUrl}/auth/reset-password?token=${raw}`;

    await this.emailService.passwordReset({
      to: user.email,
      name: user.name,
      resetUrl,
      expiresInMinutes: RESET_TOKEN_TTL_MINUTES,
    });
  }

  async resetPassword(rawToken: string, newPassword: string): Promise<void> {
    if (!rawToken) throw new BadRequestException('Token inválido');
    if (!newPassword || newPassword.length < 8) {
      throw new BadRequestException('A senha deve ter no mínimo 8 caracteres');
    }

    const record = await this.resetTokenRepo.findOne({
      where: { tokenHash: sha256(rawToken) },
      relations: ['user'],
    });

    if (!record || record.usedAt) {
      throw new BadRequestException('Token inválido ou já utilizado');
    }
    if (record.expiresAt < new Date()) {
      await this.resetTokenRepo.delete(record.id);
      throw new BadRequestException('Token expirado. Solicite um novo link de redefinição.');
    }

    const passwordHash = await bcrypt.hash(newPassword, 10);

    await Promise.all([
      this.userRepo.update(record.userId, { passwordHash }),
      this.resetTokenRepo.update(record.id, { usedAt: new Date() }),
      // Invalidate ALL refresh tokens for this user (security: force re-login everywhere)
      this.refreshTokenRepo.delete({ userId: record.userId }),
    ]);
  }

  // ── Private ────────────────────────────────────────────────────────────────

  private async _signAccess(
    user: Pick<User, 'id' | 'email' | 'companyId' | 'role'>,
  ): Promise<string> {
    return this.jwtService.signAsync({
      sub: user.id,
      email: user.email,
      companyId: user.companyId,
      role: user.role,
    });
  }

  private async _issueRefreshToken(userId: number, userAgent?: string): Promise<string> {
    const raw = randomUUID();
    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + REFRESH_TOKEN_TTL_DAYS);

    await this.refreshTokenRepo.insert({
      userId,
      tokenHash: sha256(raw),
      expiresAt,
      userAgent: userAgent?.slice(0, 512) ?? null,
    });

    return raw;
  }

  static readonly REFRESH_COOKIE = REFRESH_COOKIE;
  static readonly REFRESH_TTL_MS = REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60 * 1000;
}
