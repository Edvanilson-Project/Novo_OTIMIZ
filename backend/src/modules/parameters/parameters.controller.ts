import { Controller, Get, Put, Body, UseGuards } from '@nestjs/common';
import { ParametersService } from './parameters.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { CompanyParameters } from '../database/entities/company-parameters.entity';

@Controller('parameters')
@UseGuards(JwtAuthGuard)
export class ParametersController {
  constructor(private readonly parametersService: ParametersService) {}

  @Get()
  async getParameters(): Promise<CompanyParameters> {
    return this.parametersService.getParameters();
  }

  @Put()
  async updateParameters(@Body() updateData: Partial<CompanyParameters>): Promise<CompanyParameters> {
    return this.parametersService.updateParameters(updateData);
  }
}
