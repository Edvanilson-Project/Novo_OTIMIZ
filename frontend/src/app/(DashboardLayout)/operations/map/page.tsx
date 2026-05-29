'use client';

import React, { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Snackbar,
  Stack,
  Switch,
  Typography,
} from '@mui/material';
import { IconMapPin, IconX } from '@tabler/icons-react';
import { terminalsApi, operationsApi } from '@/lib/api';
import type { MapTerminal, MapTripLine } from '../../../components/shared/OperationsMap';

// react-leaflet acessa `window` no carregamento → precisa client-only.
const OperationsMap = dynamic(() => import('../../../components/shared/OperationsMap'), {
  ssr: false,
  loading: () => <Box sx={{ height: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>Carregando mapa…</Box>,
});

interface ScheduleSummary {
  id: number;
  referenceDate?: string;
  status?: string;
}

interface ScheduleBlock {
  id: number;
  block_id: number;
  start_time: number;
  end_time: number;
  total_cost: number;
  trips: Array<{ id: number; start_time: number; end_time: number }>;
}

export default function OperationsMapPage() {
  const [terminals, setTerminals] = useState<MapTerminal[]>([]);
  const [schedules, setSchedules] = useState<ScheduleSummary[]>([]);
  const [selectedScheduleId, setSelectedScheduleId] = useState<string>('');
  const [trips, setTrips] = useState<MapTripLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [tripsLoading, setTripsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scheduleBlocks, setScheduleBlocks] = useState<ScheduleBlock[]>([]);
  const [selectedTerminal, setSelectedTerminal] = useState<MapTerminal | null>(null);
  const [selectedTrip, setSelectedTrip] = useState<MapTripLine | null>(null);
  const [reassigning, setReassigning] = useState(false);
  const [snack, setSnack] = useState<{ open: boolean; message: string; severity: 'success' | 'error' }>({ open: false, message: '', severity: 'success' });
  const [colorByLine, setColorByLine] = useState(true);
  const [lineFilter, setLineFilter] = useState<Set<string>>(new Set());
  const [timeRange, setTimeRange] = useState<[number, number]>([0, 1440]);

  const lineStats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const t of trips) {
      if (t.lineCode) counts.set(t.lineCode, (counts.get(t.lineCode) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([code, count], i, arr) => ({
        code,
        count,
        color: `hsl(${Math.round((i / Math.max(1, arr.length)) * 360)}, 70%, 45%)`,
      }));
  }, [trips]);

  // Reset filtros quando troca schedule
  useEffect(() => {
    setLineFilter(new Set());
    setTimeRange([0, 1440]);
  }, [selectedScheduleId]);

  const timeFilterActive = timeRange[0] > 0 || timeRange[1] < 1440;

  const filteredTrips = useMemo(() => {
    let result = trips;
    if (lineFilter.size > 0) result = result.filter((t) => t.lineCode && lineFilter.has(t.lineCode));
    if (timeRange[0] > 0 || timeRange[1] < 1440) {
      result = result.filter(
        (t) => t.startTime == null || (t.startTime >= timeRange[0] && t.startTime <= timeRange[1]),
      );
    }
    return result;
  }, [trips, lineFilter, timeRange]);

  const lineColors = useMemo(() => {
    if (!colorByLine) return undefined;
    const map: Record<string, string> = {};
    for (const { code, color } of lineStats) map[code] = color;
    return map;
  }, [colorByLine, lineStats]);

  async function handleReassign(tripId: number, targetBlockId: number) {
    if (!selectedScheduleId) return;
    setReassigning(true);
    try {
      await operationsApi.reassignTrip({ scheduleId: Number(selectedScheduleId), tripId, targetBlockId });
      setSnack({ open: true, message: `Viagem #${tripId} reatribuída ao bloco ${targetBlockId}.`, severity: 'success' });
      setSelectedTrip(null);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      setSnack({ open: true, message: err?.response?.data?.message ?? 'Erro ao reatribuir viagem.', severity: 'error' });
    } finally {
      setReassigning(false);
    }
  }

  function toggleLineFilter(code: string) {
    setLineFilter((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [terms, latest] = await Promise.all([
          terminalsApi.getAll(),
          operationsApi.getLatestSchedule().catch(() => null),
        ]);
        setTerminals(Array.isArray(terms) ? terms : []);
        if (latest?.id) {
          setSchedules([latest]);
          setSelectedScheduleId(String(latest.id));
          setScheduleBlocks(Array.isArray(latest.blocks) ? latest.blocks : []);
        }
      } catch (e: unknown) {
        const err = e as { response?: { data?: { message?: string } }; message?: string };
        setError(err?.response?.data?.message ?? err?.message ?? 'Falha ao carregar dados do mapa.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedScheduleId) {
      setTrips([]);
      return;
    }
    (async () => {
      setTripsLoading(true);
      try {
        const result = await operationsApi.getTrips({ scheduleId: Number(selectedScheduleId) });
        const rawItems: unknown[] = Array.isArray(result) ? result : (result as { items?: unknown[] })?.items ?? [];
        setTrips(
          rawItems.map((item) => {
            const t = item as {
              id?: number; originLatitude?: number | null; originLongitude?: number | null;
              destinationLatitude?: number | null; destinationLongitude?: number | null;
              lineCode?: string | null; originId?: number | null; destinationId?: number | null;
              startTime?: number | null; endTime?: number | null; duration?: number | null; distanceKm?: number | null;
            };
            return ({
            id: t.id ?? 0,
            originLatitude: t.originLatitude ?? null,
            originLongitude: t.originLongitude ?? null,
            destinationLatitude: t.destinationLatitude ?? null,
            destinationLongitude: t.destinationLongitude ?? null,
            lineCode: t.lineCode ?? null,
            originId: t.originId ?? null,
            destinationId: t.destinationId ?? null,
            startTime: t.startTime ?? null,
            endTime: t.endTime ?? null,
            duration: t.duration ?? null,
            distanceKm: t.distanceKm ?? null,
          });
          }),
        );
      } catch (e: unknown) {
        const err = e as { response?: { data?: { message?: string } }; message?: string };
        setError(err?.response?.data?.message ?? err?.message ?? 'Falha ao carregar viagens.');
      } finally {
        setTripsLoading(false);
      }
    })();
  }, [selectedScheduleId]);

  const terminalsWithCoords = terminals.filter(
    (t) => typeof t.latitude === 'number' && typeof t.longitude === 'number',
  ).length;
  const tripsWithCoords = filteredTrips.filter(
    (t) =>
      typeof t.originLatitude === 'number' &&
      typeof t.originLongitude === 'number' &&
      typeof t.destinationLatitude === 'number' &&
      typeof t.destinationLongitude === 'number',
  ).length;

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            Mapa Operacional
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Visualize terminais e viagens da operação no mapa.
          </Typography>
        </Box>
        <FormControl size="small" sx={{ minWidth: 240 }}>
          <InputLabel id="schedule-select-label">Schedule (viagens)</InputLabel>
          <Select
            labelId="schedule-select-label"
            label="Schedule (viagens)"
            value={selectedScheduleId}
            onChange={(e) => setSelectedScheduleId(String(e.target.value ?? ''))}
            disabled={loading}
          >
            <MenuItem value="">Nenhum (só terminais)</MenuItem>
            {schedules.map((s) => (
              <MenuItem key={s.id} value={String(s.id)}>
                #{s.id} {s.referenceDate ?? ''} {s.status ? `(${s.status})` : ''}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack sx={{ flexDirection: 'row', gap: 3, alignItems: 'center', flexWrap: 'wrap' }}>
            <Stack sx={{ flexDirection: 'row', alignItems: 'center', gap: 1 }}>
              <IconMapPin size={18} color="#e53935" />
              <Typography variant="body2">
                <strong>{terminalsWithCoords}</strong> de {terminals.length} terminais com coordenadas
              </Typography>
            </Stack>
            {!!selectedScheduleId && (
              <Typography variant="body2">
                <strong>{tripsWithCoords}</strong> de {filteredTrips.length} viagens
                {(lineFilter.size > 0 || timeFilterActive) ? ` (filtrado de ${trips.length})` : ''}
                {' '}com coordenadas
                {tripsLoading ? ' (carregando…)' : ''}
              </Typography>
            )}
            {!!selectedScheduleId && lineStats.length > 0 && (
              <FormControlLabel
                sx={{ ml: 'auto' }}
                control={
                  <Switch
                    size="small"
                    checked={colorByLine}
                    onChange={(e) => setColorByLine(e.target.checked)}
                  />
                }
                label={<Typography variant="body2">Colorir por linha</Typography>}
              />
            )}
          </Stack>
          {lineStats.length > 0 && (
            <Box sx={{ mt: 1.5, display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
              {lineStats.map(({ code, count, color }) => {
                const active = lineFilter.has(code);
                const dimmed = lineFilter.size > 0 && !active;
                return (
                  <Stack
                    key={code}
                    onClick={() => toggleLineFilter(code)}
                    sx={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 0.75,
                      px: 1,
                      py: 0.25,
                      borderRadius: 1,
                      cursor: 'pointer',
                      bgcolor: active ? 'primary.main' : 'action.hover',
                      color: active ? 'primary.contrastText' : 'inherit',
                      opacity: dimmed ? 0.45 : 1,
                      transition: 'all 0.15s',
                      border: '1px solid',
                      borderColor: active ? 'primary.dark' : 'transparent',
                      fontSize: '0.75rem',
                      '&:hover': { opacity: 1, borderColor: active ? 'primary.dark' : 'divider' },
                    }}
                  >
                    {colorByLine && (
                      <Box sx={{ width: 12, height: 4, bgcolor: color, borderRadius: 0.5 }} />
                    )}
                    <Typography variant="caption" sx={{ color: 'inherit' }}>
                      {code} · {count}
                    </Typography>
                  </Stack>
                );
              })}
              {lineFilter.size > 0 && (
                <Typography
                  variant="caption"
                  onClick={() => setLineFilter(new Set())}
                  sx={{ cursor: 'pointer', textDecoration: 'underline', ml: 1 }}
                >
                  limpar filtro
                </Typography>
              )}
            </Box>
          )}
          {!!selectedScheduleId && (
            <Box sx={{ mt: 1.5, px: 0.5 }}>
              <Stack sx={{ flexDirection: 'row', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <Typography variant="caption" color="textSecondary">
                  Faixa horária: <strong>{minsToHHMM(timeRange[0])}</strong> – <strong>{minsToHHMM(timeRange[1])}</strong>
                </Typography>
                {timeFilterActive && (
                  <Typography
                    variant="caption"
                    onClick={() => setTimeRange([0, 1440])}
                    sx={{ cursor: 'pointer', textDecoration: 'underline', ml: 1 }}
                  >
                    resetar
                  </Typography>
                )}
              </Stack>
              <Slider
                value={timeRange}
                onChange={(_, v) => setTimeRange(v as [number, number])}
                min={0}
                max={1440}
                step={15}
                size="small"
                marks={[
                  { value: 0, label: '00:00' },
                  { value: 360, label: '06:00' },
                  { value: 720, label: '12:00' },
                  { value: 1080, label: '18:00' },
                  { value: 1440, label: '24:00' },
                ]}
                sx={{ color: timeFilterActive ? 'primary.main' : 'action.active' }}
              />
            </Box>
          )}
        </CardContent>
      </Card>

      {terminals.length === 0 && !loading ? (
        <Alert severity="info">
          Nenhum terminal cadastrado. Cadastre terminais em <strong>Operações → Terminais</strong> para vê-los no mapa.
        </Alert>
      ) : terminalsWithCoords === 0 && tripsWithCoords === 0 ? (
        <Alert severity="warning">
          Nenhum terminal ou viagem tem coordenadas (latitude/longitude) preenchidas. Preencha esses campos para ver os dados no mapa.
        </Alert>
      ) : (
        <Box sx={{ borderRadius: 1, overflow: 'hidden' }}>
          <OperationsMap
            terminals={terminals}
            trips={filteredTrips}
            height={650}
            selectedTerminalId={selectedTerminal?.id ?? null}
            selectedTripId={selectedTrip?.id ?? null}
            onSelectTerminal={(t) => {
              setSelectedTrip(null);
              setSelectedTerminal(t);
            }}
            onSelectTrip={(t) => {
              setSelectedTerminal(null);
              setSelectedTrip(t);
            }}
            lineColors={lineColors}
          />
        </Box>
      )}

      <Drawer
        anchor="right"
        open={selectedTerminal !== null || selectedTrip !== null}
        onClose={() => {
          setSelectedTerminal(null);
          setSelectedTrip(null);
        }}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 360 }, p: 2 } } }}
      >
        <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">
            {selectedTerminal ? 'Terminal' : 'Viagem'}
          </Typography>
          <IconButton size="small" onClick={() => { setSelectedTerminal(null); setSelectedTrip(null); }}>
            <IconX size={18} />
          </IconButton>
        </Stack>
        <Divider sx={{ mb: 2 }} />

        {selectedTerminal && (
          <TerminalDetails terminal={selectedTerminal} trips={trips} />
        )}
        {selectedTrip && (
          <TripDetails
            trip={selectedTrip}
            terminals={terminals}
            blocks={scheduleBlocks}
            onReassign={handleReassign}
            reassigning={reassigning}
          />
        )}
      </Drawer>

      <Snackbar
        open={snack.open}
        autoHideDuration={4000}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snack.severity} variant="filled" onClose={() => setSnack((s) => ({ ...s, open: false }))}>
          {snack.message}
        </Alert>
      </Snackbar>
    </Container>
  );
}

function TerminalDetails({ terminal, trips }: { terminal: MapTerminal; trips: MapTripLine[] }) {
  const originatingCount = trips.filter((t) => t.originId === terminal.id).length;
  const terminatingCount = trips.filter((t) => t.destinationId === terminal.id).length;

  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="overline" color="textSecondary">Nome</Typography>
        <Typography variant="body1" sx={{ fontWeight: 500 }}>{terminal.name}</Typography>
      </Box>
      <Box>
        <Typography variant="overline" color="textSecondary">Coordenadas</Typography>
        <Typography variant="body2">
          {typeof terminal.latitude === 'number' && typeof terminal.longitude === 'number'
            ? `${terminal.latitude.toFixed(5)}, ${terminal.longitude.toFixed(5)}`
            : '—'}
        </Typography>
      </Box>
      <Divider />
      <Box>
        <Typography variant="overline" color="textSecondary">Viagens originando aqui</Typography>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>{originatingCount}</Typography>
      </Box>
      <Box>
        <Typography variant="overline" color="textSecondary">Viagens terminando aqui</Typography>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>{terminatingCount}</Typography>
      </Box>
    </Stack>
  );
}

