import { Column, Entity } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('terminals')
export class Terminal extends TenantBaseEntity {
  @Column()
  terminalId: string;

  @Column()
  name: string;

  @Column({ nullable: true })
  city: string;

  @Column({ type: 'float', nullable: true })
  latitude: number;

  @Column({ type: 'float', nullable: true })
  longitude: number;
}
