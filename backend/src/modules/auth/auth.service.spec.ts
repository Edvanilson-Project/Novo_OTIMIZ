import { UnauthorizedException, ForbiddenException, BadRequestException } from '@nestjs/common';
import { createHash } from 'crypto';
import { AuthService } from './auth.service';

jest.mock('bcrypt', () => ({
  compare: jest.fn(),
  hash: jest.fn().mockResolvedValue('hashed_pw'),
}));
jest.mock('crypto', () => ({
  ...jest.requireActual('crypto'),
  randomUUID: jest.fn().mockReturnValue('uuid-refresh-token'),
}));
import * as bcrypt from 'bcrypt';

function sha256(raw: string) {
  return createHash('sha256').update(raw).digest('hex');
}

const HASH_OF_UUID = sha256('uuid-refresh-token');
const FUTURE_DATE = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
const PAST_DATE = new Date(Date.now() - 1000);

const validUser = {
  id: 1,
  email: 'admin@test.com',
  passwordHash: 'hashed_pw',
  companyId: 16,
  name: 'Admin',
  role: 'company_admin',
  isActive: true,
};

function makeUserRepo(user: any = validUser) {
  return {
    findOne: jest.fn().mockResolvedValue(user),
    update: jest.fn().mockResolvedValue({ affected: 1 }),
  } as any;
}

function makeRefreshTokenRepo(record: any = null) {
  return {
    findOne: jest.fn().mockResolvedValue(record),
    insert: jest.fn().mockResolvedValue(undefined),
    delete: jest.fn().mockResolvedValue({ affected: 1 }),
  } as any;
}

function makeResetTokenRepo(record: any = null) {
  return {
    findOne: jest.fn().mockResolvedValue(record),
    insert: jest.fn().mockResolvedValue(undefined),
    delete: jest.fn().mockResolvedValue({ affected: 1 }),
    update: jest.fn().mockResolvedValue({ affected: 1 }),
  } as any;
}

function makeEmailService() {
  return {
    passwordReset: jest.fn().mockResolvedValue(undefined),
    optimizationComplete: jest.fn().mockResolvedValue(undefined),
  } as any;
}

function makeJwtService(token = 'signed_token') {
  return { signAsync: jest.fn().mockResolvedValue(token) } as any;
}

function makeService(overrides: {
  userRepo?: any;
  refreshRepo?: any;
  resetRepo?: any;
  jwt?: any;
  email?: any;
} = {}) {
  return new AuthService(
    overrides.userRepo ?? makeUserRepo(),
    overrides.refreshRepo ?? makeRefreshTokenRepo(),
    overrides.resetRepo ?? makeResetTokenRepo(),
    overrides.jwt ?? makeJwtService(),
    overrides.email ?? makeEmailService(),
  );
}

