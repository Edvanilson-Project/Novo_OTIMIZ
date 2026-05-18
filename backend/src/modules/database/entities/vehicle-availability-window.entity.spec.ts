import {
  VehicleAvailabilityWindow,
  AvailabilityReason,
} from './vehicle-availability-window.entity';

describe('VehicleAvailabilityWindow Entity', () => {
  it('should create an instance', () => {
    const window = new VehicleAvailabilityWindow();
    window.vehicleId = 1;
    window.startTime = new Date('2026-05-10 08:00:00');
    window.endTime = new Date('2026-05-10 12:00:00');
    window.companyId = 1;
    window.reason = AvailabilityReason.OTHER;
    window.isRecurring = false;

    expect(window.vehicleId).toBe(1);
    expect(window.reason).toBe(AvailabilityReason.OTHER);
    expect(window.isRecurring).toBe(false);
  });

  it('should support maintenance reason', () => {
    const window = new VehicleAvailabilityWindow();
    window.reason = AvailabilityReason.MAINTENANCE;
    window.description = 'Scheduled maintenance';

    expect(window.reason).toBe(AvailabilityReason.MAINTENANCE);
    expect(window.description).toBe('Scheduled maintenance');
  });

  it('should support inspection reason', () => {
    const window = new VehicleAvailabilityWindow();
    window.reason = AvailabilityReason.INSPECTION;

    expect(window.reason).toBe(AvailabilityReason.INSPECTION);
  });

  it('should support fuel reason', () => {
    const window = new VehicleAvailabilityWindow();
    window.reason = AvailabilityReason.FUEL;

    expect(window.reason).toBe(AvailabilityReason.FUEL);
  });

  it('should support cleaning reason', () => {
    const window = new VehicleAvailabilityWindow();
    window.reason = AvailabilityReason.CLEANING;

    expect(window.reason).toBe(AvailabilityReason.CLEANING);
  });

  it('should support repair reason', () => {
    const window = new VehicleAvailabilityWindow();
    window.reason = AvailabilityReason.REPAIR;

    expect(window.reason).toBe(AvailabilityReason.REPAIR);
  });

  it('should track recurring windows', () => {
    const window = new VehicleAvailabilityWindow();
    window.isRecurring = true;
    window.recurringPattern = 'weekly';

    expect(window.isRecurring).toBe(true);
    expect(window.recurringPattern).toBe('weekly');
  });

  it('should support bi-weekly pattern', () => {
    const window = new VehicleAvailabilityWindow();
    window.recurringPattern = 'bi-weekly';

    expect(window.recurringPattern).toBe('bi-weekly');
  });

  it('should support monthly pattern', () => {
    const window = new VehicleAvailabilityWindow();
    window.recurringPattern = 'monthly';

    expect(window.recurringPattern).toBe('monthly');
  });

  it('should track timestamps', () => {
    const window = new VehicleAvailabilityWindow();
    const now = new Date();
    window.createdAt = now;
    window.updatedAt = now;

    expect(window.createdAt).toBe(now);
    expect(window.updatedAt).toBe(now);
  });

  it('should validate time windows', () => {
    const window = new VehicleAvailabilityWindow();
    const start = new Date('2026-05-10 08:00:00');
    const end = new Date('2026-05-10 16:00:00');
    window.startTime = start;
    window.endTime = end;

    expect(window.startTime.getTime()).toBeLessThan(window.endTime.getTime());
  });
});
