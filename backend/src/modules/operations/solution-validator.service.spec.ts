import { NotFoundException } from '@nestjs/common';
import { SolutionValidatorService } from './solution-validator.service';

function makeBlockRepo(blocks: any[] = []) {
  return { find: jest.fn().mockResolvedValue(blocks) } as any;
}
function makeDutyRepo(duties: any[] = []) {
  return { find: jest.fn().mockResolvedValue(duties) } as any;
}
function makeTripRepo(trips: any[] = []) {
  return { find: jest.fn().mockResolvedValue(trips) } as any;
}

const trip1 = { tripId: 101, startTime: 480, endTime: 540 };
const trip2 = { tripId: 102, startTime: 550, endTime: 610 };
const trip3 = { tripId: 103, startTime: 620, endTime: 680 };

describe('SolutionValidatorService', () => {
  let service: SolutionValidatorService;
  let blockRepo: ReturnType<typeof makeBlockRepo>;
  let dutyRepo: ReturnType<typeof makeDutyRepo>;
  let tripRepo: ReturnType<typeof makeTripRepo>;

  beforeEach(() => {
    blockRepo = makeBlockRepo();
    dutyRepo = makeDutyRepo();
    tripRepo = makeTripRepo();
    service = new SolutionValidatorService(blockRepo, dutyRepo, tripRepo);
  });

  // ── validate — clean solution ──────────────────────────────────────────────

  it('returns valid=true for a clean solution', () => {
    const blocks = [{ blockId: 1, trips: [trip1, trip2, trip3] }];
    const duties = [{ dutyId: 1, startTime: 480, endTime: 680 }];
    const trips = [trip1, trip2, trip3];
    const result = service.validate(blocks, duties, trips);
    expect(result.valid).toBe(true);
    expect(result.errorCount).toBe(0);
  });

  // ── checkTimeOverlaps ──────────────────────────────────────────────────────

  it('detects TIME_OVERLAP when trips in same block overlap', () => {
    const overlapping = { tripId: 202, startTime: 530, endTime: 590 };
    const blocks = [{ blockId: 1, trips: [trip1, overlapping] }];
    const result = service.validate(blocks, [], []);
    expect(result.errors.some((e) => e.type === 'TIME_OVERLAP')).toBe(true);
    expect(result.valid).toBe(false);
  });

  it('accepts trips in same block that do not overlap', () => {
    const blocks = [{ blockId: 1, trips: [trip1, trip2] }];
    const result = service.validate(blocks, [], []);
    const overlaps = result.errors.filter((e) => e.type === 'TIME_OVERLAP');
    expect(overlaps).toHaveLength(0);
  });

  it('uses block.items when block.trips is absent', () => {
    const blocks = [{ blockId: 1, items: [trip1, trip2] }];
    const result = service.validate(blocks, [], []);
    expect(result.stats.totalVehicles).toBe(1);
  });

  // ── checkDeadheadGaps ─────────────────────────────────────────────────────

  it('detects INSUFFICIENT_DEADHEAD when gap < 5 minutes', () => {
    const close = { tripId: 202, startTime: 542, endTime: 600 }; // 542-540=2 min gap
    const blocks = [{ blockId: 1, trips: [trip1, close] }];
    const result = service.validate(blocks, [], []);
    expect(result.errors.some((e) => e.type === 'INSUFFICIENT_DEADHEAD')).toBe(
      true,
    );
  });

  it('accepts trips with gap >= 5 minutes', () => {
    const blocks = [{ blockId: 1, trips: [trip1, trip2] }]; // gap=10min
    const result = service.validate(blocks, [], []);
    const gaps = result.errors.filter(
      (e) => e.type === 'INSUFFICIENT_DEADHEAD',
    );
    expect(gaps).toHaveLength(0);
  });

  // ── checkMaxShift ─────────────────────────────────────────────────────────

  it('detects MAX_SHIFT_EXCEEDED when duty spread exceeds default 600min', () => {
    const duties = [{ dutyId: 1, startTime: 1, endTime: 702 }]; // spread=701 > 600
    const result = service.validate([], duties, []);
    expect(result.errors.some((e) => e.type === 'MAX_SHIFT_EXCEEDED')).toBe(
      true,
    );
    expect(result.valid).toBe(false);
  });

  it('respects custom maxShiftMinutes param', () => {
    const duties = [{ dutyId: 1, startTime: 1, endTime: 482 }]; // spread=481 > 480
    const result = service.validate([], duties, [], { maxShiftMinutes: 480 });
    expect(result.errors.some((e) => e.type === 'MAX_SHIFT_EXCEEDED')).toBe(
      true,
    );
  });

  it('duty within max shift generates no MAX_SHIFT_EXCEEDED error', () => {
    const duties = [{ dutyId: 1, startTime: 480, endTime: 960 }]; // 480 min = default max
    const result = service.validate([], duties, [], { maxShiftMinutes: 600 });
    const errs = result.errors.filter((e) => e.type === 'MAX_SHIFT_EXCEEDED');
    expect(errs).toHaveLength(0);
  });

  // ── checkMealBreakPosition ────────────────────────────────────────────────

  it('generates MEAL_BREAK_INSUFFICIENT warning for long duty with tight schedule', () => {
    const duties = [
      { dutyId: 1, metadata: { work_time: 400, spread_time: 420 } },
    ];
    const result = service.validate([], duties, [], { meal_break_minutes: 30 });
    expect(
      result.warnings.some((w) => w.type === 'MEAL_BREAK_INSUFFICIENT'),
    ).toBe(true);
  });

  it('no meal break warning when work_time below threshold', () => {
    const duties = [
      { dutyId: 1, metadata: { work_time: 300, spread_time: 320 } },
    ];
    const result = service.validate([], duties, []);
    const warns = result.warnings.filter(
      (w) => w.type === 'MEAL_BREAK_INSUFFICIENT',
    );
    expect(warns).toHaveLength(0);
  });

  it('no meal break warning when available break is sufficient', () => {
    const duties = [
      { dutyId: 1, metadata: { work_time: 400, spread_time: 480 } },
    ];
    const result = service.validate([], duties, []);
    const warns = result.warnings.filter(
      (w) => w.type === 'MEAL_BREAK_INSUFFICIENT',
    );
    expect(warns).toHaveLength(0);
  });

  // ── calculateStats ─────────────────────────────────────────────────────────

  it('calculateStats computes correct allocation percentage', () => {
    const blocks = [{ blockId: 1, trips: [trip1, trip2] }];
    const trips = [trip1, trip2, trip3];
    const result = service.validate(blocks, [], trips);
    expect(result.stats.totalTrips).toBe(3);
    expect(result.stats.allocatedTrips).toBe(2);
    expect(result.stats.unallocatedTrips).toBe(1);
    expect(result.stats.allocationPercentage).toBeCloseTo(66.67, 1);
  });

  it('calculateStats returns 0% allocation when no blocks', () => {
    const trips = [trip1, trip2];
    const result = service.validate([], [], trips);
    expect(result.stats.allocationPercentage).toBe(0);
  });

  it('calculateStats computes totalOperatorHours', () => {
    const duties = [
      { dutyId: 1, startTime: 480, endTime: 600 }, // 120 min = 2h
      { dutyId: 2, startTime: 600, endTime: 660 }, // 60 min = 1h
    ];
    const result = service.validate([], duties, []);
    expect(result.stats.totalOperatorHours).toBeCloseTo(3, 1);
    expect(result.stats.avgDutyHours).toBeCloseTo(1.5, 1);
  });

  it('avgDutyHours is 0 when no duties', () => {
    const result = service.validate([], [], []);
    expect(result.stats.avgDutyHours).toBe(0);
  });

  // ── validateScheduleById ──────────────────────────────────────────────────

  it('throws NotFoundException when no blocks or duties found', async () => {
    blockRepo.find.mockResolvedValue([]);
    dutyRepo.find.mockResolvedValue([]);
    await expect(service.validateScheduleById(99, 16)).rejects.toThrow(
      NotFoundException,
    );
  });

  it('returns validation result for a valid schedule', async () => {
    blockRepo.find.mockResolvedValue([
      {
        blockId: 1,
        tripIds: [1, 2],
        companyId: 16,
        scheduleId: 5,
        metadata: {},
      },
    ]);
    dutyRepo.find.mockResolvedValue([
      {
        dutyId: 1,
        tripIds: [],
        companyId: 16,
        scheduleId: 5,
        metadata: { work_time: 120, spread_time: 180 },
      },
    ]);
    tripRepo.find.mockResolvedValue([
      {
        id: 1,
        startTime: 480,
        endTime: 540,
        duration: 60,
        originId: 1,
        destinationId: 2,
      },
      {
        id: 2,
        startTime: 550,
        endTime: 610,
        duration: 60,
        originId: 2,
        destinationId: 1,
      },
    ]);
    const result = await service.validateScheduleById(5, 16);
    expect(result).toHaveProperty('valid');
    expect(result.stats.totalVehicles).toBe(1);
  });

  it('handles blocks with no tripIds gracefully', async () => {
    blockRepo.find.mockResolvedValue([
      { blockId: 2, tripIds: [], companyId: 16, scheduleId: 5, metadata: {} },
    ]);
    dutyRepo.find.mockResolvedValue([]);
    tripRepo.find.mockResolvedValue([]);
    const result = await service.validateScheduleById(5, 16);
    expect(result).toHaveProperty('stats');
  });
});
