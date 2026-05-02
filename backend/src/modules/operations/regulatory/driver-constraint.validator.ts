import { Injectable } from '@nestjs/common';

export interface DutySegment {
  startTime: Date;
  endTime: Date;
  drivingMinutes: number;
  type: 'driving' | 'break' | 'meal' | 'duty';
}

export interface DriverConstraint {
  maxConsecutiveDrivingMinutes: number; // e.g., 270 (4.5 hours)
  mandatoryBreakAfterMinutes: number; // e.g., 270
  mandatoryBreakDurationMinutes: number; // e.g., 15
  maxDailyDrivingMinutes: number; // e.g., 540 (9 hours)
  maxWeeklyDrivingMinutes: number; // e.g., 3240 (54 hours)
  minRestBetweenShiftsMinutes: number; // e.g., 480 (8 hours)
  mealBreakDurationMinutes: number; // e.g., 30-45
  mealBreakFrequencyMinutes: number; // e.g., 360 (6 hours)
}

export interface ConstraintViolation {
  violationType: string;
  driverName: string;
  drivingMinutes: number;
  allowedMinutes: number;
  violationTime?: Date;
}

@Injectable()
export class DriverConstraintValidator {
  private readonly defaultConstraints: DriverConstraint = {
    maxConsecutiveDrivingMinutes: 270, // 4.5 hours
    mandatoryBreakAfterMinutes: 270,
    mandatoryBreakDurationMinutes: 15,
    maxDailyDrivingMinutes: 540, // 9 hours
    maxWeeklyDrivingMinutes: 3240, // 54 hours
    minRestBetweenShiftsMinutes: 480, // 8 hours
    mealBreakDurationMinutes: 30,
    mealBreakFrequencyMinutes: 360, // 6 hours
  };

  validate(
    segments: DutySegment[],
    constraints: Partial<DriverConstraint> = {},
  ): {
    isValid: boolean;
    violations: ConstraintViolation[];
    recommendations: string[];
  } {
    const rules = { ...this.defaultConstraints, ...constraints };
    const violations: ConstraintViolation[] = [];
    const recommendations: string[] = [];

    // Check consecutive driving time
    const consViolation = this.checkConsecutiveDriving(segments, rules);
    if (consViolation) {
      violations.push(consViolation);
      recommendations.push(
        `Inserir pausa de ${rules.mandatoryBreakDurationMinutes}min após ${rules.maxConsecutiveDrivingMinutes}min dirigindo`,
      );
    }

    // Check daily driving time
    const dailyViolation = this.checkDailyDriving(segments, rules);
    if (dailyViolation) {
      violations.push(dailyViolation);
      recommendations.push('Reduzir viagens do dia para cumprir limite de 9h dirigindo');
    }

    // Check meal breaks
    const mealViolation = this.checkMealBreaks(segments, rules);
    if (mealViolation) {
      violations.push(mealViolation);
      recommendations.push('Inserir pausa para refeição (30-45 minutos)');
    }

    return {
      isValid: violations.length === 0,
      violations,
      recommendations,
    };
  }

  private checkConsecutiveDriving(
    segments: DutySegment[],
    rules: DriverConstraint,
  ): ConstraintViolation | null {
    let consecutiveMinutes = 0;
    let lastWasBreak = false;

    for (const segment of segments) {
      if (segment.type === 'driving') {
        // If we just had a break, this is the start of a new consecutive period
        if (lastWasBreak) {
          consecutiveMinutes = 0;
          lastWasBreak = false;
        }

        consecutiveMinutes += segment.drivingMinutes;

        // Check if limit exceeded on this segment
        if (consecutiveMinutes > rules.maxConsecutiveDrivingMinutes) {
          return {
            violationType: 'consecutive_driving_exceeded',
            driverName: 'Unknown',
            drivingMinutes: consecutiveMinutes,
            allowedMinutes: rules.maxConsecutiveDrivingMinutes,
            violationTime: segment.endTime,
          };
        }
      } else if (segment.type === 'break' || segment.type === 'meal') {
        // Check if break is long enough to reset counter
        const breakDuration = (segment.endTime.getTime() - segment.startTime.getTime()) / (60 * 1000);
        if (breakDuration >= 15) {
          // 15 minute break resets counter
          consecutiveMinutes = 0;
          lastWasBreak = true;
        }
      }
    }

    return null;
  }

