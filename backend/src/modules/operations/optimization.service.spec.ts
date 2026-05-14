import axios from 'axios';
import { Schedule } from '../database/entities/schedule.entity';
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
      find: jest.fn().mockResolvedValue([]),
      findOne: jest.fn().mockResolvedValue(null),
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
      noopRepo as any, // TripRepo
      noopRepo as any, // DriverRepo
      noopRepo as any, // CompanyParametersRepo
      scheduleRepo as any, // ScheduleRepo
      noopRepo as any, // VehicleTypeRepo
      noopRepo as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      {} as any, // DataSource
      gateway as any, // OptimizationGateway
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any, // ConfigService
      { getCompanyId: jest.fn() } as any, // TenantContext
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
    ((service as any).persistResults as jest.Mock).mockResolvedValueOnce('completed');
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

    expect((service as any).persistResults).toHaveBeenCalledWith(
      259,
      16,
      {
        status: 'ok',
        split_groups: 0,
      },
      {},
    );
    expect(gateway.notifyOptimizationFinished).toHaveBeenCalledWith(16, 259, {
      status: 'completed',
    });
    expect(scheduleRepo.update).not.toHaveBeenCalledWith(259, expect.objectContaining({ status: expect.anything() }));
  });

  it('marca a execucao como failed quando o resultado concluido vem com hard violation', async () => {
    ((service as any).persistResults as jest.Mock).mockResolvedValueOnce('failed');
    mockedAxios.get.mockResolvedValueOnce({
      data: {
        status: 'completed',
        result: {
          solver_explanation: { status: 'hard_violation' },
          meta: { hard_constraint_report: { output: { ok: false } } },
        },
      },
    } as any);

    (service as any).pollOptimizerTask('task-invalid', 300, 16);
    await Promise.resolve();
    await Promise.resolve();

    expect((service as any).persistResults).toHaveBeenCalledWith(
      300,
      16,
      expect.objectContaining({
        solver_explanation: { status: 'hard_violation' },
      }),
      {},
    );
    expect(gateway.notifyOptimizationFailed).toHaveBeenCalledWith(
      16,
      'Resultado inválido: solver_explanation.status=hard_violation.',
    );
    expect(gateway.notifyOptimizationFinished).not.toHaveBeenCalled();
  });

  it('propaga parametros de pareamento e VSP avancado para o optimizer', () => {
    const params = {
      force_round_trip: true,
      allow_vehicle_swap: false,
      vehicle_fixed_cost: 1350,
      preferred_pair_window_minutes: 45,
      preserve_preferred_pairs: true,
      min_break_minutes: 30,
      enforce_min_interval: true,
      strict_zero_gap_validation: true,
      strict_operational_mode: true,
      strict_hard_constraints: true,
      strict_gps_validation: false,
      strict_terminal_sync_validation: false,
      group_infeasibility_mode: 'production',
      max_driving_time_minutes: 300,
      min_layover_minutes: 18,
      pullout_counts_in_driver_shift: false,
      pullback_counts_in_driver_shift: false,
      max_shift_minutes: 720,
      max_vehicles: 12,
      ilp_timeout_seconds: 45,
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
    expect(cct.max_driving_minutes).toBe(300);
    expect(cct.enforce_min_interval).toBe(true);
    expect(cct.pullout_counts_in_driver_shift).toBe(false);
    expect(cct.pullback_counts_in_driver_shift).toBe(false);
    expect(cct.strict_zero_gap_validation).toBe(true);
    expect(cct.strict_operational_mode).toBe(true);
    expect(cct.strict_hard_constraints).toBe(true);
    expect(cct.strict_gps_validation).toBe(false);
    expect(cct.strict_terminal_sync_validation).toBe(false);
    expect(cct.group_infeasibility_mode).toBe('production');
    expect(vsp.force_round_trip).toBe(true);
    expect(vsp.allow_vehicle_swap).toBe(false);
    expect(vsp.fixed_vehicle_activation_cost).toBe(1350);
    expect(vsp.min_layover_minutes).toBe(30);
    expect(vsp.enforce_min_interval).toBe(true);
    expect(vsp.strict_zero_gap_validation).toBe(true);
    expect(vsp.strict_operational_mode).toBe(true);
    expect(vsp.strict_hard_constraints).toBe(true);
    expect(vsp.max_vehicles).toBe(12);
    expect(vsp.ilp_timeout_seconds).toBe(45);
    expect(vsp.pair_break_penalty).toBe(2200);
    expect(vsp.paired_trip_bonus).toBe(300);
    expect(vsp.allow_multi_line_block).toBe(false);
    expect(vsp.vehicle_idle_gap_behavior).toBe('return_to_garage');
    expect(vsp.vehicle_idle_gap_threshold_minutes).toBe(240);
    expect(vsp.group_infeasibility_mode).toBe('production');
  });

  it('normaliza percentuais legados antes de montar os parametros CCT', () => {
    const cct = (service as any).buildCctParams({
      waiting_time_pay_pct: 30,
      holiday_extra_pct: 100,
      nocturnal_extra_pct: 20,
      max_driving_time_minutes: 240,
      meal_break_minutes: 15,
      max_shift_minutes: 840,
    });

    expect(cct.waiting_time_pay_pct).toBeCloseTo(0.3);
    expect(cct.holiday_extra_pct).toBeCloseTo(1);
    expect(cct.nocturnal_extra_pct).toBeCloseTo(0.2);
  });

  it('envia trip_group_id bruto e delega a inferencia ao optimizer', async () => {
    const tripRepo = {
      find: jest.fn().mockResolvedValue([
        {
          id: 1,
          tripId: 1001,
          lineId: 11,
          lineCode: '11',
          tripGroupId: null,
          direction: 'outbound',
          startTime: 100,
          endTime: 150,
          originId: 10,
          destinationId: 20,
          duration: 50,
          distanceKm: 12,
        },
        {
          id: 2,
          tripId: 1002,
          lineId: 11,
          lineCode: '11',
          tripGroupId: 501,
          direction: 'return',
          startTime: 160,
          endTime: 210,
          originId: 20,
          destinationId: 10,
          duration: 50,
          distanceKm: 12,
        },
      ]),
      findOne: jest.fn(),
      save: jest.fn(),
      update: jest.fn(),
    };
    const driverRepo = { find: jest.fn().mockResolvedValue([]) };
    const paramRepo = {
      findOne: jest.fn().mockResolvedValue({
        force_round_trip: true,
        allow_vehicle_swap: true,
        group_infeasibility_mode: 'production',
        random_seed: 42,
        pricing_enabled: true,
        use_set_covering: true,
      }),
    };
    const scheduleRepoLocal = {
      findOne: jest.fn().mockResolvedValueOnce(null),
      save: jest.fn().mockResolvedValue({ id: 91, companyId: 16, status: 'processing' }),
      update: jest.fn().mockResolvedValue(undefined),
    };

    mockedAxios.post.mockResolvedValueOnce({ data: { task_id: 'task-group-sync' } } as any);

    const localService = new OptimizationService(
      tripRepo as any,
      driverRepo as any,
      paramRepo as any,
      scheduleRepoLocal as any,
      { find: jest.fn().mockResolvedValue([]) } as any, // VehicleTypeRepo
      { find: jest.fn().mockResolvedValue([]) } as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      {} as any,
      gateway as any,
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any,
      { getCompanyId: jest.fn() } as any,
    );
    (localService as any).pollOptimizerTask = jest.fn();
    (localService as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };

    await localService.runOptimization(16, 'hybrid_pipeline');

    const payload = mockedAxios.post.mock.calls[0][1] as any;
    expect(payload.trips).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 1, trip_group_id: null }),
        expect.objectContaining({ id: 2, trip_group_id: 501 }),
      ]),
    );
    expect(payload.request_metadata).toEqual({
      trip_group_inference_mode: 'optimizer_only',
      backend_trip_group_stats: {
        group_count: 0,
        grouped_trip_count: 0,
        max_group_size: 0,
      },
      company_id: 16,
      scenario_id: 'schedule-91',
      run_id: 91,
      baseline_schedule_id: null,
      requested_operational_quality_mode: null,
      persisted_operational_quality_mode: null,
      effective_operational_quality_mode: 'balanced',
      operational_quality_mode: 'balanced',
    });
    expect(payload.cct_params.group_infeasibility_mode).toBe('production');
    expect(payload.vsp_params.group_infeasibility_mode).toBe('production');
    expect(payload.optimization_params.group_infeasibility_mode).toBe('production');
    expect(payload.optimization_params.random_seed).toBe(42);
    expect(payload.optimization_params.pricing_enabled).toBe(true);
    expect(payload.optimization_params.use_set_covering).toBe(true);
  });

  it('persistResults copia dados operacionais de meta mesmo quando a raiz vem com defaults vazios', async () => {
    const manager = {
      create: jest.fn((_entity, data) => data),
      save: jest.fn().mockResolvedValue(undefined),
      update: jest.fn().mockResolvedValue(undefined),
    };
    const localService = new OptimizationService(
      {} as any, // TripRepo
      {} as any, // DriverRepo
      {} as any, // CompanyParametersRepo
      {} as any, // ScheduleRepo
      {} as any, // VehicleTypeRepo
      {} as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      { transaction: async (cb: any) => cb(manager) } as any, // DataSource
      gateway as any, // OptimizationGateway
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any, // ConfigService
      { getCompanyId: jest.fn() } as any, // TenantContext
    );
    (localService as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };

    await (localService as any).persistResults(
      55,
      16,
      {
        blocks: [],
        duties: [],
        vehicles: 7,
        crew: 5,
        total_cost: 1234,
        total_trips: 99,
        unassigned_trips: 0,
        cct_violations: 0,
        vsp_algorithm: 'hybrid_pipeline',
        rejected_scenarios: [],
        justification: [],
        trade_offs: [],
        operational_quality_decision: {},
        meta: {
          chosen_scenario: 'current_plan',
          rejected_scenarios: [{ scenario_id: 'strict_plan' }],
          justification: ['Mantem estabilidade operacional.'],
          trade_offs: ['Aumenta custo total.'],
          operational_quality_decision: {
            mode: 'strict',
            chosen_scenario: 'current_plan',
            chosen_title: 'Plano sem excecoes criticas',
            rejected_scenarios: [{ scenario_id: 'strict_plan' }],
            justification: ['Mantem estabilidade operacional.'],
            trade_offs: ['Aumenta custo total.'],
          },
        },
      },
      {
        optimizationParams: {
          operational_quality_mode: 'strict',
        },
      },
    );

    expect(manager.update).toHaveBeenCalledWith(
      Schedule,
      55,
      expect.objectContaining({
        metadata: expect.objectContaining({
          operational_quality_mode: 'strict',
          chosen_scenario: 'current_plan',
          rejected_scenarios: [{ scenario_id: 'strict_plan' }],
          justification: ['Mantem estabilidade operacional.'],
          trade_offs: ['Aumenta custo total.'],
          operational_quality_decision: expect.objectContaining({
            mode: 'strict',
            chosen_scenario: 'current_plan',
          }),
        }),
      }),
    );
  });

  it('persistResults le chosen_scenario e operational_quality_decision de result.result.meta', async () => {
    const manager = {
      create: jest.fn((_entity, data) => data),
      save: jest.fn().mockResolvedValue(undefined),
      update: jest.fn().mockResolvedValue(undefined),
    };
    const localService = new OptimizationService(
      {} as any, // TripRepo
      {} as any, // DriverRepo
      {} as any, // CompanyParametersRepo
      {} as any, // ScheduleRepo
      {} as any, // VehicleTypeRepo
      {} as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      { transaction: async (cb: any) => cb(manager) } as any, // DataSource
      gateway as any, // OptimizationGateway
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any, // ConfigService
      { getCompanyId: jest.fn() } as any, // TenantContext
    );
    (localService as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };

    await (localService as any).persistResults(
      56,
      16,
      {
        blocks: [],
        duties: [],
        vehicles: 3,
        crew: 2,
        total_cost: 456,
        total_trips: 12,
        unassigned_trips: 0,
        cct_violations: 0,
        vsp_algorithm: 'hybrid_pipeline',
        result: {
          meta: {
            chosen_scenario: 'lowest_cost',
            rejected_scenarios: [{ scenario_id: 'current_plan' }],
            justification: ['Reduz custo total.'],
            trade_offs: ['Menor folga operacional.'],
            operational_quality_decision: {
              mode: 'optimized',
              chosen_scenario: 'lowest_cost',
              chosen_title: 'Menor custo',
              rejected_scenarios: [{ scenario_id: 'current_plan' }],
              justification: ['Reduz custo total.'],
              trade_offs: ['Menor folga operacional.'],
            },
          },
        },
      },
      {
        optimizationParams: {
          operational_quality_mode: 'optimized',
        },
      },
    );

    expect(manager.update).toHaveBeenCalledWith(
      Schedule,
      56,
      expect.objectContaining({
        metadata: expect.objectContaining({
          operational_quality_mode: 'optimized',
          chosen_scenario: 'lowest_cost',
          rejected_scenarios: [{ scenario_id: 'current_plan' }],
          justification: ['Reduz custo total.'],
          trade_offs: ['Menor folga operacional.'],
          operational_quality_decision: expect.objectContaining({
            mode: 'optimized',
            chosen_scenario: 'lowest_cost',
          }),
        }),
      }),
    );
  });

  it('latest-schedule monta resultSummary com chosen_scenario e decision vindos do metadata', async () => {
    const scheduleRepoLocal = {
      findOne: jest.fn().mockResolvedValue({
        id: 88,
        companyId: 16,
        status: 'completed',
        totalCost: 321,
        cctViolations: 0,
        createdAt: new Date('2026-04-30T11:20:40.357Z'),
        updatedAt: new Date('2026-04-30T11:20:50.437Z'),
        metadata: {
          hard_issue_count: 0,
          soft_issue_count: 1,
          trip_group_audit: {
            split_groups: 0,
            same_block_groups: 149,
          },
          operational_quality_mode: 'optimized',
          operational_quality_decision: {
            mode: 'optimized',
            chosen_scenario: 'lowest_cost',
            chosen_title: 'Plano mais barato',
            rejected_scenarios: [{ scenario_id: 'current_plan' }],
            justification: ['Menor custo total.'],
            trade_offs: ['Aceita mais risco operacional.'],
          },
        },
      }),
    };
    const mockedBlockRepo = {
      find: jest.fn().mockResolvedValue([]),
    };
    const mockedDutyRepo = {
      find: jest.fn().mockResolvedValue([
        {
          dutyId: 463,
          tripIds: [],
          cost: 123,
          metadata: {
            start_time: 315,
            end_time: 829,
            work_time: 296,
            spread_time: 514,
            duty_time_segments: [],
            operational_time_report: { mandatory_rest_required: true },
            quality_metrics: { soft_issue_count: 1 },
          },
        },
      ]),
    };
    const localService = new OptimizationService(
      { find: jest.fn() } as any, // TripRepo
      {} as any, // DriverRepo
      {} as any, // CompanyParametersRepo
      scheduleRepoLocal as any, // ScheduleRepo
      {} as any, // VehicleTypeRepo
      {} as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      {
        getRepository: jest.fn()
          .mockReturnValueOnce(mockedBlockRepo)
          .mockReturnValueOnce(mockedDutyRepo),
      } as any, // DataSource
      gateway as any, // OptimizationGateway
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any, // ConfigService
      { getCompanyId: jest.fn() } as any, // TenantContext
    );
    (localService as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };

    const latest = await localService.getLatestSchedule(16);

    expect(latest.resultSummary.chosen_scenario).toBe('lowest_cost');
    expect(latest.resultSummary.operational_quality_mode).toBe('optimized');
    expect(latest.resultSummary.rejected_scenarios).toEqual([{ scenario_id: 'current_plan' }]);
    expect(latest.resultSummary.operational_quality_decision).toEqual(
      expect.objectContaining({
        mode: 'optimized',
        chosen_scenario: 'lowest_cost',
      }),
    );
    expect(latest.resultSummary.hardIssueCount).toBe(0);
    expect(latest.resultSummary.softIssueCount).toBe(1);
    expect(latest.resultSummary.tripGroupAudit).toEqual(
      expect.objectContaining({
        split_groups: 0,
        same_block_groups: 149,
      }),
    );
    expect(latest.chosen_scenario).toBe('lowest_cost');
    expect(latest.operational_quality_mode).toBe('optimized');
    expect(latest.hardIssueCount).toBe(0);
    expect(latest.softIssueCount).toBe(1);
    expect(latest.trip_group_audit).toEqual(
      expect.objectContaining({
        split_groups: 0,
        same_block_groups: 149,
      }),
    );
    expect(latest.operational_quality_decision).toEqual(
      expect.objectContaining({
        mode: 'optimized',
        chosen_scenario: 'lowest_cost',
      }),
    );
    expect(latest.duties).toHaveLength(1);
    expect(latest.duties[0]).toEqual(
      expect.objectContaining({
        duty_id: 463,
        operational_time_report: { mandatory_rest_required: true },
        quality_metrics: { soft_issue_count: 1 },
        duty_time_segments: [],
      }),
    );
  });

  it.each([
    ['strict'],
    ['balanced'],
    ['optimized'],
  ])('envia override operational_quality_mode=%s ao optimizer', async (mode) => {
    mockedAxios.post.mockReset();
    mockedAxios.post.mockResolvedValueOnce({ data: { task_id: `task-${mode}` } } as any);

    const tripRepo = {
      find: jest.fn().mockResolvedValue([
        {
          id: 1,
          tripId: 1001,
          lineId: 11,
          lineCode: '11',
          tripGroupId: null,
          direction: 'outbound',
          startTime: 100,
          endTime: 150,
          originId: 10,
          destinationId: 20,
          duration: 50,
          distanceKm: 12,
        },
      ]),
    };
    const scheduleRepoLocal = {
      findOne: jest.fn().mockResolvedValueOnce(null),
      save: jest.fn().mockResolvedValue({ id: 901, companyId: 16, status: 'processing' }),
      update: jest.fn().mockResolvedValue(undefined),
    };
    const localService = new OptimizationService(
      tripRepo as any, // TripRepo
      { find: jest.fn().mockResolvedValue([]) } as any, // DriverRepo
      {
        findOne: jest.fn().mockResolvedValue({
          force_round_trip: true,
          allow_vehicle_swap: true,
          random_seed: 42,
        }),
      } as any, // CompanyParametersRepo
      scheduleRepoLocal as any, // ScheduleRepo
      { find: jest.fn().mockResolvedValue([]) } as any, // VehicleTypeRepo
      { find: jest.fn().mockResolvedValue([]) } as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      {} as any, // DataSource
      gateway as any, // OptimizationGateway
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any, // ConfigService
      { getCompanyId: jest.fn() } as any, // TenantContext
    );
    (localService as any).pollOptimizerTask = jest.fn();
    (localService as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };

    await localService.runOptimization(16, 'hybrid_pipeline', mode);

    const payload = mockedAxios.post.mock.calls[0][1] as any;
    const pollingContext = ((localService as any).pollOptimizerTask as jest.Mock).mock.calls[0][3];
    expect(payload.optimization_params.operational_quality_mode).toBe(mode);
    expect(payload.request_metadata.operational_quality_mode).toBe(mode);
    expect(payload.request_metadata.requested_operational_quality_mode).toBe(mode);
    expect(payload.request_metadata.effective_operational_quality_mode).toBe(mode);
    expect(pollingContext.request_metadata.operational_quality_mode).toBe(mode);
  });

  it('usa modo persistido quando nao ha override e cai para balanced quando nao existe persisted', async () => {
    mockedAxios.post.mockReset();
    mockedAxios.post.mockResolvedValue({ data: { task_id: 'task-default-mode' } } as any);

    const tripRepo = {
      find: jest.fn().mockResolvedValue([
        {
          id: 1,
          tripId: 1001,
          lineId: 11,
          lineCode: '11',
          tripGroupId: null,
          direction: 'outbound',
          startTime: 100,
          endTime: 150,
          originId: 10,
          destinationId: 20,
          duration: 50,
          distanceKm: 12,
        },
      ]),
    };
    const scheduleRepoLocal = {
      findOne: jest.fn().mockResolvedValueOnce(null).mockResolvedValueOnce(null),
      save: jest.fn()
        .mockResolvedValueOnce({ id: 902, companyId: 16, status: 'processing' })
        .mockResolvedValueOnce({ id: 903, companyId: 16, status: 'processing' }),
      update: jest.fn().mockResolvedValue(undefined),
    };
    const paramRepo = {
      findOne: jest.fn()
        .mockResolvedValueOnce({
          force_round_trip: true,
          allow_vehicle_swap: true,
          operational_quality_mode: 'optimized',
        })
        .mockResolvedValueOnce({
          force_round_trip: true,
          allow_vehicle_swap: true,
          operational_quality_mode: null,
        }),
    };
    const noopMock = {
      find: jest.fn().mockResolvedValue([]),
      findOne: jest.fn().mockResolvedValue(null),
    };
    const localService = new OptimizationService(
      tripRepo as any,
      { find: jest.fn().mockResolvedValue([]) } as any,
      paramRepo as any,
      scheduleRepoLocal as any,
      noopMock as any, // VehicleTypeRepo
      noopMock as any, // VehicleRepo
      { save: jest.fn().mockResolvedValue({ id: 7777 }), update: jest.fn().mockResolvedValue(undefined), findOne: jest.fn().mockResolvedValue(null) } as any, // OptimizationRunRepo
      {} as any,
      gateway as any,
      { get: jest.fn().mockReturnValue('test-strong-key-for-specs-only') } as any,
      { getCompanyId: jest.fn() } as any,
    );
    (localService as any).pollOptimizerTask = jest.fn();
    (localService as any).logger = {
      warn: jest.fn(),
      error: jest.fn(),
      log: jest.fn(),
    };

    await localService.runOptimization(16, 'hybrid_pipeline');
    await localService.runOptimization(16, 'hybrid_pipeline');

    const payloadWithPersisted = mockedAxios.post.mock.calls[0][1] as any;
    const payloadWithFallback = mockedAxios.post.mock.calls[1][1] as any;

    expect(payloadWithPersisted.optimization_params.operational_quality_mode).toBe('optimized');
    expect(payloadWithFallback.optimization_params.operational_quality_mode).toBe('balanced');
  });

  it('mantem codigo de erro quando o polling atinge timeout controlado', async () => {
    mockedAxios.get.mockResolvedValue({ data: { status: 'processing' } } as any);
    (service as any).persistFailure = jest.fn().mockResolvedValue(undefined);

    (service as any).pollOptimizerTask('task-timeout', 777, 16, {
      pollingMaxAttemptsOverride: 1,
    });

    await jest.advanceTimersByTimeAsync(5000);
    await Promise.resolve();

    expect((service as any).persistFailure).toHaveBeenCalledWith(
      777,
      16,
      expect.objectContaining({
        error_type: 'timeout',
        error_code: 'OPTIMIZER_POLLING_TIMEOUT',
        task_id: 'task-timeout',
      }),
    );
  });
});
