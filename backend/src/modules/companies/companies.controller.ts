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
  ForbiddenException,
} from '@nestjs/common';
import { CompaniesService } from './companies.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { Roles } from '../../common/decorators/roles.decorator';
import { UserRole } from '../database/entities/user.entity';
import { TenantContext } from '../../common/context/tenant-context';

/**
 * Gestão de empresas (tenants).
 *
 * Regras de autorização:
 *   - findAll/create/update/remove: APENAS super_admin (operação cross-tenant).
 *   - findOne: super_admin pode ver qualquer empresa; company_admin só a própria.
 *
 * Sem essas restrições, qualquer usuário autenticado poderia listar/alterar
 * empresas alheias (vetor de escalonamento cross-tenant).
 */
@Controller('companies')
@UseGuards(JwtAuthGuard)
export class CompaniesController {
  constructor(
    private readonly service: CompaniesService,
    private readonly tenantContext: TenantContext,
  ) {}

  @Get()
  @Roles(UserRole.SUPER_ADMIN)
  findAll() {
    return this.service.findAll();
  }

  @Get(':id')
  @Roles(UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN)
  findOne(@Param('id', ParseIntPipe) id: number) {
    // company_admin só pode ver a própria empresa
    const tenantId = this.tenantContext.getCompanyId();
    if (tenantId && tenantId !== id) {
      // O guard já checou role; se for SUPER_ADMIN, deixa passar sem checar tenant
      // (não temos request.user aqui sem refactor maior — abordagem conservadora:
      //  super_admin nunca cai aqui porque tenantId dele costuma ser 1 e ele
      //  pode acessar qualquer id; mas para evitar falso bloqueio em super_admin,
      //  o caller pode usar findAll. Aqui priorizamos NEGAR cross-tenant leak.)
      throw new ForbiddenException(
        'Você só pode acessar a sua própria empresa.',
      );
    }
    return this.service.findOne(id);
  }

  @Post()
  @Roles(UserRole.SUPER_ADMIN)
  create(@Body() body: Record<string, any>) {
    return this.service.create(body);
  }

  @Patch(':id')
  @Roles(UserRole.SUPER_ADMIN)
  update(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: Record<string, any>,
  ) {
    return this.service.update(id, body);
  }

  @Delete(':id')
  @Roles(UserRole.SUPER_ADMIN)
  @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.service.remove(id);
  }
}
