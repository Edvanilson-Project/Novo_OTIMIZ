import { Test, TestingModule } from '@nestjs/testing';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';

describe('AuthController', () => {
  let controller: AuthController;
  let service: jest.Mocked<Partial<AuthService>>;

  const mockResponse = () => {
    const res: any = {};
    res.cookie = jest.fn().mockReturnValue(res);
    res.clearCookie = jest.fn().mockReturnValue(res);
    return res;
  };

  beforeEach(async () => {
    service = {
      login: jest.fn().mockResolvedValue({
        access_token: 'tok123',
        user: { id: 1, email: 'a@b.com' },
      }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [AuthController],
      providers: [{ provide: AuthService, useValue: service }],
    }).compile();

    controller = module.get(AuthController);
  });

  it('login calls authService and returns token + user', async () => {
    const res = mockResponse();
    const result = await controller.login(
      { email: 'a@b.com', password: 'pass' },
      res,
    );
    expect(service.login).toHaveBeenCalledWith('a@b.com', 'pass');
    expect(result).toMatchObject({ access_token: 'tok123', user: { id: 1 } });
    expect(result.message).toBe('Login realizado com sucesso');
  });

  it('login sets httpOnly cookie', async () => {
    const res = mockResponse();
    await controller.login({ email: 'a@b.com', password: 'pass' }, res);
    expect(res.cookie).toHaveBeenCalledWith(
      'access_token',
      'tok123',
      expect.objectContaining({ httpOnly: true }),
    );
  });

  it('logout clears cookie and returns message', () => {
    const res = mockResponse();
    const result = controller.logout(res);
    expect(res.clearCookie).toHaveBeenCalledWith('access_token');
    expect(result).toMatchObject({ message: 'Logout realizado com sucesso' });
  });
});
