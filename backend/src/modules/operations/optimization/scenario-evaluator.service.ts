import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Schedule } from '../../database/entities/schedule.entity';
import { BlockAssignment } from '../../database/entities/block-assignment.entity';
import {
  OptimizationRun,
  OptimizationRunStatus,
} from '../../database/entities/optimization-run.entity';
import { TenantContext } from '../../../common/context/tenant-context';
import { OptimizationService } from '../optimization.service';

export interface ScenarioOption {
  id: string;
  name: string;
  description: string;
  // Estado da run (RUNNING enquanto otimizador trabalha; COMPLETED quando há resultado real)
  status: OptimizationRunStatus | 'baseline';
  // Métricas: presentes quando status === COMPLETED ou baseline (current).
  totalCost: number | null;
  vehiclesUsed: number | null;
  tripsUnassigned: number | null;
  cctViolations: number | null;
  feasible: boolean;
  maintenanceWarnings: string[];
  // Rastreabilidade — permite frontend recuperar resultado completo do schedule gerado
  optimizationRunId: number | null;
  resultScheduleId: number | null;
  inputFingerprint: string | null;
  algorithm: string | null;
  startedAt: Date | null;
  completedAt: Date | null;
  errorMessage: string | null;
}

interface ScenarioConfig {
  id: 'cost-optimized' | 'service-optimized' | 'maintenance-aware';
  name: string;
  description: string;
  algorithm: string;
  optimizationParamsOverride: Record<string, any>;
  // Vidaútil de uma run completed antes de re-otimizar (idempotência). Default 30min.
  reuseTtlMs?: number;
}

const SCENARIO_CONFIGS: ScenarioConfig[] = [
  {
    id: 'cost-optimized',
    name: 'Otimizado para Custo',
    description:
      'ILP exato (VCSP+PuLP/CBC) minimizando custo total. Penalidade CCT alta para evitar trade-offs ilegais.',
    algorithm: 'vcsp_pulp',
    optimizationParamsOverride: {
      time_budget_s: 120,
      ilp_timeout_seconds: 120,
      cct_violation_penalty: 1000,
    },
    reuseTtlMs: 30 * 60 * 1000,
  },
  {
    id: 'service-optimized',
    name: 'Otimizado para Serviço',
    description:
      'MCNF + preservação de pares preferenciais — minimiza troca de motorista por viagem (qualidade operacional).',
    algorithm: 'mcnf',
    optimizationParamsOverride: {
      time_budget_s: 90,
      force_round_trip: true,
      preserve_preferred_pairs: true,
      preferred_pair_window_minutes: 60,
      paired_trip_bonus: 100,
    },
    reuseTtlMs: 30 * 60 * 1000,
  },
  {
    id: 'maintenance-aware',
    name: 'Consciente de Manutenção',
    description:
      'Hybrid pipeline considerando janelas de indisponibilidade de veículos (entity VehicleAvailabilityWindow).',
    algorithm: 'hybrid_pipeline',
    optimizationParamsOverride: {
      time_budget_s: 90,
      // O optimizer já recebe vehicles do banco; janelas de manutenção viram restrições de
      // assignment quando vehicle.availability_windows estiver populada. Aqui sinalizamos
      // para o modo operacional considerar isso (consumido pelo evaluator + dispatcher).
      respect_vehicle_availability_windows: true,
    },
    reuseTtlMs: 30 * 60 * 1000,
  },
];

@Injectable()
export class ScenarioEvaluatorService {
  private readonly logger = new Logger(ScenarioEvaluatorService.name);

  constructor(
    @InjectRepository(Schedule)
    private scheduleRepo: Repository<Schedule>,
    @InjectRepository(BlockAssignment)
    private blockRepo: Repository<BlockAssignment>,
    @InjectRepository(OptimizationRun)
    private optimizationRunRepo: Repository<OptimizationRun>,
    private tenantContext: TenantContext,
    private optimizationService: OptimizationService,
  ) {}

  /**
   * Para cada cenário (cost/service/maintenance), garante uma OptimizationRun:
   * - reusa run COMPLETED dentro da TTL para o mesmo baseline schedule,
   * - senão enfileira nova run real no optimizer.
   * Retorna estado atual (status + métricas se já completed) — frontend polla.
   */
  async generateScenarios(scheduleId: number): Promise<ScenarioOption[]> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new NotFoundException('Empresa não identificada.');

    const baseline = await this.scheduleRepo.findOne({
      where: { id: scheduleId, companyId },
      relations: ['blocks'],
    });
    if (!baseline)
      throw new NotFoundException(`Schedule ${scheduleId} não encontrado.`);

    const out: ScenarioOption[] = [this.materializeCurrent(baseline)];