  private checkDailyDriving(
    segments: DutySegment[],
    rules: DriverConstraint,
  ): ConstraintViolation | null {
    const totalDriving = segments
      .filter((s) => s.type === 'driving')
      .reduce((sum, s) => sum + s.drivingMinutes, 0);

    if (totalDriving > rules.maxDailyDrivingMinutes) {
      return {
        violationType: 'daily_driving_exceeded',
        driverName: 'Unknown',
        drivingMinutes: totalDriving,
        allowedMinutes: rules.maxDailyDrivingMinutes,
      };
    }

    return null;
  }

  private checkMealBreaks(
    segments: DutySegment[],
    rules: DriverConstraint,
  ): ConstraintViolation | null {
    let timeSinceLastMeal = 0;

    for (const segment of segments) {
      if (segment.type === 'meal') {
        // Check meal break duration
        const mealDuration = (segment.endTime.getTime() - segment.startTime.getTime()) / (60 * 1000);
        if (mealDuration < rules.mealBreakDurationMinutes) {
          return {
            violationType: 'meal_break_too_short',
            driverName: 'Unknown',
            drivingMinutes: mealDuration,
            allowedMinutes: rules.mealBreakDurationMinutes,
          };
        }
        timeSinceLastMeal = 0;
      } else if (segment.type === 'driving') {
        timeSinceLastMeal += segment.drivingMinutes;
      } else if (segment.type === 'break') {
        // Breaks don't reset meal timer
        continue;
      }

      // Check if meal break is overdue
      if (timeSinceLastMeal > rules.mealBreakFrequencyMinutes) {
        // Only return violation if no meal break found in subsequent segments
        const hasMealAfter = segments.slice(segments.indexOf(segment)).some((s) => s.type === 'meal');
        if (!hasMealAfter) {
          return {
            violationType: 'meal_break_overdue',
            driverName: 'Unknown',
            drivingMinutes: timeSinceLastMeal,
            allowedMinutes: rules.mealBreakFrequencyMinutes,
          };
        }
      }
    }

    return null;
  }

  insertMandatoryBreaks(
    segments: DutySegment[],
    constraints: Partial<DriverConstraint> = {},
  ): DutySegment[] {
    const rules = { ...this.defaultConstraints, ...constraints };
    const result: DutySegment[] = [];
    let consecutiveMinutes = 0;

    for (const segment of segments) {
      if (segment.type === 'driving') {
        if (
          consecutiveMinutes + segment.drivingMinutes >
          rules.maxConsecutiveDrivingMinutes
        ) {
          // Insert break before this segment
          const breakStart = new Date(
            segment.startTime.getTime() -
              (rules.mandatoryBreakDurationMinutes * 60 * 1000),
          );
          const breakEnd = segment.startTime;

          result.push({
            startTime: breakStart,
            endTime: breakEnd,
            drivingMinutes: 0,
            type: 'break',
          });

          consecutiveMinutes = 0;
        }

        result.push(segment);
        consecutiveMinutes += segment.drivingMinutes;
      } else {
        result.push(segment);
        if (segment.type === 'break' || segment.type === 'meal') {
          consecutiveMinutes = 0;
        }
      }
    }

    return result;
  }

  insertMealBreaks(
    segments: DutySegment[],
    constraints: Partial<DriverConstraint> = {},
  ): DutySegment[] {
    const rules = { ...this.defaultConstraints, ...constraints };
    const result: DutySegment[] = [];
    let timeSinceMeal = 0;

    for (const segment of segments) {
      if (segment.type === 'driving') {
        timeSinceMeal += segment.drivingMinutes;

        // Check if meal break is needed before next driving segment
        if (timeSinceMeal > rules.mealBreakFrequencyMinutes) {
          const mealStart = new Date(
            segment.endTime.getTime() +
              (rules.mealBreakDurationMinutes * 60 * 1000),
          );
          const mealEnd = new Date(mealStart.getTime() + (30 * 60 * 1000)); // 30 min meal

          result.push(segment);
          result.push({
            startTime: segment.endTime,
            endTime: mealEnd,
            drivingMinutes: 0,
            type: 'meal',
          });

          timeSinceMeal = 0;
          continue;
        }
      }

      result.push(segment);
      if (segment.type === 'meal') {
        timeSinceMeal = 0;
      }
    }

    return result;
  }
}
