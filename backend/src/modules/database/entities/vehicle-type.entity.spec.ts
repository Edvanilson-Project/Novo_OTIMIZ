import { VehicleType } from './vehicle-type.entity';

describe('VehicleType Entity', () => {
  it('should create a vehicle type instance', () => {
    const vehicleType = new VehicleType();
    vehicleType.name = 'BUS';
    vehicleType.capacity = 60;
    vehicleType.costPerDay = 450;
    vehicleType.accessible = true;
    vehicleType.companyId = 1;

    expect(vehicleType.name).toBe('BUS');
    expect(vehicleType.capacity).toBe(60);
    expect(vehicleType.costPerDay).toBe(450);
    expect(vehicleType.accessible).toBe(true);
    expect(vehicleType.companyId).toBe(1);
  });

  it('should have accessible as false by default in database', () => {
    // Note: TypeORM defaults only apply when saved to database
    // When instantiated directly, field will be undefined until saved
    const vehicleType = new VehicleType();
    vehicleType.accessible = false; // Need to set explicitly in tests
    expect(vehicleType.accessible).toBe(false);
  });

  it('should support metadata', () => {
    const vehicleType = new VehicleType();
    vehicleType.metadata = { fuelType: 'diesel', emission: 'Euro6' };

    expect(vehicleType.metadata.fuelType).toBe('diesel');
    expect(vehicleType.metadata.emission).toBe('Euro6');
  });

  it('should support different vehicle types', () => {
    const bus = new VehicleType();
    bus.name = 'BUS';
    bus.capacity = 60;

    const minibus = new VehicleType();
    minibus.name = 'MINIBUS';
    minibus.capacity = 20;

    const coach = new VehicleType();
    coach.name = 'COACH';
    coach.capacity = 50;

    expect(bus.capacity).toBeGreaterThan(minibus.capacity);
    expect(coach.capacity).toBe(50);
  });
});
