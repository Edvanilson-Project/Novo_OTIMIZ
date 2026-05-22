'use client';

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { IconClock, IconAlertTriangle, IconScale, IconCurrencyDollar } from '@tabler/icons-react';
import { operationReportingApi } from '@/lib/api';

interface DutyStat {
  dutyId: number;
  workMinutes: number;
  spreadMinutes: number;
  cost: number;
  overtimeMinutes: number;
  restViolations: number;
  shiftViolations: number;
  tripCount: number;
}

interface DutyStatsReport {
  scheduleId: number;
  totalDuties: number;
  duties: DutyStat[];
  summary: {
    avgWorkMinutes: number;
    minWorkMinutes: number;
    maxWorkMinutes: number;
    p5WorkMinutes: number;
    p95WorkMinutes: number;
    giniWorkTime: number;
    totalCost: number;
    avgCost: number;
    totalRestViolations: number;
    totalShiftViolations: number;
    totalOvertimeMinutes: number;
  };
}

interface Props {
  scheduleId: number;
}

function fmtMin(min: number) {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return `${h}h${m.toString().padStart(2, '0')}`;
}

function KpiCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color?: string }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
          <Box sx={{ color: color ?? 'primary.main' }}>{icon}</Box>
          <Typography variant="caption" color="text.secondary">{label}</Typography>
        </Stack>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>{value}</Typography>
      </CardContent>
    </Card>
  );
}

export default function DutyStatsPanel({ scheduleId }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DutyStatsReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const d = await operationReportingApi.getDutyStats(scheduleId);
        if (!cancelled) { setData(d); setError(null); }
      } catch (err) {
        const axiosErr = err as { response?: { data?: { message?: string } }; message?: string };
        if (!cancelled) setError(axiosErr?.response?.data?.message ?? axiosErr?.message ?? 'Erro ao carregar jornadas');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [scheduleId]);

  if (loading) {
    return <Box sx={{ py: 6, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>;
  }
  if (error || !data) {
    return <Alert severity="info">{error ?? 'Sem dados de jornadas disponíveis.'}</Alert>;
  }

  if (!data.summary) {
    return <Alert severity="info">Resumo de jornadas indisponível para esta escala.</Alert>;
  }

  const s = data.summary;
  const violations = s.totalRestViolations + s.totalShiftViolations;

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
        Resumo de Jornadas — {data.totalDuties} jornadas
      </Typography>

      {/* KPI cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconClock size={20} />}
            label="Jornada Média"
            value={fmtMin(s.avgWorkMinutes)}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconClock size={20} />}
            label="P5 / P95"
            value={`${fmtMin(s.p5WorkMinutes)} / ${fmtMin(s.p95WorkMinutes)}`}
            color="info.main"
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconScale size={20} />}
            label="Gini (equidade)"
            value={s.giniWorkTime.toFixed(3)}
            color={s.giniWorkTime > 0.2 ? 'warning.main' : 'success.main'}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconAlertTriangle size={20} />}
            label="Violações totais"
            value={String(violations)}
            color={violations > 0 ? 'error.main' : 'success.main'}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconCurrencyDollar size={20} />}
            label="Custo Total"
            value={`R$ ${s.totalCost.toFixed(0)}`}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconCurrencyDollar size={20} />}
            label="Custo Médio/Jornada"
            value={`R$ ${s.avgCost.toFixed(0)}`}
            color="secondary.main"
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconClock size={20} />}
            label="Horas Extras Totais"
            value={fmtMin(s.totalOvertimeMinutes)}
            color={s.totalOvertimeMinutes > 0 ? 'warning.main' : 'success.main'}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <KpiCard
            icon={<IconClock size={20} />}
            label="Min / Max"
            value={`${fmtMin(s.minWorkMinutes)} / ${fmtMin(s.maxWorkMinutes)}`}
            color="text.secondary"
          />
        </Grid>
      </Grid>

      {/* Per-duty table */}
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
        Detalhe por Jornada
      </Typography>
      <TableContainer component={Card} variant="outlined" sx={{ maxHeight: 420 }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell>Jornada</TableCell>
              <TableCell align="right">Trabalho</TableCell>
              <TableCell align="right">Amplitude</TableCell>
              <TableCell align="right">Custo</TableCell>
              <TableCell align="right">H. Extra</TableCell>
              <TableCell align="right">Viagens</TableCell>
              <TableCell align="center">Violações</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.duties.map((d) => {
              const hasViolation = d.restViolations + d.shiftViolations > 0;
              return (
                <TableRow key={d.dutyId} hover sx={hasViolation ? { bgcolor: 'error.50' } : undefined}>
                  <TableCell>{d.dutyId}</TableCell>
                  <TableCell align="right">{fmtMin(d.workMinutes)}</TableCell>
                  <TableCell align="right">{fmtMin(d.spreadMinutes)}</TableCell>
                  <TableCell align="right">R$ {d.cost.toFixed(0)}</TableCell>
                  <TableCell align="right">{d.overtimeMinutes > 0 ? fmtMin(d.overtimeMinutes) : '—'}</TableCell>
                  <TableCell align="right">{d.tripCount}</TableCell>
                  <TableCell align="center">
                    {hasViolation ? (
                      <Tooltip title={`Descanso: ${d.restViolations} | Jornada: ${d.shiftViolations}`}>
                        <Chip
                          size="small"
                          label={d.restViolations + d.shiftViolations}
                          color="error"
                          variant="outlined"
                        />
                      </Tooltip>
                    ) : (
                      <Chip size="small" label="OK" color="success" variant="outlined" />
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
