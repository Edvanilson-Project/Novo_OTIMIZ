import { Column, Entity, ManyToOne, JoinColumn, OneToMany } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';
import { VehicleType } from './vehicle-type.entity';
import { Terminal } from './terminal.entity';
import { BlockAssignment } from './block-assignment.entity';
import { VehicleMaintenance } from './vehicle-maintenance.entity';
import { VehicleAvailabilityWindow } from './vehicle-availability-window.entity';

/**
 * Vehicle: Representa um veículo individual na frota
 * Cada veículo tem um tipo, um depot de origem, e podem ter múltiplos blocos alocados
 */
@Entity('vehicles')
export class Vehicle extends TenantBaseEntity {
  @Column()
  vehicleId: string; // Identificador único do veículo (ex: "BUS-001")

  @Column()
  typeId: number; // FK para VehicleType

  @ManyToOne(() => VehicleType, (type) => type.vehicles, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'typeId' })
  type: VehicleType;

  @Column()
  depotId: number; // FK para Terminal (garagem/depot)

  @ManyToOne(() => Terminal, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'depotId' })
  depot: Terminal;

  @Column({ type: 'boolean', default: true })
  isActive: boolean; // Veículo ativo ou desativado

  @Column({ type: 'text', nullable: true })
  licensePlate: string; // Placa do veículo (opcional)

  @Column({ type: 'float', nullable: true })
  odometer: number; // Quilometragem atual (opcional)

  @Column({ type: 'timestamp', nullable: true })
  lastMaintenanceDate: Date; // Última manutenção (opcional)

  @Column({ type: 'jsonb', nullable: true })
  metadata: any; // Dados adicionais

  @OneToMany(() => BlockAssignment, (block) => block.vehicle)
  blocks: BlockAssignment[];

  @OneToMany(() => VehicleMaintenance, (maintenance) => maintenance.vehicle)
  maintenance: VehicleMaintenance[];

  @OneToMany(
    () => VehicleAvailabilityWindow,
    (window) => window.vehicle,
  )
  availabilityWindows: VehicleAvailabilityWindow[];
}
