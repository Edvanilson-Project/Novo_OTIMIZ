import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import {
  VehicleMaintenance,
  MaintenanceStatus,
} from '../database/entities/vehicle-maintenance.entity';
import { VehicleAvailabilityWindow } from '../database/entities/vehicle-availability-window.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Injectable()
export class VehicleMaintenanceService {
  constructor(
    @InjectRepository(VehicleMaintenance)
    private maintenanceRepo: Repository<VehicleMaintenance>,
    @InjectRepository(VehicleAvailabilityWindow)
    private availabilityRepo: Repository<VehicleAvailabilityWindow>,
    private tenantContext: TenantContext,
  ) {}

  async scheduleMaintenance(
    vehicleId: number,
    data: Record<string, unknown>,
  ): Promise<VehicleMaintenance> {
    const companyId = this.tenantContext.getCompanyId();

    const maintenanceDate = new Date(String(data.maintenanceDate));
    if (maintenanceDate < new Date()) {
      throw new BadRequestException('Cannot schedule maintenance in the past');
    }

    const existing = await this.maintenanceRepo.findOne({
      where: {
        vehicleId,
        maintenanceDate,
        companyId,
        status: MaintenanceStatus.SCHEDULED,
      },
    });

    if (existing) {
      throw new BadRequestException(
        'Maintenance already scheduled for this date',
      );
    }

    const maintenanceData: Partial<VehicleMaintenance> = {
      vehicleId,
      maintenanceDate,
      maintenanceType:
        (data.maintenanceType as VehicleMaintenance['maintenanceType']) ||
        'preventive',
      estimatedDurationHours: Number(data.estimatedDurationHours ?? 4),
      cost: Number(data.cost ?? 0),
      description: data.description as string | undefined,
      notes: data.notes as string | undefined,
      status: MaintenanceStatus.SCHEDULED,
      companyId,
    };
    const maintenance = this.maintenanceRepo.create(maintenanceData);

    return this.maintenanceRepo.save(maintenance);
  }

  async getMaintenanceHistory(
    vehicleId: number,
  ): Promise<VehicleMaintenance[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.maintenanceRepo.find({
      where: { vehicleId, companyId },
      order: { maintenanceDate: 'DESC' },
    });
  }

  async getUnavailablePeriods(
    vehicleId: number,
    _startDate: Date,
    _endDate: Date,
  ): Promise<VehicleAvailabilityWindow[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.availabilityRepo.find({
      where: {
        vehicleId,
        companyId,
      },
    });
  }

  async checkVehicleAvailability(
    vehicleId: number,
    startTime: Date,
    endTime: Date,
  ): Promise<{ available: boolean; conflicts: VehicleAvailabilityWindow[] }> {
    const companyId = this.tenantContext.getCompanyId();
    const windows = await this.availabilityRepo.find({
      where: { vehicleId, companyId },
    });

    const conflicts = windows.filter((w) => {
      return !(endTime <= w.startTime || startTime >= w.endTime);
    });

    return {
      available: conflicts.length === 0,
      conflicts,
    };
  }

  async updateMaintenanceStatus(
    vehicleId: number,
    maintenanceId: number,
    status: MaintenanceStatus,
  ): Promise<VehicleMaintenance> {
    const companyId = this.tenantContext.getCompanyId();
    const maintenance = await this.maintenanceRepo.findOne({
      where: { id: maintenanceId, vehicleId, companyId },
    });

    if (!maintenance) {
      throw new NotFoundException('Maintenance record not found');
    }

    maintenance.status = status;
    return this.maintenanceRepo.save(maintenance);
  }

  async cancelMaintenance(
    vehicleId: number,
    maintenanceId: number,
  ): Promise<void> {
    const companyId = this.tenantContext.getCompanyId();
    const maintenance = await this.maintenanceRepo.findOne({
      where: { id: maintenanceId, vehicleId, companyId },
    });

    if (!maintenance) {
      throw new NotFoundException('Maintenance record not found');
    }

    if (maintenance.status === MaintenanceStatus.COMPLETED) {
      throw new BadRequestException('Cannot cancel completed maintenance');
    }

    maintenance.status = MaintenanceStatus.CANCELLED;
    await this.maintenanceRepo.save(maintenance);
  }

  async createAvailabilityWindow(
    vehicleId: number,
    data: Record<string, unknown>,
  ): Promise<VehicleAvailabilityWindow> {
    const companyId = this.tenantContext.getCompanyId();

    const windowData: Partial<VehicleAvailabilityWindow> = {
      vehicleId,
      startTime: new Date(String(data.startTime)),
      endTime: new Date(String(data.endTime)),
      reason:
        (data.reason as VehicleAvailabilityWindow['reason']) ?? undefined,
      description: data.description as string | undefined,
      isRecurring: Boolean(data.isRecurring),
      recurringPattern: data.recurringPattern as string | undefined,
      companyId,
    };
    const window = this.availabilityRepo.create(windowData);

    return this.availabilityRepo.save(window);
  }

  async deleteAvailabilityWindow(
    vehicleId: number,
    windowId: number,
  ): Promise<void> {
    const companyId = this.tenantContext.getCompanyId();
    const window = await this.availabilityRepo.findOne({
      where: { id: windowId, vehicleId, companyId },
    });

    if (!window) {
      throw new NotFoundException('Availability window not found');
    }

    await this.availabilityRepo.remove(window);
  }
}
