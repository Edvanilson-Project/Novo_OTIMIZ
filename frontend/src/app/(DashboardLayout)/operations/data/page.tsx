"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  Box, Grid, Stack, Button, Tabs, Tab, Alert, Snackbar,
  CircularProgress, Paper, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, IconButton, Tooltip,
  MenuItem, Select, FormControl, InputLabel, Chip, FormControlLabel, Switch, Divider, Typography,
} from "@mui/material";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import {
  IconUpload, IconFileSpreadsheet, IconUsers, IconPlus,
  IconEdit, IconTrash, IconRefresh, IconEraser, IconArrowBack,
  IconDownload,
} from "@tabler/icons-react";
import ExcelJS from "exceljs";
import { saveAs } from "file-saver";
import DashboardCard from "@/app/components/shared/DashboardCard";
import ParentCard from "@/app/components/shared/ParentCard";
import { operationsApi, linesApi, terminalsApi, gtfsApi } from "@/lib/api";
import { minToHHMM } from "@/lib/format";

// ─── Tipos ────────────────────────────────────────────────────────────────────
interface Trip {
  id: number;
  tripId: number;
  lineCode?: string;
  lineId?: number;
  pairId?: string;
  startTime: number;
  endTime: number;
  duration: number;
  originId: number;
  destinationId: number;
  distanceKm: number;
  direction?: string;
  depotId?: number | null;
  isReliefPoint?: boolean;
  midTripReliefPointId?: number | null;
  midTripReliefOffsetMinutes?: number | null;
}

interface Driver {
  id: number;
  driverId: string;
  name: string;
  role?: string;
  maxHoursPerDay?: number;
  lastShiftEnd?: number;
}

interface Line {
  id: number;
  lineId: string;
  name: string;
  isActive: boolean;
  originTerminalId?: number;
  destinationTerminalId?: number;
  distanceKm?: number;
  returnDistanceKm?: number;
  avgTripDurationMinutes?: number;
  avgReturnDurationMinutes?: number;
}
interface Terminal { id: number; terminalId: string; name: string; }

interface TripFormState {
  lineCode: string;
  startTime: string;
  endTime: string;
  duration: number;
  originId: number;
  destinationId: number;
  distanceKm: number;
  direction: string;
  roundTrip: boolean;
  // campos da VOLTA (apenas quando roundTrip=true)
  returnStartTime: string;
  returnEndTime: string;
  returnDuration: number;
  returnOriginId: number;
  returnDestinationId: number;
  returnDistanceKm: number;
  // Rendição (relief points)
  isReliefPoint: boolean;
  midTripReliefPointId: number | null;
  midTripReliefOffsetMinutes: number | null;
  // Multi-depot
  depotId: number | null;
}

const EMPTY_TRIP: TripFormState = {
  lineCode: "", startTime: "06:00", endTime: "14:00",
  duration: 0, originId: 0, destinationId: 0, distanceKm: 0,
  direction: "IDA", roundTrip: false,
  returnStartTime: "14:00", returnEndTime: "22:00",
  returnDuration: 0, returnOriginId: 0, returnDestinationId: 0, returnDistanceKm: 0,
  isReliefPoint: false, midTripReliefPointId: null, midTripReliefOffsetMinutes: null,
  depotId: null,
};

const EMPTY_DRIVER: Omit<Driver, "id"> = {
  driverId: "", name: "", role: "Motorista", maxHoursPerDay: 480, lastShiftEnd: 0,
};

