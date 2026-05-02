import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleMaintenance } from '../database/entities/vehicle-maintenance.entity';
import { TenantContext } from '../../common/context/tenant-context';

export interface VehicleMetrics {
  vehicleId: number;
  vehicleLabel: string;
  healthScore: number;
  lastMaintenanceDate?: Date;
  odometer: number;
  utilizationRate: number;
  maintenanceStatus: 'good' | 'warning' | 'critical';
  estimatedCostPerDay: number;
  issues: string[];
  recommendations: string[];
}

@Injectable()
export class VehicleMetricsService {
  constructor(
    @InjectRepository(Vehicle)
    private vehicleRepo: Repository<Vehicle>,
    @InjectRepository(VehicleMaintenance)
    private maintenanceRepo: Repository<VehicleMaintenance>,
    private tenantContext: TenantContext,
  ) {}

  async getVehicleMetrics(vehicleId: number): Promise<VehicleMetrics> {
    const companyId = this.tenantContext.getCompanyId();

    const vehicle = await this.vehicleRepo.findOne({
      where: { id: vehicleId, companyId },
      relations: ['type'],
    });

    if (!vehicle) {
      throw new Error('Vehicle not found');
    }

    const maintenanceHistory = await this.maintenanceRepo.find({
      where: { vehicleId, companyId },
      order: { maintenanceDate: 'DESC' },
    });

    const lastMaintenance = maintenanceHistory[0];
    const healthScore = this.calculateHealthScore(vehicle, maintenanceHistory);
    const maintenanceStatus = this.getMaintenanceStatus(healthScore);
    const { issues, recommendations } = this.analyzeVehicleIssues(
      vehicle,
      maintenanceHistory,
      healthScore,
    );

    return {
      vehicleId: vehicle.id,
      vehicleLabel: vehicle.vehicleId,
      healthScore,
      lastMaintenanceDate: lastMaintenance?.maintenanceDate,
      odometer: vehicle.odometer || 0,
      utilizationRate: this.estimateUtilizationRate(vehicle),
      maintenanceStatus,
      estimatedCostPerDay: vehicle.type?.costPerDay || 800,
      issues,
      recommendations,
    };
  }

  async getAllVehiclesMetrics(): Promise<VehicleMetrics[]> {
    const companyId = this.tenantContext.getCompanyId();
    const vehicles = await this.vehicleRepo.find({
      where: { companyId },
      relations: ['type'],
    });

    const metrics = await Promise.all(
      vehicles.map((v) => this.getVehicleMetrics(v.id)),
    );

    return metrics;
  }

  private calculateHealthScore(
    vehicle: Vehicle,
    maintenanceHistory: VehicleMaintenance[],
  ): number {
    let score = 100;

    // Active status penalty
    if (!vehicle.isActive) {
      score -= 50;
    }

    // Maintenance recency penalty
    if (maintenanceHistory.length === 0) {
      score -= 20;
    } else {
      const lastMaint = maintenanceHistory[0].maintenanceDate;
      const daysSinceLastMaint = Math.floor(
        (new Date().getTime() - new Date(lastMaint).getTime()) / (1000 * 60 * 60 * 24),
      );

      if (daysSinceLastMaint > 180) {
        score -= 30;
      } else if (daysSinceLastMaint > 90) {
        score -= 15;
      }
    }

    // Odometer penalty
    if (vehicle.odometer) {
      if (vehicle.odometer > 500000) {
        score -= 25;
      } else if (vehicle.odometer > 300000) {
        score -= 15;
      } else if (vehicle.odometer > 150000) {
        score -= 5;
      }
    }

    return Math.max(0, Math.min(100, score));
  }

  private getMaintenanceStatus(healthScore: number): 'good' | 'warning' | 'critical' {
    if (healthScore >= 80) return 'good';
    if (healthScore >= 60) return 'warning';
    return 'critical';
  }

  private analyzeVehicleIssues(
    vehicle: Vehicle,
    maintenanceHistory: VehicleMaintenance[],
    healthScore: number,
  ): { issues: string[]; recommendations: string[] } {
    const issues: string[] = [];
    const recommendations: string[] = [];

    if (!vehicle.isActive) {
      issues.push('Veículo inativo');
    }

    if (maintenanceHistory.length === 0) {
      issues.push('Sem histórico de manutenção');
      recommendations.push('Agendar manutenção preventiva imediatamente');
    } else {
      const lastMaint = maintenanceHistory[0].maintenanceDate;
      const daysSinceLastMaint = Math.floor(
        (new Date().getTime() - new Date(lastMaint).getTime()) / (1000 * 60 * 60 * 24),
      );

      if (daysSinceLastMaint > 180) {
        issues.push(`Manutenção vencida (${daysSinceLastMaint} dias)`);
        recommendations.push('Agendar manutenção preventiva urgentemente');
      } else if (daysSinceLastMaint > 90) {
        issues.push(`Próxima manutenção em breve (${daysSinceLastMaint} dias)`);
        recommendations.push('Considerar agendar manutenção preventiva');
      }
    }

    if (vehicle.odometer) {
      if (vehicle.odometer > 500000) {
        issues.push(`Quilometragem crítica (${vehicle.odometer.toLocaleString()} km)`);
        recommendations.push('Considerar aposentadoria ou grande revisão do veículo');
      } else if (vehicle.odometer > 300000) {
        issues.push(`Quilometragem elevada (${vehicle.odometer.toLocaleString()} km)`);
        recommendations.push('Aumentar frequência de manutenções preventivas');
      }
    }

    if (healthScore < 60) {
      recommendations.push('Revisar plano de operações - veículo pode não estar confiável');
    }

    return { issues, recommendations };
  }

  private estimateUtilizationRate(vehicle: Vehicle): number {
    // Placeholder: would integrate with actual operation data
    // For now, estimate based on odometer and assumed daily km
    if (!vehicle.odometer || vehicle.odometer === 0) return 0;

    // Assume average 300 km/day
    const estimatedDays = vehicle.odometer / 300;
    const maxDays = 365 * 10; // 10 years typical vehicle life
    const utilizationRate = (estimatedDays / maxDays) * 100;

    return Math.min(100, Math.round(utilizationRate));
  }
}
