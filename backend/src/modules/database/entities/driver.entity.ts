import { Entity, Column } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('drivers')
export class Driver extends TenantBaseEntity {
  @Column()
  driverId: string;

  @Column()
  name: string;

  @Column({ nullable: true })
  role: string;

  @Column({ type: 'integer', default: 480 })
  maxHoursPerDay: number;

  @Column({ type: 'integer', default: 0 })
  lastShiftEnd: number;

  @Column({ type: 'jsonb', nullable: true })
  metadata: any;
}
