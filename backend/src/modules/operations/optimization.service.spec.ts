import axios from 'axios';
import { OptimizationService } from './optimization.service';

jest.mock('axios');

describe('OptimizationService polling', () => {
  const mockedAxios = axios as jest.Mocked<typeof axios>;

  let service: OptimizationService;
  let scheduleRepo: { update: jest.Mock };
  let gateway: {
    notifyOptimizationQueued: jest.Mock;
    notifyOptimizationProgress: jest.Mock;
    notifyOptimizationFinished: jest.Mock;
    notifyOptimizationFailed: jest.Mock;
    notifyOptimizationStale: jest.Mock;
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();

    const noopRepo = {
      find: jest.fn(),
      findOne: jest.fn(),
      save: jest.fn(),
      update: jest.fn(),
    };

    scheduleRepo = {
      update: jest.fn().mockResolvedValue(undefined),
    };

    gateway = {
      notifyOptimizationQueued: jest.fn(),
      notifyOptimizationProgress: jest.fn(),
      notifyOptimizationFinished: jest.fn(),
      notifyOptimizationFailed: jest.fn(),
      notifyOptimizationStale: jest.fn(),
    };

    service = new OptimizationService(
      noopRepo as any,
      noopRepo as any,
      noopRepo as any,
      scheduleRepo as any,
      {} as any,
      gateway as any,
      { get: jest.fn().mockReturnValue('internal-key-123456') } as any,
      { getCompanyId: jest.fn() } as any,
    );

    (service as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };
    (service as any).persistResults = jest.fn().mockResolvedValue(undefined);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('nao agenda um novo poll enquanto o anterior ainda esta em andamento', async () => {
    mockedAxios.get
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve({ data: { status: 'processing', progress_pct: 35 } }), 1000);
          }) as any,
      )
      .mockResolvedValueOnce({
        data: {
          status: 'completed',
          result: { status: 'ok', split_groups: 0 },
        },
      } as any);

    (service as any).pollOptimizerTask('task-1', 259, 16);

    expect(mockedAxios.get).toHaveBeenCalledTimes(1);

    await jest.advanceTimersByTimeAsync(5000);
    expect(mockedAxios.get).toHaveBeenCalledTimes(1);

    await jest.advanceTimersByTimeAsync(1000);
    await jest.advanceTimersByTimeAsync(5000);
    expect(mockedAxios.get).toHaveBeenCalledTimes(2);

    await Promise.resolve();

    expect((service as any).persistResults).toHaveBeenCalledWith(259, 16, {
      status: 'ok',
      split_groups: 0,
    });
    expect(gateway.notifyOptimizationFinished).toHaveBeenCalledWith(16, 259, {
      status: 'completed',
    });
    expect(scheduleRepo.update).not.toHaveBeenCalledWith(259, expect.objectContaining({ status: expect.anything() }));
  });

  it('propaga parametros de pareamento e VSP avancado para o optimizer', () => {
    const params = {
      force_round_trip: true,
      allow_vehicle_swap: false,
      vehicle_fixed_cost: 1350,
      preferred_pair_window_minutes: 45,
      preserve_preferred_pairs: true,
      min_break_minutes: 30,
      min_layover_minutes: 18,
      max_shift_minutes: 720,
      max_vehicles: 12,
      pair_break_penalty: 2200,
      paired_trip_bonus: 300,
      allow_multi_line_block: false,
      vehicle_idle_gap_behavior: 'return_to_garage',
      vehicle_idle_gap_threshold_minutes: 240,
    };

    const cct = (service as any).buildCctParams(params);
    const vsp = (service as any).buildVspParams(params, cct);

    expect(cct.enforce_trip_groups_hard).toBe(true);
    expect(cct.operator_pairing_hard).toBe(true);
    expect(cct.operator_single_vehicle_only).toBe(true);
    expect(vsp.force_round_trip).toBe(true);
    expect(vsp.allow_vehicle_swap).toBe(false);
    expect(vsp.fixed_vehicle_activation_cost).toBe(1350);
    expect(vsp.min_layover_minutes).toBe(30);
    expect(vsp.max_vehicles).toBe(12);
    expect(vsp.pair_break_penalty).toBe(2200);
    expect(vsp.paired_trip_bonus).toBe(300);
    expect(vsp.allow_multi_line_block).toBe(false);
    expect(vsp.vehicle_idle_gap_behavior).toBe('return_to_garage');
    expect(vsp.vehicle_idle_gap_threshold_minutes).toBe(240);
  });
});
