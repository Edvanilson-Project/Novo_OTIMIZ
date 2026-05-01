import { ParametersService } from './parameters.service';

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
      save: jest.fn(async (entity) => entity),
      create: jest.fn((entity) => entity),
    };
    tenantContext = {
      getCompanyId: jest.fn().mockReturnValue(16),
    };

    service = new ParametersService(parametersRepository as any, tenantContext as any);
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

    const result = await service.updateParameters({ driver_cost_per_minute: 0.82 });

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
});