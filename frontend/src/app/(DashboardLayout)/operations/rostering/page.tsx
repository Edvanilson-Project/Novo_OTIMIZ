'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Card, CardContent, CardHeader, Button, Stack, Typography,
  TextField, Alert, CircularProgress, Chip, Divider,
  FormControl, InputLabel, Select, MenuItem, Paper, Tooltip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import {
  IconCalendarStats, IconUsers, IconPlayerPlay, IconCheck,
  IconAlertTriangle,
} from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { operationsApi, weeklyRosteringApi } from '@/lib/api';

const DAY_LABELS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

interface Driver { id: number; driverId: string; name: string; }

interface DutySlot {
  id: number;
  start_time: number;  // minutos desde meia-noite
  end_time: number;
  duration: number;
}

interface WeeklyAssignment {
  operator_id: string;
  day_index: number;
  duty_id: number;
  duty_start: number;
  duty_end: number;
  duty_minutes: number;
}

interface OperatorSchedule {
  operator_id: string;
  assignments: WeeklyAssignment[];
  total_minutes: number;
  days_worked: number;
  days_off: number[];
  weekly_cost: number;
}

interface RosteringResult {
  status: string;
  schedules: OperatorSchedule[];
  unassigned_by_day: Record<number, number[]>;
  fairness_gini: number;
  total_minutes_assigned: number;
  elapsed_ms: number;
  algorithm: string;
  feasible: boolean;
  meta: Record<string, any>;
}

