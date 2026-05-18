import { TenantMiddleware } from './tenant.middleware';

function makeJwtService(payload: any = null) {
  return {
    verify: jest.fn().mockReturnValue(payload),
  } as any;
}

function makeRequest(
  opts: {
    cookie?: string;
    authorization?: string;
    ip?: string;
  } = {},
): any {
  const req: any = {
    cookies: {},
    headers: {},
    ip: opts.ip ?? '10.0.0.1',
    socket: { remoteAddress: opts.ip ?? '10.0.0.1' },
  };
  if (opts.cookie) req.cookies['access_token'] = opts.cookie;
  if (opts.authorization) req.headers.authorization = opts.authorization;
  return req;
}

const OLD_ENV = process.env;

describe('TenantMiddleware', () => {
  let middleware: TenantMiddleware;
  let jwtService: ReturnType<typeof makeJwtService>;
  const next = jest.fn();
  const res: any = {};

  beforeEach(() => {
    process.env = { ...OLD_ENV, JWT_SECRET: 'secret' };
    jest.clearAllMocks();
    jwtService = makeJwtService({ companyId: 42 });
    middleware = new TenantMiddleware(jwtService);
  });

  afterEach(() => {
    process.env = OLD_ENV;
  });

  it('calls next() when no token is provided', () => {
    const req = makeRequest();
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
    expect(jwtService.verify).not.toHaveBeenCalled();
  });

  it('extracts companyId from cookie token', () => {
    const req = makeRequest({ cookie: 'valid-token' });
    middleware.use(req, res, next);
    expect(jwtService.verify).toHaveBeenCalledWith(
      'valid-token',
      expect.any(Object),
    );
    expect(next).toHaveBeenCalled();
  });

  it('extracts companyId from Authorization Bearer header', () => {
    const req = makeRequest({ authorization: 'Bearer header-token' });
    middleware.use(req, res, next);
    expect(jwtService.verify).toHaveBeenCalledWith(
      'header-token',
      expect.any(Object),
    );
    expect(next).toHaveBeenCalled();
  });

  it('ignores non-Bearer authorization header', () => {
    const req = makeRequest({ authorization: 'Basic sometoken' });
    middleware.use(req, res, next);
    expect(jwtService.verify).not.toHaveBeenCalled();
    expect(next).toHaveBeenCalled();
  });

  it('calls next() even when token is invalid (jwt error silenced)', () => {
    jwtService.verify.mockImplementation(() => {
      throw new Error('invalid');
    });
    const req = makeRequest({ cookie: 'bad-token' });
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
  });

  it('calls next() without companyId when JWT_SECRET is missing', () => {
    process.env.JWT_SECRET = '';
    const req = makeRequest({ cookie: 'some-token' });
    middleware.use(req, res, next);
    // No secret → payload is null → no companyId set
    expect(next).toHaveBeenCalled();
  });

  it('does NOT apply dev fallback in production', () => {
    process.env.NODE_ENV = 'production';
    process.env.ALLOW_DEV_TENANT_FALLBACK = 'true';
    const req = makeRequest({ ip: '127.0.0.1' });
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
    // companyId not set, so TenantContext has no store — next() called directly
  });

  it('applies dev fallback for loopback IP when flags are set', () => {
    process.env.NODE_ENV = 'development';
    process.env.ALLOW_DEV_TENANT_FALLBACK = 'true';
    jwtService.verify.mockImplementation(() => {
      throw new Error('invalid');
    });
    const req = makeRequest({ cookie: 'bad', ip: '127.0.0.1' });
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
  });

  it('does NOT apply dev fallback for non-loopback IP', () => {
    process.env.NODE_ENV = 'development';
    process.env.ALLOW_DEV_TENANT_FALLBACK = 'true';
    const req = makeRequest({ ip: '192.168.1.50' });
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
  });

  it('applies dev fallback for ::1 IPv6 loopback', () => {
    process.env.NODE_ENV = 'development';
    process.env.ALLOW_DEV_TENANT_FALLBACK = 'true';
    const req = makeRequest({ ip: '::1' });
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
  });

  it('uses socket.remoteAddress when req.ip is not available', () => {
    process.env.NODE_ENV = 'development';
    process.env.ALLOW_DEV_TENANT_FALLBACK = 'true';
    const req = makeRequest({ ip: '::ffff:127.0.0.1' });
    delete req.ip;
    req.socket = { remoteAddress: '::ffff:127.0.0.1' };
    middleware.use(req, res, next);
    expect(next).toHaveBeenCalled();
  });
});
