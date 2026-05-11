'use client';
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  Box, Typography, Stack, Paper, Tooltip, Button, Divider,
  Alert, Snackbar, Chip, TextField, MenuItem, Select,
  FormControl, InputLabel, Tabs, Tab,
  Table, TableBody, TableCell, TableHead, TableRow, TableContainer,
  Collapse, IconButton,
  alpha, useTheme, type Theme,
} from '@mui/material';
import { List, type RowComponentProps } from 'react-window';
import {
  IconBus, IconUsers, IconMaximize, IconMinimize,
  IconFileSpreadsheet, IconTable, IconRoute, IconClipboardData,
  IconChevronDown, IconChevronUp,
  IconFlag, IconMapPin, IconCoffee, IconClock,
} from '@tabler/icons-react';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import type { Line, Terminal, OptimizationResultSummary } from '../../_types';
import {
  minToHHMM, minToDuration, fmtCurrency, fmtSignedCurrency,
  getTripPublicId, type TripIntervalPolicy,
} from '../_helpers/formatters';
import { getLinePalette, getGanttColors } from '../../_tokens/design-tokens';
import { OperationalConflictIndicator } from './OperationalConflictIndicator';
import { operationsApi } from '@/lib/api';

// ─── Constants ───────────────────────────────────────────────────────────────
const MIN_SCALE = 1;
const MAX_SCALE = 8;
const BASE_PIXELS_PER_MINUTE = 2;
const ROW_HEIGHT = 68;
const HEADER_HEIGHT = 44;
const OVERNIGHT_START_MIN = 1440;
const HORIZON_MINUTES = 1800;
const SIDEBAR_WIDTH = 140;
const DESCANSO_MIN_GAP = 5; // min gap to show as interval event

// ─── Domain Interfaces ────────────────────────────────────────────────────────
export type EventKind = 'inicio_jornada' | 'fim_jornada' | 'soltura' | 'viagem' | 'recolhimento' | 'descanso' | 'deslocamento_operacional' | 'troca_motorista' | 'troca_veiculo';
export type IntervalKind = 'espera' | 'descanso' | 'refeicao';

export interface PlanEvent {
  kind: EventKind;
  tripId?: number;
  linha: string;
  sentido: string;
  inicio: number;
  chegada: number;
  origemName: string;
  destinoName: string;
  km: number;
  duracao: number;
  gapMinutes?: number;
  intervalKind?: IntervalKind;
  vehicleId?: number;
  vehicleFromId?: number;
  vehicleToId?: number;
  dutyId?: number | null;
  tripIds?: number[];
  tripCount?: number;
  eventScope?: string;
  explanation?: string;
  color?: string;
}

export interface PlanGroup {
  id: number;
  label: string;
  tripCount: number;
  totalKm: number;
  startTime: number;
  endTime: number;
  workTime?: number;
  totalCost?: number;
  violations?: number;
  driverDisplayName?: string;
  operatorNotAssigned?: boolean;
  issueCodes?: string[];
  issueSeverity?: 'soft' | '';
  issueExplanation?: string;
  events: PlanEvent[];
}

interface DutyAuditSummary {
  dutyStart: number | null;
  dutyEnd: number | null;
  operatorNotAssigned: boolean;
  driverDisplayName: string;
  issueCodes: string[];
  issueSeverity: 'soft' | '';
  issueExplanation: string;
  mandatoryRestRequired: boolean;
  hasValidMandatoryRest: boolean | null;
}

// ─── Component Interfaces ─────────────────────────────────────────────────────
export interface TabGanttProps {
  res: OptimizationResultSummary;
  lines: Line[];
  terminals: Terminal[];
  intervalPolicy?: TripIntervalPolicy;
  onWhatIfUpdate?: (newCost: number | null) => void;
}

interface TripMetadata {
  lineId: number | null;
  lineCode: string | null;
  color: string;
}

