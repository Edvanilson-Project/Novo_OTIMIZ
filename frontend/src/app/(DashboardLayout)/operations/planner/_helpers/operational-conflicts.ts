import type { OptimizationResultSummary } from '../../_types';

interface TripWithTimes {
  start_time: number;
  end_time: number;
  origin_id?: number | string | null;
  destination_id?: number | string | null;
  destination_terminal_id?: number | null;
  direction?: 'outbound' | 'inbound' | string;
  is_paired?: boolean;
}

function resolvedPolicy(res: OptimizationResultSummary) {
  const summary = res as Record<string, unknown>;
  const meta = (summary.metadata ?? summary.meta ?? {}) as Record<string, unknown>;
  const input = (meta.input ?? summary.resolved_params ?? {}) as Record<string, unknown>;
  const cct = (input.cct_params ?? input.cct ?? {}) as Record<string, unknown>;
  const vsp = (input.vsp_params ?? input.vsp ?? {}) as Record<string, unknown>;
  return {
    minBreakMinutes: Number(cct.min_break_minutes ?? 30),
    mealBreakMinutes: Number(cct.meal_break_minutes ?? cct.min_break_minutes ?? 30),
    minLayoverMinutes: Number(vsp.min_layover_minutes ?? cct.min_layover_minutes ?? cct.min_break_minutes ?? 8),
  };
}

export interface OperationalConflict {
  type: 'overlap' | 'time-violation' | 'no-return' | 'break-violation' | 'unrealistic' | 'paired-orphan' | 'layover-violation';
  severity: 'error' | 'warning';
  blockId?: number;
  message: string;
  count: number;
}

/**
 * Detect operational conflicts in optimization result
 * Conflicts: overlapping trips, time violations, missing returns to depot, break violations
 */
export function detectOperationalConflicts(res: OptimizationResultSummary): OperationalConflict[] {
  const conflicts: OperationalConflict[] = [];
  const { blocks = [] } = res;
  const policy = resolvedPolicy(res);

  // Check each block for conflicts
  blocks.forEach((block) => {
    const tripDetails = block.trip_details ?? (block.trips || []);
    const trips: TripWithTimes[] = tripDetails
      .filter(t => typeof t === 'object' && t != null && 'start_time' in t && 'end_time' in t)
      .map(t => t as unknown as TripWithTimes)
      .sort((a, b) => a.start_time - b.start_time);

    // Detect overlapping trips (impossible state)
    for (let i = 0; i < trips.length - 1; i++) {
      const current = trips[i];
      const next = trips[i + 1];

      if (current.end_time > next.start_time) {
        conflicts.push({
          type: 'overlap',
          severity: 'error',
          blockId: block.block_id,
          message: `Bloco ${block.block_id}: Viagens sobrepostas detectadas (impossível)`,
          count: 1,
        });
        break;
      }

      // Detect unrealistic gaps (< 2 minutes between trips)
      const gap = next.start_time - current.end_time;
      if (gap < 2 && gap >= 0) {
        conflicts.push({
          type: 'unrealistic',
          severity: 'warning',
          blockId: block.block_id,
          message: `Bloco ${block.block_id}: Intervalo muito curto entre viagens (${gap}min)`,
          count: 1,
        });
        break;
      }
    }

    // Detect break violations using the same break parameters sent to the solver.
    if (trips.length >= 2) {
      const blockStart = trips[0].start_time;
      const blockEnd = trips[trips.length - 1].end_time;
      const blockDuration = blockEnd - blockStart;

      if (blockDuration >= 360) { // 6 hours
        let maxGap = 0;
        for (let i = 0; i < trips.length - 1; i++) {
          const gap = trips[i + 1].start_time - trips[i].end_time;
          maxGap = Math.max(maxGap, gap);
        }

        const requiredBreak = Math.max(policy.minBreakMinutes, policy.mealBreakMinutes);
        if (maxGap < requiredBreak && blockDuration >= 360) {
          conflicts.push({
            type: 'break-violation',
            severity: 'warning',
            blockId: block.block_id,
            message: `Bloco ${block.block_id}: Nenhum intervalo ≥${requiredBreak}min em jornada de ${Math.round(blockDuration / 60)}h`,
            count: 1,
          });
        }
      }
    }

    // Detect paired-orphan: paired trips without matching counterpart direction
    const pairedTrips = trips.filter(t => t.is_paired);
    if (pairedTrips.length > 0) {
      const outbound = pairedTrips.filter(t => t.direction === 'outbound').length;
      const inbound = pairedTrips.filter(t => t.direction === 'inbound').length;
      if (outbound !== inbound) {
        conflicts.push({
          type: 'paired-orphan',
          severity: 'warning',
          blockId: block.block_id,
          message: `Bloco ${block.block_id}: Viagem pareada sem retorno correspondente (ida: ${outbound}, volta: ${inbound})`,
          count: 1,
        });
      }
    }

    // Detect layover-violation: gap at same terminal outside configured VSP window.
    const LAYOVER_MIN = policy.minLayoverMinutes;
    const LAYOVER_MAX = 90;
    for (let i = 0; i < trips.length - 1; i++) {
      const curr = trips[i];
      const next = trips[i + 1];
      const sameTerminal =
        curr.destination_id != null &&
        next.origin_id != null &&
        String(curr.destination_id) === String(next.origin_id);
      if (sameTerminal) {
        const layover = next.start_time - curr.end_time;
        if (layover < LAYOVER_MIN) {
          conflicts.push({
            type: 'layover-violation',
            severity: 'warning',
            blockId: block.block_id,
            message: `Bloco ${block.block_id}: Layover insuficiente no terminal (${layover}min < ${LAYOVER_MIN}min mínimo)`,
            count: 1,
          });
          break;
        }
        if (layover > LAYOVER_MAX) {
          conflicts.push({
            type: 'layover-violation',
            severity: 'warning',
            blockId: block.block_id,
            message: `Bloco ${block.block_id}: Layover excessivo no terminal (${layover}min > ${LAYOVER_MAX}min máximo)`,
            count: 1,
          });
          break;
        }
      }
    }

    // Detect missing return to depot (last trip not ending at depot)
    const lastTrip = trips[trips.length - 1];
    if (lastTrip && lastTrip.destination_terminal_id && lastTrip.destination_terminal_id !== 1) {
      // Assuming terminal_id 1 is depot/garagem
      conflicts.push({
        type: 'no-return',
        severity: 'warning',
        blockId: block.block_id,
        message: `Bloco ${block.block_id}: Não retorna à garagem ao final do dia`,
        count: 1,
      });
    }
  });

  // Consolidate conflicts by type
  const consolidated: OperationalConflict[] = [];
  const typeMap = new Map<string, OperationalConflict>();

  conflicts.forEach((c) => {
    const key = `${c.type}-${c.severity}`;
    if (typeMap.has(key)) {
      const existing = typeMap.get(key)!;
      existing.count++;
    } else {
      typeMap.set(key, { ...c });
      consolidated.push({ ...c });
    }
  });

  return consolidated;
}
