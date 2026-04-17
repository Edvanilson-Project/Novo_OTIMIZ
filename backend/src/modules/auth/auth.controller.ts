import { Controller, Post, Body, Res, HttpStatus } from '@nestjs/common';
import * as express from 'express';
import { AuthService } from './auth.service';

@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  @Post('login')
  async login(@Body() body: any, @Res({ passthrough: true }) response: express.Response) {
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

  @Post('logout')
  async logout(@Res({ passthrough: true }) response: express.Response) {
    response.clearCookie('access_token');
    return { message: 'Logout realizado com sucesso' };
  }
}
