/**
 * Formatadores específicos do módulo de otimização.
 *
 * Formatadores genéricos (moeda, duração, HH:MM, percent, etc.) são
 * re-exportados de `@/lib/format` — fonte única de verdade. Este arquivo
 * mantém apenas o que é específico do domínio de otimização (direção,
 * comparações, janelas de bloco, policies de intervalo).
 */
import type {
  OptimizationRun,
  OptimizationReproducibility, OptimizationPerformance,
  OptimizationComparisonMetric,
  OptimizationBlock, OptimizationDuty, TripDetail,
} from '../../_types';

interface OptimizationSettings {
  cctMinBreakMinutes?: number;
  cctMealBreakMinutes?: number;
  cctMinLayoverMinutes?: number;
  connectionToleranceMinutes?: number;
  [key: string]: unknown;
}
import {
  asRecord,
  toMinuteValue,
  minToDuration,
  minToHHMM,
  fmtCurrency,
  fmtSignedCurrency,
  fmtNumber,
  fmtSignedNumber,
  fmtSignedPercent,
  fmtElapsedMsCompact,
  labelizeKey,
  truncateMiddle,
} from '@/lib/format';

// Re-export para preservar imports existentes (`from '../_helpers/formatters'`).
export {
  asRecord,
  toMinuteValue,
  minToDuration,
  minToHHMM,
  fmtCurrency,
  fmtSignedCurrency,
  fmtNumber,
  fmtSignedNumber,
  fmtSignedPercent,
  fmtElapsedMsCompact,
  labelizeKey,
  truncateMiddle,
};

// ── Direção (específico do domínio) ──
export function directionLabel(direction?: 'outbound' | 'inbound' | string) {
  const normalized = direction?.toLowerCase();
  if (normalized === 'outbound' || normalized === 'ida') return 'Ida';
  if (normalized === 'inbound' || normalized === 'volta') return 'Volta';
  return 'Sem sentido';
}

// ── Comparação ──
export function formatComparisonValue(
  key: string,
  value?: number | null,
  category: 'metrics' | 'performance' = 'metrics',
  signed = false,
): string {
  const lowerKey = key.toLowerCase();
  if (
    category === 'performance' || lowerKey.includes('elapsed') ||
    lowerKey.endsWith('_ms') || lowerKey.includes('solver_ms') ||
    lowerKey.includes('validation_ms') || lowerKey.includes('enrichment_ms')
  ) {
    return signed ? fmtSignedNumber(value, 'ms') : fmtNumber(value, 'ms');
  }
  if (lowerKey.includes('cost')) return signed ? fmtSignedCurrency(value) : fmtCurrency(value);
  return signed ? fmtSignedNumber(value) : fmtNumber(value);
}

export type ComparisonPreference = 'lower' | 'higher' | 'neutral';

export function getComparisonPreference(
  key: string,
  category: 'metrics' | 'performance' = 'metrics',
): ComparisonPreference {
  if (category === 'performance') return 'lower';
  switch (key) {
    case 'vehicles': case 'crew': case 'totalCost': case 'cctViolations':
    case 'hardIssues': case 'softIssues': case 'unassignedTrips': case 'uncoveredBlocks':
      return 'lower';
    case 'totalTrips': return 'neutral';
    default: return key.toLowerCase().includes('cost') ? 'lower' : 'neutral';
  }
}

export function getComparisonDeltaStatus(
  metric: OptimizationComparisonMetric,
  preference: ComparisonPreference,
): { tone: 'success' | 'error' | 'neutral'; label: string } {
  if (!metric.delta) return { tone: 'neutral', label: 'Igual' };
  if (preference === 'neutral') return { tone: 'neutral', label: 'Mudou' };
  const improved = preference === 'lower' ? metric.delta < 0 : metric.delta > 0;
  return improved ? { tone: 'success', label: 'Melhora' } : { tone: 'error', label: 'Piora' };
}

// ── Reprodutibilidade ──
export function readReproValue<T = unknown>(
  reproducibility: OptimizationReproducibility | null | undefined,
  snakeKey: keyof OptimizationReproducibility,
  camelKey?: keyof OptimizationReproducibility,
): T | null {
  const camelValue = camelKey ? reproducibility?.[camelKey] : undefined;
  return (camelValue ?? reproducibility?.[snakeKey] ?? null) as T | null;
}

export function getRunAuditSnapshot(run: OptimizationRun): {
  inputHash: string | null;
  paramsHash: string | null;
  timeBudgetS: number | null;
  totalElapsedMs: number | null;
} {
  const params = asRecord(run.params) ?? {};
  const resolvedParams = asRecord(params.resolved) ?? {};
  const versioning = asRecord(params.versioning);
  const resultSummary = asRecord(run.resultSummary) ?? {};
  const meta = asRecord(resultSummary.meta) ?? {};
  const reproducibility = (resultSummary.reproducibility ?? meta.reproducibility ?? null) as OptimizationReproducibility | null;
  const performance = (resultSummary.performance ?? meta.performance ?? null) as OptimizationPerformance | null;
  const timeBudgetValue =
    readReproValue<number>(reproducibility, 'time_budget_s', 'timeBudgetS') ??
    resolvedParams.timeBudgetSeconds ?? params.timeBudgetSeconds ?? null;
  const elapsedValue = performance?.total_elapsed_ms ?? run.durationMs ?? null;

  return {
    inputHash:
      readReproValue<string>(reproducibility, 'input_hash', 'inputHash') ??
      (typeof versioning?.inputHash === 'string' ? versioning.inputHash : null),
    paramsHash: readReproValue<string>(reproducibility, 'params_hash', 'paramsHash') ?? null,
    timeBudgetS: Number.isFinite(Number(timeBudgetValue)) ? Number(timeBudgetValue) : null,
    totalElapsedMs: Number.isFinite(Number(elapsedValue)) ? Number(elapsedValue) : null,
  };
}

