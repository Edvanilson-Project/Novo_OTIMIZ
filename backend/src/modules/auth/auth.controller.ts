import {
  Controller,
  Post,
  Get,
  Body,
  Res,
  Req,
  UseGuards,
  UnauthorizedException,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiBody,
  ApiProperty,
} from '@nestjs/swagger';
import {
  IsEmail,
  IsString,
  MinLength,
  IsNotEmpty,
} from 'class-validator';
import * as express from 'express';
import { AuthService } from './auth.service';
import { Public } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from './jwt-auth.guard';

class LoginDto {
  @ApiProperty({ example: 'admin@empresa.com.br' })
  @IsEmail()
  email: string;

  @ApiProperty({ minLength: 6 })
  @IsString()
  @MinLength(6)
  password: string;
}

class ForgotPasswordDto {
  @ApiProperty({ example: 'usuario@empresa.com.br' })
  @IsEmail()
  email: string;
}

class ResetPasswordDto {
  @ApiProperty({ description: 'Token recebido por e-mail' })
  @IsString()
  @IsNotEmpty()
  token: string;

  @ApiProperty({ minLength: 8 })
  @IsString()
  @MinLength(8)
  newPassword: string;
}

const isProd = () => process.env.NODE_ENV === 'production';
const cookieOpts = () => ({
  httpOnly: true,
  secure: isProd(),
  sameSite: 'lax' as const,
});

@ApiTags('auth')
@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  @Public()
  @Post('login')
  @HttpCode(HttpStatus.OK)
  @Throttle({ short: { ttl: 60_000, limit: parseInt(process.env.THROTTLE_LOGIN_LIMIT ?? '10', 10) } })
  @ApiOperation({ summary: 'Autenticar usuário', description: 'Retorna JWT e define cookies HttpOnly.' })
  @ApiBody({ type: LoginDto })
  @ApiResponse({ status: 200, description: 'Login bem-sucedido.' })
  @ApiResponse({ status: 401, description: 'Credenciais inválidas.' })
  async login(
    @Body() body: LoginDto,
    @Res({ passthrough: true }) response: express.Response,
    @Req() req: express.Request,
  ) {
    const userAgent = req.headers['user-agent'];
    const result = await this.authService.login(body.email, body.password, userAgent);

    response.cookie('access_token', result.access_token, {
      ...cookieOpts(),
      maxAge: 15 * 60 * 1000,
    });
    response.cookie(AuthService.REFRESH_COOKIE, result.refresh_token, {
      ...cookieOpts(),
      maxAge: AuthService.REFRESH_TTL_MS,
      path: '/api/v1/auth',
    });

    return { message: 'Login realizado com sucesso', user: result.user };
  }

  @Public()
  @Post('refresh')
  @HttpCode(HttpStatus.OK)
  @Throttle({ short: { ttl: 60_000, limit: 20 } })
  @ApiOperation({ summary: 'Renovar access token' })
  @ApiResponse({ status: 200, description: 'Novo access_token emitido.' })
  @ApiResponse({ status: 403, description: 'Refresh token inválido ou expirado.' })
  async refresh(
    @Req() req: express.Request,
    @Res({ passthrough: true }) response: express.Response,
  ) {
    const rawRefresh = (req.cookies as Record<string, string>)?.[AuthService.REFRESH_COOKIE];
    if (!rawRefresh) throw new UnauthorizedException('Refresh token ausente');

    const userAgent = req.headers['user-agent'];
    const result = await this.authService.refresh(rawRefresh, userAgent);

    response.cookie('access_token', result.access_token, {
      ...cookieOpts(),
      maxAge: 15 * 60 * 1000,
    });
    response.cookie(AuthService.REFRESH_COOKIE, result.refresh_token, {
      ...cookieOpts(),
      maxAge: AuthService.REFRESH_TTL_MS,
      path: '/api/v1/auth',
    });

    return { message: 'Token renovado com sucesso', user: result.user };
  }

  @Get('profile')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Perfil do usuário autenticado' })
  @ApiResponse({ status: 200, description: 'Dados do usuário atual.' })
  @ApiResponse({ status: 401, description: 'Não autenticado.' })
  getProfile(@Req() req: express.Request) {
    // JwtAuthGuard preenche req.user com o payload validado
    return (req as express.Request & { user: unknown }).user;
  }

  @Public()
  @Post('logout')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Encerrar sessão' })
  @ApiResponse({ status: 200, description: 'Logout realizado.' })
  async logout(
    @Req() req: express.Request,
    @Res({ passthrough: true }) response: express.Response,
  ) {
    const rawRefresh = (req.cookies as Record<string, string>)?.[AuthService.REFRESH_COOKIE];
    await this.authService.logout(rawRefresh);
    response.clearCookie('access_token');
    response.clearCookie(AuthService.REFRESH_COOKIE, { path: '/api/v1/auth' });
    return { message: 'Logout realizado com sucesso' };
  }

  // ── Password Reset ──────────────────────────────────────────────────────

  @Public()
  @Post('forgot-password')
  @HttpCode(HttpStatus.OK)
  @Throttle({ short: { ttl: 60_000, limit: 5 } })
  @ApiOperation({
    summary: 'Solicitar redefinição de senha',
    description: 'Envia e-mail com link de redefinição. Sempre retorna 200 (não revela existência do e-mail).',
  })
  @ApiBody({ type: ForgotPasswordDto })
  @ApiResponse({ status: 200, description: 'Se o e-mail existir, instruções foram enviadas.' })
  async forgotPassword(@Body() body: ForgotPasswordDto) {
    await this.authService.forgotPassword(body.email);
    return { message: 'Se este e-mail estiver cadastrado, você receberá as instruções em breve.' };
  }

  @Public()
  @Post('reset-password')
  @HttpCode(HttpStatus.OK)
  @Throttle({ short: { ttl: 60_000, limit: 5 } })
  @ApiOperation({ summary: 'Redefinir senha com token' })
  @ApiBody({ type: ResetPasswordDto })
  @ApiResponse({ status: 200, description: 'Senha redefinida com sucesso.' })
  @ApiResponse({ status: 400, description: 'Token inválido, expirado ou senha fraca.' })
  async resetPassword(@Body() body: ResetPasswordDto) {
    await this.authService.resetPassword(body.token, body.newPassword);
    return { message: 'Senha redefinida com sucesso. Faça login com sua nova senha.' };
  }
}