// converte "HH:MM" para minutos desde meia-noite
function hhmmToMin(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

// ─── Página ───────────────────────────────────────────────────────────────────
export default function OperationsDataPage() {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [gtfsUploading, setGtfsUploading] = useState(false);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [terminals, setTerminals] = useState<Terminal[]>([]);
  const [notification, setNotification] = useState({
    open: false, message: "", severity: "success" as "success" | "error" | "info" | "warning",
  });

  // Trip dialog
  const [tripDialog, setTripDialog] = useState(false);
  const [editingTrip, setEditingTrip] = useState<Trip | null>(null);
  const [tripForm, setTripForm] = useState<TripFormState>(EMPTY_TRIP);

  // Viagem par ao editar
  const [editingPairTrip, setEditingPairTrip] = useState<Trip | null>(null);

  // Driver dialog
  const [driverDialog, setDriverDialog] = useState(false);
  const [editingDriver, setEditingDriver] = useState<Driver | null>(null);
  const [driverForm, setDriverForm] = useState<Omit<Driver, "id">>(EMPTY_DRIVER);
  const [driverError, setDriverError] = useState<string | null>(null);

  const notify = (message: string, severity: "success" | "error" | "info" | "warning" = "success") =>
    setNotification({ open: true, message, severity });

  const handleExportLayout = async () => {
    const workbook = new ExcelJS.Workbook();

    // Sheet 1: Viagens (Template Completo)
    const tripsSheet = workbook.addWorksheet("Viagens");
    const tripsTemplate = [
      { trip_id: 1001, line_code: "101-A", line_name: "Linha Exemplo Matriz", pair_id: "P001", direction: "IDA", start_time: "06:00", end_time: "07:30", duration: 90, origin_id: 1, origin_name: "Terminal Norte", destination_id: 2, destination_name: "Terminal Sul", distance_km: 25.50 },
      { trip_id: 1002, line_code: "101-A", line_name: "Linha Exemplo Matriz", pair_id: "P001", direction: "VOLTA", start_time: "07:45", end_time: "09:15", duration: 90, origin_id: 2, origin_name: "Terminal Sul", destination_id: 1, destination_name: "Terminal Norte", distance_km: 25.50 },
    ];
    tripsSheet.addRow(Object.keys(tripsTemplate[0]));
    tripsTemplate.forEach(row => tripsSheet.addRow(Object.values(row) as unknown[]));

    // Sheet 2: Motoristas (Template Completo)
    const driversSheet = workbook.addWorksheet("Motoristas");
    const driversTemplate = [
      { driver_id: "M001", name: "João Silva", role: "Motorista", max_hours_per_day: 480, last_shift_end: 0 },
      { driver_id: "M002", name: "Maria Souza", role: "Motorista/Cobrador", max_hours_per_day: 540, last_shift_end: 1320 },
    ];
    driversSheet.addRow(Object.keys(driversTemplate[0]));
    driversTemplate.forEach(row => driversSheet.addRow(Object.values(row) as unknown[]));

    const buffer = await workbook.xlsx.writeBuffer();
    saveAs(new Blob([buffer], { type: "application/octet-stream" }), "layout_importacao_otimiz.xlsx");
    notify("Layout exportado com sucesso! Preencha os dados e importe.", "success");
  };

  const fetchReferenceData = useCallback(async () => {
    try {
      const [linesData, terminalsData] = await Promise.all([linesApi.getAll(), terminalsApi.getAll()]);
      setLines(Array.isArray(linesData) ? linesData.filter((l: Line) => l.isActive) : []);
      setTerminals(Array.isArray(terminalsData) ? terminalsData : []);
    } catch { /* silent */ }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 0) {
        const data = await operationsApi.getTrips({ limit: 500 });
        setTrips(Array.isArray(data) ? data : (data as { data?: unknown[] }).data ?? []);
      } else {
        const data = await operationsApi.getDrivers();
        setDrivers(Array.isArray(data) ? data : (data as { data?: unknown[] }).data ?? []);
      }
    } catch {
      notify("Erro ao carregar dados.", "error");
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { fetchReferenceData(); }, [fetchReferenceData]);
  useEffect(() => { fetchData(); }, [fetchData]);

  // Duração calculada ao vivo (com suporte a virada de meia-noite)
  const calcDuration = useMemo(() => {
    const s = hhmmToMin(tripForm.startTime);
    const e = hhmmToMin(tripForm.endTime);
    if (!tripForm.startTime || !tripForm.endTime) return 0;
    return e >= s ? e - s : 1440 + e - s;
  }, [tripForm.startTime, tripForm.endTime]);

  const calcReturnDuration = useMemo(() => {
    const s = hhmmToMin(tripForm.returnStartTime);
    const e = hhmmToMin(tripForm.returnEndTime);
    if (!tripForm.returnStartTime || !tripForm.returnEndTime) return 0;
    return e >= s ? e - s : 1440 + e - s;
  }, [tripForm.returnStartTime, tripForm.returnEndTime]);

  // ─── GTFS Import ─────────────────────────────────────────────────────────
  const handleGtfsImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setGtfsUploading(true);
    try {
      const result = await gtfsApi.import(file);
      const { imported, skipped, errors } = result;
      const msg = `GTFS importado: ${imported.terminals} terminais, ${imported.lines} linhas, ${imported.trips} viagens` +
        (skipped > 0 ? ` (${skipped} ignorados)` : '');
      notify(msg, errors.length > 0 ? "warning" : "success");
      if (errors.length > 0) console.warn('GTFS import errors:', errors);
      fetchData();
      fetchReferenceData();
    } catch (error: unknown) {
      const axErr = error as { response?: { data?: { message?: string } } };
      const msg = axErr?.response?.data?.message ?? "Erro ao importar GTFS.";
      notify(msg, "error");
    } finally {
      setGtfsUploading(false);
      event.target.value = "";
    }
  };

  // ─── Upload ───────────────────────────────────────────────────────────────
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", activeTab === 0 ? "trips" : "drivers");
    try {
      const result = await operationsApi.upload(formData);
      const r = result as { inserted?: number; skipped?: number };
      const msg = r?.inserted !== undefined
        ? `Importados: ${r.inserted} registros${r.skipped ? `, ignorados: ${r.skipped}` : ""}`
        : "Upload concluído!";
      notify(msg);
      fetchData();
    } catch (error: unknown) {
      const errData = (error as { response?: { data?: { errors?: string[]; message?: string } } })?.response?.data;
      const msg = errData?.errors?.slice(0, 3).join(" | ") ?? errData?.message ?? "Erro no upload.";
      notify(msg, "error");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  // ─── CRUD Viagens ──────────────────────────────────────────────────────────
  const toHHMM = (min: number) => {
    const h = Math.floor(min / 60).toString().padStart(2, "0");
    const m = (min % 60).toString().padStart(2, "0");
    return `${h}:${m}`;
  };

  const openCreateTrip = () => {
    setEditingTrip(null);
    setEditingPairTrip(null);
    setTripForm(EMPTY_TRIP);
    setTripDialog(true);
  };

  const openEditTrip = (row: Trip) => {
    const pairTrip = row.pairId ? trips.find(t => t.pairId === row.pairId && t.id !== row.id) ?? null : null;
    setEditingTrip(row);
    setEditingPairTrip(pairTrip);
    setTripForm({
      lineCode: row.lineCode ?? "",
      startTime: toHHMM(row.startTime),
      endTime: toHHMM(row.endTime),
      duration: row.duration,
      originId: row.originId,
      destinationId: row.destinationId,
      distanceKm: row.distanceKm,
      direction: row.direction ?? "IDA",
      roundTrip: !!pairTrip,
      returnStartTime: pairTrip ? toHHMM(pairTrip.startTime) : toHHMM(row.endTime),
      returnEndTime: pairTrip ? toHHMM(pairTrip.endTime) : toHHMM(row.endTime + row.duration),
      returnDuration: pairTrip?.duration ?? 0,
      returnOriginId: pairTrip?.originId ?? row.destinationId,
      returnDestinationId: pairTrip?.destinationId ?? row.originId,
      returnDistanceKm: pairTrip?.distanceKm ?? row.distanceKm,
      isReliefPoint: !!row.isReliefPoint,
      midTripReliefPointId: row.midTripReliefPointId ?? null,
      midTripReliefOffsetMinutes: row.midTripReliefOffsetMinutes ?? null,
      depotId: row.depotId ?? null,
    });
    setTripDialog(true);
  };

  // Ao ativar roundTrip, pré-preenche os campos da VOLTA
  const handleToggleRoundTrip = (checked: boolean) => {
    setTripForm(f => ({
      ...f,
      roundTrip: checked,
      direction: checked ? "IDA" : f.direction,
      returnStartTime: f.endTime,
      returnOriginId: f.destinationId,
      returnDestinationId: f.originId,
      returnDistanceKm: f.distanceKm,
    }));
  };

  const handleSaveTrip = async () => {
    // Validações client-side antes de submit. Mantém formato HH:MM (ou HH:MM > 24h
    // para overnight). originId != destinationId. distanceKm > 0. duration plausível
    // (1..480min). end > start. Estas validações evitam submetting de dados inválidos
    // que o backend rejeitaria com erro genérico.
    const HHMM = /^([0-9]{1,2}):([0-5][0-9])$/;
    const parseHHMM = (s: string): number | null => {
      const m = HHMM.exec(s.trim());
      if (!m) return null;
      const h = Number(m[1]); const min = Number(m[2]);
      if (h < 0 || h > 47) return null;  // permite até 47:59 para overnight
      return h * 60 + min;
    };
    const validateLeg = (label: string, st: string, et: string, oid: number, did: number, dist: number): string | null => {
      if (!st || !et) return `${label}: início e fim são obrigatórios.`;
      const sm = parseHHMM(st);
      const em = parseHHMM(et);
      if (sm === null) return `${label}: horário de início inválido (use HH:MM, ex: 06:00).`;
      if (em === null) return `${label}: horário de fim inválido (use HH:MM, ex: 14:00).`;
      const adjustedEnd = em < sm ? em + 1440 : em; // overnight
      const dur = adjustedEnd - sm;
      if (dur <= 0) return `${label}: fim deve ser depois do início.`;
      if (dur > 480) return `${label}: duração ${dur}min excede 8h — verifique se está correto.`;
      if (oid === did) return `${label}: terminal de origem e destino não podem ser iguais.`;
      if (dist <= 0) return `${label}: distância (km) deve ser maior que zero.`;
      return null;
    };

    const idaErr = validateLeg("IDA", tripForm.startTime, tripForm.endTime, Number(tripForm.originId), Number(tripForm.destinationId), Number(tripForm.distanceKm || 0));
    if (idaErr) { notify(idaErr, "error"); return; }
    if (tripForm.roundTrip) {
      const voltaErr = validateLeg("VOLTA", tripForm.returnStartTime || "", tripForm.returnEndTime || "", Number(tripForm.returnOriginId), Number(tripForm.returnDestinationId), Number(tripForm.returnDistanceKm || 0));
      if (voltaErr) { notify(voltaErr, "error"); return; }
    }
    try {
      const payload: Record<string, unknown> = {
        lineCode: tripForm.lineCode || undefined,
        startTime: tripForm.startTime,
        endTime: tripForm.endTime,
        duration: tripForm.duration || undefined,
        originId: tripForm.originId,
        destinationId: tripForm.destinationId,
        distanceKm: tripForm.distanceKm,
        direction: tripForm.direction || "IDA",
        roundTrip: tripForm.roundTrip,
        isReliefPoint: tripForm.isReliefPoint,
        midTripReliefPointId: tripForm.midTripReliefPointId,
        midTripReliefOffsetMinutes: tripForm.midTripReliefOffsetMinutes,
        depotId: tripForm.depotId,
      };
      if (tripForm.roundTrip) {
        payload.returnStartTime = tripForm.returnStartTime;
        payload.returnEndTime = tripForm.returnEndTime;
        payload.returnDuration = tripForm.returnDuration || undefined;
        payload.returnOriginId = tripForm.returnOriginId;
        payload.returnDestinationId = tripForm.returnDestinationId;
        payload.returnDistanceKm = tripForm.returnDistanceKm;
      }
      if (editingTrip) {
        await operationsApi.updateTrip(editingTrip.id, payload);
        // Se existe viagem par e roundTrip está ativo, atualiza a par também
        if (editingPairTrip && tripForm.roundTrip) {
          const returnPayload: Record<string, unknown> = {
            lineCode: tripForm.lineCode || undefined,
            startTime: tripForm.returnStartTime,
            endTime: tripForm.returnEndTime,
            duration: tripForm.returnDuration || undefined,
            originId: tripForm.returnOriginId,
            destinationId: tripForm.returnDestinationId,
            distanceKm: tripForm.returnDistanceKm,
            direction: tripForm.direction === "IDA" ? "VOLTA" : "IDA",
          };
          await operationsApi.updateTrip(editingPairTrip.id, returnPayload);
          notify("Viagem e par atualizados!");
        } else {
          notify("Viagem atualizada!");
        }
      } else {
        const result = await operationsApi.createTrip(payload) as { trips?: unknown[] };
        const count = result?.trips ? result.trips.length : 1;
        notify(count > 1 ? `${count} viagens criadas (IDA + VOLTA com mesmo pairId)!` : "Viagem criada!");
      }
      setTripDialog(false);
      fetchData();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      notify(err?.response?.data?.message ?? "Erro ao salvar viagem.", "error");
    }
  };

  const handleDeleteTrip = async (id: number, pairId?: string) => {
    const pairTrip = pairId ? trips.find(t => t.pairId === pairId && t.id !== id) ?? null : null;
    const msg = pairTrip
      ? `Esta viagem tem uma par (pairId: ${pairId}). Excluir AMBAS (IDA + VOLTA)?`
      : "Excluir esta viagem? Esta ação não pode ser desfeita.";
    if (!confirm(msg)) return;
    try {
      await operationsApi.deleteTrip(id);
      if (pairTrip) await operationsApi.deleteTrip(pairTrip.id);
      notify(pairTrip ? "Viagem e par excluídos." : "Viagem excluída.");
      fetchData();
    } catch {
      notify("Erro ao excluir viagem.", "error");
    }
  };

  const handleClearAllTrips = async () => {
    if (!confirm(`Limpar TODAS as ${trips.length} viagens? Esta ação não pode ser desfeita.`)) return;
    try {
      await operationsApi.clearTrips();
      notify(`${trips.length} viagens removidas.`, "info");
      setTrips([]);
    } catch {
      notify("Erro ao limpar viagens.", "error");
    }
  };

  // ─── CRUD Motoristas ──────────────────────────────────────────────────────
  const openCreateDriver = () => { setEditingDriver(null); setDriverForm(EMPTY_DRIVER); setDriverError(null); setDriverDialog(true); };
  const openEditDriver = (row: Driver) => {
    setEditingDriver(row);
    setDriverForm({
      driverId: row.driverId, name: row.name, role: row.role ?? "Motorista",
      maxHoursPerDay: row.maxHoursPerDay ?? 480, lastShiftEnd: row.lastShiftEnd ?? 0,
    });
    setDriverDialog(true);
  };

  const handleSaveDriver = async () => {
    if (!driverForm.driverId || !driverForm.name) {
      setDriverError("Cód. Motorista e Nome Completo são obrigatórios."); return;
    }
    setDriverError(null);
    try {
      if (editingDriver) {
        await operationsApi.updateDriver(editingDriver.id, driverForm);
        notify("Motorista atualizado!");
      } else {
        await operationsApi.createDriver(driverForm);
        notify("Motorista criado!");
      }
      setDriverDialog(false);
      fetchData();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      notify(err?.response?.data?.message ?? "Erro ao salvar motorista.", "error");
    }
  };

  const handleDeleteDriver = async (id: number) => {
    if (!confirm("Excluir este motorista? Esta ação não pode ser desfeita.")) return;
    try {
      await operationsApi.deleteDriver(id);
      notify("Motorista excluído.");
      fetchData();
    } catch {
      notify("Erro ao excluir motorista.", "error");
    }
  };

  // ─── Colunas ──────────────────────────────────────────────────────────────
  const tripColumns: GridColDef[] = [
    { field: "tripId", headerName: "Trip ID", width: 80 },
    { field: "lineCode", headerName: "Linha", width: 100, renderCell: (p) => p.value ? <Chip label={p.value} size="small" variant="outlined" /> : "—" },
    { field: "pairId", headerName: "Par", width: 60, sortable: false, renderCell: (p) => p.value ? <Chip label="Par" size="small" color="info" title={p.value} /> : "—" },
    { field: "direction", headerName: "Sentido", width: 80, renderCell: (p) => p.value ? <Chip label={p.value} size="small" color={p.value === "IDA" ? "primary" : "secondary"} /> : "—" },
    { field: "startTime", headerName: "Início", width: 80, renderCell: (p: GridRenderCellParams) => minToHHMM(p.value ?? 0) },
    { field: "endTime", headerName: "Fim", width: 80, renderCell: (p: GridRenderCellParams) => minToHHMM(p.value ?? 0) },
    { field: "duration", headerName: "Dur.(min)", width: 85 },
    { field: "originId", headerName: "Origem", width: 70 },
    { field: "destinationId", headerName: "Destino", width: 70 },
    { field: "distanceKm", headerName: "Km", width: 65 },
    {
      field: "_actions", headerName: "Ações", width: 100, sortable: false,
      renderCell: (p: GridRenderCellParams) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar"><IconButton size="small" onClick={() => openEditTrip(p.row)}><IconEdit size={16} /></IconButton></Tooltip>
          <Tooltip title="Excluir"><IconButton size="small" color="error" onClick={() => handleDeleteTrip(p.row.id, p.row.pairId)}><IconTrash size={16} /></IconButton></Tooltip>
        </Stack>
      ),
    },
  ];

  const driverColumns: GridColDef[] = [
    { field: "id", headerName: "ID", width: 70 },
    { field: "driverId", headerName: "Cód.", width: 110 },
    { field: "name", headerName: "Nome Completo", flex: 1 },
    { field: "role", headerName: "Função", width: 140 },
    { field: "maxHoursPerDay", headerName: "Jornada Máx. (min)", width: 160 },
    { field: "lastShiftEnd", headerName: "Fim Turno", width: 120, renderCell: (p) => p.value ? minToHHMM(p.value) : "—" },
    {
      field: "_actions", headerName: "Ações", width: 100, sortable: false,
      renderCell: (p: GridRenderCellParams) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar"><IconButton size="small" onClick={() => openEditDriver(p.row)}><IconEdit size={16} /></IconButton></Tooltip>
          <Tooltip title="Excluir"><IconButton size="small" color="error" onClick={() => handleDeleteDriver(p.row.id)}><IconTrash size={16} /></IconButton></Tooltip>
        </Stack>
      ),
    },
  ];

  // ─── Subformulário reutilizável de campos de viagem (memoizado para evitar perda de foco) ───
  // eslint-disable-next-line react/display-name
  const TripFields = useMemo(() => ({
    prefix, startTime, endTime, duration, originId, destinationId, distanceKm, direction,
    onStartTime, onEndTime, onDuration, onOriginId, onDestinationId, onDistanceKm, onDirection,
    showDirection = true, calcDur,
  }: {
    prefix: string;
    startTime: string; endTime: string; duration: number;
    originId: number; destinationId: number; distanceKm: number; direction: string;
    onStartTime(v: string): void; onEndTime(v: string): void; onDuration(v: number): void;
    onOriginId(v: number): void; onDestinationId(v: number): void; onDistanceKm(v: number): void;
    onDirection(v: string): void;
    showDirection?: boolean; calcDur: number;
  }) => (
    <Grid container spacing={2}>
      <Grid size={{ xs: 6 }}>
        <TextField fullWidth size="small" label={`${prefix} Início (HH:MM, ex: 06:00 ou 25:30)`} type="text"
          placeholder="HH:MM" inputMode="numeric"
          value={startTime} onChange={e => {
            const v = e.target.value;
            onStartTime(v);
            if (endTime && /^\d{1,2}:\d{2}$/.test(v) && /^\d{1,2}:\d{2}$/.test(endTime)) {
              const s = hhmmToMin(v), en = hhmmToMin(endTime);
              if (en >= s) onDuration(en - s);
            }
          }} />
      </Grid>
      <Grid size={{ xs: 6 }}>
        <TextField fullWidth size="small" label={`${prefix} Fim (HH:MM, ex: 14:00 ou 25:30)`} type="text"
          placeholder="HH:MM" inputMode="numeric"
          value={endTime} onChange={e => {
            const v = e.target.value;
            onEndTime(v);
            if (startTime && /^\d{1,2}:\d{2}$/.test(v) && /^\d{1,2}:\d{2}$/.test(startTime)) {
              const s = hhmmToMin(startTime), en = hhmmToMin(v);
              if (en >= s) onDuration(en - s);
            }
          }} />
      </Grid>
      {calcDur > 0 && (
        <Grid size={{ xs: 12 }}>
          <Alert severity={calcDur > 720 ? "warning" : "info"} sx={{ py: 0 }}>
            Duração: <strong>{calcDur} min</strong>
            {calcDur > 720 && " — viagem muito longa, confirme os horários"}
          </Alert>
        </Grid>
      )}
      <Grid size={{ xs: 6 }}>
        <TextField fullWidth size="small" label="Duração (min)" type="number"
          helperText="Auto-calculada — edite para ajuste fino"
          value={duration} onChange={e => onDuration(Number(e.target.value))} />
      </Grid>
      <Grid size={{ xs: 6 }}>
        <TextField fullWidth size="small" label="Distância (km)" type="number"
          value={distanceKm} onChange={e => onDistanceKm(Number(e.target.value))} />
      </Grid>
      <Grid size={{ xs: 6 }}>
        <FormControl fullWidth size="small">
          <InputLabel>Origem</InputLabel>
          <Select label="Origem" value={originId}
            onChange={e => onOriginId(Number(e.target.value))}>
            <MenuItem value={0}><em>— Selecione —</em></MenuItem>
            {terminals.map(t => <MenuItem key={t.id} value={t.id}>{t.terminalId} — {t.name}</MenuItem>)}
          </Select>
        </FormControl>
      </Grid>
      <Grid size={{ xs: 6 }}>
        <FormControl fullWidth size="small">
          <InputLabel>Destino</InputLabel>
          <Select label="Destino" value={destinationId}
            onChange={e => onDestinationId(Number(e.target.value))}>
            <MenuItem value={0}><em>— Selecione —</em></MenuItem>
            {terminals.map(t => <MenuItem key={t.id} value={t.id}>{t.terminalId} — {t.name}</MenuItem>)}
          </Select>
        </FormControl>
      </Grid>
      {showDirection && (
        <Grid size={{ xs: 12 }}>
          <FormControl fullWidth size="small">
            <InputLabel>Sentido</InputLabel>
            <Select label="Sentido" value={direction} onChange={e => onDirection(e.target.value)}>
              <MenuItem value="IDA">IDA</MenuItem>
              <MenuItem value="VOLTA">VOLTA</MenuItem>
              <MenuItem value="CIRCULAR">CIRCULAR</MenuItem>
            </Select>
          </FormControl>
        </Grid>
      )}
    </Grid>
  ), [terminals]);

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard title="Gestão de Dados Operacionais" subtitle="Gerencie viagens e motoristas para o motor de otimização">
        <Stack spacing={3}>
          {/* ── Header ── */}
          <Paper variant="outlined" sx={{ p: 2, backgroundColor: "background.default" }}>
            <Grid container spacing={2} sx={{ alignItems: "center" }}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)}>
                  <Tab icon={<IconFileSpreadsheet size={20} />} label="Viagens" />
                  <Tab icon={<IconUsers size={20} />} label="Motoristas" />
                </Tabs>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
                  <Tooltip title="Atualizar lista">
                    <IconButton onClick={fetchData} disabled={loading}><IconRefresh size={20} /></IconButton>
                  </Tooltip>
                  {activeTab === 0 && (
                    <>
                      <Button variant="outlined" startIcon={<IconPlus size={18} />} onClick={openCreateTrip} size="small">
                        Nova Viagem
                      </Button>
                      <Button variant="outlined" color="error" startIcon={<IconEraser size={18} />}
                        onClick={handleClearAllTrips} disabled={trips.length === 0} size="small">
                        Limpar ({trips.length})
                      </Button>
                    </>
                  )}
                  {activeTab === 1 && (
                    <Button variant="outlined" startIcon={<IconPlus size={18} />} onClick={openCreateDriver} size="small">
                      Novo Motorista
                    </Button>
                  )}
                  {activeTab === 0 && (
                    <Tooltip title="Importar arquivo GTFS (.zip) — cria terminais, linhas e viagens automaticamente">
                      <Button variant="outlined" color="info" component="label"
                        startIcon={gtfsUploading ? <CircularProgress size={18} color="inherit" /> : <IconUpload size={18} />}
                        disabled={gtfsUploading} size="small">
                        {gtfsUploading ? "Importando..." : "Importar GTFS"}
                        <input type="file" hidden accept=".zip" onChange={handleGtfsImport} />
                      </Button>
                    </Tooltip>
                  )}
                  <Tooltip title="Baixar modelo de planilha para importação (CSV/Excel)">
                    <Button variant="outlined" color="secondary" startIcon={<IconDownload size={18} />}
                      onClick={handleExportLayout} size="small">
                      Exportar Layout
                    </Button>
                  </Tooltip>
                  <Button variant="contained" component="label"
                    startIcon={uploading ? <CircularProgress size={18} color="inherit" /> : <IconUpload size={18} />}
                    disabled={uploading} size="small">
                    {uploading ? "Processando..." : `Importar ${activeTab === 0 ? "Viagens" : "Motoristas"}`}
                    <input type="file" hidden accept=".xlsx,.csv" onChange={handleFileUpload} />
                  </Button>
                </Stack>
              </Grid>
            </Grid>
          </Paper>

          {/* ── Tabela ── */}
          <ParentCard title={activeTab === 0 ? `Viagens Carregadas (${trips.length})` : `Base de Motoristas (${drivers.length})`}>
            <Box sx={{ height: 580, width: "100%", mt: 2 }}>
              <DataGrid
                rows={activeTab === 0 ? trips : drivers}
                columns={activeTab === 0 ? tripColumns : driverColumns}
                loading={loading}
                pageSizeOptions={[25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                disableRowSelectionOnClick
                sx={{ border: 0, "& .MuiDataGrid-columnHeaders": { backgroundColor: "action.hover" } }}
              />
            </Box>
          </ParentCard>
        </Stack>
      </DashboardCard>

      {/* ── Dialog Viagem ── */}
      <Dialog open={tripDialog} onClose={() => setTripDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingTrip ? "Editar Viagem" : "Nova Viagem"}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2.5} sx={{ mt: 1 }}>

            {/* Linha */}
            <FormControl fullWidth size="small">
              <InputLabel>Linha</InputLabel>
              <Select label="Linha" value={tripForm.lineCode}
                onChange={e => {
                  const code = e.target.value as string;
                  const selected = lines.find(l => l.lineId === code);
                  // Auto-fill defaults from line when direction = IDA
                  setTripForm(f => ({
                    ...f,
                    lineCode: code,
                    ...(selected && f.direction === 'IDA' ? {
                      originId: selected.originTerminalId ?? f.originId,
                      destinationId: selected.destinationTerminalId ?? f.destinationId,
                      distanceKm: selected.distanceKm ?? f.distanceKm,
                      duration: selected.avgTripDurationMinutes ?? f.duration,
                    } : {}),
                    ...(selected && f.direction === 'VOLTA' ? {
                      originId: selected.destinationTerminalId ?? f.originId,
                      destinationId: selected.originTerminalId ?? f.destinationId,
                      distanceKm: selected.returnDistanceKm ?? selected.distanceKm ?? f.distanceKm,
                      duration: selected.avgReturnDurationMinutes ?? selected.avgTripDurationMinutes ?? f.duration,
                    } : {}),
                  }));
                }}>
                <MenuItem value=""><em>— Sem linha —</em></MenuItem>
                {lines.map(l => <MenuItem key={l.id} value={l.lineId}>{l.lineId} — {l.name}</MenuItem>)}
              </Select>
            </FormControl>

            {/* ── IDA ── */}
            <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 700 }}>
              {tripForm.roundTrip ? "IDA" : "Dados da Viagem"}
            </Typography>

            <TripFields
              prefix=""
              startTime={tripForm.startTime} endTime={tripForm.endTime}
              duration={tripForm.duration} originId={tripForm.originId}
              destinationId={tripForm.destinationId} distanceKm={tripForm.distanceKm}
              direction={tripForm.direction} calcDur={calcDuration}
              onStartTime={v => setTripForm(f => ({ ...f, startTime: v }))}
              onEndTime={v => setTripForm(f => ({ ...f, endTime: v }))}
              onDuration={v => setTripForm(f => ({ ...f, duration: v }))}
              onOriginId={v => setTripForm(f => ({ ...f, originId: v }))}
              onDestinationId={v => setTripForm(f => ({ ...f, destinationId: v }))}
              onDistanceKm={v => setTripForm(f => ({ ...f, distanceKm: v }))}
              onDirection={v => {
                const selected = lines.find(l => l.lineId === tripForm.lineCode);
                setTripForm(f => ({
                  ...f, direction: v,
                  ...(selected && v === 'IDA' ? {
                    originId: selected.originTerminalId ?? f.originId,
                    destinationId: selected.destinationTerminalId ?? f.destinationId,
                    distanceKm: selected.distanceKm ?? f.distanceKm,
                    duration: selected.avgTripDurationMinutes ?? f.duration,
                  } : {}),
                  ...(selected && v === 'VOLTA' ? {
                    originId: selected.destinationTerminalId ?? f.originId,
                    destinationId: selected.originTerminalId ?? f.destinationId,
                    distanceKm: selected.returnDistanceKm ?? selected.distanceKm ?? f.distanceKm,
                    duration: selected.avgReturnDurationMinutes ?? selected.avgTripDurationMinutes ?? f.duration,
                  } : {}),
                }));
              }}
              showDirection={!tripForm.roundTrip}
            />

            {/* Toggle IDA+VOLTA (apenas criação) */}
            {!editingTrip && (
              <>
                <Divider />
                <FormControlLabel
                  control={<Switch checked={tripForm.roundTrip} onChange={e => handleToggleRoundTrip(e.target.checked)} />}
                  label={<Typography variant="body2" sx={{ fontWeight: 600 }}>Lançar IDA + VOLTA juntas (mesmo pairId)</Typography>}
                />
              </>
            )}

            {/* ── VOLTA (expansível) ── */}
            {tripForm.roundTrip && (
              <>
                <Divider />
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <IconArrowBack size={18} />
                  <Typography variant="subtitle2" color="secondary" sx={{ fontWeight: 700 }}>
                    VOLTA — sentido invertido automático
                  </Typography>
                </Stack>

                <TripFields
                  prefix="Volta:"
                  startTime={tripForm.returnStartTime} endTime={tripForm.returnEndTime}
                  duration={tripForm.returnDuration} originId={tripForm.returnOriginId}
                  destinationId={tripForm.returnDestinationId} distanceKm={tripForm.returnDistanceKm}
                  direction="VOLTA" calcDur={calcReturnDuration}
                  onStartTime={v => setTripForm(f => ({ ...f, returnStartTime: v }))}
                  onEndTime={v => setTripForm(f => ({ ...f, returnEndTime: v }))}
                  onDuration={v => setTripForm(f => ({ ...f, returnDuration: v }))}
                  onOriginId={v => setTripForm(f => ({ ...f, returnOriginId: v }))}
                  onDestinationId={v => setTripForm(f => ({ ...f, returnDestinationId: v }))}
                  onDistanceKm={v => setTripForm(f => ({ ...f, returnDistanceKm: v }))}
                  onDirection={() => { /* sempre VOLTA */ }}
                  showDirection={false}
                />

                <Alert severity="success" sx={{ py: 0.5 }}>
                  Serão criadas <strong>2 viagens</strong> com o mesmo <strong>pairId</strong>:
                  IDA ({tripForm.startTime}→{tripForm.endTime}) + VOLTA ({tripForm.returnStartTime}→{tripForm.returnEndTime})
                </Alert>
              </>
            )}

            {/* ── Rendição (relief points) ── opcional, requer allow_relief_points habilitado */}
            <Divider />
            <Stack spacing={1.5}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Rendição (opcional)
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Permite que o motorista entregue o veículo a outro motorista no terminal de origem/destino
                ou em um ponto intermediário no meio da viagem. Requer parâmetro &quot;Permitir Pontos de Rendição&quot;
                ativo em /settings/parameters.
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={tripForm.isReliefPoint}
                    onChange={e => setTripForm(f => ({ ...f, isReliefPoint: e.target.checked }))}
                  />
                }
                label={
                  <Typography variant="body2">
                    Origem/destino desta viagem é ponto de rendição
                  </Typography>
                }
              />

              <Stack direction="row" spacing={1.5}>
                <FormControl fullWidth size="small">
                  <InputLabel>Ponto de rendição (terminal intermediário)</InputLabel>
                  <Select
                    value={tripForm.midTripReliefPointId == null ? "" : String(tripForm.midTripReliefPointId)}
                    label="Ponto de rendição (terminal intermediário)"
                    onChange={e => {
                      const v = e.target.value;
                      setTripForm(f => ({
                        ...f,
                        midTripReliefPointId: v === "" ? null : Number(v),
                      }));
                    }}
                  >
                    <MenuItem value="">— Nenhum —</MenuItem>
                    {terminals
                      .filter(t => t.id !== Number(tripForm.originId) && t.id !== Number(tripForm.destinationId))
                      .map(t => (
                        <MenuItem key={t.id} value={String(t.id)}>
                          {t.name || `Terminal #${t.id}`}
                        </MenuItem>
                      ))}
                  </Select>
                </FormControl>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="Min após início (split)"
                  slotProps={{ htmlInput: { min: 1, max: tripForm.duration || 480 } }}
                  value={tripForm.midTripReliefOffsetMinutes ?? ""}
                  onChange={e => setTripForm(f => ({
                    ...f,
                    midTripReliefOffsetMinutes: e.target.value === "" ? null : Number(e.target.value),
                  }))}
                  helperText="Quando dividir a viagem"
                />
              </Stack>

              {tripForm.midTripReliefPointId && !tripForm.midTripReliefOffsetMinutes && (
                <Alert severity="warning" sx={{ py: 0.5 }}>
                  Ponto intermediário definido, mas falta o offset. Optimizer ignorará split.
                </Alert>
              )}
            </Stack>

            {/* ── Depósito (multi-depot) ── opcional */}
            <Divider />
            <Stack spacing={1.5}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Depósito (opcional)
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Associar a viagem a um depósito específico ativa otimização multi-depot:
                veículos só servem viagens do mesmo depósito.
              </Typography>
              <TextField
                size="small"
                type="number"
                label="ID do Depósito"
                slotProps={{ htmlInput: { min: 1 } }}
                value={tripForm.depotId ?? ""}
                onChange={e => setTripForm(f => ({
                  ...f,
                  depotId: e.target.value === "" ? null : Number(e.target.value),
                }))}
                helperText="Deixe vazio para sem restrição de depósito"
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTripDialog(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleSaveTrip}>
            {editingTrip ? "Salvar" : tripForm.roundTrip ? "Criar IDA + VOLTA" : "Criar Viagem"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Dialog Motorista ── */}
      <Dialog open={driverDialog} onClose={() => { setDriverDialog(false); setDriverError(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>{editingDriver ? "Editar Motorista" : "Novo Motorista"}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {driverError && <Alert severity="error">{driverError}</Alert>}
            <Grid container spacing={2}>
              <Grid size={{ xs: 6 }}>
                <TextField fullWidth size="small" label="Cód. Motorista *"
                  helperText="Identificador único (matrícula)"
                  value={driverForm.driverId}
                  onChange={e => setDriverForm(f => ({ ...f, driverId: e.target.value }))} />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField fullWidth size="small" label="Nome Completo *"
                  value={driverForm.name}
                  onChange={e => setDriverForm(f => ({ ...f, name: e.target.value }))} />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Função</InputLabel>
                  <Select label="Função" value={driverForm.role ?? "Motorista"}
                    onChange={e => setDriverForm(f => ({ ...f, role: e.target.value }))}>
                    <MenuItem value="Motorista">Motorista</MenuItem>
                    <MenuItem value="Cobrador">Cobrador</MenuItem>
                    <MenuItem value="Motorista/Cobrador">Motorista/Cobrador</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField fullWidth size="small" label="Jornada Máx. (min)" type="number"
                  helperText="Ex: 480 = 8h"
                  value={driverForm.maxHoursPerDay ?? 480}
                  onChange={e => setDriverForm(f => ({ ...f, maxHoursPerDay: Number(e.target.value) }))} />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField fullWidth size="small" label="Fim Último Turno (min)" type="number"
                  helperText="0 = disponível desde meia-noite"
                  value={driverForm.lastShiftEnd ?? 0}
                  onChange={e => setDriverForm(f => ({ ...f, lastShiftEnd: Number(e.target.value) }))} />
              </Grid>
            </Grid>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDriverDialog(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleSaveDriver}>{editingDriver ? "Salvar" : "Criar"}</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={notification.open} autoHideDuration={6000} onClose={() => setNotification(n => ({ ...n, open: false }))}>
        <Alert severity={notification.severity} sx={{ width: "100%" }}>{notification.message}</Alert>
      </Snackbar>
    </Box>
  );
}