function toMinuteValue(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatDutyReference(dutyId: number | null | undefined): string {
  return dutyId != null ? `D${dutyId}` : '—';
}

function toCsvBoolean(value: boolean | null | undefined): string {
  return value ? 'True' : 'False';
}

function minToHHMMExport(minutes: number): string {
  const safeMinutes = Math.max(0, Math.floor(minutes));
  const hours = Math.floor(safeMinutes / 60);
  const mins = safeMinutes % 60;
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
}

function buildDutyAuditSummary(duty: any): DutyAuditSummary {
  const dutyId = Number(duty?.duty_id ?? duty?.id ?? 0);
  const report = duty?.operational_time_report ?? {};
  const issueCodes = Array.isArray(report?.violations)
    ? report.violations.map((code: unknown) => String(code)).filter(Boolean)
    : [];
  const operatorNotAssigned = Boolean(report?.operator_not_assigned ?? true);
  const dutyStart = toMinuteValue(report?.duty_start ?? duty?.start_time);
  const dutyEnd = toMinuteValue(report?.duty_end ?? duty?.end_time);
  const issueExplanation = String(report?.suggestion ?? report?.user_explanation ?? '').trim();

  return {
    dutyStart,
    dutyEnd,
    operatorNotAssigned,
    driverDisplayName: operatorNotAssigned
      ? `Operador não atribuído (${formatDutyReference(dutyId)})`
      : `Jornada ${formatDutyReference(dutyId)}`,
    issueCodes,
    issueSeverity: issueCodes.length > 0 ? 'soft' : '',
    issueExplanation,
    mandatoryRestRequired: Boolean(report?.mandatory_rest_required ?? false),
    hasValidMandatoryRest: report?.has_valid_mandatory_rest == null
      ? null
      : Boolean(report?.has_valid_mandatory_rest),
  };
}

function buildDutyExportFields(duty: any) {
  const audit = buildDutyAuditSummary(duty);
  return {
    driver_display_name: audit.driverDisplayName,
    operator_not_assigned: toCsvBoolean(audit.operatorNotAssigned),
    duty_start: audit.dutyStart != null ? minToHHMMExport(audit.dutyStart) : '',
    duty_end: audit.dutyEnd != null ? minToHHMMExport(audit.dutyEnd) : '',
    mandatory_rest_required: toCsvBoolean(audit.mandatoryRestRequired),
    has_valid_mandatory_rest: audit.hasValidMandatoryRest == null ? '' : toCsvBoolean(audit.hasValidMandatoryRest),
    issue_severity: audit.issueSeverity,
    issue_codes: audit.issueCodes.join(';'),
    issue_explanation: audit.issueExplanation,
  };
}

function normalizeTripIds(rawTripIds: unknown): number[] {
  if (!Array.isArray(rawTripIds)) {
    return [];
  }
  const seen = new Set<number>();
  const normalized: number[] = [];
  rawTripIds.forEach((tripId) => {
    const numeric = Number(tripId);
    if (!Number.isFinite(numeric) || numeric <= 0 || seen.has(numeric)) {
      return;
    }
    seen.add(numeric);
    normalized.push(numeric);
  });
  return normalized;
}

function resolveSegmentBlockId(segment: Record<string, any>, tripDetails: any[]): number | null {
  for (const key of ['block_id', 'from_block_id', 'to_block_id']) {
    const value = Number(segment[key]);
    if (Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  for (const trip of tripDetails) {
    const value = Number(trip?.block_id ?? trip?.vehicle_id ?? 0);
    if (Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  return null;
}

function normalizeExportSegments(rawSegments: any[], tripById: Map<number, any>): Record<string, any>[] {
  if (!Array.isArray(rawSegments) || rawSegments.length === 0) {
    return [];
  }

  const baseSegments = rawSegments.map((segment) => {
    const segType = String(segment?.type ?? segment?.event_type ?? 'unknown');
    const tripIds = normalizeTripIds(segment?.trip_ids);
    const tripDetails = sortOperationalTrips(tripIds.map((tripId) => tripById.get(tripId)).filter(Boolean));
    const blockId = resolveSegmentBlockId(segment, tripDetails);
    const tripCount = tripIds.length;
    const bundleEventType = segType === 'commercial_trip' && tripCount > 1
      ? 'commercial_trip_bundle'
      : segType;
    const eventScope = segment?.event_scope ?? (segType === 'commercial_trip' || segType === 'deadhead' ? 'driver_vehicle' : 'driver');
    return {
      ...segment,
      type: segType,
      event_type: segType,
      event_scope: eventScope,
      trip_ids: tripIds,
      trip_count: tripCount,
      block_id: blockId,
      vehicle_id: blockId,
      ...(bundleEventType !== segType
        ? {
            bundle_event_type: bundleEventType,
            explanation: segment?.explanation ?? `Segmento operacional agrupado com ${tripCount} viagens reais.`,
          }
        : {}),
    };
  });

  return baseSegments;
}

// ─── Event Kind Config ────────────────────────────────────────────────────────
const EVENT_CONFIG: Record<EventKind, { label: string; description: string; color: 'success' | 'primary' | 'error' | 'warning' | 'default' | 'info' | 'secondary'; icon: React.ReactNode }> = {
  inicio_jornada:  { label: 'Início de jornada', description: 'Marca o começo da jornada do motorista.', color: 'info', icon: <IconCoffee size={14} /> },
  fim_jornada:     { label: 'Fim de jornada', description: 'Marca o término da jornada do motorista.', color: 'info', icon: <IconCoffee size={14} /> },
  soltura:         { label: 'Soltura', description: 'Saída do veículo da garagem para o terminal de início da operação.', color: 'success', icon: <IconMapPin size={14} /> },
  viagem:          { label: 'Viagem', description: 'Trecho comercial: ônibus em operação com passageiros.', color: 'primary', icon: <IconBus size={14} /> },
  recolhimento:    { label: 'Recolhimento', description: 'Retorno do veículo à garagem ao final da operação.', color: 'error',   icon: <IconFlag size={14} /> },
  descanso:        { label: 'Descanso/Refeição', description: 'Intervalo obrigatório, refeição ou espera operacional.', color: 'warning', icon: <IconCoffee size={14} /> },
  deslocamento_operacional: { label: 'Deslocamento oper.', description: 'Deslocamento sem passageiros entre pontos da operação.', color: 'default', icon: <IconBus size={14} /> },
  troca_motorista: { label: 'Troca motorista', description: 'Rendição: motorista entrega o veículo a outro no meio da operação.', color: 'default', icon: <IconUsers size={14} /> },
  troca_veiculo:   { label: 'Troca de veículo', description: 'Mesmo motorista assume um veículo diferente.', color: 'secondary', icon: <IconRoute size={14} /> },
};

function sortOperationalTrips<T extends Record<string, any>>(trips: T[]): T[] {
  return [...trips].sort((left, right) => {
    const startDiff = Number(left.start_time ?? left.startTime ?? 0) - Number(right.start_time ?? right.startTime ?? 0);
    if (startDiff !== 0) {
      return startDiff;
    }

    const endDiff = Number(left.end_time ?? left.endTime ?? 0) - Number(right.end_time ?? right.endTime ?? 0);
    if (endDiff !== 0) {
      return endDiff;
    }

    return Number(left.id ?? left.tripId ?? left.trip_id ?? 0) - Number(right.id ?? right.tripId ?? right.trip_id ?? 0);
  });
}

function resolveDutyDetailedTrips(duty: any, tripById: Map<number, any>): any[] {
  const dutyId = duty.duty_id ?? duty.id;
  const explicitTrips = Array.isArray(duty.detailed_trip_assignments) ? duty.detailed_trip_assignments : [];
  if (explicitTrips.length > 0) {
    return explicitTrips
      .map((trip: any) => {
        const sourceTripId = Number(trip.source_trip_id ?? trip.id ?? trip.trip_id ?? 0);
        const hydratedTrip = tripById.get(sourceTripId) ?? tripById.get(Number(trip.trip_id ?? 0));
        const vehicleId = trip.vehicle_id ?? trip.block_id ?? hydratedTrip?.block_id ?? hydratedTrip?.vehicle_id ?? null;
        return {
          ...hydratedTrip,
          ...trip,
          source_trip_id: sourceTripId || undefined,
          trip_id: trip.trip_id ?? trip.public_trip_id ?? trip.id,
          block_id: trip.block_id ?? vehicleId,
          vehicle_id: vehicleId,
          duty_id: dutyId,
          driver_id: dutyId,
        };
      })
      .sort((left: any, right: any) => {
        const sequenceDiff = Number(left.sequence_in_duty ?? 0) - Number(right.sequence_in_duty ?? 0);
        if (sequenceDiff !== 0) {
          return sequenceDiff;
        }
        return sortOperationalTrips([left, right])[0] === left ? -1 : 1;
      })
      .map((trip: any, index: number) => ({
        ...trip,
        sequence_in_duty: Number(trip.sequence_in_duty ?? index + 1),
        sequence_in_bundle: Number(trip.sequence_in_bundle ?? 1),
        bundle_trip_count: Number(trip.bundle_trip_count ?? 1),
        bundle_event_type: trip.bundle_event_type ?? (Number(trip.bundle_trip_count ?? 1) > 1 ? 'commercial_trip_bundle' : 'commercial_trip'),
      }));
  }

  const segmentTrips = Array.isArray(duty.duty_time_segments)
    ? duty.duty_time_segments.flatMap((segment: any, absoluteIndex: number) => {
      if ((segment.type ?? segment.event_type) !== 'commercial_trip') {
        return [];
      }
      const trips = sortOperationalTrips(
        (Array.isArray(segment.trip_ids) ? segment.trip_ids : [])
          .map((tripId: number) => tripById.get(Number(tripId)))
          .filter(Boolean),
      );
      return trips.map((trip: any, tripIndex: number) => ({
        ...trip,
        source_trip_id: trip.tripId ?? trip.id ?? trip.trip_id,
        trip_id: trip.trip_id ?? trip.tripId ?? trip.id,
        block_id: trip.block_id ?? segment.block_id ?? null,
        vehicle_id: trip.block_id ?? segment.block_id ?? null,
        duty_id: dutyId,
        driver_id: dutyId,
        event_scope: 'trip',
        sequence_in_duty: 0,
        segment_sequence: absoluteIndex + 1,
        sequence_in_bundle: tripIndex + 1,
        bundle_trip_count: trips.length,
        bundle_event_type: segment.bundle_event_type ?? (trips.length > 1 ? 'commercial_trip_bundle' : 'commercial_trip'),
        is_paired: trips.length > 1,
      }));
    })
    : [];

  const fallbackTrips = segmentTrips.length > 0
    ? segmentTrips
    : sortOperationalTrips(
      ((duty.trip_ids || duty.trips || []) as number[])
        .map((tripId: number) => tripById.get(Number(tripId)))
        .filter(Boolean)
        .map((trip: any) => ({
          ...trip,
          source_trip_id: trip.tripId ?? trip.id ?? trip.trip_id,
          trip_id: trip.trip_id ?? trip.tripId ?? trip.id,
          block_id: trip.block_id ?? null,
          vehicle_id: trip.block_id ?? null,
          duty_id: dutyId,
          driver_id: dutyId,
          event_scope: 'trip',
          sequence_in_bundle: 1,
          bundle_trip_count: 1,
          bundle_event_type: 'commercial_trip',
          is_paired: false,
        })),
    );

  return fallbackTrips.map((trip: any, index: number) => ({
    ...trip,
    sequence_in_duty: Number(trip.sequence_in_duty ?? index + 1),
  }));
}

// ─── Helper: build PlanEvent[] from a sorted trip list ───────────────────────
// Soltura  = deadhead garagem → primeiro terminal (antes da 1ª viagem)
// Viagem   = todas as viagens operacionais (primeiro, meio, último)
// Ociosa   = intervalo entre viagens (≥ DESCANSO_MIN_GAP)
// Refeição = intervalo ≥ mealBreakMinutes
// Recolhimento = deadhead último terminal → garagem (após a última viagem)
function buildEvents(
  trips: any[],
  terminalMap: Map<number, Terminal>,
  lineByCode: Map<string, Line>,
  intervalPolicy?: TripIntervalPolicy,
  vehicleId?: number,
  dutyIdOverride?: number | null,
  includeSoltura = true,
  includeRecolhimento = true,
  blockBuffer?: { start: number; end: number },
): PlanEvent[] {
  const realTrips = trips.filter((t) => t.lineCode || t.lineId);
  if (realTrips.length === 0) return [];

  const mealThreshold = intervalPolicy?.mealBreakMinutes ?? 60;
  const breakThreshold = intervalPolicy?.minBreakMinutes ?? 30;
  const events: PlanEvent[] = [];

  const tName = (id?: number) =>
    id != null ? (terminalMap.get(id)?.shortName ?? terminalMap.get(id)?.name ?? `T${id}`) : '—';

  const firstTrip = realTrips[0];
  const lastTrip = realTrips[realTrips.length - 1];

  // Linha da primeira viagem (para dados de soltura)
  const firstLine = lineByCode.get(firstTrip.lineCode ?? '');
  // Linha da última viagem (para dados de recolhimento)
  const lastLine = lineByCode.get(lastTrip.lineCode ?? '');

  // ── Soltura: garagem → terminal da 1ª viagem ──────────────────────────────
  const solturaMinutes = firstLine?.solturaMinutes ?? blockBuffer?.start ?? 0;
  if (includeSoltura && solturaMinutes > 0) {
    const solturaEnd = firstTrip.start_time ?? 0;
    const solturaStart = solturaEnd - solturaMinutes;
    events.push({
      kind: 'soltura',
      linha: '—',
      sentido: '—',
      inicio: solturaStart,
      chegada: solturaEnd,
      origemName: firstLine?.garageTerminalId ? tName(firstLine.garageTerminalId) : '(Garagem)',
      destinoName: tName(firstTrip.origin_id),
      km: firstLine?.garageDistanceKm ?? 0,
      duracao: solturaMinutes,
      vehicleId,
      dutyId: dutyIdOverride,
    });
  }

  // ── Viagens operacionais + intervalos (ociosa/descanso/refeição) ───────────
  realTrips.forEach((t, idx) => {
    events.push({
      kind: 'viagem',
      tripId: t.tripId,
      linha: t.lineCode ?? String(t.lineId ?? '—'),
      sentido: t.direction ?? t.sentido ?? (t.tripId % 2 === 0 ? 'VOLTA' : 'IDA'),
      inicio: t.start_time ?? 0,
      chegada: t.end_time ?? 0,
      origemName: tName(t.origin_id),
      destinoName: tName(t.destination_id),
      km: t.distance_km ?? 0,
      duracao: (t.end_time ?? 0) - (t.start_time ?? 0),
      vehicleId,
      dutyId: dutyIdOverride,
      color: t.color,
    });

    // Intervalo entre viagens consecutivas (ociosa/descanso/refeição)
    const next = realTrips[idx + 1];
    if (next) {
      const gap = (next.start_time ?? 0) - (t.end_time ?? 0);
      if (gap >= DESCANSO_MIN_GAP) {
        const intervalKind: IntervalKind = gap >= mealThreshold
          ? 'refeicao'
          : gap >= breakThreshold
            ? 'descanso'
            : 'espera';
        events.push({
          kind: 'descanso',
          linha: '—',
          sentido: '—',
          inicio: t.end_time ?? 0,
          chegada: next.start_time ?? 0,
          origemName: tName(t.destination_id),
          destinoName: tName(next.origin_id),
          km: 0,
          duracao: gap,
          gapMinutes: gap,
          intervalKind,
          vehicleId,
          dutyId: dutyIdOverride,
          color: intervalKind === 'refeicao' ? '#2e7d32' : intervalKind === 'descanso' ? '#ffc107' : '#90a4ae',
        });
      }
    }
  });

  // ── Recolhimento: último terminal → garagem ───────────────────────────────
  const recolhMinutes = lastLine?.recolhimentoMinutes ?? blockBuffer?.end ?? 0;
  if (includeRecolhimento && recolhMinutes > 0) {
    const recolhimentoStart = lastTrip.end_time ?? 0;
    const recolhimentoEnd = recolhimentoStart + recolhMinutes;
    events.push({
      kind: 'recolhimento',
      linha: '—',
      sentido: '—',
      inicio: recolhimentoStart,
      chegada: recolhimentoEnd,
      origemName: tName(lastTrip.destination_id),
      destinoName: lastLine?.garageTerminalId ? tName(lastLine.garageTerminalId) : '(Garagem)',
      km: lastLine?.recolhimentoDistanceKm ?? 0,
      duracao: recolhMinutes,
      vehicleId,
      dutyId: dutyIdOverride,
    });
  }

  return events;
}

// ─── Helper: build PlanEvent[] correctly directly from duty_time_segments ───
function buildEventsFromSegments(
  dutySegments: any[],
  dutyId: number | undefined,
  terminalMap: Map<number, Terminal>,
  tripById: Map<number, any>,
  detailedTrips: any[] = [],
  blockId?: number
): PlanEvent[] {
  const events: PlanEvent[] = [];
  const detailedTripsBySegment = new Map<number, any[]>();

  detailedTrips.forEach((trip: any) => {
    const key = Number(trip.segment_sequence ?? 0);
    if (!Number.isFinite(key) || key <= 0) {
      return;
    }
    const current = detailedTripsBySegment.get(key) ?? [];
    current.push(trip);
    detailedTripsBySegment.set(key, current);
  });

  dutySegments.forEach((seg, segIndex) => {
    const type = seg.type ?? seg.event_type;
    const start = Number(seg.start ?? 0);
    const end = Number(seg.end ?? start);
    const dur = end - start;

    let kind: EventKind | null = null;
    let intervalKind: IntervalKind | undefined;

    if (type === 'commercial_trip') kind = 'viagem';
    else if (type === 'pullout' || type === 'vehicle_pullout') kind = 'soltura';
    else if (type === 'pullback' || type === 'vehicle_pullback') kind = 'recolhimento';
    else if (type === 'idle' || type === 'driver_idle') { kind = 'descanso'; intervalKind = 'espera'; }
    else if (type === 'normal_break') { kind = 'descanso'; intervalKind = 'refeicao'; }
    else if (type === 'mandatory_rest') { kind = 'descanso'; intervalKind = 'descanso'; }
    else if (type === 'duty_start') kind = 'inicio_jornada';
    else if (type === 'duty_end') kind = 'fim_jornada';
    else if (type === 'deadhead') kind = 'deslocamento_operacional';
    else if (type === 'driver_change') kind = 'troca_motorista';
    // driver_vehicle_change is intentionally skipped — vehicle-change bookkeeping events are not shown

    if (!kind) return;

    const tName = (id?: number | string) =>
      id != null ? (terminalMap.get(Number(id))?.shortName ?? terminalMap.get(Number(id))?.name ?? `T${id}`) : '—';

    if (type === 'commercial_trip') {
      const segmentKey = seg.segment_sequence ?? (segIndex + 1);
      const segmentTrips = sortOperationalTrips(
        (detailedTripsBySegment.get(segmentKey) ??
          (Array.isArray(seg.trip_ids) ? seg.trip_ids : [])
            .map((tripId: number) => tripById.get(Number(tripId)))
            .filter(Boolean)) as any[],
      );
      if (segmentTrips.length > 0) {
        segmentTrips.forEach((trip: any) => {
          const sourceTripId = Number(trip.source_trip_id ?? trip.tripId ?? trip.id ?? trip.trip_id ?? 0);
          const hydratedTrip = tripById.get(sourceTripId) ?? tripById.get(Number(trip.trip_id ?? 0));
          const lineCode = trip.lineCode ?? hydratedTrip?.lineCode ?? trip.line_code ?? hydratedTrip?.line_code ?? null;
          const lineId = trip.lineId ?? hydratedTrip?.lineId ?? trip.line_id ?? hydratedTrip?.line_id ?? null;
          const vehicleId = trip.vehicle_id ?? trip.block_id ?? hydratedTrip?.block_id ?? seg.block_id ?? blockId;
          events.push({
            kind,
            tripId: sourceTripId || undefined,
            tripIds: [sourceTripId],
            tripCount: Number(trip.bundle_trip_count ?? segmentTrips.length),
            linha: lineCode ?? String(lineId ?? '—'),
            sentido: trip.direction ?? hydratedTrip?.direction ?? trip.sentido ?? hydratedTrip?.sentido ?? '—',
            inicio: Number(trip.start_time ?? hydratedTrip?.start_time ?? start),
            chegada: Number(trip.end_time ?? hydratedTrip?.end_time ?? end),
            origemName: tName(trip.origin_id ?? hydratedTrip?.origin_id ?? seg.location_start),
            destinoName: tName(trip.destination_id ?? hydratedTrip?.destination_id ?? seg.location_end),
            km: Number(trip.distance_km ?? hydratedTrip?.distance_km ?? seg.distance_km ?? 0),
            duracao: Number(trip.duration ?? hydratedTrip?.duration ?? ((trip.end_time ?? hydratedTrip?.end_time ?? end) - (trip.start_time ?? hydratedTrip?.start_time ?? start))),
            vehicleId: vehicleId != null ? Number(vehicleId) : undefined,
            dutyId,
            eventScope: 'trip',
            explanation: seg.explanation,
            color: trip.color ?? hydratedTrip?.color,
          });
        });
        return;
      }
    }

    // Fetch trip if possible to get line names
    let trip = null;
    let tid = null;
    if (Array.isArray(seg.trip_ids) && seg.trip_ids.length > 0) {
      tid = Number(seg.trip_ids[0]);
      trip = tripById.get(tid);
    } else if (seg.tripId || seg.trip_id) {
      tid = Number(seg.tripId ?? seg.trip_id);
      trip = tripById.get(tid);
    }

    let color = trip?.color;
    if (kind === 'descanso') {
      color = intervalKind === 'refeicao' ? '#2e7d32' : intervalKind === 'descanso' ? '#ffc107' : '#90a4ae';
    }

    events.push({
      kind,
      tripId: tid ?? undefined,
      linha: trip?.lineCode ?? String(trip?.lineId ?? '—'),
      sentido: trip?.direction ?? trip?.sentido ?? '—',
      inicio: start,
      chegada: end,
      origemName: tName(seg.location_start ?? seg.location ?? trip?.origin_id),
      destinoName: tName(seg.location_end ?? seg.location ?? trip?.destination_id),
      km: Number(seg.distance_km ?? trip?.distance_km ?? 0),
      duracao: dur,
      gapMinutes: kind === 'descanso' ? dur : undefined,
      intervalKind,
      vehicleId: (blockId ?? seg.block_id) != null
        ? Number(blockId ?? seg.block_id)
        : undefined,
      vehicleFromId: seg.from_vehicle_id != null ? Number(seg.from_vehicle_id) : undefined,
      vehicleToId: seg.to_vehicle_id != null ? Number(seg.to_vehicle_id) : undefined,
      dutyId,
      tripIds: Array.isArray(seg.trip_ids) ? seg.trip_ids.map(Number) : undefined,
      tripCount: Number(seg.trip_count ?? (Array.isArray(seg.trip_ids) ? seg.trip_ids.length : 0) ?? 0),
      eventScope: seg.event_scope,
      explanation: seg.explanation,
      color,
    });
  });

  return events;
}


// ─── Helper: export CSV ───────────────────────────────────────────────────────
function exportCsv(rows: Record<string, unknown>[], filename: string) {
  const ws = XLSX.utils.json_to_sheet(rows);
  const csv = XLSX.utils.sheet_to_csv(ws);
  saveAs(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' }), filename);
}

function exportExcel(rows: Record<string, unknown>[], filename: string, sheet = 'Dados') {
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheet);
  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })], { type: 'application/octet-stream' }), filename);
}

