import { Injectable, NotFoundException } from '@nestjs/common';
import { CompanyParametersRepository } from '../database/repositories/company-parameters.repository';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Injectable()
export class ParametersService {
  constructor(
    private readonly parametersRepository: CompanyParametersRepository,
    private readonly tenantContext: TenantContext,
  ) {}

  async getParameters(): Promise<CompanyParameters> {
    const params = await this.parametersRepository.findOne({ where: {} });
    if (!params) {
      // Se não houver, criamos o padrão para o tenant
      return this.createDefaultParameters();
    }
    return params;
  }

  async updateParameters(updateData: Partial<CompanyParameters>): Promise<CompanyParameters> {
    let params = await this.parametersRepository.findOne({ where: {} });
    
    if (!params) {
      params = await this.createDefaultParameters();
    }

    // Remove campos que não devem ser alterados via API
    delete (updateData as any).id;
    delete (updateData as any).companyId;
    delete (updateData as any).createdAt;
    delete (updateData as any).updatedAt;

    Object.assign(params, updateData);
    return this.parametersRepository.save(params);
  }

  private async createDefaultParameters(): Promise<CompanyParameters> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new Error('Company ID not found in context');

    const newParams = this.parametersRepository.create({
      companyId,
      driver_cost_per_minute: 0.5,
      collector_cost_per_minute: 0.4,
      force_round_trip: true,
      allow_vehicle_swap: true,
      max_driving_time_minutes: 480,
      meal_break_minutes: 60,
      vehicle_fixed_cost: 800.0,
    });

    return this.parametersRepository.save(newParams);
  }
}