    for (const cfg of SCENARIO_CONFIGS) {
      out.push(await this.ensureScenarioRun(companyId, baseline, cfg));
    }
    return out;
  }

  /**
   * Compara duas runs (ou o baseline) por scenarioId. Lê do banco — nenhum cálculo derivado de cache.
   */
  async compareScenarios(
    scheduleId: number,
    scenario1Id: string,
    scenario2Id: string,
  ): Promise<{
    scenario1: ScenarioOption;
    scenario2: ScenarioOption;
    savings: number;
    savingsPercent: number | null;
    differences: string[];
  }> {
    const scenarios = await this.generateScenarios(scheduleId);
    const s1 = scenarios.find((s) => s.id === scenario1Id);
    const s2 = scenarios.find((s) => s.id === scenario2Id);
    if (!s1 || !s2) throw new NotFoundException('Cenário não encontrado.');

    const c1 = s1.totalCost ?? 0;
    const c2 = s2.totalCost ?? 0;
    const savings = c1 - c2;
    const savingsPercent =
      c1 > 0 ? Math.round(((c1 - c2) / c1) * 1000) / 10 : null;
    const differences: string[] = [];

    if (
      s1.status !== 'baseline' &&
      s1.status !== OptimizationRunStatus.COMPLETED
    ) {
      differences.push(
        `Cenário ${s1.id} ainda em ${s1.status} — comparação parcial.`,
      );
    }
    if (
      s2.status !== 'baseline' &&
      s2.status !== OptimizationRunStatus.COMPLETED
    ) {
      differences.push(
        `Cenário ${s2.id} ainda em ${s2.status} — comparação parcial.`,
      );
    }

    if ((s1.vehiclesUsed ?? 0) !== (s2.vehiclesUsed ?? 0)) {
      const diff = (s2.vehiclesUsed ?? 0) - (s1.vehiclesUsed ?? 0);
      differences.push(
        `Veículos: ${s1.vehiclesUsed ?? '?'} vs ${s2.vehiclesUsed ?? '?'} (${diff > 0 ? '+' : ''}${diff})`,
      );
    }
    if ((s1.tripsUnassigned ?? 0) !== (s2.tripsUnassigned ?? 0)) {
      differences.push(
        `Viagens não atribuídas: ${s1.tripsUnassigned ?? '?'} vs ${s2.tripsUnassigned ?? '?'}`,
      );
    }
    if ((s1.cctViolations ?? 0) !== (s2.cctViolations ?? 0)) {
      differences.push(
        `Violações CCT: ${s1.cctViolations ?? '?'} vs ${s2.cctViolations ?? '?'}`,
      );
    }
    if (c1 !== c2) {
      differences.push(
        `Custo: R$ ${c1.toFixed(2)} vs R$ ${c2.toFixed(2)} (diff R$ ${savings.toFixed(2)}${savingsPercent !== null ? `, ${savingsPercent}%` : ''})`,
      );
    }

    return {
      scenario1: s1,
      scenario2: s2,
      savings,
      savingsPercent,
      differences,
    };
  }

  /** Retorna a run mais recente de um cenário para um schedule baseline (para polling). */
  async getScenarioRun(
    baselineScheduleId: number,
    scenarioId: string,
  ): Promise<OptimizationRun | null> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) return null;
    return this.optimizationRunRepo.findOne({
      where: { companyId, baselineScheduleId, scenarioId },
      order: { createdAt: 'DESC' },
    });
  }

  /**
   * Idempotência por cenário:
   * 1. busca run COMPLETED recente para esse baseline+scenario — se existir, retorna ela
   * 2. busca run RUNNING/PENDING ativa — retorna estado atual sem enfileirar de novo
   * 3. senão, enfileira nova run real via OptimizationService
   */
  private async ensureScenarioRun(
    companyId: number,
    baseline: Schedule,
    cfg: ScenarioConfig,
  ): Promise<ScenarioOption> {
    const reuseTtl = cfg.reuseTtlMs ?? 30 * 60 * 1000;
    const cutoff = new Date(Date.now() - reuseTtl);

    // 1) Reuso de run COMPLETED dentro da TTL
    const completed = await this.optimizationRunRepo
      .createQueryBuilder('run')
      .where('run.companyId = :companyId', { companyId })
      .andWhere('run.baselineScheduleId = :baselineId', {
        baselineId: baseline.id,
      })
      .andWhere('run.scenarioId = :scenarioId', { scenarioId: cfg.id })
      .andWhere('run.status = :status', {
        status: OptimizationRunStatus.COMPLETED,
      })
      .andWhere('run.completedAt > :cutoff', { cutoff })
      .orderBy('run.completedAt', 'DESC')
      .getOne();
    if (completed) {
      this.logger.log(
        `[SCENARIO] reusando run ${completed.id} cenário=${cfg.id} schedule=${baseline.id}`,
      );
      return this.toScenarioOption(cfg, completed);
    }

    // 2) Run em andamento (RUNNING ou PENDING) — não reenfileira
    const inFlight = await this.optimizationRunRepo.findOne({
      where: [
        {
          companyId,
          baselineScheduleId: baseline.id,
          scenarioId: cfg.id,
          status: OptimizationRunStatus.RUNNING,
        },
        {
          companyId,
          baselineScheduleId: baseline.id,
          scenarioId: cfg.id,
          status: OptimizationRunStatus.PENDING,
        },
      ],
      order: { createdAt: 'DESC' },
    });
    if (inFlight) {
      this.logger.log(
        `[SCENARIO] aguardando run em curso ${inFlight.id} cenário=${cfg.id} schedule=${baseline.id}`,
      );
      return this.toScenarioOption(cfg, inFlight);
    }

    // 3) Enfileira nova otimização real
    try {
      const submission = await this.optimizationService.runOptimization(
        companyId,
        cfg.algorithm,
        undefined,
        {
          scenarioId: cfg.id,
          baselineScheduleId: baseline.id,
          optimizationParamsOverride: cfg.optimizationParamsOverride,
          skipTenantLock: true,
        },
      );
      const run = await this.optimizationRunRepo.findOne({
        where: { id: (submission as any).optimizationRunId },
      });
      if (!run) {
        return this.placeholderScenario(
          cfg,
          'Run criada mas não localizada no repositório.',
        );
      }
      this.logger.log(
        `[SCENARIO] nova run ${run.id} cenário=${cfg.id} schedule=${baseline.id} algorithm=${cfg.algorithm}`,
      );
      return this.toScenarioOption(cfg, run);
    } catch (err) {
      this.logger.warn(
        `[SCENARIO] falha ao enfileirar cenário=${cfg.id} schedule=${baseline.id}: ${(err as Error).message}`,
      );
      return this.placeholderScenario(cfg, (err as Error).message);
    }
  }

  private toScenarioOption(
    cfg: ScenarioConfig,
    run: OptimizationRun,
  ): ScenarioOption {
    const metrics = run.metrics ?? {};
    return {
      id: cfg.id,
      name: cfg.name,
      description: cfg.description,
      status: run.status,
      totalCost:
        run.status === OptimizationRunStatus.COMPLETED
          ? Number(metrics.totalCost ?? 0)
          : null,
      vehiclesUsed:
        run.status === OptimizationRunStatus.COMPLETED
          ? Number(metrics.numVehicles ?? 0)
          : null,
      tripsUnassigned:
        run.status === OptimizationRunStatus.COMPLETED
          ? Number(metrics.unassignedTrips ?? 0)
          : null,
      cctViolations:
        run.status === OptimizationRunStatus.COMPLETED
          ? Number(metrics.cctViolations ?? 0)
          : null,
      feasible:
        run.status === OptimizationRunStatus.COMPLETED &&
        Number(metrics.hardIssueCount ?? 0) === 0,
      maintenanceWarnings: [],
      optimizationRunId: run.id,
      resultScheduleId: run.resultScheduleId,
      inputFingerprint: run.inputFingerprint,
      algorithm: run.algorithm,
      startedAt: run.createdAt,
      completedAt: run.completedAt,
      errorMessage: run.errorMessage,
    };
  }

  private placeholderScenario(
    cfg: ScenarioConfig,
    errorMessage: string,
  ): ScenarioOption {
    return {
      id: cfg.id,
      name: cfg.name,
      description: cfg.description,
      status: OptimizationRunStatus.FAILED,
      totalCost: null,
      vehiclesUsed: null,
      tripsUnassigned: null,
      cctViolations: null,
      feasible: false,
      maintenanceWarnings: [],
      optimizationRunId: null,
      resultScheduleId: null,
      inputFingerprint: null,
      algorithm: cfg.algorithm,
      startedAt: null,
      completedAt: null,
      errorMessage,
    };
  }

  private materializeCurrent(baseline: Schedule): ScenarioOption {
    return {
      id: 'current',
      name: 'Cenário Atual',
      description: 'Schedule atualmente em operação (sem re-otimizar).',
      status: 'baseline',
      totalCost: Number(baseline.totalCost ?? 0),
      vehiclesUsed: baseline.blocks?.length ?? 0,
      tripsUnassigned: 0,
      cctViolations: Number(baseline.cctViolations ?? 0),
      feasible: true,
      maintenanceWarnings: [],
      optimizationRunId: null,
      resultScheduleId: baseline.id,
      inputFingerprint: null,
      algorithm: null,
      startedAt: baseline.createdAt,
      completedAt: baseline.createdAt,
      errorMessage: null,
    };
  }
}