// ─── ExportButtons ────────────────────────────────────────────────────────────
function ExportButtons({ rows, filename, sheet }: { rows: Record<string, unknown>[]; filename: string; sheet?: string }) {
  return (
    <Stack direction="row" spacing={1}>
      <Tooltip title="Exportar CSV">
        <Button size="small" variant="outlined" startIcon={<IconFileSpreadsheet size={15} />}
          onClick={() => exportCsv(rows, `${filename}.csv`)}>CSV</Button>
      </Tooltip>
      <Tooltip title="Exportar Excel">
        <Button size="small" variant="outlined" color="success" startIcon={<IconTable size={15} />}
          onClick={() => exportExcel(rows, `${filename}.xlsx`, sheet)}>Excel</Button>
      </Tooltip>
    </Stack>
  );
}

// ─── Operational Event Type Mapping (Solver → CSV) ────────────────────────────
const OPERATIONAL_EVENT_LABELS: Record<string, string> = {
  commercial_trip: 'Viagem',
  commercial_trip_bundle: 'Viagem agrupada',
  idle: 'Ociosa',
  driver_idle: 'Ociosa',
  normal_break: 'Intervalo normal',
  mandatory_rest: 'Descanso obrigatório',
  pullout: 'Soltura',
  pullback: 'Recolhimento',
  deadhead: 'Deslocamento operacional',
  driver_change: 'Troca de motorista',
  driver_vehicle_change: 'Troca de veículo',
  duty_start: 'Início de jornada',
  duty_end: 'Fim de jornada',
};

const WORK_TIME_TYPES = new Set(['commercial_trip', 'commercial_trip_bundle', 'deadhead']);
const DRIVING_TIME_TYPES = new Set(['commercial_trip', 'commercial_trip_bundle', 'deadhead']);

/** Build operational export rows using solver duty_time_segments as primary source */
function buildOperationalExportRows(
  duties: any[],
  effectiveBlocks: any[],
  scheduleId: number | string,
  tripById: Map<number, any>,
): Record<string, unknown>[] {
  // tripId → blockId map
  const tripToBlock = new Map<number, number>();
  effectiveBlocks.forEach((b) => {
    const blockId = b.block_id ?? b.id;
    (b.items || b.trips || []).forEach((t: any) => {
      const tid = t.tripId ?? t.id ?? t.trip_id;
      if (tid != null) tripToBlock.set(Number(tid), Number(blockId));
    });
  });

  const rows: Record<string, unknown>[] = [];

  duties.forEach((duty: any) => {
    const dutyId = duty.duty_id ?? duty.id;
    const segments = normalizeExportSegments(duty.duty_time_segments ?? [], tripById);
    const dutyTripIds: number[] = duty.trip_ids ?? [];
    const dutyExportFields = buildDutyExportFields(duty);

    if (segments.length > 0) {
      // ── Primary path: use solver segments ──
      segments.forEach((seg: any, idx: number) => {
        const baseEventType = seg.type ?? seg.event_type ?? 'unknown';
        const tripCount = Number(seg.trip_count ?? (Array.isArray(seg.trip_ids) ? seg.trip_ids.length : 0) ?? 0);
        const eventType = baseEventType === 'commercial_trip' && tripCount > 1
          ? 'commercial_trip_bundle'
          : baseEventType;
        const eventLabel = OPERATIONAL_EVENT_LABELS[eventType] ?? eventType;
        const startTime = Number(seg.start ?? 0);
        const endTime = Number(seg.end ?? 0);
        const computedDuration = endTime - startTime;
        const segDuration = Number(seg.duration ?? computedDuration);
        const durationMismatch = segDuration !== computedDuration;
        const tripIds = Array.isArray(seg.trip_ids) ? seg.trip_ids.join(';') : '';
        const eventScope = seg.event_scope ?? (baseEventType === 'commercial_trip' ? 'driver_vehicle' : 'driver');

        // Flags: respect segment-level overrides when available
        const isWorkTime = seg.is_work_time ?? WORK_TIME_TYPES.has(eventType);
        const isDrivingTime = seg.is_driving_time ?? DRIVING_TIME_TYPES.has(eventType);
        const isIdleTime = seg.is_idle_time ?? (baseEventType === 'idle' || baseEventType === 'driver_idle');
        const isNormalBreak = seg.is_normal_break ?? (baseEventType === 'normal_break');
        const isMandatoryRest = seg.is_mandatory_rest ?? (baseEventType === 'mandatory_rest');
        const isPullout = seg.is_pullout ?? (baseEventType === 'pullout');
        const isPullback = seg.is_pullback ?? (baseEventType === 'pullback');
        const restValid = seg.rest_valid ?? (baseEventType === 'mandatory_rest');
        const driverId = dutyId != null ? String(dutyId) : '';

        // Infer block_id from trip_ids or segment metadata
        const segBlockId = seg.block_id ?? seg.from_block_id ?? (
          Array.isArray(seg.trip_ids) && seg.trip_ids.length > 0
            ? tripToBlock.get(Number(seg.trip_ids[0]))
            : null
        ) ?? '';
        const {
          driver_display_name,
          operator_not_assigned,
          duty_start,
          duty_end,
          mandatory_rest_required,
          has_valid_mandatory_rest,
          issue_severity,
          issue_codes,
          issue_explanation,
        } = dutyExportFields;

        rows.push({
          schedule_id: scheduleId,
          block_id: segBlockId,
          duty_id: dutyId,
          driver_id: driverId,
          driver_display_name,
          operator_not_assigned,
          vehicle_id: eventScope === 'driver_vehicle' ? segBlockId : '',
          from_vehicle_id: seg.from_vehicle_id ?? seg.from_block_id ?? '',
          to_vehicle_id: seg.to_vehicle_id ?? seg.to_block_id ?? '',
          sequence: idx + 1,
          event_type: eventType,
          event_label: eventLabel,
          event_scope: eventScope,
          duty_start,
          duty_end,
          start_time: minToHHMMExport(startTime),
          end_time: minToHHMMExport(endTime),
          duration_minutes: segDuration,
          origin_id: seg.location_start ?? seg.location ?? '',
          destination_id: seg.location_end ?? seg.location ?? '',
          trip_ids: tripIds,
          trip_count: tripCount,
          is_work_time: toCsvBoolean(Boolean(isWorkTime)),
          is_driving_time: toCsvBoolean(Boolean(isDrivingTime)),
          is_idle_time: toCsvBoolean(Boolean(isIdleTime)),
          is_normal_break: toCsvBoolean(Boolean(isNormalBreak)),
          is_mandatory_rest: toCsvBoolean(Boolean(isMandatoryRest)),
          is_pullout: toCsvBoolean(Boolean(isPullout)),
          is_pullback: toCsvBoolean(Boolean(isPullback)),
          rest_valid: toCsvBoolean(Boolean(restValid)),
          mandatory_rest_required,
          has_valid_mandatory_rest,
          rule_code: '',
          violation_code: durationMismatch ? 'EXPORT_DURATION_MISMATCH' : '',
          issue_severity,
          issue_codes,
          issue_explanation,
          explanation: seg.explanation ?? (driverId ? 'Motorista real não disponível; usando identificador da jornada' : ''),
        });
      });
    } else {
      // ── Fallback: reconstruct from trip gaps ──
      const fallbackExplanation = 'Classificação inferida pelo frontend por ausência de segmentos do solver';

      // Get trips for this duty from blocks
      const dutyTrips = dutyTripIds
        .map((tid: number) => {
          for (const b of effectiveBlocks) {
            const found = (b.items || b.trips || []).find(
              (t: any) => (t.tripId ?? t.id ?? t.trip_id) === tid
            );
            if (found) return { ...found, _blockId: b.block_id ?? b.id };
          }
          return null;
        })
        .filter(Boolean)
        .sort((a: any, b: any) => (a.start_time ?? 0) - (b.start_time ?? 0));

      if (dutyTrips.length === 0) return;

      let seq = 0;
      dutyTrips.forEach((trip: any, idx: number) => {
        const tid = trip.tripId ?? trip.id ?? trip.trip_id;
        const st = Number(trip.start_time ?? 0);
        const et = Number(trip.end_time ?? 0);
        const driverId = dutyId != null ? String(dutyId) : '';
        const {
          driver_display_name,
          operator_not_assigned,
          duty_start,
          duty_end,
          mandatory_rest_required,
          has_valid_mandatory_rest,
          issue_severity,
          issue_codes,
          issue_explanation,
        } = dutyExportFields;
        seq++;
        rows.push({
          schedule_id: scheduleId,
          block_id: trip._blockId ?? '',
          duty_id: dutyId,
          driver_id: driverId,
          driver_display_name,
          operator_not_assigned,
          vehicle_id: trip._blockId ?? '',
          from_vehicle_id: '',
          to_vehicle_id: '',
          sequence: seq,
          event_type: 'commercial_trip',
          event_label: 'Viagem',
          event_scope: 'driver_vehicle',
          duty_start,
          duty_end,
          start_time: minToHHMMExport(st),
          end_time: minToHHMMExport(et),
          duration_minutes: et - st,
          origin_id: trip.origin_id ?? '',
          destination_id: trip.destination_id ?? '',
          trip_ids: String(tid),
          trip_count: 1,
          is_work_time: 'True',
          is_driving_time: 'True',
          is_idle_time: 'False',
          is_normal_break: 'False',
          is_mandatory_rest: 'False',
          is_pullout: 'False',
          is_pullback: 'False',
          rest_valid: 'False',
          mandatory_rest_required,
          has_valid_mandatory_rest,
          rule_code: '',
          violation_code: '',
          issue_severity,
          issue_codes,
          issue_explanation,
          explanation: driverId ? 'Motorista real não disponível; usando identificador da jornada' : fallbackExplanation,
        });

        // Gap between consecutive trips
        const nextTrip = dutyTrips[idx + 1];
        if (nextTrip) {
          const gapStart = et;
          const gapEnd = Number(nextTrip.start_time ?? 0);
          const gap = gapEnd - gapStart;
          if (gap > 0) {
            const gapType = gap >= 30 ? 'normal_break' : 'idle';
            seq++;
            rows.push({
              schedule_id: scheduleId,
              block_id: trip._blockId ?? '',
              duty_id: dutyId,
              driver_id: driverId,
              driver_display_name: dutyExportFields.driver_display_name,
              operator_not_assigned: dutyExportFields.operator_not_assigned,
              vehicle_id: '',
              from_vehicle_id: '',
              to_vehicle_id: '',
              sequence: seq,
              event_type: gapType,
              event_label: OPERATIONAL_EVENT_LABELS[gapType] ?? gapType,
              event_scope: 'driver',
              duty_start: dutyExportFields.duty_start,
              duty_end: dutyExportFields.duty_end,
              start_time: minToHHMMExport(gapStart),
              end_time: minToHHMMExport(gapEnd),
              duration_minutes: gap,
              origin_id: trip.destination_id ?? '',
              destination_id: nextTrip.origin_id ?? '',
              trip_ids: '',
              trip_count: 0,
              is_work_time: 'False',
              is_driving_time: 'False',
              is_idle_time: toCsvBoolean(gapType === 'idle'),
              is_normal_break: toCsvBoolean(gapType === 'normal_break'),
              is_mandatory_rest: 'False',
              is_pullout: 'False',
              is_pullback: 'False',
              rest_valid: 'False',
              mandatory_rest_required: dutyExportFields.mandatory_rest_required,
              has_valid_mandatory_rest: dutyExportFields.has_valid_mandatory_rest,
              rule_code: '',
              violation_code: '',
              issue_severity: dutyExportFields.issue_severity,
              issue_codes: dutyExportFields.issue_codes,
              issue_explanation: dutyExportFields.issue_explanation,
              explanation: driverId ? 'Motorista real não disponível; usando identificador da jornada' : fallbackExplanation,
            });
          }
        }
      });
    }
  });

  return rows;
}

