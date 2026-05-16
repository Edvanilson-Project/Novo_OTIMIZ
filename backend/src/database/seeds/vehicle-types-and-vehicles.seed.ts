import { DataSource } from 'typeorm';
import { VehicleType } from '../../modules/database/entities/vehicle-type.entity';
import { Vehicle } from '../../modules/database/entities/vehicle.entity';
import { Terminal } from '../../modules/database/entities/terminal.entity';

export async function seedVehiclesData(dataSource: DataSource) {
  const vehicleTypeRepository = dataSource.getRepository(VehicleType);
  const vehicleRepository = dataSource.getRepository(Vehicle);
  const terminalRepository = dataSource.getRepository(Terminal);

  // Seed Terminals/Depots for Company 1
  const mainDepot = await terminalRepository.save({
    terminalId: 'GARAGEM-CENTRAL',
    name: 'Garagem Central',
    city: 'Salvador',
    latitude: -12.9714,
    longitude: -38.5014,
    isDepot: true,
    companyId: 1,
  });

  const northDepot = await terminalRepository.save({
    terminalId: 'GARAGEM-NORTE',
    name: 'Garagem Norte',
    city: 'Salvador',
    latitude: -12.9100,
    longitude: -38.4800,
    isDepot: true,
    companyId: 1,
  });

  await terminalRepository.save([
    { terminalId: 'TER-CENTRO', name: 'Terminal Centro', city: 'Salvador', latitude: -12.9777, longitude: -38.5016, isDepot: false, companyId: 1 },
    { terminalId: 'TER-BARRA', name: 'Terminal Barra', city: 'Salvador', latitude: -13.0078, longitude: -38.5321, isDepot: false, companyId: 1 },
    { terminalId: 'TER-IGUATEMI', name: 'Terminal Iguatemi', city: 'Salvador', latitude: -12.9855, longitude: -38.4524, isDepot: false, companyId: 1 },
  ]);

  // Seed Vehicle Types for Company 1
  const busType = await vehicleTypeRepository.save({
    name: 'BUS',
    capacity: 60,
    costPerDay: 450,
    accessible: true,
    description: 'Standard city bus with 60 passenger capacity',
    companyId: 1,
  });

  const minibuslType = await vehicleTypeRepository.save({
    name: 'MINIBUS',
    capacity: 20,
    costPerDay: 250,
    accessible: true,
    description: 'Minibus with 20 passenger capacity',
    companyId: 1,
  });

  const coachType = await vehicleTypeRepository.save({
    name: 'COACH',
    capacity: 50,
    costPerDay: 400,
    accessible: false,
    description: 'Long-distance coach with 50 passenger capacity',
    companyId: 1,
  });

  // Seed Vehicles for Company 1 — split between 2 real depots
  const vehicles = [
    {
      vehicleId: 'BUS-001', typeId: busType.id, depotId: mainDepot.id, isActive: true,
      licensePlate: 'ABC-1234', odometer: 120000, lastMaintenanceDate: new Date('2026-04-01'),
      companyId: 1, metadata: { fuelType: 'diesel', emission: 'Euro6' },
    },
    {
      vehicleId: 'BUS-002', typeId: busType.id, depotId: mainDepot.id, isActive: true,
      licensePlate: 'ABC-1235', odometer: 115000, lastMaintenanceDate: new Date('2026-03-15'),
      companyId: 1, metadata: { fuelType: 'diesel', emission: 'Euro6' },
    },
    {
      vehicleId: 'MINIBUS-001', typeId: minibuslType.id, depotId: northDepot.id, isActive: true,
      licensePlate: 'ABC-2001', odometer: 80000, lastMaintenanceDate: new Date('2026-04-10'),
      companyId: 1, metadata: { fuelType: 'gasoline', emission: 'Euro6' },
    },
    {
      vehicleId: 'COACH-001', typeId: coachType.id, depotId: northDepot.id, isActive: true,
      licensePlate: 'ABC-3001', odometer: 250000, lastMaintenanceDate: new Date('2026-03-01'),
      companyId: 1, metadata: { fuelType: 'diesel', emission: 'Euro5' },
    },
  ];

  await vehicleRepository.save(vehicles);

  console.log('✓ Terminals, vehicle types, and vehicles seeded successfully');
  console.log(`  - Created 5 terminals (2 depots + 3 stops)`);
  console.log(`  - Created 3 vehicle types`);
  console.log(`  - Created ${vehicles.length} vehicles across 2 depots`);
}