describe('AuthService', () => {
  let service: AuthService;

  beforeEach(() => {
    (bcrypt.compare as jest.Mock).mockResolvedValue(true);
    service = makeService();
  });

  // ── login ────────────────────────────────────────────────────────────────

  it('login returns access_token, refresh_token and user', async () => {
    const result = await service.login('admin@test.com', 'secret');
    expect(result.access_token).toBe('signed_token');
    expect(result.refresh_token).toBe('uuid-refresh-token');
    expect(result.user.id).toBe(1);
    expect(result.user.companyId).toBe(16);
  });

  it('login inserts refresh token record with SHA-256 hash', async () => {
    const refreshRepo = makeRefreshTokenRepo();
    service = makeService({ refreshRepo });
    await service.login('admin@test.com', 'secret');
    expect(refreshRepo.insert).toHaveBeenCalledWith(
      expect.objectContaining({ tokenHash: HASH_OF_UUID, userId: 1 }),
    );
  });

  it('login updates lastLoginAt', async () => {
    const userRepo = makeUserRepo();
    service = makeService({ userRepo });
    await service.login('admin@test.com', 'secret');
    expect(userRepo.update).toHaveBeenCalledWith(1, expect.objectContaining({ lastLoginAt: expect.any(Date) }));
  });

  it('login throws UnauthorizedException when user not found', async () => {
    service = makeService({ userRepo: makeUserRepo(null) });
    await expect(service.login('x@x.com', 'pass')).rejects.toThrow(UnauthorizedException);
  });

  it('login throws UnauthorizedException when password is wrong', async () => {
    (bcrypt.compare as jest.Mock).mockResolvedValue(false);
    await expect(service.login('admin@test.com', 'wrong')).rejects.toThrow(UnauthorizedException);
  });

  it('login throws UnauthorizedException for inactive user', async () => {
    service = makeService({ userRepo: makeUserRepo({ ...validUser, isActive: false }) });
    await expect(service.login('admin@test.com', 'secret')).rejects.toThrow(UnauthorizedException);
  });

  // ── refresh ──────────────────────────────────────────────────────────────

  it('refresh returns new tokens when record exists and not expired', async () => {
    const record = {
      id: 99,
      tokenHash: HASH_OF_UUID,
      expiresAt: FUTURE_DATE,
      userId: 1,
      user: validUser,
    };
    service = makeService({ refreshRepo: makeRefreshTokenRepo(record), jwt: makeJwtService('new_tok') });
    const result = await service.refresh('uuid-refresh-token');
    expect(result.access_token).toBe('new_tok');
    expect(result.refresh_token).toBe('uuid-refresh-token');
  });

  it('refresh uses O(1) SHA-256 lookup (not bcrypt scan)', async () => {
    const refreshRepo = makeRefreshTokenRepo({
      id: 99, tokenHash: HASH_OF_UUID, expiresAt: FUTURE_DATE, userId: 1, user: validUser,
    });
    service = makeService({ refreshRepo });
    await service.refresh('uuid-refresh-token');
    expect(refreshRepo.findOne).toHaveBeenCalledWith(
      expect.objectContaining({ where: { tokenHash: HASH_OF_UUID } }),
    );
  });

  it('refresh deletes old token (rotation)', async () => {
    const refreshRepo = makeRefreshTokenRepo({
      id: 99, tokenHash: HASH_OF_UUID, expiresAt: FUTURE_DATE, userId: 1, user: validUser,
    });
    service = makeService({ refreshRepo });
    await service.refresh('uuid-refresh-token');
    expect(refreshRepo.delete).toHaveBeenCalledWith(99);
  });

  it('refresh throws ForbiddenException when record not found', async () => {
    service = makeService({ refreshRepo: makeRefreshTokenRepo(null) });
    await expect(service.refresh('bad-token')).rejects.toThrow(ForbiddenException);
  });

  it('refresh throws ForbiddenException when token expired', async () => {
    const expiredRecord = {
      id: 88, tokenHash: HASH_OF_UUID, expiresAt: PAST_DATE, userId: 1, user: validUser,
    };
    service = makeService({ refreshRepo: makeRefreshTokenRepo(expiredRecord) });
    await expect(service.refresh('uuid-refresh-token')).rejects.toThrow(ForbiddenException);
  });

  it('refresh throws UnauthorizedException for empty token', async () => {
    await expect(service.refresh('')).rejects.toThrow(UnauthorizedException);
  });

  // ── logout ───────────────────────────────────────────────────────────────

  it('logout deletes token by SHA-256 hash', async () => {
    const refreshRepo = makeRefreshTokenRepo();
    service = makeService({ refreshRepo });
    await service.logout('uuid-refresh-token');
    expect(refreshRepo.delete).toHaveBeenCalledWith({ tokenHash: HASH_OF_UUID });
  });

  it('logout is a no-op when token is undefined', async () => {
    const refreshRepo = makeRefreshTokenRepo();
    service = makeService({ refreshRepo });
    await expect(service.logout(undefined)).resolves.toBeUndefined();
    expect(refreshRepo.delete).not.toHaveBeenCalled();
  });

  // ── forgotPassword ───────────────────────────────────────────────────────

  it('forgotPassword sends email and inserts reset token', async () => {
    const resetRepo = makeResetTokenRepo();
    const emailSvc = makeEmailService();
    service = makeService({ resetRepo, email: emailSvc });
    await service.forgotPassword('admin@test.com');
    expect(resetRepo.insert).toHaveBeenCalledWith(
      expect.objectContaining({ userId: 1, tokenHash: expect.any(String) }),
    );
    expect(emailSvc.passwordReset).toHaveBeenCalledWith(
      expect.objectContaining({ to: 'admin@test.com' }),
    );
  });

  it('forgotPassword is silent when user not found (no enumeration)', async () => {
    const resetRepo = makeResetTokenRepo();
    const emailSvc = makeEmailService();
    service = makeService({ userRepo: makeUserRepo(null), resetRepo, email: emailSvc });
    await expect(service.forgotPassword('unknown@test.com')).resolves.toBeUndefined();
    expect(resetRepo.insert).not.toHaveBeenCalled();
    expect(emailSvc.passwordReset).not.toHaveBeenCalled();
  });

  // ── resetPassword ────────────────────────────────────────────────────────

  it('resetPassword updates passwordHash and marks token used', async () => {
    const resetRecord = {
      id: 55,
      tokenHash: HASH_OF_UUID,
      expiresAt: FUTURE_DATE,
      usedAt: null,
      userId: 1,
      user: validUser,
    };
    const resetRepo = makeResetTokenRepo(resetRecord);
    const userRepo = makeUserRepo();
    const refreshRepo = makeRefreshTokenRepo();
    service = makeService({ userRepo, refreshRepo, resetRepo });
    await service.resetPassword('uuid-refresh-token', 'NewPass123!');
    expect(userRepo.update).toHaveBeenCalledWith(1, expect.objectContaining({ passwordHash: 'hashed_pw' }));
    expect(resetRepo.update).toHaveBeenCalledWith(55, expect.objectContaining({ usedAt: expect.any(Date) }));
    // Invalidates all refresh tokens after password reset
    expect(refreshRepo.delete).toHaveBeenCalledWith({ userId: 1 });
  });

  it('resetPassword throws BadRequestException for already-used token', async () => {
    const usedRecord = {
      id: 55,
      tokenHash: HASH_OF_UUID,
      expiresAt: FUTURE_DATE,
      usedAt: new Date(),
      userId: 1,
    };
    service = makeService({ resetRepo: makeResetTokenRepo(usedRecord) });
    await expect(service.resetPassword('uuid-refresh-token', 'NewPass123!')).rejects.toThrow(BadRequestException);
  });

  it('resetPassword throws BadRequestException for expired token', async () => {
    const expiredRecord = {
      id: 55,
      tokenHash: HASH_OF_UUID,
      expiresAt: PAST_DATE,
      usedAt: null,
      userId: 1,
    };
    service = makeService({ resetRepo: makeResetTokenRepo(expiredRecord) });
    await expect(service.resetPassword('uuid-refresh-token', 'NewPass123!')).rejects.toThrow(BadRequestException);
  });

  it('resetPassword throws BadRequestException for password too short', async () => {
    await expect(service.resetPassword('uuid-refresh-token', 'short')).rejects.toThrow(BadRequestException);
  });
});
