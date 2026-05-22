import { BadRequestException } from '@nestjs/common';
import { ParametersService } from './parameters.service';

const normalizedBase = {
  id: 3,
  companyId: 16,
  driver_cost_per_minute: 0.5,
  waiting_time_pay_pct: 0.3, // already fraction (≤1), no normalization
  holiday_extra_pct: 0.5,
  nocturnal_extra_pct: 0.2,
  max_shift_minutes: 840,
  max_work_minutes: 480,
  meal_break_minutes: 60,
  min_shift_minutes: 240,
  min_work_minutes: 60,
  min_workpiece_minutes: 30,
  max_workpiece_minutes: 480,
  min_trips_per_piece: 1,
  max_trips_per_piece: 10,
  split_shift_min_gap_minutes: 60,
  split_shift_max_gap_minutes: 180,
  nocturnal_start_hour: 22,
  nocturnal_end_hour: 5,
  algorithm_preference: 'greedy',
  apply_cct: true,
  min_break_minutes: 30,
};

describe('ParametersService', () => {
  let service: ParametersService;
  let parametersRepository: {
    findOne: jest.Mock;
    save: jest.Mock;
    create: jest.Mock;
  };
  let tenantContext: {
    getCompanyId: jest.Mock;
  };

  beforeEach(() => {
    parametersRepository = {
      findOne: jest.fn(),
      save: jest.fn((entity) => entity),
      create: jest.fn((entity) => entity),
    };
    tenantContext = {
      getCompanyId: jest.fn().mockReturnValue(16),
    };

    service = new ParametersService(
      parametersRepository as any,
      tenantContext as any,
    );
  });

  it('normaliza percentuais legados ao carregar parametros', async () => {
    parametersRepository.findOne.mockResolvedValue({
      id: 3,
      companyId: 16,
      waiting_time_pay_pct: 30,
      holiday_extra_pct: 100,
      nocturnal_extra_pct: 20,
    });

    const result = await service.getParameters();

    expect(parametersRepository.save).toHaveBeenCalledWith(
      expect.objectContaining({
        waiting_time_pay_pct: 0.3,
        holiday_extra_pct: 1,
        nocturnal_extra_pct: 0.2,
      }),
    );
    expect(result.waiting_time_pay_pct).toBeCloseTo(0.3);
    expect(result.holiday_extra_pct).toBeCloseTo(1);
    expect(result.nocturnal_extra_pct).toBeCloseTo(0.2);
  });

  it('normaliza percentuais legados existentes antes de aplicar update', async () => {
    parametersRepository.findOne.mockResolvedValue({
      id: 3,
      companyId: 16,
      driver_cost_per_minute: 0.5,
      waiting_time_pay_pct: 30,
      holiday_extra_pct: 100,
      nocturnal_extra_pct: 20,
      max_shift_minutes: 840,
      max_work_minutes: 480,
      meal_break_minutes: 15,
      nocturnal_start_hour: null,
      nocturnal_end_hour: null,
    });

    const result = await service.updateParameters({
      driver_cost_per_minute: 0.82,
    });

    expect(parametersRepository.save).toHaveBeenCalledWith(
      expect.objectContaining({
        driver_cost_per_minute: 0.82,
        waiting_time_pay_pct: 0.3,
        holiday_extra_pct: 1,
        nocturnal_extra_pct: 0.2,
      }),
    );
    expect(result.driver_cost_per_minute).toBeCloseTo(0.82);
    expect(result.waiting_time_pay_pct).toBeCloseTo(0.3);
    expect(result.holiday_extra_pct).toBeCloseTo(1);
    expect(result.nocturnal_extra_pct).toBeCloseTo(0.2);
  });

  // ── getParameters — edge cases ────────────────────────────────────────────

  it('throws BadRequestException when tenant not identified in getParameters', async () => {
    tenantContext.getCompanyId.mockReturnValue(null);
    await expect(service.getParameters()).rejects.toThrow(BadRequestException);
  });

  it('creates default parameters when none exist', async () => {
    parametersRepository.findOne.mockResolvedValue(null);
    await service.getParameters();
    expect(parametersRepository.save).toHaveBeenCalled();
    expect(parametersRepository.create).toHaveBeenCalledWith(
      expect.objectContaining({ companyId: 16, apply_cct: true }),
    );
  });

  it('returns existing params when no normalization needed', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    const result = await service.getParameters();
    expect(result.companyId).toBe(16);
    // No extra save when normalization is not triggered
    expect(parametersRepository.save).not.toHaveBeenCalled();
  });

  // ── updateParameters — bad tenant ─────────────────────────────────────────

  it('throws BadRequestException when tenant not identified in updateParameters', async () => {
    tenantContext.getCompanyId.mockReturnValue(null);
    await expect(service.updateParameters({})).rejects.toThrow(
      BadRequestException,
    );
  });

  it('creates defaults when params not found before update', async () => {
    parametersRepository.findOne.mockResolvedValue(null);
    await service.updateParameters({ apply_cct: true });
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  // ── validateAndSanitizeParameters — field types ───────────────────────────

  it('throws BadRequestException for negative integer field', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ max_shift_minutes: -1 } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException for non-integer in integer field', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ max_shift_minutes: 10.5 } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException for nocturnal_start_hour > 23', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ nocturnal_start_hour: 25 } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException for percentage field > 100', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ waiting_time_pay_pct: 150 } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException for negative non-negative field', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ driver_cost_per_minute: -5 } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts boolean true', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ apply_cct: true } as any);
    expect(parametersRepository.save).toHaveBeenCalledWith(
      expect.objectContaining({ apply_cct: true }),
    );
  });

  it('accepts string "false" for boolean field', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ apply_cct: 'false' } as any);
    expect(parametersRepository.save).toHaveBeenCalledWith(
      expect.objectContaining({ apply_cct: false }),
    );
  });

  it('throws BadRequestException for invalid boolean string', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ apply_cct: 'yes' } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid algorithm_preference', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ algorithm_preference: 'genetic' } as any);
    expect(parametersRepository.save).toHaveBeenCalledWith(
      expect.objectContaining({ algorithm_preference: 'genetic' }),
    );
  });

  it('throws BadRequestException for invalid algorithm_preference', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ algorithm_preference: 'magic_ai' } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid vehicle_idle_gap_behavior', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({
      vehicle_idle_gap_behavior: 'stay_at_terminal',
    } as any);
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  it('throws BadRequestException for invalid vehicle_idle_gap_behavior', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({
        vehicle_idle_gap_behavior: 'teleport',
      } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid group_infeasibility_mode', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({
      group_infeasibility_mode: 'production',
    } as any);
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  it('throws BadRequestException for invalid group_infeasibility_mode', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ group_infeasibility_mode: 'chaos' } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid operational_quality_mode', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({
      operational_quality_mode: 'strict',
    } as any);
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  it('throws for invalid operational_quality_mode', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ operational_quality_mode: 'random' } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid terminal_location_ids', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ terminal_location_ids: [1, 2] } as any);
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  it('throws for non-array terminal_location_ids', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ terminal_location_ids: 'abc' } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid goal_weights object', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ goal_weights: { cost: 1 } } as any);
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  it('throws for goal_weights as array', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ goal_weights: [1, 2] } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('accepts valid dynamic_rules list', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ dynamic_rules: [{ rule: 'x' }] } as any);
    expect(parametersRepository.save).toHaveBeenCalled();
  });

  it('throws for dynamic_rules as non-array', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ dynamic_rules: 'bad' } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws BadRequestException for unknown parameter', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await expect(
      service.updateParameters({ unknown_field: 1 } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('sets null when field value is empty string', async () => {
    parametersRepository.findOne.mockResolvedValue({ ...normalizedBase });
    await service.updateParameters({ max_shift_minutes: '' } as any);
    expect(parametersRepository.save).toHaveBeenCalledWith(
      expect.objectContaining({ max_shift_minutes: null }),
    );
  });

  // ── validateParameterRanges ────────────────────────────────────────────────

  it('throws when min_break_minutes is out of allowed range', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      min_break_minutes: 100,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  // ── validateCrossFieldRelations ────────────────────────────────────────────

  it('throws when min_shift > max_shift', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      min_shift_minutes: 700,
      max_shift_minutes: 600,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws when min_work > max_work', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      min_work_minutes: 500,
      max_work_minutes: 400,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws when nocturnal_start_hour equals nocturnal_end_hour', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      nocturnal_start_hour: 5,
      nocturnal_end_hour: 5,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws when max_shift < max_work + meal_break', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      max_shift_minutes: 500,
      max_work_minutes: 480,
      meal_break_minutes: 60,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws when min_trips_per_piece > max_trips_per_piece', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      min_trips_per_piece: 10,
      max_trips_per_piece: 5,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws when min_workpiece_minutes > max_workpiece_minutes', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      min_workpiece_minutes: 500,
      max_workpiece_minutes: 300,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });

  it('throws when split_shift_min_gap > split_shift_max_gap', async () => {
    parametersRepository.findOne.mockResolvedValue({
      ...normalizedBase,
      split_shift_min_gap_minutes: 200,
      split_shift_max_gap_minutes: 100,
    });
    await expect(
      service.updateParameters({ apply_cct: true } as any),
    ).rejects.toThrow(BadRequestException);
  });
});
