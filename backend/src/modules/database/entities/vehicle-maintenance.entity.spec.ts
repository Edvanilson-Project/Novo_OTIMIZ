import {
  VehicleMaintenance,
  MaintenanceType,
  MaintenanceStatus,
} from './vehicle-maintenance.entity';

describe('VehicleMaintenance Entity', () => {
  it('should create an instance with defaults', () => {
    const maintenance = new VehicleMaintenance();
    maintenance.vehicleId = 1;
    maintenance.maintenanceDate = new Date('2026-05-10');
    maintenance.estimatedDurationHours = 8;
    maintenance.cost = 500;
    maintenance.companyId = 1;
    maintenance.maintenanceType = MaintenanceType.PREVENTIVE;
    maintenance.status = MaintenanceStatus.SCHEDULED;

    expect(maintenance.vehicleId).toBe(1);
    expect(maintenance.maintenanceType).toBe(MaintenanceType.PREVENTIVE);
    expect(maintenance.status).toBe(MaintenanceStatus.SCHEDULED);
  });

  it('should support corrective maintenance', () => {
    const maintenance = new VehicleMaintenance();
    maintenance.maintenanceType = MaintenanceType.CORRECTIVE;
    maintenance.cost = 1200;

    expect(maintenance.maintenanceType).toBe(MaintenanceType.CORRECTIVE);
    expect(maintenance.cost).toBe(1200);
  });

  it('should support inspection type', () => {
    const maintenance = new VehicleMaintenance();
    maintenance.maintenanceType = MaintenanceType.INSPECTION;

    expect(maintenance.maintenanceType).toBe(MaintenanceType.INSPECTION);
  });

  it('should track maintenance status changes', () => {
    const maintenance = new VehicleMaintenance();
    maintenance.status = MaintenanceStatus.SCHEDULED;
    expect(maintenance.status).toBe(MaintenanceStatus.SCHEDULED);

    maintenance.status = MaintenanceStatus.IN_PROGRESS;
    expect(maintenance.status).toBe(MaintenanceStatus.IN_PROGRESS);

    maintenance.status = MaintenanceStatus.COMPLETED;
    expect(maintenance.status).toBe(MaintenanceStatus.COMPLETED);
  });

  it('should support cancellation', () => {
    const maintenance = new VehicleMaintenance();
    maintenance.status = MaintenanceStatus.CANCELLED;

    expect(maintenance.status).toBe(MaintenanceStatus.CANCELLED);
  });

  it('should store description and notes', () => {
    const maintenance = new VehicleMaintenance();
    maintenance.description = 'Oil change and filter replacement';
    maintenance.notes = 'Vehicle reported slight noise during start';

    expect(maintenance.description).toBe('Oil change and filter replacement');
    expect(maintenance.notes).toBe(
      'Vehicle reported slight noise during start',
    );
  });

  it('should track timestamp fields', () => {
    const maintenance = new VehicleMaintenance();
    const now = new Date();
    maintenance.createdAt = now;
    maintenance.updatedAt = now;

    expect(maintenance.createdAt).toBe(now);
    expect(maintenance.updatedAt).toBe(now);
  });
});