function buildDetailedTripExportRows(
  duties: any[],
  tripById: Map<number, any>,
  scheduleId: number | string,
): Record<string, unknown>[] {
  return duties.flatMap((duty: any) => {
    const dutyId = duty.duty_id ?? duty.id;
    return resolveDutyDetailedTrips(duty, tripById).map((trip: any) => {
      const sourceTripId = Number(trip.source_trip_id ?? trip.tripId ?? trip.id ?? trip.trip_id ?? 0);
      const publicTripId = trip.trip_id ?? trip.public_trip_id ?? sourceTripId;
      const startTime = Number(trip.start_time ?? trip.startTime ?? 0);
      const endTime = Number(trip.end_time ?? trip.endTime ?? 0);
      return {
        schedule_id: scheduleId,
        duty_id: dutyId,
        driver_id: dutyId,
        sequence_in_duty: trip.sequence_in_duty ?? '',
        segment_sequence: trip.segment_sequence ?? '',
        sequence_in_bundle: trip.sequence_in_bundle ?? 1,
        bundle_trip_count: trip.bundle_trip_count ?? 1,
        bundle_event_type: trip.bundle_event_type ?? 'commercial_trip',
        source_trip_id: sourceTripId,
        public_trip_id: publicTripId,
        line_id: trip.line_id ?? trip.lineId ?? '',
        line_code: trip.line_code ?? trip.lineCode ?? '',
        direction: trip.direction ?? trip.sentido ?? '',
        start_time: minToHHMMExport(startTime),
        end_time: minToHHMMExport(endTime),
        duration_minutes: Number(trip.duration ?? trip.duracao ?? (endTime - startTime)),
        origin_id: trip.origin_id ?? trip.originId ?? '',
        destination_id: trip.destination_id ?? trip.destinationId ?? '',
        block_id: trip.block_id ?? '',
        vehicle_id: trip.vehicle_id ?? trip.block_id ?? '',
        sequence_in_block: trip.sequence_in_block ?? '',
        trip_group_id: trip.trip_group_id ?? '',
        pair_id: trip.pair_id ?? '',
      };
    });
  });
}

function buildDriverExportRows(
  duties: any[],
  tripById: Map<number, any>,
  scheduleId: number | string,
): Record<string, unknown>[] {
  return duties.flatMap((duty: any) => {
    const dutyId = duty.duty_id ?? duty.id;
    const dutyExportFields = buildDutyExportFields(duty);
    const normalizedSegments = normalizeExportSegments(duty.duty_time_segments ?? [], tripById);
    const detailedTrips = resolveDutyDetailedTrips(duty, tripById);
    const detailedBySegment = new Map<number, any[]>();

    detailedTrips.forEach((trip: any) => {
      const segmentSequence = Number(trip.segment_sequence ?? 0);
      if (!Number.isFinite(segmentSequence) || segmentSequence <= 0) {
        return;
      }
      const currentTrips = detailedBySegment.get(segmentSequence) ?? [];
      currentTrips.push(trip);
      detailedBySegment.set(segmentSequence, currentTrips);
    });

    return normalizedSegments.flatMap((segment: any, sequence: number) => {
      const segType = String(segment.type ?? segment.event_type ?? 'unknown');
      const {
        driver_display_name,
        operator_not_assigned,
        duty_start,
        duty_end,
        mandatory_rest_required,
        has_valid_mandatory_rest,
        issue_severity,
        issue_codes,
        issue_explanation,
      } = dutyExportFields;
      if (segType === 'commercial_trip') {
        const segmentTrips = sortOperationalTrips(detailedBySegment.get(sequence + 1) ?? []);
        if (segmentTrips.length > 0) {
          return segmentTrips.map((trip: any) => {
            const sourceTripId = trip.source_trip_id ?? trip.tripId ?? trip.id ?? trip.trip_id ?? '';
            const startTime = Number(trip.start_time ?? trip.startTime ?? 0);
            const endTime = Number(trip.end_time ?? trip.endTime ?? 0);
            return {
              schedule_id: scheduleId,
              duty_id: dutyId,
              driver_id: dutyId,
              driver_display_name,
              operator_not_assigned,
              duty_start,
              duty_end,
              sequence: sequence + 1,
              event_type: 'commercial_trip',
              event_label: OPERATIONAL_EVENT_LABELS.commercial_trip,
              event_scope: 'trip',
              line_code: trip.line_code ?? trip.lineCode ?? '',
              direction: trip.direction ?? trip.sentido ?? '',
              start_time: minToHHMMExport(startTime),
              end_time: minToHHMMExport(endTime),
              duration_minutes: Number(trip.duration ?? trip.duracao ?? (endTime - startTime)),
              trip_id: sourceTripId,
              trip_ids: String(sourceTripId),
              trip_count: 1,
              origin_id: trip.origin_id ?? trip.originId ?? '',
              destination_id: trip.destination_id ?? trip.destinationId ?? '',
              vehicle_id: trip.vehicle_id ?? trip.block_id ?? '',
              from_vehicle_id: '',
              to_vehicle_id: '',
              sequence_in_duty: trip.sequence_in_duty ?? '',
              sequence_in_bundle: trip.sequence_in_bundle ?? 1,
              mandatory_rest_required,
              has_valid_mandatory_rest,
              issue_severity,
              issue_codes,
              issue_explanation,
              explanation: segment.explanation ?? '',
            };
          });
        }
      }

      const tripCount = Number(segment.trip_count ?? (Array.isArray(segment.trip_ids) ? segment.trip_ids.length : 0) ?? 0);
      const eventType = segType === 'commercial_trip' && tripCount > 1 ? 'commercial_trip_bundle' : segType;
      const startTime = Number(segment.start ?? 0);
      const endTime = Number(segment.end ?? startTime);
      const eventScope = segment.event_scope ?? 'driver';

      return [{
        schedule_id: scheduleId,
        duty_id: dutyId,
        driver_id: dutyId,
        driver_display_name,
        operator_not_assigned,
        duty_start,
        duty_end,
        sequence: sequence + 1,
        event_type: eventType,
        event_label: OPERATIONAL_EVENT_LABELS[eventType] ?? eventType,
        event_scope: eventScope,
        line_code: '',
        direction: '',
        start_time: minToHHMMExport(startTime),
        end_time: minToHHMMExport(endTime),
        duration_minutes: Number(segment.duration ?? (endTime - startTime)),
        trip_id: '',
        trip_ids: Array.isArray(segment.trip_ids) ? segment.trip_ids.join(';') : '',
        trip_count: tripCount,
        origin_id: segment.location_start ?? segment.location ?? '',
        destination_id: segment.location_end ?? segment.location ?? '',
        vehicle_id: eventScope === 'driver_vehicle' ? (segment.vehicle_id ?? segment.block_id ?? '') : '',
        from_vehicle_id: segment.from_vehicle_id ?? segment.from_block_id ?? '',
        to_vehicle_id: segment.to_vehicle_id ?? segment.to_block_id ?? '',
        sequence_in_duty: '',
        sequence_in_bundle: '',
        mandatory_rest_required,
        has_valid_mandatory_rest,
        issue_severity,
        issue_codes,
        issue_explanation,
        explanation: segment.explanation ?? '',
      }];
    });
  });
}

// ─── EventKindChip ────────────────────────────────────────────────────────────
function eventDisplayLabel(event: Pick<PlanEvent, 'kind' | 'gapMinutes' | 'intervalKind'>): string {
  if (event.kind !== 'descanso') return EVENT_CONFIG[event.kind].label;
  const duration = event.gapMinutes != null ? ` (${minToDuration(event.gapMinutes)})` : '';
  if (event.intervalKind === 'refeicao') return `Intervalo normal${duration}`;
  if (event.intervalKind === 'descanso') return `Descanso obrigatório${duration}`;
  return `Ociosa${duration}`;
}

function EventKindChip({ kind, gap, intervalKind }: { kind: EventKind; gap?: number; intervalKind?: IntervalKind }) {
  const cfg = EVENT_CONFIG[kind];
  if (kind === 'descanso' && gap != null) {
    const resolvedKind: IntervalKind = intervalKind ?? 'espera';
    return (
      <Chip
        size="small"
        icon={resolvedKind === 'espera' ? undefined : <IconCoffee size={12} />}
        label={eventDisplayLabel({ kind, gapMinutes: gap, intervalKind: resolvedKind })}
        color={resolvedKind === 'refeicao' ? 'success' : resolvedKind === 'descanso' ? 'warning' : 'default'}
        variant="outlined"
        sx={{ fontWeight: 700 }}
      />
    );
  }
  return (
    <Tooltip title={cfg.description} arrow placement="top">
      <Chip
        size="small"
        icon={<>{cfg.icon}</>}
        label={cfg.label}
        color={cfg.color}
        variant="outlined"
        sx={{ fontWeight: 700 }}
      />
    </Tooltip>
  );
}

// ─── Sub-table columns header ─────────────────────────────────────────────────
const EVENT_COLS = ['Evento', 'Linha', 'Sentido', 'Início', 'Chegada', 'Origem', 'Destino', 'KM'];
const VEHICLE_HEADER_COLS = 6;

// ─── CollapsibleGroupRow ──────────────────────────────────────────────────────
interface CollapsibleGroupRowProps {
  group: PlanGroup;
  showCost?: boolean;
  defaultOpen?: boolean;
}

