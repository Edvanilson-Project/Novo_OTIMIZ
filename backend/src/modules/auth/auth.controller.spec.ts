import { Test, TestingModule } from '@nestjs/testing';
import { UnauthorizedException } from '@nestjs/common';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import { JwtAuthGuard } from './jwt-auth.guard';

describe('AuthController', () => {
  let controller: AuthController;
  let service: jest.Mocked<Partial<AuthService>>;

  const mockResponse = () => {
    const res: any = {};
    res.cookie = jest.fn().mockReturnValue(res);
    res.clearCookie = jest.fn().mockReturnValue(res);
    return res;
  };

  const mockRequest = (cookies: Record<string, string> = {}, ua = 'jest-agent') =>
    ({ cookies, headers: { 'user-agent': ua } } as any);

  beforeEach(async () => {
    service = {
      login: jest.fn().mockResolvedValue({
        access_token: 'tok123',
        refresh_token: 'ref456',
        user: { id: 1, name: 'Test', companyId: 1, role: 'company_admin' },
      }),
      refresh: jest.fn().mockResolvedValue({
        access_token: 'new_tok',
        refresh_token: 'new_ref',
        user: { id: 1, name: 'Test', companyId: 1, role: 'company_admin' },
      }),
      logout: jest.fn().mockResolvedValue(undefined),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [AuthController],
      providers: [{ provide: AuthService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(AuthController);
  });

  // ── login ────────────────────────────────────────────────────────────────

  it('login calls authService and returns user (no token in body)', async () => {
    const res = mockResponse();
    const req = mockRequest();
    const result = await controller.login({ email: 'a@b.com', password: 'pass123' }, res, req);
    expect(service.login).toHaveBeenCalledWith('a@b.com', 'pass123', 'jest-agent');
    expect(result).toMatchObject({ user: { id: 1 }, message: 'Login realizado com sucesso' });
    expect((result as any).access_token).toBeUndefined();
  });

  it('login sets access_token httpOnly cookie with 15min maxAge', async () => {
    const res = mockResponse();
    const req = mockRequest();
    await controller.login({ email: 'a@b.com', password: 'pass123' }, res, req);
    expect(res.cookie).toHaveBeenCalledWith(
      'access_token',
      'tok123',
      expect.objectContaining({ httpOnly: true, maxAge: 15 * 60 * 1000 }),
    );
  });

  it('login sets refresh_token httpOnly cookie with 7-day maxAge', async () => {
    const res = mockResponse();
    const req = mockRequest();
    await controller.login({ email: 'a@b.com', password: 'pass123' }, res, req);
    expect(res.cookie).toHaveBeenCalledWith(
      AuthService.REFRESH_COOKIE,
      'ref456',
      expect.objectContaining({ httpOnly: true, maxAge: AuthService.REFRESH_TTL_MS }),
    );
  });

  // ── refresh ──────────────────────────────────────────────────────────────

  it('refresh calls authService.refresh with cookie value', async () => {
    const req = mockRequest({ [AuthService.REFRESH_COOKIE]: 'my-refresh-token' });
    const res = mockResponse();
    const result = await controller.refresh(req, res);
    expect(service.refresh).toHaveBeenCalledWith('my-refresh-token', 'jest-agent');
    expect(result).toMatchObject({ message: 'Token renovado com sucesso' });
  });

  it('refresh sets new cookies', async () => {
    const req = mockRequest({ [AuthService.REFRESH_COOKIE]: 'my-refresh-token' });
    const res = mockResponse();
    await controller.refresh(req, res);
    expect(res.cookie).toHaveBeenCalledWith('access_token', 'new_tok', expect.any(Object));
    expect(res.cookie).toHaveBeenCalledWith(AuthService.REFRESH_COOKIE, 'new_ref', expect.any(Object));
  });

  it('refresh throws UnauthorizedException when no cookie present', async () => {
    const req = mockRequest({});
    const res = mockResponse();
    await expect(controller.refresh(req, res)).rejects.toThrow(UnauthorizedException);
  });

  // ── logout ───────────────────────────────────────────────────────────────

  it('logout calls authService.logout and clears both cookies', async () => {
    const req = mockRequest({ [AuthService.REFRESH_COOKIE]: 'ref123' });
    const res = mockResponse();
    const result = await controller.logout(req, res);
    expect(service.logout).toHaveBeenCalledWith('ref123');
    expect(res.clearCookie).toHaveBeenCalledWith('access_token');
    expect(res.clearCookie).toHaveBeenCalledWith(AuthService.REFRESH_COOKIE, expect.any(Object));
    expect(result).toMatchObject({ message: 'Logout realizado com sucesso' });
  });

  it('logout works even without refresh cookie in request', async () => {
    const req = mockRequest({});
    const res = mockResponse();
    await expect(controller.logout(req, res)).resolves.toMatchObject({ message: 'Logout realizado com sucesso' });
  });
});
