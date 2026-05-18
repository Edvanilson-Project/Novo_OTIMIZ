import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { Vehicle } from './vehicle.entity';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

export enum AvailabilityReason {
  MAINTENANCE = 'maintenance',
  INSPECTION = 'inspection',
  FUEL = 'fuel',
  CLEANING = 'cleaning',
  REPAIR = 'repair',
  OTHER = 'other',
}

@Entity('vehicle_availability_windows')
export class VehicleAvailabilityWindow extends TenantBaseEntity {
  @Column()
  vehicleId: number;

  @ManyToOne(() => Vehicle, (vehicle) => vehicle.availabilityWindows, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'vehicleId' })
  vehicle: Vehicle;

  @Column({ type: 'timestamp' })
  startTime: Date;

  @Column({ type: 'timestamp' })
  endTime: Date;

  @Column({
    type: 'enum',
    enum: AvailabilityReason,
    default: AvailabilityReason.OTHER,
  })
  reason: AvailabilityReason;

  @Column({ nullable: true })
  description: string;

  @Column({ default: false })
  isRecurring: boolean;

  @Column({ nullable: true })
  recurringPattern: string; // e.g., "weekly", "bi-weekly", "monthly"
}