function minsToHHMM(m: number): string {
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function formatMinutes(min: number | null | undefined): string {
  if (min == null) return '—';
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function TripDetails({
  trip,
  terminals,
  blocks = [],
  onReassign,
  reassigning = false,
}: {
  trip: MapTripLine;
  terminals: MapTerminal[];
  blocks?: ScheduleBlock[];
  onReassign?: (tripId: number, targetBlockId: number) => void;
  reassigning?: boolean;
}) {
  const origin = terminals.find((t) => t.id === trip.originId);
  const destination = terminals.find((t) => t.id === trip.destinationId);
  const currentBlock = blocks.find((b) => b.trips.some((bt) => bt.id === trip.id));
  const [targetBlockId, setTargetBlockId] = React.useState<number | ''>('');

  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="overline" color="textSecondary">ID</Typography>
        <Typography variant="body1">#{trip.id}</Typography>
      </Box>
      <Box>
        <Typography variant="overline" color="textSecondary">Linha</Typography>
        <Typography variant="body1">{trip.lineCode ?? '—'}</Typography>
      </Box>
      <Divider />
      <Box>
        <Typography variant="overline" color="textSecondary">Origem</Typography>
        <Typography variant="body2">{origin?.name ?? (trip.originId != null ? `Terminal #${trip.originId}` : '—')}</Typography>
      </Box>
      <Box>
        <Typography variant="overline" color="textSecondary">Destino</Typography>
        <Typography variant="body2">{destination?.name ?? (trip.destinationId != null ? `Terminal #${trip.destinationId}` : '—')}</Typography>
      </Box>
      <Divider />
      <Stack sx={{ flexDirection: 'row', gap: 4 }}>
        <Box>
          <Typography variant="overline" color="textSecondary">Início</Typography>
          <Typography variant="body2">{formatMinutes(trip.startTime)}</Typography>
        </Box>
        <Box>
          <Typography variant="overline" color="textSecondary">Fim</Typography>
          <Typography variant="body2">{formatMinutes(trip.endTime)}</Typography>
        </Box>
      </Stack>
      <Stack sx={{ flexDirection: 'row', gap: 4 }}>
        <Box>
          <Typography variant="overline" color="textSecondary">Duração</Typography>
          <Typography variant="body2">{trip.duration != null ? `${trip.duration} min` : '—'}</Typography>
        </Box>
        <Box>
          <Typography variant="overline" color="textSecondary">Distância</Typography>
          <Typography variant="body2">{trip.distanceKm != null ? `${trip.distanceKm.toFixed(2)} km` : '—'}</Typography>
        </Box>
      </Stack>

      {blocks.length > 0 && onReassign && (
        <>
          <Divider />
          <Box>
            <Typography variant="overline" color="textSecondary">Bloco atual</Typography>
            <Typography variant="body2">
              {currentBlock ? `Bloco ${currentBlock.block_id} (${currentBlock.trips.length} viagens)` : '—'}
            </Typography>
          </Box>
          <FormControl size="small" fullWidth>
            <InputLabel>Mover para bloco</InputLabel>
            <Select
              value={targetBlockId}
              label="Mover para bloco"
              onChange={(e) => setTargetBlockId(e.target.value as number)}
              disabled={reassigning}
            >
              {blocks
                .filter((b) => b.block_id !== currentBlock?.block_id)
                .map((b) => (
                  <MenuItem key={b.block_id} value={b.block_id}>
                    Bloco {b.block_id} · {b.trips.length} viagens · {formatMinutes(b.start_time)}–{formatMinutes(b.end_time)}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
          <Button
            variant="outlined"
            size="small"
            disabled={targetBlockId === '' || reassigning}
            startIcon={reassigning ? <CircularProgress size={14} /> : undefined}
            onClick={() => targetBlockId !== '' && onReassign(trip.id, targetBlockId as number)}
          >
            {reassigning ? 'Reatribuindo…' : 'Confirmar Reatribuição'}
          </Button>
        </>
      )}
    </Stack>
  );
}
