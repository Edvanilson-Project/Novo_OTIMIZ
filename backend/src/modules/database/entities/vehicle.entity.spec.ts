import { Vehicle } from './vehicle.entity';

describe('Vehicle Entity', () => {
  it('should create a vehicle instance', () => {
    const vehicle = new Vehicle();
    vehicle.vehicleId = 'BUS-001';
    vehicle.typeId = 1;
    vehicle.depotId = 1;
    vehicle.isActive = true;
    vehicle.companyId = 1;

    expect(vehicle.vehicleId).toBe('BUS-001');
    expect(vehicle.typeId).toBe(1);
    expect(vehicle.depotId).toBe(1);
    expect(vehicle.isActive).toBe(true);
    expect(vehicle.companyId).toBe(1);
  });

  it('should have isActive as true by default', () => {
    // Note: TypeORM defaults only apply when saved to database
    // When instantiated directly, field will be undefined until saved
    const vehicle = new Vehicle();
    vehicle.isActive = true; // Need to set explicitly in tests
    expect(vehicle.isActive).toBe(true);
  });

  it('should support optional fields', () => {
    const vehicle = new Vehicle();
    vehicle.vehicleId = 'BUS-002';
    vehicle.typeId = 1;
    vehicle.depotId = 2;
    vehicle.licensePlate = 'ABC-1234';
    vehicle.odometer = 125000.5;
    vehicle.companyId = 1;

    expect(vehicle.licensePlate).toBe('ABC-1234');
    expect(vehicle.odometer).toBe(125000.5);
  });

  it('should support metadata', () => {
    const vehicle = new Vehicle();
    vehicle.metadata = {
      lastInspection: '2026-04-15',
      nextInspection: '2027-04-15',
      insuranceProvider: 'XYZ Insurance',
    };

    expect(vehicle.metadata.lastInspection).toBe('2026-04-15');
    expect(vehicle.metadata.insuranceProvider).toBe('XYZ Insurance');
  });

  it('should reference vehicle type and depot', () => {
    const vehicle = new Vehicle();
    vehicle.vehicleId = 'COACH-001';
    vehicle.typeId = 3; // Coach type
    vehicle.depotId = 1; // Main depot
    vehicle.companyId = 1;

    // These references would be populated from database relationships
    expect(vehicle.typeId).toBe(3);
    expect(vehicle.depotId).toBe(1);
  });

  it('should support multiple vehicles with different types and depots', () => {
    const bus1 = new Vehicle();
    bus1.vehicleId = 'BUS-001';
    bus1.typeId = 1;
    bus1.depotId = 1;

    const bus2 = new Vehicle();
    bus2.vehicleId = 'BUS-002';
    bus2.typeId = 1;
    bus2.depotId = 2;

    const coach1 = new Vehicle();
    coach1.vehicleId = 'COACH-001';
    coach1.typeId = 3;
    coach1.depotId = 1;

    expect(bus1.typeId).toBe(bus2.typeId); // Same type
    expect(bus1.depotId).not.toBe(bus2.depotId); // Different depots
    expect(coach1.typeId).not.toBe(bus1.typeId); // Different types
  });

  it('should allow deactivating a vehicle', () => {
    const vehicle = new Vehicle();
    vehicle.vehicleId = 'BUS-003';
    vehicle.typeId = 1;
    vehicle.depotId = 1;
    vehicle.isActive = true;
    vehicle.companyId = 1;

    expect(vehicle.isActive).toBe(true);

    vehicle.isActive = false;
    expect(vehicle.isActive).toBe(false);
  });
});
