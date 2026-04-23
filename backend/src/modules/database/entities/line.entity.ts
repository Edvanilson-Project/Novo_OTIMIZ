import { Column, Entity } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('lines')
export class Line extends TenantBaseEntity {
  @Column()
  lineId: string;

  @Column()
  name: string;

  @Column({ nullable: true })
  description: string;

  @Column({ default: true })
  isActive: boolean;

  // ── Terminais operacionais (por sentido IDA) ──────────────────────────────
  // VOLTA usa os mesmos terminais invertidos: origin↔destination
  @Column({ nullable: true })
  originTerminalId: number; // terminal de saída IDA

  @Column({ nullable: true })
  destinationTerminalId: number; // terminal de chegada IDA

  // ── Distâncias e duração operacional ─────────────────────────────────────
  @Column({ type: 'float', nullable: true })
  distanceKm: number; // distância IDA (km)

  @Column({ type: 'float', nullable: true })
  returnDistanceKm: number; // distância VOLTA (km)

  @Column({ nullable: true })
  avgTripDurationMinutes: number; // duração média IDA (min)

  @Column({ nullable: true })
  avgReturnDurationMinutes: number; // duração média VOLTA (min)

  // ── Garagem / Soltura / Recolhimento ──────────────────────────────────────
  @Column({ nullable: true })
  garageTerminalId: number; // terminal da garagem (origem soltura / destino recolhimento)

  @Column({ type: 'float', nullable: true })
  garageDistanceKm: number; // distância garagem → primeiro terminal (soltura)

  @Column({ nullable: true })
  solturaMinutes: number; // duração trajeto garagem → primeiro terminal (min)

  @Column({ type: 'float', nullable: true })
  recolhimentoDistanceKm: number; // distância último terminal → garagem

  @Column({ nullable: true })
  recolhimentoMinutes: number; // duração trajeto último terminal → garagem (min)
}
