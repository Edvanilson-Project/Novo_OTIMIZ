import { Column, Entity, OneToMany } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';
import { Vehicle } from './vehicle.entity';

/**
 * VehicleType: Define tipos de veículos (ônibus, minibus, coach)
 * Cada tipo tem capacidade, custo e características próprias
 */
@Entity('vehicle_types')
export class VehicleType extends TenantBaseEntity {
  @Column()
  name: string; // 'BUS', 'MINIBUS', 'COACH'

  @Column({ type: 'integer' })
  capacity: number; // Capacidade de passageiros

  @Column({ type: 'float' })
  costPerDay: number; // Custo operacional diário (R$)

  @Column({ type: 'boolean', default: false })
  accessible: boolean; // Acessibilidade para pessoas com deficiência

  @Column({ type: 'text', nullable: true })
  description: string; // Descrição adicional

  @Column({ type: 'jsonb', nullable: true })
  metadata: any; // Dados adicionais (consumo, emissões, etc)

  @OneToMany(() => Vehicle, (vehicle) => vehicle.type)
  vehicles: Vehicle[];
}
