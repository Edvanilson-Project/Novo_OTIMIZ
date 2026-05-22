import {
  DriverConstraintValidator,
  DutySegment,
} from './driver-constraint.validator';

describe('DriverConstraintValidator', () => {
  let validator: DriverConstraintValidator;

  beforeEach(() => {
    validator = new DriverConstraintValidator();
  });

  describe('Basic validation', () => {
    it('should pass valid segments', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 10:00'),
          drivingMinutes: 120,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 10:00'),
          endTime: new Date('2026-05-15 10:15'),
          drivingMinutes: 0,
          type: 'break',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(true);
      expect(result.violations).toHaveLength(0);
    });

    it('should detect consecutive driving violation', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 13:00'),
          drivingMinutes: 300, // 5 hours
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(false);
      expect(result.violations.length).toBeGreaterThan(0);
      expect(result.violations[0].violationType).toBe(
        'consecutive_driving_exceeded',
      );
    });

    it('should detect daily driving limit violation', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 17:30'),
          drivingMinutes: 570, // 9.5 hours
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(false);
      expect(
        result.violations.some(
          (v) => v.violationType === 'daily_driving_exceeded',
        ),
      ).toBe(true);
    });
  });

  describe('Consecutive driving with breaks', () => {
    it('should reset consecutive counter after break', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 12:30'),
          drivingMinutes: 270,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 12:30'),
          endTime: new Date('2026-05-15 12:45'),
          drivingMinutes: 0,
          type: 'break',
        },
        {
          startTime: new Date('2026-05-15 12:45'),
          endTime: new Date('2026-05-15 17:15'),
          drivingMinutes: 270,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 17:15'),
          endTime: new Date('2026-05-15 18:00'),
          drivingMinutes: 0,
          type: 'meal',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(true);
    });

    it('should detect violation if break is too short', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 12:31'),
          drivingMinutes: 271,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 12:31'),
          endTime: new Date('2026-05-15 12:45'),
          drivingMinutes: 0,
          type: 'break',
        },
        {
          startTime: new Date('2026-05-15 12:45'),
          endTime: new Date('2026-05-15 17:15'),
          drivingMinutes: 270,
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(false);
    });
  });

  describe('Meal break validation', () => {
    it('should detect missing meal break', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 14:30'),
          drivingMinutes: 390, // 6.5 hours without meal
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(false);
      expect(
        result.violations.some((v) => v.violationType === 'meal_break_overdue'),
      ).toBe(true);
    });

    it('should accept meal break within time limit', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 12:00'),
          drivingMinutes: 240,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 12:00'),
          endTime: new Date('2026-05-15 12:45'),
          drivingMinutes: 0,
          type: 'meal',
        },
        {
          startTime: new Date('2026-05-15 12:45'),
          endTime: new Date('2026-05-15 17:15'),
          drivingMinutes: 270,
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(true);
    });

    it('should detect meal break too short', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 14:30'),
          drivingMinutes: 360,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 14:30'),
          endTime: new Date('2026-05-15 14:35'),
          drivingMinutes: 5, // too short
          type: 'meal',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(false);
      expect(
        result.violations.some(
          (v) => v.violationType === 'meal_break_too_short',
        ),
      ).toBe(true);
    });
  });

  describe('Break insertion', () => {
    it('should insert mandatory breaks', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 13:00'),
          drivingMinutes: 300, // 5 hours - should trigger break insertion
          type: 'driving',
        },
      ];

      const result = validator.insertMandatoryBreaks(segments);

      // Should have inserted a break
      expect(result.length).toBeGreaterThan(segments.length);
      expect(result.some((s) => s.type === 'break')).toBe(true);
    });

    it('should insert meal breaks', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 14:30'),
          drivingMinutes: 390, // 6.5 hours - should trigger meal
          type: 'driving',
        },
      ];

      const result = validator.insertMealBreaks(segments);

      expect(result.some((s) => s.type === 'meal')).toBe(true);
    });

    it('should preserve original segments in insertion', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 12:00'),
          drivingMinutes: 240,
          type: 'driving',
        },
      ];

      const result = validator.insertMandatoryBreaks(segments);

      // Original segment should be preserved
      expect(result.some((s) => s.drivingMinutes === 240)).toBe(true);
    });
  });

  describe('Custom constraints', () => {
    it('should apply custom maximum driving time', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 12:00'),
          drivingMinutes: 240,
          type: 'driving',
        },
      ];

      const customConstraints = {
        maxConsecutiveDrivingMinutes: 180, // 3 hours
      };

      const result = validator.validate(segments, customConstraints);

      expect(result.isValid).toBe(false);
    });

    it('should apply custom meal break frequency', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 12:00'),
          drivingMinutes: 240,
          type: 'driving',
        },
      ];

      const customConstraints = {
        mealBreakFrequencyMinutes: 120, // 2 hours
      };

      const result = validator.validate(segments, customConstraints);

      expect(result.isValid).toBe(false);
    });
  });

  describe('Recommendations', () => {
    it('should provide recommendations for violations', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 13:30'),
          drivingMinutes: 330,
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.recommendations.length).toBeGreaterThan(0);
      expect(result.recommendations[0]).toContain('pausa');
    });

    it('should provide multiple recommendations for multiple violations', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 08:00'),
          endTime: new Date('2026-05-15 18:00'),
          drivingMinutes: 600, // 10 hours
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.recommendations.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('Complex scenarios', () => {
    it('should handle full day with multiple segments', () => {
      const segments: DutySegment[] = [
        {
          startTime: new Date('2026-05-15 06:00'),
          endTime: new Date('2026-05-15 10:00'),
          drivingMinutes: 240,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 10:00'),
          endTime: new Date('2026-05-15 10:15'),
          drivingMinutes: 0,
          type: 'break',
        },
        {
          startTime: new Date('2026-05-15 10:15'),
          endTime: new Date('2026-05-15 14:15'),
          drivingMinutes: 240,
          type: 'driving',
        },
        {
          startTime: new Date('2026-05-15 14:15'),
          endTime: new Date('2026-05-15 15:00'),
          drivingMinutes: 0,
          type: 'meal',
        },
        {
          startTime: new Date('2026-05-15 15:00'),
          endTime: new Date('2026-05-15 16:48'),
          drivingMinutes: 60,
          type: 'driving',
        },
      ];

      const result = validator.validate(segments);

      expect(result.isValid).toBe(true);
    });
  });
});
