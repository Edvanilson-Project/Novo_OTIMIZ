import { UnauthorizedException } from '@nestjs/common';
import { AuthService } from './auth.service';

jest.mock('bcrypt', () => ({
  compare: jest.fn(),
}));
import * as bcrypt from 'bcrypt';

function makeUserRepo(user?: any) {
  return {
    findOne: jest.fn().mockResolvedValue(user ?? null),
  } as any;
}

function makeJwtService(token = 'signed_token') {
  return {
    signAsync: jest.fn().mockResolvedValue(token),
  } as any;
}

const validUser = {
  id: 1,
  email: 'admin@test.com',
  passwordHash: 'hashed',
  companyId: 16,
  name: 'Admin',
  role: 'company_admin',
};

describe('AuthService', () => {
  let service: AuthService;
  let userRepo: ReturnType<typeof makeUserRepo>;
  let jwtService: ReturnType<typeof makeJwtService>;

  beforeEach(() => {
    userRepo = makeUserRepo(validUser);
    jwtService = makeJwtService();
    service = new AuthService(userRepo, jwtService);
    (bcrypt.compare as jest.Mock).mockResolvedValue(true);
  });

  it('login returns access_token and user on valid credentials', async () => {
    const result = await service.login('admin@test.com', 'secret');
    expect(result.access_token).toBe('signed_token');
    expect(result.user.id).toBe(1);
    expect(result.user.companyId).toBe(16);
  });

  it('login throws UnauthorizedException when user not found', async () => {
    userRepo.findOne.mockResolvedValue(null);
    await expect(service.login('x@x.com', 'pass')).rejects.toThrow(
      UnauthorizedException,
    );
  });

  it('login throws UnauthorizedException when password is wrong', async () => {
    (bcrypt.compare as jest.Mock).mockResolvedValue(false);
    await expect(service.login('admin@test.com', 'wrong')).rejects.toThrow(
      UnauthorizedException,
    );
  });

  it('login calls jwtService.signAsync with correct payload', async () => {
    await service.login('admin@test.com', 'secret');
    expect(jwtService.signAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        sub: 1,
        email: 'admin@test.com',
        companyId: 16,
      }),
    );
  });
});
