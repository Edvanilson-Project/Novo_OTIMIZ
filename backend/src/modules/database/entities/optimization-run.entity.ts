import { Column, Entity, Index, ManyToOne, JoinColumn } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';
import { Schedule } from './schedule.entity';

export enum OptimizationRunStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

@Entity('optimization_runs')
@Index(['companyId', 'baselineScheduleId', 'scenarioId', 'inputFingerprint'])
export class OptimizationRun extends TenantBaseEntity {
  @Column({ type: 'varchar', length: 64 })
  scenarioId: string;

  @Column({ type: 'integer', nullable: true })
  baselineScheduleId: number | null;

  @ManyToOne(() => Schedule, { nullable: true, onDelete: 'SET NULL' })
  @JoinColumn({ name: 'baselineScheduleId' })
  baselineSchedule: Schedule | null;

  @Column({ type: 'integer', nullable: true })
  resultScheduleId: number | null;

  @ManyToOne(() => Schedule, { nullable: true, onDelete: 'CASCADE' })
  @JoinColumn({ name: 'resultScheduleId' })
  resultSchedule: Schedule | null;

  @Column({ type: 'varchar', length: 64 })
  inputFingerprint: string;

  @Column({ type: 'jsonb' })
  params: Record<string, any>;

  @Column({ type: 'varchar', length: 64, nullable: true })
  algorithm: string | null;

  @Column({ type: 'integer', nullable: true })
  randomSeed: number | null;

  @Column({
    type: 'enum',
    enum: OptimizationRunStatus,
    default: OptimizationRunStatus.PENDING,
  })
  status: OptimizationRunStatus;

  @Column({ type: 'jsonb', nullable: true })
  metrics: Record<string, any> | null;

  @Column({ type: 'text', nullable: true })
  errorMessage: string | null;

  @Column({ type: 'integer', nullable: true })
  durationMs: number | null;

  @Column({ type: 'timestamp', nullable: true })
  completedAt: Date | null;
}