function minToHHMM(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function hhmmToMin(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

export default function WeeklyRosteringPage() {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [selectedDriverIds, setSelectedDriverIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [result, setResult] = useState<RosteringResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Weekly constraints
  const [weeklyLimitH, setWeeklyLimitH] = useState(44);
  const [minDaysOff, setMinDaysOff] = useState(1);
  const [minInterShiftH, setMinInterShiftH] = useState(11);
  const [timeBudget, setTimeBudget] = useState(30);

  // Duties per day: day 0-6 → list of duty slots
  const [dailyDuties, setDailyDuties] = useState<Record<number, DutySlot[]>>(() => {
    const init: Record<number, DutySlot[]> = {};
    for (let d = 0; d < 7; d++) init[d] = [];
    return init;
  });

  const [nextDutyId, setNextDutyId] = useState(1);
  const [newDuty, setNewDuty] = useState({ dayIndex: 0, start: '06:00', end: '14:00' });

  useEffect(() => {
    operationsApi.getDrivers()
      .then((data: unknown) => {
        const raw = data as { drivers?: Driver[]; data?: Driver[] } | Driver[];
        const list: Driver[] = Array.isArray(raw) ? raw : ((raw as { drivers?: Driver[]; data?: Driver[] }).drivers ?? (raw as { data?: Driver[] }).data ?? []);
        setDrivers(list);
        setSelectedDriverIds(list.slice(0, Math.min(5, list.length)).map((d) => d.id));
      })
      .catch(() => setDrivers([]))
      .finally(() => setFetching(false));
  }, []);

  const addDuty = useCallback(() => {
    const start = hhmmToMin(newDuty.start);
    const end = hhmmToMin(newDuty.end);
    if (end <= start) { setError('Horário de fim deve ser após o início.'); return; }
    setError(null);
    const duty: DutySlot = { id: nextDutyId, start_time: start, end_time: end, duration: end - start };
    setNextDutyId((n) => n + 1);
    setDailyDuties((prev) => ({
      ...prev,
      [newDuty.dayIndex]: [...(prev[newDuty.dayIndex] || []), duty],
    }));
  }, [newDuty, nextDutyId]);

  const removeDuty = useCallback((dayIndex: number, dutyId: number) => {
    setDailyDuties((prev) => ({
      ...prev,
      [dayIndex]: (prev[dayIndex] || []).filter((d) => d.id !== dutyId),
    }));
  }, []);

  const handleRun = useCallback(async () => {
    const selectedDrivers = drivers.filter((d) => selectedDriverIds.includes(d.id));
    if (selectedDrivers.length === 0) { setError('Selecione ao menos um motorista.'); return; }

    const totalDuties = Object.values(dailyDuties).reduce((s, arr) => s + arr.length, 0);
    if (totalDuties === 0) { setError('Adicione ao menos uma jornada.'); return; }

    setError(null);
    setLoading(true);
    setResult(null);

    try {
      const body = {
        operators: selectedDrivers.map((d) => ({
          id: String(d.id),
          name: d.name,
          cp: '',
          last_shift_end: 0,
          metadata: {},
        })),
        daily_duties: Object.fromEntries(
          Object.entries(dailyDuties).map(([day, duties]) => [day, duties])
        ),
        weekly_hour_limit_minutes: weeklyLimitH * 60,
        min_days_off: minDaysOff,
        min_inter_shift_rest_minutes: minInterShiftH * 60,
        time_budget_s: timeBudget,
      };

      const res = await weeklyRosteringApi.solve(body);
      setResult(res);
    } catch (e) {
      const axiosErr = e as { response?: { data?: { detail?: string; message?: string } } };
      setError(
        axiosErr?.response?.data?.detail ||
          axiosErr?.response?.data?.message ||
          'Erro ao executar escala semanal.',
      );
    } finally {
      setLoading(false);
    }
  }, [drivers, selectedDriverIds, dailyDuties, weeklyLimitH, minDaysOff, minInterShiftH, timeBudget]);

  const operatorName = (opId: string) => {
    const d = drivers.find((d) => String(d.id) === opId);
    return d ? d.name : opId;
  };

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 3 }}>
        <IconCalendarStats size={28} />
        <Typography variant="h4">Escala Semanal (Weekly Crew Rostering)</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Atribui motoristas a jornadas ao longo da semana respeitando CLT Art.67 (folga mínima),
        limite de 44h/semana e CCT 11h entre dias consecutivos. Usa CP-SAT com fallback greedy.
      </Typography>

      <Stack spacing={3}>
        {/* ── Parâmetros ── */}
        <DashboardCard title="Parâmetros da Semana">
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ flexWrap: 'wrap' }}>
            <TextField
              label="Limite semanal (h)"
              type="number"
              size="small"
              value={weeklyLimitH}
              onChange={(e) => setWeeklyLimitH(Number(e.target.value))}
              slotProps={{ htmlInput: { min: 1, max: 60 } }}
              sx={{ width: 160 }}
            />
            <TextField
              label="Folgas mínimas por semana"
              type="number"
              size="small"
              value={minDaysOff}
              onChange={(e) => setMinDaysOff(Number(e.target.value))}
              slotProps={{ htmlInput: { min: 0, max: 6 } }}
              sx={{ width: 200 }}
            />
            <TextField
              label="Descanso entre dias (h)"
              type="number"
              size="small"
              value={minInterShiftH}
              onChange={(e) => setMinInterShiftH(Number(e.target.value))}
              slotProps={{ htmlInput: { min: 1, max: 24 } }}
              sx={{ width: 200 }}
            />
            <TextField
              label="Tempo de otimização (s)"
              type="number"
              size="small"
              value={timeBudget}
              onChange={(e) => setTimeBudget(Number(e.target.value))}
              slotProps={{ htmlInput: { min: 5, max: 300 } }}
              sx={{ width: 200 }}
            />
          </Stack>
        </DashboardCard>

        {/* ── Motoristas ── */}
        <DashboardCard title={`Motoristas (${selectedDriverIds.length} selecionados)`}>
          {fetching ? (
            <CircularProgress size={20} />
          ) : drivers.length === 0 ? (
            <Alert severity="warning">Nenhum motorista cadastrado. Importe motoristas primeiro.</Alert>
          ) : (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              {drivers.map((d) => (
                <Chip
                  key={d.id}
                  label={d.name || d.driverId}
                  color={selectedDriverIds.includes(d.id) ? 'primary' : 'default'}
                  variant={selectedDriverIds.includes(d.id) ? 'filled' : 'outlined'}
                  onClick={() =>
                    setSelectedDriverIds((prev) =>
                      prev.includes(d.id) ? prev.filter((x) => x !== d.id) : [...prev, d.id]
                    )
                  }
                  clickable
                  icon={<IconUsers size={14} />}
                />
              ))}
            </Stack>
          )}
        </DashboardCard>

        {/* ── Jornadas por dia ── */}
        <DashboardCard title="Jornadas por Dia da Semana">
          <Stack spacing={2}>
            {/* Formulário de adição */}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: 'flex-end' }}>
              <FormControl size="small" sx={{ minWidth: 100 }}>
                <InputLabel>Dia</InputLabel>
                <Select
                  value={newDuty.dayIndex}
                  label="Dia"
                  onChange={(e) => setNewDuty((p) => ({ ...p, dayIndex: Number(e.target.value) }))}
                >
                  {DAY_LABELS.map((label, i) => (
                    <MenuItem key={i} value={i}>{label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                label="Início"
                size="small"
                value={newDuty.start}
                onChange={(e) => setNewDuty((p) => ({ ...p, start: e.target.value }))}
                placeholder="HH:MM"
                sx={{ width: 100 }}
              />
              <TextField
                label="Fim"
                size="small"
                value={newDuty.end}
                onChange={(e) => setNewDuty((p) => ({ ...p, end: e.target.value }))}
                placeholder="HH:MM"
                sx={{ width: 100 }}
              />
              <Button variant="outlined" onClick={addDuty}>+ Jornada</Button>
            </Stack>

            {/* Grid de jornadas */}
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 1 }}>
              {DAY_LABELS.map((label, dayIdx) => (
                <Paper key={dayIdx} variant="outlined" sx={{ p: 1, minHeight: 80 }}>
                  <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', mb: 0.5 }}>
                    {label}
                  </Typography>
                  <Stack spacing={0.5}>
                    {(dailyDuties[dayIdx] || []).map((duty) => (
                      <Chip
                        key={duty.id}
                        label={`${minToHHMM(duty.start_time)}-${minToHHMM(duty.end_time)}`}
                        size="small"
                        variant="outlined"
                        color="primary"
                        onDelete={() => removeDuty(dayIdx, duty.id)}
                      />
                    ))}
                    {(dailyDuties[dayIdx] || []).length === 0 && (
                      <Typography variant="caption" color="text.disabled">—</Typography>
                    )}
                  </Stack>
                </Paper>
              ))}
            </Box>
          </Stack>
        </DashboardCard>

        {error && <Alert severity="error">{error}</Alert>}

        <Button
          variant="contained"
          size="large"
          onClick={handleRun}
          disabled={loading}
          startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <IconPlayerPlay size={20} />}
          sx={{ alignSelf: 'flex-start' }}
        >
          {loading ? 'Calculando escala...' : 'Calcular Escala Semanal'}
        </Button>

        {/* ── Resultado ── */}
        {result && (
          <Stack spacing={2}>
            <Divider />
            <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
              <Chip
                label={result.feasible ? 'Solução viável' : 'Solução parcial'}
                color={result.feasible ? 'success' : 'warning'}
                icon={result.feasible ? <IconCheck size={14} /> : <IconAlertTriangle size={14} />}
              />
              <Chip label={`Algoritmo: ${result.algorithm}`} variant="outlined" />
              <Chip label={`Gini equidade: ${result.fairness_gini.toFixed(3)}`} variant="outlined" />
              <Chip label={`Total horas: ${(result.total_minutes_assigned / 60).toFixed(1)}h`} variant="outlined" />
              <Chip label={`Tempo: ${result.elapsed_ms.toFixed(0)} ms`} variant="outlined" />
            </Stack>

            {Object.keys(result.unassigned_by_day).some(
              (d) => (result.unassigned_by_day[Number(d)] || []).length > 0,
            ) && (
              <Alert severity="warning">
                Jornadas não atribuídas: {Object.entries(result.unassigned_by_day)
                  .filter(([, ids]) => ids.length > 0)
                  .map(([day, ids]) => `${DAY_LABELS[Number(day)]}: ${ids.length}`)
                  .join(', ')}
              </Alert>
            )}

            <DashboardCard title="Grade Semanal">
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 700 }}>Motorista</TableCell>
                      {DAY_LABELS.map((label, i) => (
                        <TableCell key={i} align="center" sx={{ fontWeight: 700 }}>
                          {label}
                        </TableCell>
                      ))}
                      <TableCell align="right" sx={{ fontWeight: 700 }}>Total</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700 }}>Folgas</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {result.schedules.map((sched) => (
                      <TableRow key={sched.operator_id} hover>
                        <TableCell sx={{ fontWeight: 600 }}>
                          {operatorName(sched.operator_id)}
                        </TableCell>
                        {DAY_LABELS.map((_, dayIdx) => {
                          const asgn = sched.assignments.find((a) => a.day_index === dayIdx);
                          const isOff = sched.days_off.includes(dayIdx);
                          return (
                            <TableCell key={dayIdx} align="center">
                              {asgn ? (
                                <Tooltip title={`${minToHHMM(asgn.duty_start)}–${minToHHMM(asgn.duty_end)} (${(asgn.duty_minutes / 60).toFixed(1)}h)`}>
                                  <Chip
                                    label={`${minToHHMM(asgn.duty_start)}`}
                                    size="small"
                                    color="primary"
                                    variant="outlined"
                                    sx={{ fontSize: '0.65rem' }}
                                  />
                                </Tooltip>
                              ) : isOff ? (
                                <Chip label="Folga" size="small" color="default" variant="outlined" sx={{ fontSize: '0.65rem' }} />
                              ) : (
                                <Typography variant="caption" color="text.disabled">—</Typography>
                              )}
                            </TableCell>
                          );
                        })}
                        <TableCell align="right">
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {(sched.total_minutes / 60).toFixed(1)}h
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="body2">
                            {sched.days_off.length}d
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </DashboardCard>
          </Stack>
        )}
      </Stack>
    </Box>
  );
}
