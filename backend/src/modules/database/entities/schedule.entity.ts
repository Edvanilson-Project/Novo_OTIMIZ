import { Entity, Column, OneToMany } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';
import { BlockAssignment } from './block-assignment.entity';
import { DutyAssignment } from './duty-assignment.entity';

export enum ScheduleStatus {
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

@Entity('schedules')
export class Schedule extends TenantBaseEntity {
  @Column({ type: 'timestamp', default: () => 'CURRENT_TIMESTAMP' })
  referenceDate: Date;

  @Column({
    type: 'enum',
    enum: ScheduleStatus,
    default: ScheduleStatus.PROCESSING,
  })
  status: ScheduleStatus;

  @Column({ type: 'jsonb', nullable: true })
  metadata: any;

  @OneToMany(() => BlockAssignment, (block) => block.schedule)
  blocks: BlockAssignment[];

  @OneToMany(() => DutyAssignment, (duty) => duty.schedule)
  duties: DutyAssignment[];

  @Column({ type: 'float', nullable: true })
  totalCost: number;

  @Column({ type: 'integer', default: 0 })
  cctViolations: number;
}
