import { OptimizationGateway } from './optimization.gateway';

describe('OptimizationGateway', () => {
  const originalJwtSecret = process.env.JWT_SECRET;

  let gateway: OptimizationGateway;
  let logger: {
    warn: jest.Mock;
    debug: jest.Mock;
    error: jest.Mock;
    log: jest.Mock;
  };

  beforeEach(() => {
    process.env.JWT_SECRET = 'test-secret';
    gateway = new OptimizationGateway({ verify: jest.fn() } as any);
    logger = {
      warn: jest.fn(),
      debug: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };
    (gateway as any).logger = logger;
  });

  afterEach(() => {
    if (originalJwtSecret === undefined) {
      delete process.env.JWT_SECRET;
    } else {
      process.env.JWT_SECRET = originalJwtSecret;
    }
    jest.restoreAllMocks();
  });

  it('emite warning apenas na primeira conexao anonima dentro da janela de throttle', () => {
    jest.spyOn(Date, 'now').mockReturnValue(1000);

    const firstClient = createAnonymousClient('anon-1', 'http://localhost:3000');
    gateway.handleConnection(firstClient as any);

    expect(logger.warn).toHaveBeenCalledTimes(1);
    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('Novas ocorrências em 60s seguirão em debug.'),
    );
    expect(firstClient.disconnect).toHaveBeenCalledWith(true);

    const secondClient = createAnonymousClient('anon-2', 'http://localhost:3000');
    gateway.handleConnection(secondClient as any);

    expect(logger.warn).toHaveBeenCalledTimes(1);
    expect(logger.debug).toHaveBeenCalledTimes(1);
    expect(logger.debug).toHaveBeenCalledWith(
      expect.stringContaining('Socket anon-2 sem token'),
    );
    expect(secondClient.disconnect).toHaveBeenCalledWith(true);
  });

  it('volta a emitir warning apos a janela de throttle expirar', () => {
    const nowSpy = jest.spyOn(Date, 'now');
    nowSpy.mockReturnValue(1000);
    gateway.handleConnection(createAnonymousClient('anon-1') as any);

    nowSpy.mockReturnValue(61_001);
    gateway.handleConnection(createAnonymousClient('anon-2') as any);

    expect(logger.warn).toHaveBeenCalledTimes(2);
    expect(logger.debug).not.toHaveBeenCalled();
  });
});

function createAnonymousClient(id: string, origin = 'http://127.0.0.1:3005') {
  return {
    id,
    handshake: {
      headers: { origin },
      address: '127.0.0.1',
      auth: undefined,
    },
    disconnect: jest.fn(),
  };
}