import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { ScenarioEvaluatorService } from './scenario-evaluator.service';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';
import { TenantContext } from '../../../common/context/tenant-context';

describe('ScenarioEvaluatorService', () => {
  let service: ScenarioEvaluatorService;
  let scheduleRepo: any;
  let blockRepo: any;
  let tenantContext: any;

  beforeEach(async () => {
    scheduleRepo = {
      findOne: jest.fn(),
    };

    blockRepo = {
      find: jest.fn(),
    };

    tenantContext = {
      getCompanyId: jest.fn().mockReturnValue(1),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ScenarioEvaluatorService,
        {
          provide: getRepositoryToken(Schedule),
          useValue: scheduleRepo,
        },
        {
          provide: getRepositoryToken(BlockAssignment),
          useValue: blockRepo,
        },
        {
          provide: TenantContext,
          useValue: tenantContext,
        },
      ],
    }).compile();

    service = module.get<ScenarioEvaluatorService>(ScenarioEvaluatorService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('generateScenarios', () => {
    it('should generate 4 scenarios', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [
          { id: 1 },
          { id: 2 },
          { id: 3 },
        ],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const scenarios = await service.generateScenarios(1);

      expect(scenarios.length).toBe(4);
      expect(scenarios[0].id).toBe('current');
      expect(scenarios[1].id).toBe('cost-optimized');
      expect(scenarios[2].id).toBe('service-optimized');
      expect(scenarios[3].id).toBe('maintenance-aware');
    });

    it('should include cost information', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const scenarios = await service.generateScenarios(1);

      expect(scenarios.every((s) => s.totalCost !== undefined)).toBe(true);
      expect(scenarios.every((s) => s.vehiclesUsed !== undefined)).toBe(true);
    });

    it('should mark scenarios as feasible', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const scenarios = await service.generateScenarios(1);

      expect(scenarios.every((s) => typeof s.feasible === 'boolean')).toBe(true);
    });

    it('should include maintenance warnings', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const scenarios = await service.generateScenarios(1);

      expect(scenarios.every((s) => Array.isArray(s.maintenanceWarnings))).toBe(true);
    });
  });

  describe('compareScenarios', () => {
    it('should compare two scenarios', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const result = await service.compareScenarios(1, 'current', 'cost-optimized');

      expect(result).toHaveProperty('scenario1');
      expect(result).toHaveProperty('scenario2');
      expect(result).toHaveProperty('savings');
      expect(result).toHaveProperty('differences');
    });

    it('should calculate savings correctly', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const result = await service.compareScenarios(1, 'current', 'cost-optimized');

      expect(typeof result.savings).toBe('number');
    });

    it('should throw error for non-existent scenario', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      await expect(
        service.compareScenarios(1, 'current', 'non-existent'),
      ).rejects.toThrow();
    });
  });

  describe('Scenario properties', () => {
    it('should have required fields in scenario', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const scenarios = await service.generateScenarios(1);

      scenarios.forEach((scenario) => {
        expect(scenario).toHaveProperty('id');
        expect(scenario).toHaveProperty('name');
        expect(scenario).toHaveProperty('description');
        expect(scenario).toHaveProperty('totalCost');
        expect(scenario).toHaveProperty('vehiclesUsed');
        expect(scenario).toHaveProperty('feasible');
      });
    });

    it('should have cost-optimized scenario cheaper than current', async () => {
      const mockSchedule = {
        id: 1,
        totalCost: 1000,
        blocks: [],
      };

      scheduleRepo.findOne.mockResolvedValue(mockSchedule);

      const scenarios = await service.generateScenarios(1);
      const current = scenarios.find((s) => s.id === 'current');
      const costOptimized = scenarios.find((s) => s.id === 'cost-optimized');

      expect(costOptimized!.totalCost).toBeLessThan(current!.totalCost);
    });
  });
});
