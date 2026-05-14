import { Column, Entity, Index } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

export enum CustomReportFormat {
  JSON = 'json',
  CSV = 'csv',
  PDF = 'pdf',
}

@Entity('custom_reports')
@Index(['companyId', 'ownerUserId'])
export class CustomReport extends TenantBaseEntity {
  @Column({ type: 'varchar', length: 200 })
  name: string;

  @Column({ type: 'text', nullable: true })
  description: string | null;

  @Column({ type: 'integer', nullable: true })
  ownerUserId: number | null;

  @Column({ type: 'jsonb' })
  metrics: string[];

  @Column({ type: 'jsonb', default: () => `'{}'::jsonb` })
  filters: Record<string, any>;

  @Column({
    type: 'enum',
    enum: CustomReportFormat,
    default: CustomReportFormat.JSON,
  })
  format: CustomReportFormat;
}
