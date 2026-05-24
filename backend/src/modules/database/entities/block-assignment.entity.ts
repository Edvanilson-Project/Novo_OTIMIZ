import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';
import { Schedule } from './schedule.entity';
import { Vehicle } from './vehicle.entity';

@Entity('block_assignments')
export class BlockAssignment extends TenantBaseEntity {
  @Column()
  scheduleId: number;

  @ManyToOne(() => Schedule, (schedule) => schedule.blocks, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'scheduleId' })
  schedule: Schedule;

  @Column({ nullable: true })
  vehicleId: number | null; // FK para Vehicle

  @ManyToOne(() => Vehicle, (vehicle) => vehicle.blocks, {
    onDelete: 'SET NULL',
  })
  @JoinColumn({ name: 'vehicleId' })
  vehicle: Vehicle;

  @Column()
  blockId: number; // ID sequencial do bloco na otimização (Block 1, Block 2, ...)

  @Column({ type: 'integer', array: true })
  tripIds: number[];

  @Column({ type: 'float', default: 0 })
  cost: number;

  @Column({ type: 'jsonb', nullable: true })
  metadata: any;
}
