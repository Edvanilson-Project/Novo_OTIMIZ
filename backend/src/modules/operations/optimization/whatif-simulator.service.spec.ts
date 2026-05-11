import { WhatIfSimulatorService } from './whatif-simulator.service';

describe('WhatIfSimulatorService', () => {
  let service: WhatIfSimulatorService;

  beforeEach(() => {
    service = new WhatIfSimulatorService(
      { findOne: jest.fn() } as any, // scheduleRepo
      { runOptimization: jest.fn() } as any, // optimizationService
      { getCompanyId: jest.fn().mockReturnValue(16) } as any, // tenantContext
    );
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('Vehicle Type Change', () => {
    it('should calculate cost increase for more expensive vehicle', () => {
      const result = service.simulateVehicleTypeChange(
        10000, // original cost
        1, // from type
        2, // to type
        800, // from type cost/day
        1200, // to type cost/day
        5, // trips
      );

      expect(result.costDifference).toBe((1200 - 800) * 5);
      expect(result.newCost).toBe(10000 + 2000);
      expect(result.feasible).toBe(true);
    });

    it('should detect cost reduction for cheaper vehicle', () => {
      const result = service.simulateVehicleTypeChange(
        10000,
        1,
        2,
        800,
        500, // cheaper vehicle
        5,
      );

      expect(result.costDifference).toBeLessThan(0);
      expect(result.newCost).toBeLessThan(10000);
      expect(result.recommendations.some((r) => r.includes('economias'))).toBe(true);
    });
  });

  describe('Time Shift', () => {
    it('should calculate impact of time shift', () => {
      const result = service.simulateTimeShift(10000, 60, 5); // +1 hour shift

      expect(result.scenario.type).toBe('time_shift');
      expect(result.newCost).toBeGreaterThan(10000);
      expect(result.feasible).toBe(true);
    });

    it('should mark large shifts as infeasible', () => {
      const result = service.simulateTimeShift(10000, 180, 5); // +3 hour shift

      expect(result.feasible).toBe(false);
      expect(result.warnings.length).toBeGreaterThan(0);
    });

    it('should provide recommendations for early shifts', () => {
      const result = service.simulateTimeShift(10000, -60, 5); // -1 hour shift

      expect(result.recommendations.some((r) => r.includes('Antecipação'))).toBe(true);
    });
  });

  describe('Trip Removal', () => {
    it('should calculate cost savings from trip removal', () => {
      const result = service.simulateTripRemoval(
        10000, // original cost
        500, // trip cost
        800, // vehicle fixed cost
        1, // only this vehicle uses this trip
      );

      expect(result.costDifference).toBeLessThan(0);
      expect(result.newCost).toBeLessThan(10000);
      expect(result.feasible).toBe(false); // Trip removal not recommended
    });

    it('should show warning about trip removal', () => {
      const result = service.simulateTripRemoval(10000, 500, 800, 1);

      expect(result.warnings.some((w) => w.includes('não é recomendada'))).toBe(true);
    });
  });

  describe('Trip Addition', () => {
    it('should calculate cost of adding new trip without new vehicle', () => {
      const result = service.simulateTripAddition(
        10000,
        300, // new trip cost
        false, // no new vehicle needed
        0,
      );

      expect(result.costDifference).toBe(300);
      expect(result.newCost).toBe(10300);
      expect(result.feasible).toBe(true);
    });

    it('should include vehicle cost when new vehicle needed', () => {
      const result = service.simulateTripAddition(
        10000,
        300,
        true, // new vehicle needed
        800, // vehicle fixed cost
      );

      expect(result.costDifference).toBe(1100);
      expect(result.newCost).toBe(11100);
      expect(result.warnings.some((w) => w.includes('novo veículo'))).toBe(true);
    });
  });

  describe('Parameter Change', () => {
    it('should calculate impact of break duration increase', () => {
      const result = service.simulateParameterChange(
        10000,
        'min_break_minutes',
        15,
        30, // increased break
      );

      expect(result.newCost).toBeGreaterThan(10000);
      expect(result.costDifferencePercent).toBeGreaterThan(0);
    });

    it('should calculate impact of break duration decrease', () => {
      const result = service.simulateParameterChange(
        10000,
        'min_break_minutes',
        30,
        15, // decreased break
      );

      expect(result.newCost).toBeLessThan(10000);
      expect(result.costDifferencePercent).toBeLessThan(0);
    });

    it('should provide generic recommendations for parameter changes', () => {
      const result = service.simulateParameterChange(
        10000,
        'vehicle_preference',
        'bus',
        'coach',
      );

      expect(result.recommendations.length).toBeGreaterThan(0);
    });
  });

  describe('Result structure', () => {
    it('should return complete what-if result', () => {
      const result = service.simulateVehicleTypeChange(10000, 1, 2, 800, 1200, 5);

      expect(result).toHaveProperty('scenario');
      expect(result).toHaveProperty('originalCost');
      expect(result).toHaveProperty('newCost');
      expect(result).toHaveProperty('costDifference');
      expect(result).toHaveProperty('costDifferencePercent');
      expect(result).toHaveProperty('feasible');
      expect(result).toHaveProperty('warnings');
      expect(result).toHaveProperty('recommendations');
    });

    it('should have correct scenario type', () => {
      const result = service.simulateVehicleTypeChange(10000, 1, 2, 800, 1200, 5);

      expect(result.scenario.type).toBe('vehicle_type_change');
      expect(result.scenario.description).toBeTruthy();
      expect(Array.isArray(result.scenario.affectedElements)).toBe(true);
    });
  });
});
