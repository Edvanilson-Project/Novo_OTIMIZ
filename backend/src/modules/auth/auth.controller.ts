import { Controller, Post, Body, Res } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { ApiTags, ApiOperation, ApiResponse, ApiBody } from '@nestjs/swagger';
import * as express from 'express';
import { AuthService } from './auth.service';
import { Public } from '../../common/decorators/roles.decorator';

@ApiTags('auth')
@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  @Public()
  @Post('login')
  @Throttle({ short: { ttl: 60_000, limit: 10 } })
  @ApiOperation({
    summary: 'Autenticar usuário',
    description: 'Retorna JWT e define cookie HttpOnly.',
  })
  @ApiBody({
    schema: { example: { email: 'admin@empresa.com', password: 'admin123' } },
  })
  @ApiResponse({
    status: 200,
    description:
      'Login bem-sucedido — retorna access_token e dados do usuário.',
  })
  @ApiResponse({ status: 401, description: 'Credenciais inválidas.' })
  async login(
    @Body() body: any,
    @Res({ passthrough: true }) response: express.Response,
  ) {
    const result = await this.authService.login(body.email, body.password);

    // Configuração do Cookie Seguro (Regra 1.4)
    response.cookie('access_token', result.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 1000 * 60 * 60 * 24, // 1 dia
    });

    return {
      message: 'Login realizado com sucesso',
      access_token: result.access_token,
      user: result.user,
    };
  }

  @Public()
  @Post('logout')
  @ApiOperation({
    summary: 'Encerrar sessão',
    description: 'Limpa o cookie de autenticação.',
  })
  @ApiResponse({ status: 200, description: 'Logout realizado.' })
  logout(@Res({ passthrough: true }) response: express.Response) {
    response.clearCookie('access_token');
    return { message: 'Logout realizado com sucesso' };
  }
}
