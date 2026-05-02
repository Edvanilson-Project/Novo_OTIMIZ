import {
  Controller,
  Post,
  Body,
  UseGuards,
  Param,
  ParseIntPipe,
} from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { SolutionValidatorService } from './solution-validator.service';

@Controller('audits')
@UseGuards(JwtAuthGuard)
export class SolutionValidatorController {
  constructor(private readonly validatorService: SolutionValidatorService) {}

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
    // TODO: Carregar resultado do banco e validar
    return {
      valid: false,
      message: 'Not yet implemented - fetch from database first',
    };
  }
}
