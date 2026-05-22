import {
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Param,
  Body,
  ParseIntPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
  Req,
  Res,
} from '@nestjs/common';
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiBearerAuth,
} from '@nestjs/swagger';
import * as express from 'express';
import { UsersService } from './users.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { Roles } from '../../common/decorators/roles.decorator';
import { UserRole } from '../database/entities/user.entity';

@ApiTags('users')
@ApiBearerAuth('JWT')
@Controller('users')
@UseGuards(JwtAuthGuard)
export class UsersController {
  constructor(private readonly service: UsersService) {}

  @Get()
  @ApiOperation({ summary: 'Listar usuários da empresa' })
  findAll() {
    return this.service.findAll();
  }

  @Get(':id')
  @ApiOperation({ summary: 'Buscar usuário por ID' })
  findOne(@Param('id', ParseIntPipe) id: number) {
    return this.service.findOne(id);
  }

  @Post()
  @Roles(UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN)
  @ApiOperation({ summary: 'Criar usuário' })
  @ApiResponse({ status: 409, description: 'E-mail já cadastrado.' })
  create(@Body() body: Record<string, unknown>) {
    return this.service.create(body);
  }

  @Patch(':id')
  @Roles(UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN)
  @ApiOperation({ summary: 'Atualizar usuário' })
  update(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: Record<string, unknown>,
  ) {
    return this.service.update(id, body);
  }

  @Delete(':id')
  @Roles(UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN)
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Remover usuário' })
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.service.remove(id);
  }

  // ── LGPD / Privacy endpoints ────────────────────────────────────────────────

  @Get('me/data-export')
  @ApiOperation({
    summary: 'Exportar meus dados pessoais (LGPD Art. 18 §2)',
    description: 'Retorna JSON com todos os dados pessoais do usuário autenticado.',
  })
  @ApiResponse({ status: 200, description: 'Dados pessoais exportados.' })
  async exportMyData(@Req() req: express.Request) {
    const authUser = (req as express.Request & { user?: { sub?: number; id?: number } }).user;
    const userId = authUser?.sub ?? authUser?.id;
    if (userId === undefined) throw new Error('Unauthorized');
    return this.service.exportMyData(userId);
  }

  @Delete('me')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({
    summary: 'Solicitar anonimização de conta (LGPD Art. 18 §6)',
    description: 'Anonimiza dados pessoais identificáveis. Registros de auditoria são mantidos (obrigação legal).',
  })
  @ApiResponse({ status: 200, description: 'Conta anonimizada com sucesso.' })
  async anonymizeMyAccount(@Req() req: express.Request, @Res({ passthrough: true }) res: express.Response) {
    const authUser = (req as express.Request & { user?: { sub?: number; id?: number } }).user;
    const userId = authUser?.sub ?? authUser?.id;
    if (userId === undefined) throw new Error('Unauthorized');
    await this.service.anonymizeAccount(userId);
    // Clear auth cookies since account is now deactivated
    res.clearCookie('access_token');
    res.clearCookie('refresh_token', { path: '/api/v1/auth' });
    return {
      message: 'Seus dados pessoais foram anonimizados. Sua sessão foi encerrada.',
    };
  }
}
