import { DataSource } from 'typeorm';
import { VehicleType } from '../../modules/database/entities/vehicle-type.entity';
import { Vehicle } from '../../modules/database/entities/vehicle.entity';

export async function seedVehiclesData(dataSource: DataSource) {
  const vehicleTypeRepository = dataSource.getRepository(VehicleType);
  const vehicleRepository = dataSource.getRepository(Vehicle);

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

  // Seed Vehicles for Company 1 (using Terminal 1 as depot)
  const vehicles = [
    {
      vehicleId: 'BUS-001',
      typeId: busType.id,
      depotId: 1, // Main depot
      isActive: true,
      licensePlate: 'ABC-1234',
      odometer: 120000,
      lastMaintenanceDate: new Date('2026-04-01'),
      companyId: 1,
      metadata: { fuelType: 'diesel', emission: 'Euro6' },
    },
    {
      vehicleId: 'BUS-002',
      typeId: busType.id,
      depotId: 1,
      isActive: true,
      licensePlate: 'ABC-1235',
      odometer: 115000,
      lastMaintenanceDate: new Date('2026-03-15'),
      companyId: 1,
      metadata: { fuelType: 'diesel', emission: 'Euro6' },
    },
    {
      vehicleId: 'MINIBUS-001',
      typeId: minibuslType.id,
      depotId: 1,
      isActive: true,
      licensePlate: 'ABC-2001',
      odometer: 80000,
      lastMaintenanceDate: new Date('2026-04-10'),
      companyId: 1,
      metadata: { fuelType: 'gasoline', emission: 'Euro6' },
    },
    {
      vehicleId: 'COACH-001',
      typeId: coachType.id,
      depotId: 1,
      isActive: true,
      licensePlate: 'ABC-3001',
      odometer: 250000,
      lastMaintenanceDate: new Date('2026-03-01'),
      companyId: 1,
      metadata: { fuelType: 'diesel', emission: 'Euro5' },
    },
  ];

  await vehicleRepository.save(vehicles);

  console.log('✓ Vehicle types and vehicles seeded successfully');
  console.log(`  - Created ${1} vehicle types`);
  console.log(`  - Created ${vehicles.length} vehicles`);
}
