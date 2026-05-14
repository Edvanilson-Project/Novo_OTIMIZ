import {
  Controller,
  Post,
  Body,
  UseGuards,
  Param,
  ParseIntPipe,
  ForbiddenException,
} from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { SolutionValidatorService } from './solution-validator.service';
import { TenantContext } from '../../common/context/tenant-context';

@Controller('audits')
@UseGuards(JwtAuthGuard)
export class SolutionValidatorController {
  constructor(
    private readonly validatorService: SolutionValidatorService,
    private readonly tenantContext: TenantContext,
  ) {}

  /**
   * POST /api/v1/audits/validate
   * Valida uma solução de otimização
   *
   * Body:
   * {
   *   "blocks": [...],
   *   "duties": [...],
   *   "trips": [...],
   *   "params": { "max_shift_minutes": 600, ... }
   * }
   *
   * Response:
   * {
   *   "valid": boolean,
   *   "errorCount": number,
   *   "errors": [...],
   *   "stats": { ... }
   * }
   */
  @Post('validate')
  validate(
    @Body()
    body: {
      blocks: any[];
      duties: any[];
      trips: any[];
      params?: Record<string, any>;
    },
  ) {
    const result = this.validatorService.validate(
      body.blocks,
      body.duties,
      body.trips,
      body.params || {},
    );

    return result;
  }

  /**
   * POST /api/v1/audits/:scheduleId/validate
   * Valida um resultado de otimização salvo no banco
   */
  @Post(':scheduleId/validate')
  async validateSchedule(
    @Param('scheduleId', ParseIntPipe) scheduleId: number,
  ) {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new ForbiddenException('Empresa não identificada no contexto autenticado.');
    return this.validatorService.validateScheduleById(scheduleId, companyId);
  }
}
