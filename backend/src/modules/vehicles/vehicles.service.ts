import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Vehicle } from '../database/entities/vehicle.entity';
import { VehicleType } from '../database/entities/vehicle-type.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Injectable()
export class VehiclesService {
  constructor(
    @InjectRepository(Vehicle)
    private readonly vehicleRepo: Repository<Vehicle>,
    @InjectRepository(VehicleType)
    private readonly vehicleTypeRepo: Repository<VehicleType>,
    private readonly tenantContext: TenantContext,
  ) {}

  // Vehicle Type methods
  async findAllVehicleTypes(): Promise<VehicleType[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.vehicleTypeRepo.find({
      where: { companyId },
      order: { name: 'ASC' },
    });
  }

  async findOneVehicleType(id: number): Promise<VehicleType> {
    const companyId = this.tenantContext.getCompanyId();
    const type = await this.vehicleTypeRepo.findOne({
      where: { id, companyId },
    });
    if (!type)
      throw new NotFoundException(`Tipo de veículo ${id} não encontrado`);
    return type;
  }

  async createVehicleType(dto: Record<string, unknown>): Promise<VehicleType> {
    const companyId = this.tenantContext.getCompanyId();
    const entity = this.vehicleTypeRepo.create({ ...dto, companyId });
    return this.vehicleTypeRepo.save(entity);
  }

  async updateVehicleType(
    id: number,
    dto: Record<string, unknown>,
  ): Promise<VehicleType> {
    const type = await this.findOneVehicleType(id);
    Object.assign(type, dto);
    return this.vehicleTypeRepo.save(type);
  }

  async removeVehicleType(id: number): Promise<void> {
    const type = await this.findOneVehicleType(id);
    await this.vehicleTypeRepo.remove(type);
  }

  // Vehicle methods
  async findAllVehicles(): Promise<Vehicle[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.vehicleRepo.find({
      where: { companyId },
      relations: ['type', 'depot'],
      order: { vehicleId: 'ASC' },
    });
  }

  async findOneVehicle(id: number): Promise<Vehicle> {
    const companyId = this.tenantContext.getCompanyId();
    const vehicle = await this.vehicleRepo.findOne({
      where: { id, companyId },
      relations: ['type', 'depot'],
    });
    if (!vehicle) throw new NotFoundException(`Veículo ${id} não encontrado`);
    return vehicle;
  }

  async createVehicle(dto: Record<string, unknown>): Promise<Vehicle> {
    const companyId = this.tenantContext.getCompanyId();
    const entity = this.vehicleRepo.create({ ...dto, companyId });
    return this.vehicleRepo.save(entity);
  }

  async updateVehicle(id: number, dto: Record<string, unknown>): Promise<Vehicle> {
    const vehicle = await this.findOneVehicle(id);
    Object.assign(vehicle, dto);
    return this.vehicleRepo.save(vehicle);
  }

  async removeVehicle(id: number): Promise<void> {
    const vehicle = await this.findOneVehicle(id);
    await this.vehicleRepo.remove(vehicle);
  }

  async getVehiclesByType(typeId: number): Promise<Vehicle[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.vehicleRepo.find({
      where: { typeId, companyId },
      relations: ['type', 'depot'],
    });
  }

  async getActiveVehicles(): Promise<Vehicle[]> {
    const companyId = this.tenantContext.getCompanyId();
    return this.vehicleRepo.find({
      where: { companyId, isActive: true },
      relations: ['type', 'depot'],
      order: { vehicleId: 'ASC' },
    });
  }
}
