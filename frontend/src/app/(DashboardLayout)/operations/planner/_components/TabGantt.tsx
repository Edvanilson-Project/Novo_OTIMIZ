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
  IconFileSpreadsheet, IconTable, IconRoute,
  IconChevronDown, IconChevronUp,
  IconFlag, IconMapPin, IconCoffee,
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
const DESCANSO_MIN_GAP = 5; // min gap to show as descanso event

// ─── Domain Interfaces ────────────────────────────────────────────────────────
export type EventKind = 'soltura' | 'viagem' | 'recolhimento' | 'descanso';

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
  vehicleId?: number;
  dutyId?: number | null;
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
  events: PlanEvent[];
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

// ─── Event Kind Config ────────────────────────────────────────────────────────
const EVENT_CONFIG: Record<EventKind, { label: string; color: 'success' | 'primary' | 'error' | 'warning'; icon: React.ReactNode }> = {
  soltura:       { label: 'Soltura',         color: 'success', icon: <IconMapPin size={14} /> },
  viagem:        { label: 'Viagem',          color: 'primary', icon: <IconBus size={14} /> },
  recolhimento:  { label: 'Recolhimento',    color: 'error',   icon: <IconFlag size={14} /> },
  descanso:      { label: 'Descanso/Refeição', color: 'warning', icon: <IconCoffee size={14} /> },
};

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
  if (includeSoltura && firstLine?.garageTerminalId && firstLine.solturaMinutes) {
    const solturaEnd = firstTrip.start_time ?? 0;
    const solturaStart = solturaEnd - firstLine.solturaMinutes;
    events.push({
      kind: 'soltura',
      linha: '—',
      sentido: '—',
      inicio: solturaStart,
      chegada: solturaEnd,
      origemName: tName(firstLine.garageTerminalId),
      destinoName: tName(firstTrip.origin_id),
      km: firstLine.garageDistanceKm ?? 0,
      duracao: firstLine.solturaMinutes,
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
        const isRefeicao = gap >= mealThreshold;
        const isDescanso = gap >= breakThreshold;
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
          vehicleId,
          dutyId: dutyIdOverride,
          color: isRefeicao ? '#ff9800' : isDescanso ? '#ffc107' : '#90a4ae',
        });
      }
    }
  });

  // ── Recolhimento: último terminal → garagem ───────────────────────────────
  if (includeRecolhimento && lastLine?.garageTerminalId && lastLine.recolhimentoMinutes) {
    const recolhimentoStart = lastTrip.end_time ?? 0;
    const recolhimentoEnd = recolhimentoStart + lastLine.recolhimentoMinutes;
    events.push({
      kind: 'recolhimento',
      linha: '—',
      sentido: '—',
      inicio: recolhimentoStart,
      chegada: recolhimentoEnd,
      origemName: tName(lastTrip.destination_id),
      destinoName: tName(lastLine.garageTerminalId),
      km: lastLine.recolhimentoDistanceKm ?? 0,
      duracao: lastLine.recolhimentoMinutes,
      vehicleId,
      dutyId: dutyIdOverride,
    });
  }

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

