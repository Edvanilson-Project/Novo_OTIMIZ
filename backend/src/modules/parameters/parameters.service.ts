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
    const companyId = this.tenantContext.getCompanyId();
    const params = await this.parametersRepository.findOne({ where: { companyId } });
    if (!params) {
      // Se não houver, criamos o padrão para o tenant
      return this.createDefaultParameters();
    }
    return params;
  }

  async updateParameters(updateData: Partial<CompanyParameters>): Promise<CompanyParameters> {
    const companyId = this.tenantContext.getCompanyId();
    let params = await this.parametersRepository.findOne({ where: { companyId } });
    
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
      allow_vehicle_swap: false,
      max_driving_time_minutes: 480,
      meal_break_minutes: 60,
      vehicle_fixed_cost: 800.0,
      enforce_trip_groups_hard: true,
      operator_pairing_hard: true,
      operator_single_vehicle_only: true,
      operator_change_terminals_only: true,
      allow_relief_points: false,
      enforce_same_depot_start_end: false,
      enforce_single_line_duty: false,
      apply_cct: true,
      strict_hard_validation: true,
      strict_union_rules: true,
      preserve_preferred_pairs: true,
      cct_violation_penalty: 500.0,
      trip_group_keep_bonus: 240.0,
      algorithm_preference: 'hybrid_pipeline',
      ilp_timeout_seconds: 120,
    });

    return this.parametersRepository.save(newParams);
  }
}
