import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';
import { Schedule } from './schedule.entity';

@Entity('duty_assignments')
export class DutyAssignment extends TenantBaseEntity {
  @Column()
  scheduleId: number;

  @ManyToOne(() => Schedule, (schedule) => schedule.duties, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'scheduleId' })
  schedule: Schedule;

  @Column()
  dutyId: number;

  @Column({ type: 'integer', array: true })
  tripIds: number[];

  @Column({ type: 'float', default: 0 })
  cost: number;

  @Column({ type: 'jsonb', nullable: true })
  metadata: any;
}
