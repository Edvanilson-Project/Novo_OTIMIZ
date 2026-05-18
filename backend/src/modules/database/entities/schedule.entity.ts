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

  // Cascade delete + ON DELETE CASCADE no FK garante que ao remover Schedule,
  // BlockAssignment e DutyAssignment relacionados são removidos junto. Antes,
  // delete do schedule deixava órfãos. As FKs em block_assignment e duty_assignment
  // já têm `ON DELETE CASCADE` no DB (constraints "FK_88f267..." e "FK_12551b...").
  // O `cascade` aqui sincroniza o comportamento via TypeORM repository methods.
  @OneToMany(() => BlockAssignment, (block) => block.schedule, {
    cascade: true,
  })
  blocks: BlockAssignment[];

  @OneToMany(() => DutyAssignment, (duty) => duty.schedule, { cascade: true })
  duties: DutyAssignment[];

  @Column({ type: 'float', nullable: true })
  totalCost: number;

  @Column({ type: 'integer', default: 0 })
  cctViolations: number;
}
