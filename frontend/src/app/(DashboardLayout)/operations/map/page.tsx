'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Container,
  Divider,
  Drawer,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
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

export default function OperationsMapPage() {
  const [terminals, setTerminals] = useState<MapTerminal[]>([]);
  const [schedules, setSchedules] = useState<ScheduleSummary[]>([]);
  const [selectedScheduleId, setSelectedScheduleId] = useState<string>('');
  const [trips, setTrips] = useState<MapTripLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [tripsLoading, setTripsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTerminal, setSelectedTerminal] = useState<MapTerminal | null>(null);
  const [selectedTrip, setSelectedTrip] = useState<MapTripLine | null>(null);

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
        }
      } catch (e: any) {
        setError(e?.response?.data?.message || e?.message || 'Falha ao carregar dados do mapa.');
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
        const items: any[] = Array.isArray(result) ? result : result?.items ?? [];
        setTrips(
          items.map((t) => ({
            id: t.id,
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
          })),
        );
      } catch (e: any) {
        setError(e?.response?.data?.message || e?.message || 'Falha ao carregar viagens.');
      } finally {
        setTripsLoading(false);
      }
    })();
  }, [selectedScheduleId]);

  const terminalsWithCoords = terminals.filter(
    (t) => typeof t.latitude === 'number' && typeof t.longitude === 'number',
  ).length;
  const tripsWithCoords = trips.filter(
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
          <Stack sx={{ flexDirection: 'row', gap: 3, alignItems: 'center' }}>
            <Stack sx={{ flexDirection: 'row', alignItems: 'center', gap: 1 }}>
              <IconMapPin size={18} color="#e53935" />
              <Typography variant="body2">
                <strong>{terminalsWithCoords}</strong> de {terminals.length} terminais com coordenadas
              </Typography>
            </Stack>
            {selectedScheduleId !== '' && (
              <Typography variant="body2">
                <strong>{tripsWithCoords}</strong> de {trips.length} viagens com coordenadas
                {tripsLoading ? ' (carregando…)' : ''}
              </Typography>
            )}
          </Stack>
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
            trips={trips}
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
          <TripDetails trip={selectedTrip} terminals={terminals} />
        )}
      </Drawer>
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

function formatMinutes(min: number | null | undefined): string {
  if (min == null) return '—';
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function TripDetails({ trip, terminals }: { trip: MapTripLine; terminals: MapTerminal[] }) {
  const origin = terminals.find((t) => t.id === trip.originId);
  const destination = terminals.find((t) => t.id === trip.destinationId);

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
    </Stack>
  );
}
