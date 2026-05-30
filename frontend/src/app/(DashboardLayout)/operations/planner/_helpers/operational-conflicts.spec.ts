/**
 * ALTO #4 — Specs do detector de conflitos operacionais.
 * Cobre: overlap, gap irrealista, break violation, paired-orphan.
 */
import { describe, expect, it } from 'vitest';
import { detectOperationalConflicts } from './operational-conflicts';
import type { OptimizationResultSummary } from '../../_types';

function makeRes(blocks: any[]): OptimizationResultSummary {
  return { blocks } as unknown as OptimizationResultSummary;
}

describe('detectOperationalConflicts — overlap', () => {
  it('detecta viagens sobrepostas no mesmo bloco', () => {
    const res = makeRes([
      {
        block_id: 1,
        trip_details: [
          { start_time: 360, end_time: 405, origin_id: 1, destination_id: 2 },
          { start_time: 400, end_time: 445, origin_id: 2, destination_id: 1 }, // overlap
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    const overlap = conflicts.find((c) => c.type === 'overlap');
    expect(overlap).toBeDefined();
    expect(overlap?.severity).toBe('error');
    expect(overlap?.blockId).toBe(1);
  });

  it('não reporta overlap quando viagens são sequenciais', () => {
    const res = makeRes([
      {
        block_id: 2,
        trip_details: [
          { start_time: 360, end_time: 405, origin_id: 1, destination_id: 2 },
          { start_time: 410, end_time: 455, origin_id: 2, destination_id: 1 },
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    expect(conflicts.find((c) => c.type === 'overlap')).toBeUndefined();
  });
});

describe('detectOperationalConflicts — gap irrealista', () => {
  it('flag warning quando gap < 2 min entre viagens', () => {
    const res = makeRes([
      {
        block_id: 3,
        trip_details: [
          { start_time: 360, end_time: 405, origin_id: 1, destination_id: 2 },
          { start_time: 406, end_time: 451, origin_id: 2, destination_id: 1 }, // gap = 1
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    const unrealistic = conflicts.find((c) => c.type === 'unrealistic');
    expect(unrealistic).toBeDefined();
    expect(unrealistic?.severity).toBe('warning');
  });
});

describe('detectOperationalConflicts — break violation (CLT art.71)', () => {
  it('flag warning quando jornada >=6h sem intervalo ≥ minBreak', () => {
    // Jornada de 8h sem nenhum gap >= 30min
    const trips = [];
    for (let i = 0; i < 16; i++) {
      trips.push({
        start_time: 360 + i * 30,
        end_time: 360 + i * 30 + 25, // 5min gap entre viagens
      });
    }
    const res = makeRes([{ block_id: 4, trip_details: trips }]);
    const conflicts = detectOperationalConflicts(res);
    const breakViol = conflicts.find((c) => c.type === 'break-violation');
    expect(breakViol).toBeDefined();
    expect(breakViol?.severity).toBe('warning');
  });

  it('sem violação se há intervalo grande suficiente', () => {
    const res = makeRes([
      {
        block_id: 5,
        trip_details: [
          { start_time: 360, end_time: 720, origin_id: 1, destination_id: 2 }, // 6h work
          { start_time: 825, end_time: 950, origin_id: 2, destination_id: 1 }, // 105min break
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    expect(conflicts.find((c) => c.type === 'break-violation')).toBeUndefined();
  });
});

describe('detectOperationalConflicts — paired-orphan', () => {
  it('flag quando ida e volta desbalanceados em pares', () => {
    const res = makeRes([
      {
        block_id: 6,
        trip_details: [
          { start_time: 360, end_time: 405, direction: 'outbound', is_paired: true },
          { start_time: 410, end_time: 455, direction: 'outbound', is_paired: true },
          { start_time: 460, end_time: 505, direction: 'inbound', is_paired: true },
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    const orphan = conflicts.find((c) => c.type === 'paired-orphan');
    expect(orphan).toBeDefined();
    expect(orphan?.message).toContain('ida: 2');
    expect(orphan?.message).toContain('volta: 1');
  });
});

describe('detectOperationalConflicts — layover', () => {
  it('flag warning quando layover no mesmo terminal > 90min (máximo)', () => {
    const res = makeRes([
      {
        block_id: 8,
        trip_details: [
          { start_time: 360, end_time: 405, origin_id: 1, destination_id: 2 },
          { start_time: 530, end_time: 575, origin_id: 2, destination_id: 1 }, // layover 125 > 90
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    const layover = conflicts.find((c) => c.type === 'layover-violation');
    expect(layover).toBeDefined();
    expect(layover?.message).toContain('excessivo');
  });

  it('flag warning quando layover no mesmo terminal < min_layover', () => {
    // policy default min_layover=8
    const res = makeRes([
      {
        block_id: 9,
        trip_details: [
          { start_time: 360, end_time: 405, origin_id: 1, destination_id: 2 },
          { start_time: 408, end_time: 453, origin_id: 2, destination_id: 1 }, // layover=3 < 8
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    const layover = conflicts.find((c) => c.type === 'layover-violation');
    expect(layover).toBeDefined();
    expect(layover?.message).toContain('insuficiente');
  });
});

describe('detectOperationalConflicts — caso feliz', () => {
  it('schedule limpo retorna 0 conflitos', () => {
    const res = makeRes([
      {
        block_id: 7,
        trip_details: [
          { start_time: 360, end_time: 405, origin_id: 1, destination_id: 2 },
          { start_time: 460, end_time: 505, origin_id: 2, destination_id: 1 }, // layover=55 OK
          { start_time: 560, end_time: 605, origin_id: 1, destination_id: 2 }, // layover=55 OK
        ],
      },
    ]);
    const conflicts = detectOperationalConflicts(res);
    expect(conflicts.length).toBe(0);
  });
});
