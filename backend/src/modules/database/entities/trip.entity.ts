import { Entity, Column } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('trips')
export class Trip extends TenantBaseEntity {
  @Column({ nullable: true, type: 'integer' })
  tripId: number;

  @Column({ nullable: true, type: 'integer' })
  lineId: number;

  @Column({ nullable: true })
  lineCode: string;

  @Column({ nullable: true })
  pairId: string;

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

  @Column({ type: 'integer', nullable: true })
  reliefPointId: number | null;

  @Column({ type: 'boolean', default: false })
  isReliefPoint: boolean;

  @Column({ type: 'integer', nullable: true })
  midTripReliefPointId: number | null;

  @Column({ type: 'integer', nullable: true })
  midTripReliefOffsetMinutes: number | null;

  @Column({ type: 'float', nullable: true })
  midTripReliefDistanceRatio: number | null;

  @Column({ type: 'float', nullable: true })
  midTripReliefElevationRatio: number | null;

  @Column({ type: 'integer', nullable: true })
  depotId: number | null;
}