function CollapsibleGroupRow({ group, showCost = false, defaultOpen = false }: CollapsibleGroupRowProps) {
  const [open, setOpen] = useState(defaultOpen);
  const theme = useTheme();
  const cols = VEHICLE_HEADER_COLS + (showCost ? 2 : 1);

  return (
    <>
      <TableRow
        onClick={() => setOpen((o) => !o)}
        sx={{
          cursor: 'pointer',
          bgcolor: open ? alpha(theme.palette.primary.main, 0.06) : 'background.paper',
          '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.04) },
          '& > td': { fontWeight: 700 },
        }}
      >
        <TableCell sx={{ width: 40, p: 0.5 }}>
          <IconButton size="small">{open ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}</IconButton>
        </TableCell>
        <TableCell sx={{ fontWeight: 800, color: 'primary.main' }}>
          <Stack spacing={0.25}>
            <Typography variant="body2" sx={{ fontWeight: 800, color: 'primary.main' }}>{group.label}</Typography>
            {group.driverDisplayName && (
              <Typography variant="caption" color="text.secondary">{group.driverDisplayName}</Typography>
            )}
          </Stack>
        </TableCell>
        <TableCell align="center">{group.tripCount} viagens</TableCell>
        <TableCell>{minToHHMM(group.startTime)}</TableCell>
        <TableCell>{minToHHMM(group.endTime)}</TableCell>
        {group.workTime !== undefined && (
          <TableCell>{minToDuration(group.workTime)}</TableCell>
        )}
        <TableCell align="right">{group.totalKm.toFixed(1)} km</TableCell>
        {showCost && <TableCell align="right">{fmtCurrency(group.totalCost ?? 0)}</TableCell>}
        <TableCell>
          <Stack direction="row" spacing={0.75} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {group.operatorNotAssigned && (
              <Chip size="small" label="Sem operador" variant="outlined" />
            )}
            {(group.issueCodes?.length ?? 0) > 0 ? (
              <Chip size="small" label={`Soft issue: ${group.issueCodes?.join(', ')}`} color="warning" />
            ) : (group.violations ?? 0) > 0 ? (
              <Chip size="small" label={`${group.violations} violação(ões)`} color="error" />
            ) : null}
          </Stack>
        </TableCell>
      </TableRow>

      <TableRow>
        <TableCell colSpan={cols + 2} sx={{ p: 0, border: 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box sx={{ bgcolor: alpha(theme.palette.background.default, 0.6), px: 3, py: 1 }}>
              {(group.operatorNotAssigned || (group.issueCodes?.length ?? 0) > 0) && (
                <Stack spacing={1} sx={{ mb: 1.5 }}>
                  {(group.issueCodes?.length ?? 0) > 0 && (
                    <Alert severity={group.issueSeverity === 'soft' ? 'warning' : 'error'}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {group.issueCodes?.join(', ')}
                      </Typography>
                      {group.issueExplanation && (
                        <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                          {group.issueExplanation}
                        </Typography>
                      )}
                    </Alert>
                  )}
                  {group.operatorNotAssigned && (
                    <Alert severity="info">
                      Operador real não atribuído. A jornada está sendo identificada por {formatDutyReference(group.id)} apenas para rastreabilidade.
                    </Alert>
                  )}
                </Stack>
              )}
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: 'background.default' }}>
                    {EVENT_COLS.map((col) => (
                      <TableCell key={col} sx={{ fontWeight: 700, fontSize: '0.72rem', py: 0.75 }}>{col}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {group.events.map((ev, idx) => (
                    <EventSubRow key={idx} event={ev} />
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

// ─── EventSubRow ──────────────────────────────────────────────────────────────
function EventSubRow({ event }: { event: PlanEvent }) {
  const theme = useTheme();
  const isDescanso = event.kind === 'descanso';
  const isShortWait = isDescanso && event.intervalKind === 'espera';

  return (
    <TableRow sx={{
      bgcolor: isDescanso
        ? alpha(isShortWait ? theme.palette.text.secondary : theme.palette.warning.main, 0.06)
        : event.kind === 'soltura'
        ? alpha(theme.palette.success.main, 0.05)
        : event.kind === 'recolhimento'
        ? alpha(theme.palette.error.main, 0.05)
        : 'inherit',
    }}>
      <TableCell sx={{ py: 0.5, minWidth: 160 }}>
        <EventKindChip kind={event.kind} gap={event.gapMinutes} intervalKind={event.intervalKind} />
      </TableCell>
      <TableCell sx={{ py: 0.5 }}>
        {!isDescanso && event.color && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: event.color, flexShrink: 0 }} />
            <Typography variant="caption" sx={{ fontWeight: 600 }}>{event.linha}</Typography>
          </Box>
        )}
        {(isDescanso || !event.color) && (
          <Typography variant="caption" color="text.secondary">{isDescanso ? '—' : event.linha}</Typography>
        )}
      </TableCell>
      <TableCell sx={{ py: 0.5 }}>
        <Typography variant="caption">{isDescanso ? '—' : event.sentido}</Typography>
      </TableCell>
      <TableCell sx={{ py: 0.5 }}>
        <Typography variant="caption" sx={{ fontWeight: 600 }}>{minToHHMM(event.inicio)}</Typography>
      </TableCell>
      <TableCell sx={{ py: 0.5 }}>
        <Typography variant="caption" sx={{ fontWeight: 600 }}>{minToHHMM(event.chegada)}</Typography>
      </TableCell>
      <TableCell sx={{ py: 0.5 }}>
        <Typography variant="caption">{event.origemName}</Typography>
      </TableCell>
      <TableCell sx={{ py: 0.5 }}>
        <Typography variant="caption">{event.destinoName}</Typography>
      </TableCell>
      <TableCell sx={{ py: 0.5 }} align="right">
        <Typography variant="caption">{isDescanso ? minToDuration(event.duracao) : `${event.km}`}</Typography>
      </TableCell>
    </TableRow>
  );
}

// ─── GanttTimeHeader ──────────────────────────────────────────────────────────
const GanttTimeHeader = React.memo(({ scale, theme }: { scale: number; theme: Theme }) => {
  const ppm = scale * BASE_PIXELS_PER_MINUTE;
  const marks: React.ReactNode[] = [];
  for (let min = 0; min <= HORIZON_MINUTES; min += 60) {
    const left = SIDEBAR_WIDTH + min * ppm;
    const isOvernight = min >= OVERNIGHT_START_MIN;
    marks.push(
      <Box key={min} sx={{ position: 'absolute', left, top: 0, height: '100%' }}>
        <Box sx={{ width: '1px', height: '100%', bgcolor: isOvernight ? 'warning.light' : 'divider', opacity: 0.6 }} />
        <Typography variant="caption" sx={{
          position: 'absolute', top: 6, left: 4, fontSize: '0.6rem',
          color: isOvernight ? 'warning.dark' : 'text.secondary',
          fontWeight: isOvernight ? 700 : 400, whiteSpace: 'nowrap',
        }}>
          {minToHHMM(min)}
        </Typography>
      </Box>
    );
  }
  return (
    <Box sx={{ position: 'relative', height: HEADER_HEIGHT, borderBottom: `1px solid ${theme.palette.divider}`, bgcolor: 'background.default', overflow: 'hidden' }}>
      <Box sx={{ position: 'absolute', left: SIDEBAR_WIDTH + OVERNIGHT_START_MIN * ppm, top: 0, bottom: 0, right: 0, bgcolor: alpha(theme.palette.warning.main, 0.07), pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: SIDEBAR_WIDTH, bgcolor: 'background.paper', borderRight: `1px solid ${theme.palette.divider}`, zIndex: 1 }} />
      {marks}
    </Box>
  );
});
GanttTimeHeader.displayName = 'GanttTimeHeader';

// ─── GanttRowItem ─────────────────────────────────────────────────────────────
const GanttRowItem = React.memo(({
  item, scale, onDragStart, colors,
}: { item: any; scale: number; onDragStart: (e: React.DragEvent, item: any) => void; colors: any }) => {
  const left = item.start_time * scale * BASE_PIXELS_PER_MINUTE;
  const width = (item.end_time - item.start_time) * scale * BASE_PIXELS_PER_MINUTE;
  const isApoio = item.kind === 'apoio' || (!item.lineId && !item.lineCode);

  return (
    <Tooltip arrow title={
      <Box sx={{ p: 0.5 }}>
        <Typography variant="caption" sx={{ display: 'block', fontWeight: 700 }}>
          {isApoio ? 'Apoio / Ociosa' : `Viagem ${item.tripId} — Linha ${item.lineCode || item.lineId}`}
        </Typography>
        <Typography variant="caption" sx={{ display: 'block' }}>
          {minToHHMM(item.start_time)} → {minToHHMM(item.end_time)} ({minToDuration(item.end_time - item.start_time)})
        </Typography>
        {!isApoio && <Typography variant="caption" sx={{ display: 'block', mt: 0.5, opacity: 0.8 }}>Clique e arraste para reatribuir</Typography>}
      </Box>
    }>
      <Box
        draggable={!isApoio}
        onDragStart={(e) => !isApoio && onDragStart(e, item)}
        sx={{
          position: 'absolute', left, width: Math.max(width, 4), height: 34, top: 17, borderRadius: 1,
          backgroundColor: isApoio ? colors.deadhead : item.color,
          border: '1px solid', borderColor: isApoio ? colors.deadheadBorder : alpha(item.color, 0.5),
          cursor: isApoio ? 'default' : 'grab',
          display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
          transition: 'transform 0.1s, box-shadow 0.1s',
          '&:hover': { transform: isApoio ? 'none' : 'scaleY(1.05)', boxShadow: isApoio ? 'none' : 3, zIndex: 10 },
          '&:active': { cursor: 'grabbing' },
          ...(isApoio && {
            backgroundImage: `linear-gradient(45deg, ${colors.deadheadBorder} 12.5%, transparent 12.5%, transparent 50%, ${colors.deadheadBorder} 50%, ${colors.deadheadBorder} 62.5%, transparent 62.5%, transparent 100%)`,
            backgroundSize: '8px 8px',
          }),
        }}
      >
        {!isApoio && width > 40 && (
          <Typography variant="caption" sx={{ color: 'white', fontWeight: 800, fontSize: '0.65rem', textShadow: '0px 1px 2px rgba(0,0,0,0.5)', userSelect: 'none' }}>
            {item.lineCode || item.lineId}
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
});
GanttRowItem.displayName = 'GanttRowItem';

// ─── Main Component ───────────────────────────────────────────────────────────
export function TabGantt({ res, lines, terminals, intervalPolicy, onWhatIfUpdate }: TabGanttProps) {
  const theme = useTheme();
  const colors = useMemo(() => getGanttColors(theme), [theme]);
  const linePalette = useMemo(() => getLinePalette(theme), [theme]);

  // 0=Gantt, 1=Veículos, 2=Motoristas, 3=Viagens
  const [activeTab, setActiveTab] = useState(0);
  const [scale, setScale] = useState(2.5);
  const [localBlocks, setLocalBlocks] = useState<any[]>([]);
  const [backupBlocks, setBackupBlocks] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [notification, setNotification] = useState<{ msg: string; sev: 'success' | 'error' | 'info' } | null>(null);
  const ganttScrollRef = useRef<HTMLDivElement>(null);

  // Centraliza o scroll horizontal no horário atual (ou no primeiro evento se for fora do horário operacional).
  const scrollToNow = useCallback(() => {
    const container = ganttScrollRef.current;
    if (!container) return;
    const now = new Date();
    const minutesNow = now.getHours() * 60 + now.getMinutes();
    const ppm = scale * BASE_PIXELS_PER_MINUTE;
    const targetX = minutesNow * ppm;
    // centraliza: posiciona o "agora" no meio da viewport visível
    const offset = container.clientWidth / 2;
    container.scrollTo({ left: Math.max(0, targetX - offset), behavior: 'smooth' });
  }, [scale]);

  const [filterLine, setFilterLine] = useState<string>('');
  const [filterSearch, setFilterSearch] = useState('');
  const [hoverBlockId, setHoverBlockId] = useState<number | null>(null);

  const tripMetadataRef = useRef<Map<number, TripMetadata>>(new Map());
  const localBlocksRef = useRef<any[]>([]);
  const backupBlocksRef = useRef<any[]>([]);
  const baselineCostRef = useRef<number>(0);
  const hydratedIdentityRef = useRef<string | null>(null);

  // índice por lineId (código alfanumérico) para lookup rápido no buildEvents
  const lineByCode = useMemo(() => new Map(lines.map((l) => [l.lineId ?? '', l])), [lines]);
  const terminalMap = useMemo(() => new Map(terminals.map((t) => [t.id, t])), [terminals]);
  const ppm = scale * BASE_PIXELS_PER_MINUTE;
  const totalWidth = HORIZON_MINUTES * ppm + SIDEBAR_WIDTH;

  const sourceBlocks = useMemo(() => {
    if (Array.isArray((res as any)?.blocks)) return (res as any).blocks;
    if (Array.isArray((res as any)?.result?.blocks)) return (res as any).result.blocks;
    return [];
  }, [res]);

  const hydrateBlocks = useCallback((rawBlocks: any[]) => {
    if (!Array.isArray(rawBlocks) || rawBlocks.length === 0) return [];

    const codeColorMap = new Map<string, string>();
    let colorIdx = 0;
    rawBlocks.forEach((block) => {
      (block as any).trips?.forEach((trip: any) => {
        if (typeof trip === 'number') return;
        const code = trip.line_code ?? trip.lineCode ?? null;
        if (code && !codeColorMap.has(code)) {
          codeColorMap.set(code, linePalette[colorIdx % linePalette.length]);
          colorIdx += 1;
        }
      });
    });

    return rawBlocks
      .map((block) => {
        const b = block as any;
        const blockId = b.block_id ?? b.blockId ?? b.id;
        const items = (b.trips || [])
          .map((trip: any) => {
            const tripId = trip.id ?? trip.trip_id ?? getTripPublicId(trip);
            const code = trip.line_code ?? trip.lineCode ?? null;
            const color = code ? (codeColorMap.get(code) ?? linePalette[0]) : linePalette[0];
            return {
              ...trip,
              tripId,
              lineId: trip.line_id ?? trip.lineId ?? null,
              lineCode: code,
              start_time: trip.start_time ?? trip.startTime ?? 0,
              end_time: trip.end_time ?? trip.endTime ?? 0,
              color,
              kind: 'trip',
              block_id: blockId,
            };
          })
          .sort((a: any, z: any) => a.start_time - z.start_time);

        return {
          ...block,
          id: blockId,
          block_id: blockId,
          start_time: b.start_time ?? b.startTime ?? 0,
          end_time: b.end_time ?? b.endTime ?? 0,
          items,
        };
      })
      .sort((a: any, b: any) => (a.block_id || 0) - (b.block_id || 0));
  }, [linePalette]);

  const hydratedBlocks = useMemo(() => hydrateBlocks(sourceBlocks), [sourceBlocks, hydrateBlocks]);
  const hydratedIdentity = useMemo(() => {
    const scheduleId = (res as any)?.id ?? (res as any)?.scheduleId ?? 'no-schedule';
    const updatedAt = (res as any)?.updatedAt ?? (res as any)?.createdAt ?? 'no-date';
    return `${scheduleId}:${updatedAt}:${hydratedBlocks.length}`;
  }, [res, hydratedBlocks.length]);

  const cloneBlocks = useCallback((blocks: any[]) => {
    if (typeof structuredClone === 'function') {
      return structuredClone(blocks);
    }
    return JSON.parse(JSON.stringify(blocks));
  }, []);

  const effectiveBlocks = useMemo(
    () => (localBlocks.length > 0 ? localBlocks : hydratedBlocks),
    [localBlocks, hydratedBlocks],
  );

  const presentLineCodes = useMemo(() => {
    const codes = new Set<string>();
    (effectiveBlocks || []).forEach((b) =>
      (b.items || []).forEach((t: any) => { const c = t.lineCode || t.line_code; if (c) codes.add(c); })
    );
    return [...codes].sort();
  }, [effectiveBlocks]);

  // ─── Hydration ───
  useEffect(() => {
    if (!res || hydratedBlocks.length === 0) return;
    if (hydratedIdentityRef.current === hydratedIdentity) return;

    const metadata = new Map<number, TripMetadata>();
    hydratedBlocks.forEach((block) => {
      (block.items || []).forEach((item: any) => {
        metadata.set(item.tripId, { lineId: item.lineId ?? null, lineCode: item.lineCode ?? null, color: item.color });
      });
    });
    tripMetadataRef.current = metadata;

    baselineCostRef.current = res ? ((res as any).totalCost ?? (res as any).total_cost ?? 0) : 0;
    const liveSnapshot = cloneBlocks(hydratedBlocks);
    const backupSnapshot = cloneBlocks(hydratedBlocks);
    setLocalBlocks(liveSnapshot);
    setBackupBlocks(backupSnapshot);
    localBlocksRef.current = liveSnapshot;
    backupBlocksRef.current = backupSnapshot;
    hydratedIdentityRef.current = hydratedIdentity;
  }, [res, hydratedBlocks, hydratedIdentity, cloneBlocks]);

  const resWithLocalBlocks = useMemo(() => ({ ...res, blocks: effectiveBlocks }), [res, effectiveBlocks]);

  const filteredBlocks = useMemo(() => {
    return effectiveBlocks.filter((block) => {
      if (filterLine && !block.items?.some((t: any) => (t.lineCode ?? t.line_code) === filterLine)) return false;
      if (filterSearch) {
        const q = filterSearch.toLowerCase();
        return String(block.block_id).includes(q) || block.items?.some((t: any) =>
          String(t.tripId ?? '').includes(q) || String(t.lineCode ?? '').toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [effectiveBlocks, filterLine, filterSearch]);

  const unassignedTrips: any[] = useMemo(() => {
    if (!res) return [];
    const raw = (res as any).metadata?.unassigned_trips || (res as any).unassigned_trips || [];
    return Array.isArray(raw) ? raw : [];
  }, [res]);

  const duties = useMemo(() => {
    if (!res) return [];
    return (res as any).resultSummary?.duties || (res as any).duties || [];
  }, [res]);

  const scheduleId = useMemo(
    () => (res as any)?.id ?? (res as any)?.scheduleId ?? '',
    [res],
  );

  const dutyAuditById = useMemo(() => {
    const auditMap = new Map<number, DutyAuditSummary>();
    duties.forEach((duty: any) => {
      const dutyId = Number(duty.duty_id ?? duty.id ?? 0);
      auditMap.set(dutyId, buildDutyAuditSummary(duty));
    });
    return auditMap;
  }, [duties]);

  // Pullout/pullback times per block derived from duty_time_segments (authoritative source)
  const blockPullTimes = useMemo(() => {
    // Build trip→blockId from effectiveBlocks to correct optimizer block_id mismatches
    const tripToBlock = new Map<number, number>();
    effectiveBlocks.forEach((b) => {
      (b.items || []).forEach((t: any) => {
        if (t.tripId) tripToBlock.set(Number(t.tripId), Number(b.block_id));
      });
    });

    const resolveBlockId = (seg: any): number => {
      // Prefer trip-based lookup (authoritative) over segment's block_id (may be stale/mismatched)
      const tripIds: number[] = Array.isArray(seg?.trip_ids) ? seg.trip_ids.map(Number) : [];
      for (const tid of tripIds) {
        const bid = tripToBlock.get(tid);
        if (bid) return bid;
      }
      return Number(seg?.block_id ?? seg?.vehicle_id ?? 0);
    };

    const pullout = new Map<number, { start: number; end: number }>();
    const pullback = new Map<number, { start: number; end: number }>();
    duties.forEach((duty: any) => {
      const segs: any[] = duty.duty_time_segments || [];
      const poSeg = segs.find((s: any) => s.type === 'pullout' || s.type === 'vehicle_pullout');
      if (poSeg) {
        const firstCT = segs.find((s: any) => s.type === 'commercial_trip');
        const bid = resolveBlockId(firstCT);
        if (bid && !pullout.has(bid))
          pullout.set(bid, { start: Number(poSeg.start), end: Number(poSeg.end) });
      }
      const pbSeg = [...segs].reverse().find((s: any) => s.type === 'pullback' || s.type === 'vehicle_pullback');
      if (pbSeg) {
        const lastCT = [...segs].reverse().find((s: any) => s.type === 'commercial_trip');
        const bid = resolveBlockId(lastCT);
        if (bid && !pullback.has(bid))
          pullback.set(bid, { start: Number(pbSeg.start), end: Number(pbSeg.end) });
      }
    });
    return { pullout, pullback };
  }, [duties, effectiveBlocks]);

  // ─── PlanGroups for Veículos tab ───
  // Vehicles show only commercial trips + one pullout (soltura) + one pullback (recolhimento).
  // Driver-specific events (descanso, troca_motorista) are NOT shown in the vehicle view.
  const vehicleGroups = useMemo((): PlanGroup[] => {
    return effectiveBlocks.map((block) => {
      const allItems: any[] = block.items || [];
      // Commercial trips are items with a line code or line id; include all as viagem
      const trips = allItems.length > 0 ? allItems : [];
      if (trips.length === 0) {
        return { id: block.block_id, label: `Veículo ${block.block_id}`, tripCount: 0, totalKm: 0, startTime: 0, endTime: 0, events: [] };
      }

      const tName = (id?: number) =>
        id != null ? (terminalMap.get(id)?.shortName ?? terminalMap.get(id)?.name ?? `T${id}`) : '—';

      const events: PlanEvent[] = [];
      const firstTrip = trips[0];
      const lastTrip = trips[trips.length - 1];

      // Soltura: 1) duty_time_segments, 2) block metadata buffer, 3) line config, 4) company params
      const po = blockPullTimes.pullout.get(block.block_id);
      const startBuffer = Number(block.metadata?.start_buffer_minutes ?? 0);
      const firstLine = lineByCode.get(firstTrip.lineCode ?? '');
      const solturaFromLine = firstLine?.solturaMinutes ?? 0;
      const solturaFromPolicy = intervalPolicy?.pulloutMinutes ?? 0;
      if (po && po.end > po.start) {
        events.push({ kind: 'soltura', linha: '—', sentido: '—', inicio: po.start, chegada: po.end, origemName: '(Garagem)', destinoName: tName(firstTrip.origin_id), km: 0, duracao: po.end - po.start, vehicleId: block.block_id });
      } else if (startBuffer > 0) {
        const solturaEnd = firstTrip.start_time ?? 0;
        events.push({ kind: 'soltura', linha: '—', sentido: '—', inicio: solturaEnd - startBuffer, chegada: solturaEnd, origemName: '(Garagem)', destinoName: tName(firstTrip.origin_id), km: 0, duracao: startBuffer, vehicleId: block.block_id });
      } else if (solturaFromLine > 0) {
        const solturaEnd = firstTrip.start_time ?? 0;
        events.push({ kind: 'soltura', linha: '—', sentido: '—', inicio: solturaEnd - solturaFromLine, chegada: solturaEnd, origemName: firstLine?.garageTerminalId ? tName(firstLine.garageTerminalId) : '(Garagem)', destinoName: tName(firstTrip.origin_id), km: firstLine?.garageDistanceKm ?? 0, duracao: solturaFromLine, vehicleId: block.block_id });
      } else if (solturaFromPolicy > 0) {
        const solturaEnd = firstTrip.start_time ?? 0;
        events.push({ kind: 'soltura', linha: '—', sentido: '—', inicio: solturaEnd - solturaFromPolicy, chegada: solturaEnd, origemName: '(Garagem)', destinoName: tName(firstTrip.origin_id), km: 0, duracao: solturaFromPolicy, vehicleId: block.block_id });
      }

      // All trips — vehicles do not have driver breaks between trips
      trips.forEach((t: any) => {
        events.push({
          kind: 'viagem', tripId: t.tripId,
          linha: t.lineCode ?? String(t.lineId ?? '—'),
          sentido: t.direction ?? t.sentido ?? '—',
          inicio: t.start_time ?? 0, chegada: t.end_time ?? 0,
          origemName: tName(t.origin_id), destinoName: tName(t.destination_id),
          km: t.distance_km ?? 0, duracao: (t.end_time ?? 0) - (t.start_time ?? 0),
          vehicleId: block.block_id, color: t.color,
        });
      });

      // Recolhimento: 1) duty_time_segments, 2) block metadata buffer, 3) line config, 4) company params
      const pb = blockPullTimes.pullback.get(block.block_id);
      const endBuffer = Number(block.metadata?.end_buffer_minutes ?? 0);
      const lastLine = lineByCode.get(lastTrip.lineCode ?? '');
      const recolhFromLine = lastLine?.recolhimentoMinutes ?? 0;
      const recolhFromPolicy = intervalPolicy?.pullbackMinutes ?? 0;
      if (pb && pb.end > pb.start) {
        events.push({ kind: 'recolhimento', linha: '—', sentido: '—', inicio: pb.start, chegada: pb.end, origemName: tName(lastTrip.destination_id), destinoName: '(Garagem)', km: 0, duracao: pb.end - pb.start, vehicleId: block.block_id });
      } else if (endBuffer > 0) {
        const recolhStart = lastTrip.end_time ?? 0;
        events.push({ kind: 'recolhimento', linha: '—', sentido: '—', inicio: recolhStart, chegada: recolhStart + endBuffer, origemName: tName(lastTrip.destination_id), destinoName: '(Garagem)', km: 0, duracao: endBuffer, vehicleId: block.block_id });
      } else if (recolhFromLine > 0) {
        const recolhStart = lastTrip.end_time ?? 0;
        events.push({ kind: 'recolhimento', linha: '—', sentido: '—', inicio: recolhStart, chegada: recolhStart + recolhFromLine, origemName: tName(lastTrip.destination_id), destinoName: lastLine?.garageTerminalId ? tName(lastLine.garageTerminalId) : '(Garagem)', km: lastLine?.recolhimentoDistanceKm ?? 0, duracao: recolhFromLine, vehicleId: block.block_id });
      } else if (recolhFromPolicy > 0) {
        const recolhStart = lastTrip.end_time ?? 0;
        events.push({ kind: 'recolhimento', linha: '—', sentido: '—', inicio: recolhStart, chegada: recolhStart + recolhFromPolicy, origemName: tName(lastTrip.destination_id), destinoName: '(Garagem)', km: 0, duracao: recolhFromPolicy, vehicleId: block.block_id });
      }

      const solturaEvt = events.find(e => e.kind === 'soltura');
      const recolhEvt = events.slice().reverse().find(e => e.kind === 'recolhimento');
      const commercialTrips = trips.filter((t: any) => t.lineCode || t.lineId);
      return {
        id: block.block_id,
        label: `Veículo ${block.block_id}`,
        tripCount: commercialTrips.length,
        totalKm: events.reduce((s, e) => s + (e.km ?? 0), 0),
        startTime: solturaEvt?.inicio ?? trips[0]?.start_time ?? 0,
        endTime: recolhEvt?.chegada ?? trips[trips.length - 1]?.end_time ?? 0,
        events,
      };
    });
  }, [effectiveBlocks, terminalMap, blockPullTimes, lineByCode, intervalPolicy]);

  // ─── PlanGroups for Motoristas tab ───
  const tripById = useMemo(() => {
    const map = new Map<number, any>();
    effectiveBlocks.forEach((b) => (b.items || []).forEach((t: any) => map.set(t.tripId, t)));
    return map;
  }, [effectiveBlocks]);

  // Quais são a 1ª e última viagem de cada bloco (para decidir soltura/recolhimento do motorista)
  const blockFirstLastTrip = useMemo(() => {
    const map = new Map<number, { firstTripId: number; lastTripId: number }>();
    effectiveBlocks.forEach((b) => {
      const sorted = (b.items || [])
        .filter((t: any) => t.lineCode || t.lineId)
        .sort((a: any, z: any) => (a.start_time ?? 0) - (z.start_time ?? 0));
      if (sorted.length > 0)
        map.set(b.block_id, { firstTripId: sorted[0].tripId, lastTripId: sorted[sorted.length - 1].tripId });
    });
    return map;
  }, [effectiveBlocks]);

  // tripId → dutyId (para a aba Viagens)
  const tripToDutyId = useMemo(() => {
    const map = new Map<number, number>();
    duties.forEach((duty: any) => {
      const dutyId = duty.duty_id ?? duty.id;
      (duty.trip_ids || []).forEach((tid: number) => map.set(tid, dutyId));
    });
    return map;
  }, [duties]);

  const dutyGroups = useMemo((): PlanGroup[] => {
    return duties.map((duty: any) => {
      const dutyId = duty.duty_id ?? duty.id;
      const tripIds: number[] = duty.trip_ids || duty.trips || [];
      const fallbackDutyTrips = tripIds
        .map((id) => tripById.get(id))
        .filter(Boolean)
        .sort((a: any, b: any) => (a.start_time ?? 0) - (b.start_time ?? 0));
      const detailedDutyTrips = resolveDutyDetailedTrips(duty, tripById);
      const dutyTrips = detailedDutyTrips.length > 0 ? detailedDutyTrips : fallbackDutyTrips;

      // Soltura só se o motorista conduz a 1ª viagem do bloco de veículo
      // Recolhimento só se o motorista conduz a última viagem do bloco de veículo
      const firstDutyTripId = dutyTrips[0]?.source_trip_id ?? dutyTrips[0]?.tripId ?? dutyTrips[0]?.id;
      const lastDutyTripId = dutyTrips[dutyTrips.length - 1]?.source_trip_id ?? dutyTrips[dutyTrips.length - 1]?.tripId ?? dutyTrips[dutyTrips.length - 1]?.id;
      let includeSoltura = false;
      let includeRecolhimento = false;
      for (const { firstTripId, lastTripId } of blockFirstLastTrip.values()) {
        if (firstDutyTripId === firstTripId) includeSoltura = true;
        if (lastDutyTripId === lastTripId) includeRecolhimento = true;
      }


      let events: PlanEvent[] = [];
      const segments = duty.duty_time_segments;
      if (segments && segments.length > 0) {
        events = buildEventsFromSegments(segments, dutyId, terminalMap, tripById, detailedDutyTrips);
      } else {
        events = buildEvents(fallbackDutyTrips, terminalMap, lineByCode, intervalPolicy, undefined, dutyId, includeSoltura, includeRecolhimento);
      }

      // Enforce soltura/recolhimento based on vehicle allocation regardless of segment path
      if (!includeSoltura) events = events.filter(e => e.kind !== 'soltura');
      if (!includeRecolhimento) events = events.filter(e => e.kind !== 'recolhimento');

      const violations = (duty.shift_violations ?? 0) + (duty.rest_violations ?? 0);
      const audit = dutyAuditById.get(Number(dutyId)) ?? buildDutyAuditSummary(duty);

      // Jornada: usa duty_start/duty_end segment times as authoritative fallback
      const solturaEvt = events.find(e => e.kind === 'soltura');
      const recolhEvt = events.slice().reverse().find(e => e.kind === 'recolhimento');
      const jornStartEvt = events.find(e => e.kind === 'inicio_jornada');
      const jornEndEvt = events.slice().reverse().find(e => e.kind === 'fim_jornada');
      const jornStart = solturaEvt?.inicio ?? jornStartEvt?.inicio ?? duty.start_time ?? dutyTrips[0]?.start_time ?? 0;
      const jornEnd = recolhEvt?.chegada ?? jornEndEvt?.chegada ?? duty.end_time ?? dutyTrips[dutyTrips.length - 1]?.end_time ?? 0;

      return {
        id: dutyId,
        label: `Jornada ${formatDutyReference(dutyId)}`,
        tripCount: dutyTrips.length,
        totalKm: events.reduce((s, e) => s + (e.km ?? 0), 0),
        startTime: jornStart,
        endTime: jornEnd,
        workTime: jornEnd - jornStart,
        totalCost: duty.total_cost ?? 0,
        violations,
        driverDisplayName: audit.driverDisplayName,
        operatorNotAssigned: audit.operatorNotAssigned,
        issueCodes: audit.issueCodes,
        issueSeverity: audit.issueSeverity,
        issueExplanation: audit.issueExplanation,
        events,
      };
    });
  }, [duties, tripById, terminalMap, lineByCode, intervalPolicy, blockFirstLastTrip, dutyAuditById]);

  // ─── Flat events for Viagens tab (all vehicle events sorted chronologically) ───
  const allEventsSorted = useMemo((): PlanEvent[] => {
    return vehicleGroups
      .flatMap((g) => g.events.map((e) => ({
        ...e,
        vehicleId: g.id,
        // Enriquece com motorista: só viagens reais têm tripId que mapeiam para um duty
        dutyId: e.tripId != null ? (tripToDutyId.get(e.tripId) ?? null) : null,
      })))
      .sort((a, b) => a.inicio - b.inicio);
  }, [vehicleGroups, tripToDutyId]);

  // ─── Export rows ───
  const vehiculosExportRows = useMemo(() =>
    vehicleGroups.flatMap((g) =>
      g.events.map((ev) => ({
        'ID Bloco': g.id,
        Veículo: g.label,
        'Saída (Bloco)': minToHHMM(g.startTime),
        'Retorno (Bloco)': minToHHMM(g.endTime),
        'Duração Total': minToDuration(g.endTime - g.startTime),
        'Num Viagens': g.tripCount,
        'Km Total Bloco': g.totalKm.toFixed(2),
        Evento: eventDisplayLabel(ev),
        Linha: ev.linha || '—',
        Sentido: ev.sentido || '—',
        'Início Evento': minToHHMM(ev.inicio),
        'Chegada Evento': minToHHMM(ev.chegada),
        'Duração (min)': ev.duracao || 0,
        Origem: ev.origemName || '—',
        Destino: ev.destinoName || '—',
        'KM Evento': ev.kind === 'descanso' ? '—' : (ev.km || 0).toFixed(2),
        Jornada: formatDutyReference(ev.dutyId),
      }))
    ), [vehicleGroups]);

  const motoristasExportRows = useMemo(
    () => buildDriverExportRows(duties, tripById, scheduleId),
    [duties, tripById, scheduleId],
  );

  const viagensDetalhadasExportRows = useMemo(
    () => buildDetailedTripExportRows(duties, tripById, scheduleId),
    [duties, tripById, scheduleId],
  );

  // ─── Drag-and-drop ───
  const handleDragStart = useCallback((e: React.DragEvent, item: any) => {
    e.dataTransfer.setData('trip_id', item.tripId.toString());
    e.dataTransfer.setData('origin_block_id', item.block_id?.toString() || '');
    e.dataTransfer.effectAllowed = 'move';
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDragEnter = useCallback((blockId: number) => {
    setHoverBlockId(blockId);
  }, []);

  const handleDragLeave = useCallback(() => {
    setHoverBlockId(null);
  }, []);

  const handleWhatIfDrop = useCallback(async (e: React.DragEvent, targetBlockId: number) => {
    e.preventDefault();
    const tripId = parseInt(e.dataTransfer.getData('trip_id'));
    const originBlockId = parseInt(e.dataTransfer.getData('origin_block_id'));
    if (isNaN(tripId) || originBlockId === targetBlockId) return;

    // Pre-move state = what we're evaluating the move against. We do NOT touch
    // backupBlocksRef here — that ref is the last *persisted* baseline and only
    // moves forward on Save. Otherwise the "Salvar Alterações" diff collapses
    // to zero and the drag never reaches the DB.
    const preMoveBlocks = localBlocksRef.current;

    const movingTrip = preMoveBlocks
      .find((b) => b.block_id === originBlockId)
      ?.items.find((t: any) => t.tripId === tripId);
    if (!movingTrip) return;

    const newLocalBlocks = preMoveBlocks.map((block) => {
      if (block.block_id === originBlockId)
        return { ...block, items: block.items.filter((t: any) => t.tripId !== tripId) };
      if (block.block_id === targetBlockId)
        return {
          ...block,
          items: [...block.items, { ...movingTrip, block_id: targetBlockId }]
            .sort((a, b) => a.start_time - b.start_time),
        };
      return block;
    });

    localBlocksRef.current = newLocalBlocks;
    setLocalBlocks(newLocalBlocks);
    setLoading(true);

    try {
      const payload = {
        blocks: preMoveBlocks.map((b) => ({
          block_id: b.block_id,
          trips: b.items.map((t: any) => ({
            id: t.tripId, start_time: t.start_time, end_time: t.end_time,
            line_id: t.lineId ?? 0, origin_id: t.origin_id ?? 0,
            destination_id: t.destination_id ?? 0, duration: t.duration ?? 0, distance_km: t.distance_km ?? 0,
          })),
        })),
        move: { trip_id: tripId, to_block_id: targetBlockId },
      };

      const result = await operationsApi.evaluateDelta(payload);

      if (result.isValid) {
        const delta = (result.totalCost ?? 0) - baselineCostRef.current;
        baselineCostRef.current = result.totalCost ?? 0;
        setNotification({
          msg: `Viagem ${tripId} movida para Veículo ${targetBlockId}. Δ custo: ${fmtSignedCurrency(delta)}. Clique em "Salvar" para persistir.`,
          sev: 'success',
        });
        if (onWhatIfUpdate) onWhatIfUpdate(result.totalCost);
      } else {
        setNotification({ msg: `Regra violada: ${result.violations?.join(', ')}`, sev: 'error' });
        localBlocksRef.current = preMoveBlocks;
        setLocalBlocks(preMoveBlocks);
      }
    } catch {
      setNotification({ msg: 'Erro ao avaliar movimento. Tente novamente.', sev: 'error' });
      localBlocksRef.current = preMoveBlocks;
      setLocalBlocks(preMoveBlocks);
    } finally {
      setLoading(false);
    }
  }, [onWhatIfUpdate]);

  // ─── Undo: revert all unsaved moves back to the last persisted baseline ───
  const handleUndo = useCallback(() => {
    const persisted = backupBlocksRef.current;
    const restored = cloneBlocks(persisted);
    localBlocksRef.current = restored;
    setLocalBlocks(restored);
    setNotification({ msg: 'Alterações descartadas.', sev: 'info' });
  }, [cloneBlocks]);

  // ─── Save ───
  const handleSave = async () => {
    const current = localBlocksRef.current;
    const backup = backupBlocksRef.current;

    const backupTripBlock = new Map<number, number>();
    backup.forEach((block) => (block.items || []).forEach((t: any) => backupTripBlock.set(t.tripId, block.block_id)));

    const moves: { tripId: number; targetBlockId: number }[] = [];
    current.forEach((block) => {
      (block.items || []).forEach((t: any) => {
        const oldBlock = backupTripBlock.get(t.tripId);
        if (oldBlock !== undefined && oldBlock !== block.block_id)
          moves.push({ tripId: t.tripId, targetBlockId: block.block_id });
      });
    });

    if (moves.length === 0) return;
    if (!res) {
      setNotification({ msg: 'Erro: Dados da otimização não carregados.', sev: 'error' });
      return;
    }
    setSaving(true);
    try {
      const scheduleId = (res as any).id || (res as any).scheduleId;
      for (const { tripId, targetBlockId } of moves)
        await operationsApi.reassignTrip({ scheduleId, tripId, targetBlockId });
      const persistedSnapshot = cloneBlocks(current);
      backupBlocksRef.current = persistedSnapshot;
      setBackupBlocks(persistedSnapshot);
      setNotification({ msg: `${moves.length} viagem(ns) salva(s)!`, sev: 'success' });
    } catch {
      setNotification({ msg: 'Erro ao salvar. Tente novamente.', sev: 'error' });
    } finally {
      setSaving(false);
    }
  };

  // Count of unsaved trip moves, diffed against the last persisted baseline.
  const unsavedMoves = useMemo(() => {
    const persistedTripBlock = new Map<number, number>();
    backupBlocks.forEach((b) =>
      (b.items || []).forEach((t: any) => persistedTripBlock.set(t.tripId, b.block_id))
    );
    let moves = 0;
    localBlocks.forEach((b) => {
      (b.items || []).forEach((t: any) => {
        const old = persistedTripBlock.get(t.tripId);
        if (old !== undefined && old !== b.block_id) moves += 1;
      });
    });
    return moves;
  }, [localBlocks, backupBlocks]);

  const hasChanges = unsavedMoves > 0;

  // ─── Gantt Row ───
  const GanttRow = useCallback(
    ({ index, style }: RowComponentProps) => {
      const block = filteredBlocks[index];
      if (!block) return <Box style={style as React.CSSProperties} />;
      const isDropTarget = hoverBlockId === block.block_id;
      return (
        <Box
          style={style}
          onDragOver={handleDragOver}
          onDragEnter={() => handleDragEnter(block.block_id)}
          onDragLeave={handleDragLeave}
          onDrop={(e) => {
            handleDragLeave();
            handleWhatIfDrop(e, block.block_id);
          }}
          sx={{
            borderBottom: `1px solid ${theme.palette.divider}`,
            display: 'flex',
            bgcolor: isDropTarget ? alpha(theme.palette.primary.main, 0.10) : 'transparent',
            outline: isDropTarget ? `2px dashed ${theme.palette.primary.main}` : 'none',
            outlineOffset: -2,
            transition: 'background-color 0.12s, outline-color 0.12s',
            '&:hover': { bgcolor: isDropTarget ? alpha(theme.palette.primary.main, 0.12) : alpha(theme.palette.primary.main, 0.02) },
          }}
        >
          <Box sx={{ width: 140, minWidth: 140, borderRight: `1px solid ${theme.palette.divider}`, p: 1.5, bgcolor: 'background.paper', zIndex: 2, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 800, color: 'primary.main' }}>Veículo {block.block_id}</Typography>
            <Typography variant="caption" color="text.secondary">
              {(block.items || []).filter((t: any) => t.lineCode || t.lineId).length} viagens
            </Typography>
          </Box>
          <Box sx={{ flexGrow: 1, position: 'relative', overflow: 'hidden', bgcolor: colors.trackBg }}>
            <Box sx={{ position: 'absolute', left: OVERNIGHT_START_MIN * scale * BASE_PIXELS_PER_MINUTE, top: 0, bottom: 0, right: 0, bgcolor: alpha(theme.palette.warning.main, 0.05), pointerEvents: 'none', zIndex: 0 }} />
            <Box sx={{ position: 'absolute', left: OVERNIGHT_START_MIN * scale * BASE_PIXELS_PER_MINUTE, top: 0, bottom: 0, width: 0, borderLeft: '2px dashed', borderColor: 'divider', opacity: 0.9, pointerEvents: 'none', zIndex: 5 }} />
            {(block.items || []).map((item: any, i: number) => (
              <GanttRowItem key={`${item.tripId}-${i}`} item={item} scale={scale} onDragStart={handleDragStart} colors={colors} />
            ))}
          </Box>
        </Box>
      );
    },
    [filteredBlocks, scale, theme, colors, handleDragStart, handleDragOver, handleDragEnter, handleDragLeave, handleWhatIfDrop, hoverBlockId]
  );

  // ─── Common toolbar controls ───
  const toolbarControls = (
    <Stack direction="row" spacing={2} sx={{ alignItems: 'center', p: 2, bgcolor: 'background.default', borderBottom: `1px solid ${theme.palette.divider}`, flexWrap: 'wrap', gap: 1 }}>
      <Typography variant="h6" sx={{ fontWeight: 700 }}>Planejador Interativo</Typography>
      <Divider orientation="vertical" flexItem />
      <OperationalConflictIndicator res={resWithLocalBlocks} />
      <Box sx={{ flexGrow: 1 }} />

      {activeTab === 0 && (
        <>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Linha</InputLabel>
            <Select value={filterLine} label="Linha" onChange={(e) => setFilterLine(e.target.value as string)}>
              <MenuItem value="">Todas</MenuItem>
              {presentLineCodes.map((code) => <MenuItem key={code} value={code}>{code}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField size="small" placeholder="Buscar bloco ou viagem…" value={filterSearch} onChange={(e) => setFilterSearch(e.target.value)} sx={{ width: 200 }} />
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>Zoom</Typography>
            <Button size="small" variant="outlined" onClick={() => setScale((s) => Math.max(MIN_SCALE, s - 0.5))}>−</Button>
            <Typography variant="caption" sx={{ minWidth: 40, textAlign: 'center' }}>{scale.toFixed(1)}x</Typography>
            <Button size="small" variant="outlined" onClick={() => setScale((s) => Math.min(MAX_SCALE, s + 0.5))}>+</Button>
          </Stack>
        </>
      )}

      {activeTab === 0 && (
        <Tooltip title="Centralizar a Gantt no horário atual">
          <Button size="small" variant="outlined" onClick={scrollToNow}
            startIcon={<IconClock size={16} />}>
            Agora
          </Button>
        </Tooltip>
      )}

      <Tooltip title={fullscreen ? 'Sair do modo tela cheia' : 'Tela cheia'}>
        <Button size="small" variant="outlined" onClick={() => setFullscreen((f) => !f)}
          startIcon={fullscreen ? <IconMinimize size={16} /> : <IconMaximize size={16} />}>
          {fullscreen ? 'Sair' : 'Tela Cheia'}
        </Button>
      </Tooltip>

      {hasChanges && (
        <Chip
          size="small"
          color="warning"
          variant="filled"
          label={`${unsavedMoves} não salv${unsavedMoves === 1 ? 'a' : 'as'}`}
          sx={{ fontWeight: 700 }}
        />
      )}
      <Button
        variant="outlined"
        color="inherit"
        size="small"
        disabled={saving || !hasChanges}
        onClick={handleUndo}
      >
        Descartar
      </Button>
      <Button variant="contained" color="primary" size="small" disabled={saving || !hasChanges} onClick={handleSave}>
        {saving ? 'Salvando…' : 'Salvar Alterações'}
      </Button>
    </Stack>
  );

  if (!res) {
    return (
      <Paper variant="outlined" sx={{ borderRadius: 2, p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          Nenhuma otimização disponível. Execute uma otimização para visualizar o Gantt.
        </Typography>
      </Paper>
    );
  }

  const ganttHeight = fullscreen ? (typeof window !== 'undefined' ? window.innerHeight - 200 : 600) : 520;

  return (
    <Paper variant="outlined" sx={{
      borderRadius: 2, overflow: 'hidden',
      ...(fullscreen && { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 1300, overflow: 'auto', bgcolor: 'background.paper', borderRadius: 0 }),
    }}>
      {toolbarControls}

      <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)} sx={{ px: 2, borderBottom: `1px solid ${theme.palette.divider}` }}>
        <Tab icon={<IconBus size={16} />} iconPosition="start" label={`Gantt (${effectiveBlocks.length})`} />
        <Tab icon={<IconTable size={16} />} iconPosition="start" label={`Veículos (${vehicleGroups.length})`} />
        <Tab icon={<IconUsers size={16} />} iconPosition="start" label={`Motoristas (${dutyGroups.length})`} />
        <Tab icon={<IconRoute size={16} />} iconPosition="start" label={`Viagens (${allEventsSorted.length})`} />
      </Tabs>

      {/* ─── Tab 0: Gantt ─── */}
      {activeTab === 0 && (
        <Box ref={ganttScrollRef} sx={{ width: '100%', overflowX: 'auto', bgcolor: 'background.paper' }}>
          <Box sx={{ width: totalWidth, minWidth: '100%' }}>
            <GanttTimeHeader scale={scale} theme={theme} />
            <Box sx={{ height: ganttHeight, width: '100%', position: 'relative' }}>
              {loading && (
                <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, bgcolor: 'rgba(255,255,255,0.7)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Typography variant="button" sx={{ fontWeight: 800, color: 'primary.main' }}>Recalculando…</Typography>
                </Box>
              )}
              {filteredBlocks.length === 0 ? (
                <Box sx={{ p: 4 }}><Alert severity="info">Nenhum bloco encontrado com os filtros selecionados.</Alert></Box>
              ) : (
                <List defaultHeight={ganttHeight} rowCount={filteredBlocks.length} rowHeight={ROW_HEIGHT} rowComponent={GanttRow} rowProps={{}} style={{ height: ganttHeight, width: totalWidth }} />
              )}
            </Box>
          </Box>
          {unassignedTrips.length > 0 && (
            <Box sx={{ p: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
              <Alert severity="warning" sx={{ mb: 1 }}>{unassignedTrips.length} viagem(ns) não atribuída(s)</Alert>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                {unassignedTrips.map((t: any, i: number) => {
                  const tid = typeof t === 'number' ? t : (t.id ?? t.trip_id);
                  const st = typeof t === 'object' ? minToHHMM(t.start_time) : '?';
                  const et = typeof t === 'object' ? minToHHMM(t.end_time) : '?';
                  return <Chip key={i} size="small" label={`Viagem ${tid}${st !== '?' ? ` (${st}–${et})` : ''}`} color="warning" variant="outlined" />;
                })}
              </Stack>
            </Box>
          )}
        </Box>
      )}

      {/* ─── Tab 1: Veículos (Collapsible Table) ─── */}
      {activeTab === 1 && (
        <Box>
          <Stack direction="row" sx={{ p: 2, justifyContent: 'space-between', alignItems: 'center', borderBottom: `1px solid ${theme.palette.divider}` }}>
            <Typography variant="caption" color="text.secondary">Clique em um veículo para expandir suas viagens</Typography>
            <ExportButtons rows={vehiculosExportRows} filename="veiculos" sheet="Veículos" />
          </Stack>
          <TableContainer sx={{ maxHeight: fullscreen ? 'calc(100vh - 160px)' : 600, overflowY: 'auto' }}>
            <Table stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 40 }} />
                  <TableCell sx={{ fontWeight: 700 }}>Veículo</TableCell>
                  <TableCell sx={{ fontWeight: 700 }} align="center">Viagens</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Saída</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Retorno</TableCell>
                  <TableCell sx={{ fontWeight: 700 }} align="right">Km Total</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {vehicleGroups.map((group) => (
                  <CollapsibleGroupRow key={group.id} group={group} showCost={false} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {/* ─── Tab 2: Motoristas (Collapsible Table) ─── */}
      {activeTab === 2 && (
        <Box>
          <Stack direction="row" sx={{ p: 2, justifyContent: 'space-between', alignItems: 'center', borderBottom: `1px solid ${theme.palette.divider}` }}>
            <Typography variant="caption" color="text.secondary">Clique em uma jornada para expandir sua representação operacional</Typography>
            <ExportButtons rows={motoristasExportRows} filename="motoristas" sheet="motoristas" />
          </Stack>
          {dutyGroups.length === 0 ? (
            <Box sx={{ p: 4 }}><Alert severity="info">Nenhuma escala de motorista gerada neste schedule.</Alert></Box>
          ) : (
            <TableContainer sx={{ maxHeight: fullscreen ? 'calc(100vh - 160px)' : 600, overflowY: 'auto' }}>
              <Table stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: 40 }} />
                    <TableCell sx={{ fontWeight: 700 }}>Jornada / Operador</TableCell>
                    <TableCell sx={{ fontWeight: 700 }} align="center">Viagens</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Início</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Fim</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Jornada</TableCell>
                    <TableCell sx={{ fontWeight: 700 }} align="right">Km Total</TableCell>
                    <TableCell sx={{ fontWeight: 700 }} align="right">Custo</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {dutyGroups.map((group) => (
                    <CollapsibleGroupRow key={group.id} group={group} showCost={true} />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      )}

      {/* ─── Tab 3: Viagens (Flat Table) ─── */}
      {activeTab === 3 && (
        <Box>
          <Stack direction="row" sx={{ p: 2, justifyContent: 'space-between', alignItems: 'center', borderBottom: `1px solid ${theme.palette.divider}` }}>
            <Typography variant="caption" color="text.secondary">
              Todos os eventos do plano em ordem cronológica ({allEventsSorted.length} entradas)
            </Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Tooltip title="Exportar Programação Operacional (CSV com segmentos do solver)">
                <Button size="small" variant="contained" color="primary"
                  startIcon={<IconClipboardData size={15} />}
                  onClick={() => {
                    const opRows = buildOperationalExportRows(duties, effectiveBlocks, scheduleId, tripById);
                    exportCsv(opRows, 'programacao_operacional.csv');
                  }}
                >Programação Operacional</Button>
              </Tooltip>
              <ExportButtons rows={viagensDetalhadasExportRows} filename="viagens_detalhadas" sheet="viagens_detalhadas" />
            </Stack>
          </Stack>
          <TableContainer sx={{ maxHeight: fullscreen ? 'calc(100vh - 160px)' : 600, overflowY: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {EVENT_COLS.map((col) => (
                    <TableCell key={col} sx={{ fontWeight: 700 }}>{col}</TableCell>
                  ))}
                  <TableCell sx={{ fontWeight: 700 }}>Veículo</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Jornada</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {allEventsSorted.map((ev, idx) => (
                  <TableRow key={idx} sx={{
                    bgcolor: ev.kind === 'descanso'
                      ? alpha(ev.intervalKind === 'espera' ? theme.palette.text.secondary : theme.palette.warning.main, 0.05)
                      : ev.kind === 'soltura'
                      ? alpha(theme.palette.success.main, 0.04)
                      : ev.kind === 'recolhimento'
                      ? alpha(theme.palette.error.main, 0.04)
                      : 'inherit',
                  }}>
                    <TableCell sx={{ py: 0.75 }}><EventKindChip kind={ev.kind} gap={ev.gapMinutes} intervalKind={ev.intervalKind} /></TableCell>
                    <TableCell>
                      {ev.kind !== 'descanso' && ev.color ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: ev.color, flexShrink: 0 }} />
                          <Typography variant="caption" sx={{ fontWeight: 600 }}>{ev.linha}</Typography>
                        </Box>
                      ) : <Typography variant="caption" color="text.secondary">{ev.kind === 'descanso' ? '—' : ev.linha}</Typography>}
                    </TableCell>
                    <TableCell><Typography variant="caption">{ev.kind === 'descanso' ? '—' : ev.sentido}</Typography></TableCell>
                    <TableCell><Typography variant="caption" sx={{ fontWeight: 600 }}>{minToHHMM(ev.inicio)}</Typography></TableCell>
                    <TableCell><Typography variant="caption" sx={{ fontWeight: 600 }}>{minToHHMM(ev.chegada)}</Typography></TableCell>
                    <TableCell><Typography variant="caption">{ev.origemName}</Typography></TableCell>
                    <TableCell><Typography variant="caption">{ev.destinoName}</Typography></TableCell>
                    <TableCell align="right">
                      <Typography variant="caption">{ev.kind === 'descanso' ? minToDuration(ev.duracao) : ev.km}</Typography>
                    </TableCell>
                    <TableCell><Typography variant="caption">{ev.vehicleId != null ? `V${ev.vehicleId}` : '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption">{formatDutyReference(ev.dutyId)}</Typography></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      <Snackbar open={Boolean(notification)} autoHideDuration={4000} onClose={() => setNotification(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {notification ? (
          <Alert severity={notification.sev} variant="filled" sx={{ fontWeight: 700 }}>{notification.msg}</Alert>
        ) : undefined}
      </Snackbar>
    </Paper>
  );
}