// ─── EventKindChip ────────────────────────────────────────────────────────────
function EventKindChip({ kind, gap }: { kind: EventKind; gap?: number }) {
  const cfg = EVENT_CONFIG[kind];
  if (kind === 'descanso' && gap != null) {
    const isRefeicao = gap >= 60;
    return (
      <Chip
        size="small"
        icon={<IconCoffee size={12} />}
        label={isRefeicao ? `Refeição (${minToDuration(gap)})` : `Descanso (${minToDuration(gap)})`}
        color={isRefeicao ? 'success' : 'warning'}
        variant="outlined"
        sx={{ fontWeight: 700 }}
      />
    );
  }
  return (
    <Chip
      size="small"
      icon={<>{cfg.icon}</>}
      label={cfg.label}
      color={cfg.color}
      variant="outlined"
      sx={{ fontWeight: 700 }}
    />
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
        <TableCell sx={{ fontWeight: 800, color: 'primary.main' }}>{group.label}</TableCell>
        <TableCell align="center">{group.tripCount} viagens</TableCell>
        <TableCell>{minToHHMM(group.startTime)}</TableCell>
        <TableCell>{minToHHMM(group.endTime)}</TableCell>
        {group.workTime !== undefined && (
          <TableCell>{minToDuration(group.workTime)}</TableCell>
        )}
        <TableCell align="right">{group.totalKm.toFixed(1)} km</TableCell>
        {showCost && <TableCell align="right">{fmtCurrency(group.totalCost ?? 0)}</TableCell>}
        {(group.violations ?? 0) > 0
          ? <TableCell><Chip size="small" label={`${group.violations} violação(ões)`} color="error" /></TableCell>
          : <TableCell />
        }
      </TableRow>

      <TableRow>
        <TableCell colSpan={cols + 2} sx={{ p: 0, border: 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box sx={{ bgcolor: alpha(theme.palette.background.default, 0.6), px: 3, py: 1 }}>
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

  return (
    <TableRow sx={{
      bgcolor: isDescanso
        ? alpha(theme.palette.warning.main, 0.06)
        : event.kind === 'soltura'
        ? alpha(theme.palette.success.main, 0.05)
        : event.kind === 'recolhimento'
        ? alpha(theme.palette.error.main, 0.05)
        : 'inherit',
    }}>
      <TableCell sx={{ py: 0.5, minWidth: 160 }}>
        <EventKindChip kind={event.kind} gap={event.gapMinutes} />
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

  const [filterLine, setFilterLine] = useState<string>('');
  const [filterSearch, setFilterSearch] = useState('');
  const [hoverBlockId, setHoverBlockId] = useState<number | null>(null);

  const tripMetadataRef = useRef<Map<number, TripMetadata>>(new Map());
  const localBlocksRef = useRef<any[]>([]);
  const backupBlocksRef = useRef<any[]>([]);
  const baselineCostRef = useRef<number>(0);

  const lineMap = useMemo(() => new Map(lines.map((l) => [l.id, l])), [lines]);
  // índice por lineId (código alfanumérico) para lookup rápido no buildEvents
  const lineByCode = useMemo(() => new Map(lines.map((l) => [l.lineId ?? '', l])), [lines]);
  const terminalMap = useMemo(() => new Map(terminals.map((t) => [t.id, t])), [terminals]);
  const ppm = scale * BASE_PIXELS_PER_MINUTE;
  const totalWidth = HORIZON_MINUTES * ppm + SIDEBAR_WIDTH;

  const presentLineCodes = useMemo(() => {
    const codes = new Set<string>();
    (localBlocks || []).forEach((b) =>
      (b.items || []).forEach((t: any) => { const c = t.lineCode || t.line_code; if (c) codes.add(c); })
    );
    return [...codes].sort();
  }, [localBlocks]);

  // ─── Hydration ───
  useEffect(() => {
    if (!res || !res.blocks) return;

    const codeColorMap = new Map<string, string>();
    let colorIdx = 0;
    res.blocks.forEach((block) => {
      (block as any).trips?.forEach((trip: any) => {
        const code = trip.line_code ?? trip.lineCode ?? null;
        if (code && !codeColorMap.has(code)) { codeColorMap.set(code, linePalette[colorIdx % linePalette.length]); colorIdx++; }
      });
    });

    const hydrated = (res.blocks || []).map((block) => {
      const b = block as any;
      const blockId = b.block_id ?? b.blockId ?? b.id;
      const items = (b.trips || []).map((trip: any) => {
        const tripId = trip.id ?? trip.trip_id ?? getTripPublicId(trip);
        const code = trip.line_code ?? trip.lineCode ?? null;
        const color = code ? (codeColorMap.get(code) ?? linePalette[0]) : linePalette[0];
        return {
          ...trip, tripId,
          lineId: trip.line_id ?? null, lineCode: code,
          start_time: trip.start_time ?? 0, end_time: trip.end_time ?? 0,
          color, kind: 'trip', block_id: blockId,
        };
      }).sort((a: any, z: any) => a.start_time - z.start_time);

      return { ...block, id: blockId, block_id: blockId, start_time: b.start_time ?? 0, end_time: b.end_time ?? 0, items };
    }).sort((a: any, b: any) => (a.block_id || 0) - (b.block_id || 0));

    const metadata = new Map<number, TripMetadata>();
    hydrated.forEach((block) => {
      (block.items || []).forEach((item: any) => {
        metadata.set(item.tripId, { lineId: item.lineId ?? null, lineCode: item.lineCode ?? null, color: item.color });
      });
    });
    tripMetadataRef.current = metadata;

    baselineCostRef.current = res ? ((res as any).totalCost ?? (res as any).total_cost ?? 0) : 0;
    setLocalBlocks(hydrated);
    setBackupBlocks(JSON.parse(JSON.stringify(hydrated)));
    localBlocksRef.current = hydrated;
    backupBlocksRef.current = JSON.parse(JSON.stringify(hydrated));
  }, [res, lineMap, linePalette]);

  const resWithLocalBlocks = useMemo(() => ({ ...res, blocks: localBlocks }), [res, localBlocks]);

  const filteredBlocks = useMemo(() => {
    return localBlocks.filter((block) => {
      if (filterLine && !block.items?.some((t: any) => (t.lineCode ?? t.line_code) === filterLine)) return false;
      if (filterSearch) {
        const q = filterSearch.toLowerCase();
        return String(block.block_id).includes(q) || block.items?.some((t: any) =>
          String(t.tripId ?? '').includes(q) || String(t.lineCode ?? '').toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [localBlocks, filterLine, filterSearch]);

  const unassignedTrips: any[] = useMemo(() => {
    if (!res) return [];
    const raw = (res as any).metadata?.unassigned_trips || (res as any).unassigned_trips || [];
    return Array.isArray(raw) ? raw : [];
  }, [res]);

  const duties = useMemo(() => {
    if (!res) return [];
    return (res as any).resultSummary?.duties || (res as any).duties || [];
  }, [res]);

  // ─── PlanGroups for Veículos tab ───
  const vehicleGroups = useMemo((): PlanGroup[] => {
    return localBlocks.map((block) => {
      const trips = (block.items || []).filter((t: any) => t.lineCode || t.lineId);
      const events = buildEvents(trips, terminalMap, lineByCode, intervalPolicy, block.block_id, undefined);

      // startTime inclui soltura (antes da 1ª viagem), endTime inclui recolhimento (após última)
      const solturaEvt = events.find(e => e.kind === 'soltura');
      const recolhEvt = events.slice().reverse().find(e => e.kind === 'recolhimento');
      return {
        id: block.block_id,
        label: `Veículo ${block.block_id}`,
        tripCount: trips.length,
        totalKm: events.reduce((s, e) => s + (e.km ?? 0), 0),
        startTime: solturaEvt?.inicio ?? trips[0]?.start_time ?? 0,
        endTime: recolhEvt?.chegada ?? trips[trips.length - 1]?.end_time ?? 0,
        events,
      };
    });
  }, [localBlocks, terminalMap, lineByCode, intervalPolicy]);

  // ─── PlanGroups for Motoristas tab ───
  const tripById = useMemo(() => {
    const map = new Map<number, any>();
    localBlocks.forEach((b) => (b.items || []).forEach((t: any) => map.set(t.tripId, t)));
    return map;
  }, [localBlocks]);

  // Quais são a 1ª e última viagem de cada bloco (para decidir soltura/recolhimento do motorista)
  const blockFirstLastTrip = useMemo(() => {
    const map = new Map<number, { firstTripId: number; lastTripId: number }>();
    localBlocks.forEach((b) => {
      const sorted = (b.items || [])
        .filter((t: any) => t.lineCode || t.lineId)
        .sort((a: any, z: any) => (a.start_time ?? 0) - (z.start_time ?? 0));
      if (sorted.length > 0)
        map.set(b.block_id, { firstTripId: sorted[0].tripId, lastTripId: sorted[sorted.length - 1].tripId });
    });
    return map;
  }, [localBlocks]);

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
      const dutyTrips = tripIds
        .map((id) => tripById.get(id))
        .filter(Boolean)
        .sort((a: any, b: any) => (a.start_time ?? 0) - (b.start_time ?? 0));

      // Soltura só se o motorista conduz a 1ª viagem do bloco de veículo
      // Recolhimento só se o motorista conduz a última viagem do bloco de veículo
      const firstDutyTripId = dutyTrips[0]?.tripId;
      const lastDutyTripId = dutyTrips[dutyTrips.length - 1]?.tripId;
      let includeSoltura = false;
      let includeRecolhimento = false;
      for (const { firstTripId, lastTripId } of blockFirstLastTrip.values()) {
        if (firstDutyTripId === firstTripId) includeSoltura = true;
        if (lastDutyTripId === lastTripId) includeRecolhimento = true;
      }

      const events = buildEvents(dutyTrips, terminalMap, lineByCode, intervalPolicy, undefined, dutyId, includeSoltura, includeRecolhimento);
      const violations = (duty.shift_violations ?? 0) + (duty.rest_violations ?? 0);

      // Jornada inclui soltura e recolhimento se configurados
      const solturaEvt = events.find(e => e.kind === 'soltura');
      const recolhEvt = events.slice().reverse().find(e => e.kind === 'recolhimento');
      const jornStart = solturaEvt?.inicio ?? duty.start_time ?? dutyTrips[0]?.start_time ?? 0;
      const jornEnd = recolhEvt?.chegada ?? duty.end_time ?? dutyTrips[dutyTrips.length - 1]?.end_time ?? 0;

      return {
        id: dutyId,
        label: `Motorista ${dutyId}`,
        tripCount: dutyTrips.length,
        totalKm: events.reduce((s, e) => s + (e.km ?? 0), 0),
        startTime: jornStart,
        endTime: jornEnd,
        workTime: jornEnd - jornStart, // jornada completa incluindo morto e deadhead
        totalCost: duty.total_cost ?? 0,
        violations,
        events,
      };
    });
  }, [duties, tripById, terminalMap, lineByCode, intervalPolicy]);

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
        Evento: EVENT_CONFIG[ev.kind].label,
        Linha: ev.linha || '—',
        Sentido: ev.sentido || '—',
        'Início Evento': minToHHMM(ev.inicio),
        'Chegada Evento': minToHHMM(ev.chegada),
        'Duração (min)': ev.duracao || 0,
        Origem: ev.origemName || '—',
        Destino: ev.destinoName || '—',
        'KM Evento': ev.kind === 'descanso' ? '—' : (ev.km || 0).toFixed(2),
        'Motorista': ev.dutyId != null ? `M${ev.dutyId}` : '—',
      }))
    ), [vehicleGroups]);

  const motoristasExportRows = useMemo(() =>
    dutyGroups.flatMap((g) =>
      g.events.map((ev) => ({
        'ID Jornada': g.id,
        Motorista: g.label,
        'Início Jornada': minToHHMM(g.startTime),
        'Fim Jornada': minToHHMM(g.endTime),
        'Duração Total (min)': g.workTime || 0,
        'Duração Formatada': minToDuration(g.workTime ?? 0),
        'Num Viagens': g.tripCount,
        'Km Total': g.totalKm.toFixed(2),
        'Custo': g.totalCost ? Number(g.totalCost) : 0,
        'Custo Formatado': fmtCurrency(g.totalCost ?? 0),
        'Violações': g.violations ?? 0,
        Evento: EVENT_CONFIG[ev.kind].label,
        Linha: ev.linha || '—',
        Sentido: ev.sentido || '—',
        'Início Evento': minToHHMM(ev.inicio),
        'Chegada Evento': minToHHMM(ev.chegada),
        'Duração Evento (min)': ev.duracao || 0,
        Origem: ev.origemName || '—',
        Destino: ev.destinoName || '—',
        'Veículo': ev.vehicleId != null ? `V${ev.vehicleId}` : '—',
      }))
    ), [dutyGroups]);

  const viagensExportRows = useMemo(() =>
    allEventsSorted.map((ev) => ({
      'ID Viagem': ev.tripId || '—',
      Evento: EVENT_CONFIG[ev.kind].label,
      Linha: ev.linha || '—',
      Sentido: ev.sentido || '—',
      'Início': minToHHMM(ev.inicio),
      'Início (min)': ev.inicio,
      'Chegada': minToHHMM(ev.chegada),
      'Chegada (min)': ev.chegada,
      'Duração (min)': ev.duracao || 0,
      Origem: ev.origemName || '—',
      Destino: ev.destinoName || '—',
      'KM': ev.kind === 'descanso' ? '—' : (ev.km || 0).toFixed(2),
      Veículo: ev.vehicleId != null ? `V${ev.vehicleId}` : '—',
      Motorista: ev.dutyId != null ? `M${ev.dutyId}` : '—',
    })), [allEventsSorted]);

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
    const restored = JSON.parse(JSON.stringify(persisted));
    localBlocksRef.current = restored;
    setLocalBlocks(restored);
    setNotification({ msg: 'Alterações descartadas.', sev: 'info' });
  }, []);

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
      backupBlocksRef.current = JSON.parse(JSON.stringify(current));
      setBackupBlocks(JSON.parse(JSON.stringify(current)));
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
        <Tab icon={<IconBus size={16} />} iconPosition="start" label={`Gantt (${localBlocks.length})`} />
        <Tab icon={<IconTable size={16} />} iconPosition="start" label={`Veículos (${vehicleGroups.length})`} />
        <Tab icon={<IconUsers size={16} />} iconPosition="start" label={`Motoristas (${dutyGroups.length})`} />
        <Tab icon={<IconRoute size={16} />} iconPosition="start" label={`Viagens (${allEventsSorted.length})`} />
      </Tabs>

      {/* ─── Tab 0: Gantt ─── */}
      {activeTab === 0 && (
        <Box sx={{ width: '100%', overflowX: 'auto', bgcolor: 'background.paper' }}>
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
            <Typography variant="caption" color="text.secondary">Clique em um motorista para expandir sua jornada</Typography>
            <ExportButtons rows={motoristasExportRows} filename="motoristas" sheet="Motoristas" />
          </Stack>
          {dutyGroups.length === 0 ? (
            <Box sx={{ p: 4 }}><Alert severity="info">Nenhuma escala de motorista gerada neste schedule.</Alert></Box>
          ) : (
            <TableContainer sx={{ maxHeight: fullscreen ? 'calc(100vh - 160px)' : 600, overflowY: 'auto' }}>
              <Table stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: 40 }} />
                    <TableCell sx={{ fontWeight: 700 }}>Motorista</TableCell>
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
            <ExportButtons rows={viagensExportRows} filename="viagens" sheet="Viagens" />
          </Stack>
          <TableContainer sx={{ maxHeight: fullscreen ? 'calc(100vh - 160px)' : 600, overflowY: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {EVENT_COLS.map((col) => (
                    <TableCell key={col} sx={{ fontWeight: 700 }}>{col}</TableCell>
                  ))}
                  <TableCell sx={{ fontWeight: 700 }}>Veículo</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Motorista</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {allEventsSorted.map((ev, idx) => (
                  <TableRow key={idx} sx={{
                    bgcolor: ev.kind === 'descanso'
                      ? alpha(theme.palette.warning.main, 0.05)
                      : ev.kind === 'soltura'
                      ? alpha(theme.palette.success.main, 0.04)
                      : ev.kind === 'recolhimento'
                      ? alpha(theme.palette.error.main, 0.04)
                      : 'inherit',
                  }}>
                    <TableCell sx={{ py: 0.75 }}><EventKindChip kind={ev.kind} gap={ev.gapMinutes} /></TableCell>
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
                    <TableCell><Typography variant="caption">{ev.dutyId != null ? `M${ev.dutyId}` : '—'}</Typography></TableCell>
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