// ── Display Windows ──
export function getDutyDisplayWindow(duty: OptimizationDuty): { start: number | null; end: number | null } {
  const meta = asRecord(duty.meta);
  return {
    start: toMinuteValue(meta?.duty_start_minutes) ?? toMinuteValue(duty.start_time),
    end: toMinuteValue(meta?.duty_end_minutes) ?? toMinuteValue(duty.end_time),
  };
}

export function getBlockDisplayWindow(block: OptimizationBlock | Record<string, any>): { start: number | null; end: number | null } {
  const b = block as Record<string, unknown>;
  const meta = asRecord(b.meta as Record<string, unknown> | undefined);
  return {
    start: toMinuteValue(meta?.operational_start_minutes) ?? toMinuteValue(b.start_time as number | undefined),
    end: toMinuteValue(meta?.operational_end_minutes) ?? toMinuteValue(b.end_time as number | undefined),
  };
}

export function getTripPublicId(trip: Partial<TripDetail> | Record<string, any>): number | null {
  const t = trip as Partial<TripDetail>;
  const value = t.trip_id ?? t.id;
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

// ── Terminais ──
export function getTerminalDisplayName(
  terminalId: number | string | null | undefined,
  terminalName: string | null | undefined,
  terminalsMap: Record<string, string>,
): string {
  if (terminalId != null) {
    const mapped = terminalsMap[String(terminalId)];
    if (mapped) return mapped;
  }
  if (terminalName) return terminalName;
  if (terminalId != null) return String(terminalId);
  return '--';
}

// ── Trip Intervals ──
export type TripIntervalClassification = 'intervalo_normal' | 'descanso_refeicao' | 'ociosa';
export type TripIntervalViewScope = 'crew' | 'vehicle';

export interface TripIntervalPolicy {
  minBreakMinutes: number;
  mealBreakMinutes: number;
  minLayoverMinutes: number;
  connectionToleranceMinutes: number;
}

export function buildTripIntervalPolicy(
  run: OptimizationRun,
  activeSettings: OptimizationSettings | null,
): TripIntervalPolicy {
  const resolved = getResolvedRunParams(run);
  return {
    minBreakMinutes: toMinuteValue(resolved.cct.min_break_minutes) ?? activeSettings?.cctMinBreakMinutes ?? 30,
    mealBreakMinutes: toMinuteValue(resolved.cct.meal_break_minutes) ?? activeSettings?.cctMealBreakMinutes ?? 60,
    minLayoverMinutes: toMinuteValue(resolved.vsp.min_layover_minutes) ?? toMinuteValue(resolved.cct.min_layover_minutes) ?? activeSettings?.cctMinLayoverMinutes ?? 8,
    connectionToleranceMinutes: toMinuteValue(resolved.cct.connection_tolerance_minutes) ?? activeSettings?.connectionToleranceMinutes ?? 0,
  };
}

export function getResolvedRunParams(run: OptimizationRun): { cct: Record<string, any>; vsp: Record<string, any> } {
  const params = asRecord(run.params);
  const resolved = asRecord(params?.resolved);
  return { cct: asRecord(resolved?.cct) ?? {}, vsp: asRecord(resolved?.vsp) ?? {} };
}

export function getTripIntervalClassificationLabel(classification: TripIntervalClassification): string {
  if (classification === 'descanso_refeicao') return 'Descanso/Refeição';
  if (classification === 'ociosa') return 'Ociosa';
  return 'Intervalo Normal';
}

export function getTripIntervalClassificationColor(classification: TripIntervalClassification): 'default' | 'success' | 'warning' {
  if (classification === 'descanso_refeicao') return 'success';
  if (classification === 'ociosa') return 'warning';
  return 'default';
}

export function classifyTripInterval({
  gapMinutes, isBoundary, isMealBreakWindow, viewScope,
}: {
  gapMinutes: number; isBoundary: boolean; isMealBreakWindow: boolean; viewScope: TripIntervalViewScope;
}): TripIntervalClassification {
  if (gapMinutes <= 0) return 'intervalo_normal';
  if (isBoundary) return 'ociosa';
  if (viewScope === 'crew' && isMealBreakWindow) return 'descanso_refeicao';
  return 'intervalo_normal';
}

export type IdleWindow = {
  start: number;
  end: number;
  duration: number;
  kind: 'apoio' | TripIntervalClassification;
};

export function formatIdleWindowLabel(window: IdleWindow): string {
  const prefix = window.kind === 'apoio' ? 'Apoio' : getTripIntervalClassificationLabel(window.kind);
  return `${prefix} ${minToHHMM(window.start)}-${minToHHMM(window.end)} (${minToDuration(window.duration)})`;
}
