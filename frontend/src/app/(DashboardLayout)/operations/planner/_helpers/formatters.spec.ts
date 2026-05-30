/**
 * ALTO #4 — Specs unit do planner.
 * Cobre paths críticos de helpers que decidem labels/classificações
 * usadas pelo Gantt e Export. Não-DOM, pura lógica.
 */
import { describe, expect, it } from 'vitest';
import {
  classifyTripInterval,
  directionLabel,
  formatIdleWindowLabel,
  getTripIntervalClassificationColor,
  getTripIntervalClassificationLabel,
} from './formatters';

describe('directionLabel', () => {
  it('outbound → Ida', () => {
    expect(directionLabel('outbound')).toBe('Ida');
  });

  it('inbound → Volta', () => {
    expect(directionLabel('inbound')).toBe('Volta');
  });

  it('IDA (case-insensitive) → Ida', () => {
    expect(directionLabel('IDA')).toBe('Ida');
  });

  it('string desconhecida → "Sem sentido"', () => {
    expect(directionLabel('CIRCULAR')).toBe('Sem sentido');
  });

  it('undefined → "Sem sentido" (não trava)', () => {
    expect(directionLabel(undefined)).toBe('Sem sentido');
  });
});

describe('classifyTripInterval', () => {
  it('gap <= 0 → intervalo_normal', () => {
    expect(
      classifyTripInterval({ gapMinutes: 0, isBoundary: false, isMealBreakWindow: false, viewScope: 'vehicle' }),
    ).toBe('intervalo_normal');
    expect(
      classifyTripInterval({ gapMinutes: -5, isBoundary: false, isMealBreakWindow: false, viewScope: 'vehicle' }),
    ).toBe('intervalo_normal');
  });

  it('boundary entre blocos → ociosa', () => {
    expect(
      classifyTripInterval({ gapMinutes: 45, isBoundary: true, isMealBreakWindow: false, viewScope: 'vehicle' }),
    ).toBe('ociosa');
  });

  it('crew + janela de refeição → descanso_refeicao', () => {
    expect(
      classifyTripInterval({ gapMinutes: 60, isBoundary: false, isMealBreakWindow: true, viewScope: 'crew' }),
    ).toBe('descanso_refeicao');
  });

  it('vehicle scope ignora isMealBreakWindow', () => {
    // VSP não tem semântica de refeição
    expect(
      classifyTripInterval({ gapMinutes: 60, isBoundary: false, isMealBreakWindow: true, viewScope: 'vehicle' }),
    ).toBe('intervalo_normal');
  });
});

describe('getTripIntervalClassificationLabel', () => {
  it('mapeia descanso_refeicao → "Descanso/Refeição"', () => {
    expect(getTripIntervalClassificationLabel('descanso_refeicao')).toBe('Descanso/Refeição');
  });
  it('mapeia ociosa → "Ociosa"', () => {
    expect(getTripIntervalClassificationLabel('ociosa')).toBe('Ociosa');
  });
  it('default → "Intervalo Normal"', () => {
    expect(getTripIntervalClassificationLabel('intervalo_normal')).toBe('Intervalo Normal');
  });
});

describe('getTripIntervalClassificationColor', () => {
  it('descanso_refeicao → success', () => {
    expect(getTripIntervalClassificationColor('descanso_refeicao')).toBe('success');
  });
  it('ociosa → warning', () => {
    expect(getTripIntervalClassificationColor('ociosa')).toBe('warning');
  });
  it('intervalo_normal → default', () => {
    expect(getTripIntervalClassificationColor('intervalo_normal')).toBe('default');
  });
});

describe('formatIdleWindowLabel', () => {
  it('apoio inclui prefixo "Apoio" + range HH:MM', () => {
    const out = formatIdleWindowLabel({ kind: 'apoio', start: 360, end: 405, duration: 45 });
    expect(out).toMatch(/^Apoio /);
    expect(out).toContain('06:00');
    expect(out).toContain('06:45');
  });

  it('descanso_refeicao usa label "Descanso/Refeição"', () => {
    const out = formatIdleWindowLabel({ kind: 'descanso_refeicao', start: 720, end: 780, duration: 60 });
    expect(out).toContain('Descanso/Refeição');
    expect(out).toContain('12:00');
    expect(out).toContain('13:00');
  });
});
