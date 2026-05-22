import {
  Controller,
  Get,
  Query,
  UseGuards,
  BadRequestException,
} from '@nestjs/common';
import { AuditService } from './audit.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { TenantContext } from '../../common/context/tenant-context';
import { Roles } from '../../common/decorators/roles.decorator';
import { UserRole } from '../database/entities/user.entity';

@Controller('audit')
@UseGuards(JwtAuthGuard)
@Roles(UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN)
export class AuditController {
  constructor(
    private readonly auditService: AuditService,
    private readonly tenantContext: TenantContext,
  ) {}

  @Get()
  find(
    @Query('entity') entity?: string,
    @Query('days') days?: string,
    @Query('page') page?: string,
    @Query('limit') limit?: string,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada.');
    return this.auditService.findByCompany(companyId, {
      entity,
      days: days ? +days : 30,
      page: page ? +page : 1,
      limit: limit ? +limit : 50,
    });
  }
}
