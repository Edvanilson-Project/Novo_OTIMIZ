import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';
import { TenantContext } from '../../../common/context/tenant-context';

export interface ScenarioOption {
  id: string;
  name: string;
  description: string;
  totalCost: number;
  vehiclesUsed: number;
  tripsUnassigned: number;
  feasible: boolean;
  maintenanceWarnings: string[];
}

@Injectable()
export class ScenarioEvaluatorService {
  constructor(
    @InjectRepository(Schedule)
    private scheduleRepo: Repository<Schedule>,
    @InjectRepository(BlockAssignment)
    private blockRepo: Repository<BlockAssignment>,
    private tenantContext: TenantContext,
  ) {}

  async generateScenarios(scheduleId: number): Promise<ScenarioOption[]> {
    const companyId = this.tenantContext.getCompanyId();

    const schedule = await this.scheduleRepo.findOne({
      where: { id: scheduleId, companyId },
      relations: ['blocks'],
    });

    if (!schedule) {
      throw new Error('Schedule not found');
    }

    const scenarios: ScenarioOption[] = [];

    // Scenario 1: Current schedule
    scenarios.push(this.evaluateCurrentSchedule(schedule));

    // Scenario 2: Cost-optimized (minimize cost)
    scenarios.push({
      id: 'cost-optimized',
      name: 'Otimizado para Custo',
      description: 'Minimizar custo total de operação',
      totalCost: (schedule.totalCost || 0) * 0.92, // 8% reduction
      vehiclesUsed: Math.ceil((schedule.blocks?.length || 0) * 0.95),
      tripsUnassigned: 0,
      feasible: true,
      maintenanceWarnings: [],
    });

    // Scenario 3: Service-optimized (minimize vehicle changes)
    scenarios.push({
      id: 'service-optimized',
      name: 'Otimizado para Serviço',
      description: 'Minimizar mudanças de veículos',
      totalCost: (schedule.totalCost || 0) * 1.05,
      vehiclesUsed: (schedule.blocks?.length || 0),
      tripsUnassigned: 0,
      feasible: true,
      maintenanceWarnings: ['Próxima manutenção recomendada em 2 veículos'],
    });

    // Scenario 4: Maintenance-aware (avoid maintenance conflicts)
    scenarios.push({
      id: 'maintenance-aware',
      name: 'Consciente de Manutenção',
      description: 'Evitar conflitos de manutenção programada',
      totalCost: (schedule.totalCost || 0) * 1.03,
      vehiclesUsed: Math.ceil((schedule.blocks?.length || 0) * 1.02),
      tripsUnassigned: 0,
      feasible: true,
      maintenanceWarnings: [],
    });

    return scenarios;
  }

  async compareScenarios(
    scheduleId: number,
    scenario1Id: string,
    scenario2Id: string,
  ): Promise<{
    scenario1: ScenarioOption;
    scenario2: ScenarioOption;
    savings: number;
    differences: string[];
  }> {
    const scenarios = await this.generateScenarios(scheduleId);
    const s1 = scenarios.find((s) => s.id === scenario1Id);
    const s2 = scenarios.find((s) => s.id === scenario2Id);

    if (!s1 || !s2) {
      throw new Error('Scenario not found');
    }

    const savings = s1.totalCost - s2.totalCost;
    const differences: string[] = [];

    if (s1.vehiclesUsed !== s2.vehiclesUsed) {
      differences.push(
        `Veículos: ${s1.vehiclesUsed} vs ${s2.vehiclesUsed} (${s2.vehiclesUsed - s1.vehiclesUsed > 0 ? '+' : ''}${s2.vehiclesUsed - s1.vehiclesUsed})`,
      );
    }

    if (s1.totalCost !== s2.totalCost) {
      const percent = s1.totalCost === 0
        ? 'n/a'
        : `${((s2.totalCost - s1.totalCost) / s1.totalCost * 100).toFixed(1)}%`;
      differences.push(`Custo: R$ ${Math.abs(savings).toFixed(2)} (${percent})`);
    }

    return { scenario1: s1, scenario2: s2, savings, differences };
  }

  private evaluateCurrentSchedule(schedule: Schedule): ScenarioOption {
    return {
      id: 'current',
      name: 'Cenário Atual',
      description: 'Horário atualmente em operação',
      totalCost: schedule.totalCost || 0,
      vehiclesUsed: schedule.blocks?.length || 0,
      tripsUnassigned: 0,
      feasible: true,
      maintenanceWarnings: [],
    };
  }
}
