import { UnauthorizedException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { JwtAuthGuard } from './jwt-auth.guard';

function makeJwtService(payload: any = { sub: 1 }) {
  return {
    verifyAsync: jest.fn().mockResolvedValue(payload),
  } as any;
}

function makeContext(
  opts: {
    isPublic?: boolean;
    authHeader?: string;
    cookie?: string;
  } = {},
): any {
  const request: any = {
    headers: {},
    cookies: {},
  };
  if (opts.authHeader) request.headers.authorization = opts.authHeader;
  if (opts.cookie) request.cookies['access_token'] = opts.cookie;

  return {
    getHandler: jest.fn().mockReturnValue({}),
    getClass: jest.fn().mockReturnValue({}),
    switchToHttp: jest
      .fn()
      .mockReturnValue({ getRequest: jest.fn().mockReturnValue(request) }),
    _request: request,
  };
}

describe('JwtAuthGuard', () => {
  let guard: JwtAuthGuard;
  let reflector: Reflector;
  let jwtService: ReturnType<typeof makeJwtService>;

  const OLD_ENV = process.env;

  beforeEach(() => {
    process.env = { ...OLD_ENV, JWT_SECRET: 'test-secret' };
    reflector = new Reflector();
    jwtService = makeJwtService();
    guard = new JwtAuthGuard(jwtService, reflector);
  });

  afterEach(() => {
    process.env = OLD_ENV;
  });

  it('allows public routes without token', async () => {
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(true);
    const ctx = makeContext();
    await expect(guard.canActivate(ctx)).resolves.toBe(true);
  });

  it('throws UnauthorizedException when no token provided', async () => {
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
    const ctx = makeContext();
    await expect(guard.canActivate(ctx)).rejects.toThrow(UnauthorizedException);
  });

  it('throws UnauthorizedException when JWT_SECRET is missing', async () => {
    process.env.JWT_SECRET = '';
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
    const ctx = makeContext({ authHeader: 'Bearer sometoken' });
    await expect(guard.canActivate(ctx)).rejects.toThrow(UnauthorizedException);
  });

  it('throws UnauthorizedException when token is invalid', async () => {
    jwtService.verifyAsync.mockRejectedValue(new Error('invalid'));
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
    const ctx = makeContext({ authHeader: 'Bearer bad-token' });
    await expect(guard.canActivate(ctx)).rejects.toThrow(UnauthorizedException);
  });

  it('returns true and sets user on request with valid Bearer token', async () => {
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
    const ctx = makeContext({ authHeader: 'Bearer valid-token' });
    const result = await guard.canActivate(ctx);
    expect(result).toBe(true);
    const req = ctx.switchToHttp().getRequest();
    expect(req.user).toEqual({ sub: 1 });
  });

  it('accepts token from cookie when no Authorization header', async () => {
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
    const ctx = makeContext({ cookie: 'cookie-token' });
    const result = await guard.canActivate(ctx);
    expect(result).toBe(true);
    expect(jwtService.verifyAsync).toHaveBeenCalledWith(
      'cookie-token',
      expect.any(Object),
    );
  });

  it('ignores non-Bearer Authorization header', async () => {
    jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
    const ctx = makeContext({ authHeader: 'Basic sometoken' });
    await expect(guard.canActivate(ctx)).rejects.toThrow(UnauthorizedException);
  });
});
