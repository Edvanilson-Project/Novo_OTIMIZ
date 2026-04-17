import { Entity, Column } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('trips')
export class Trip extends TenantBaseEntity {
  @Column()
  tripId: number;

  @Column()
  lineId: number;

  @Column({ nullable: true })
  tripGroupId: number;

  @Column({ nullable: true })
  direction: string;

  @Column({ type: 'integer', comment: 'Minutos desde meia-noite' })
  startTime: number;

  @Column({ type: 'integer' })
  endTime: number;

  @Column()
  originId: number;

  @Column()
  destinationId: number;

  @Column({ type: 'float', default: 0 })
  distanceKm: number;

  @Column({ type: 'integer', default: 0 })
  duration: number;

  @Column({ type: 'float', nullable: true })
  originLatitude: number;

  @Column({ type: 'float', nullable: true })
  originLongitude: number;

  @Column({ type: 'float', nullable: true })
  destinationLatitude: number;

  @Column({ type: 'float', nullable: true })
  destinationLongitude: number;
}
