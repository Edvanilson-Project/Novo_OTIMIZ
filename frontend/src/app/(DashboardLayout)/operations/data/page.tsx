"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  Box, Stack, Button, Alert, Snackbar, CircularProgress, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton, Tooltip, MenuItem,
  Select, FormControl, InputLabel, Chip,
} from "@mui/material";
import { DataGrid, GridColDef, GridRenderCellParams, GridSortModel } from "@mui/x-data-grid";
import { ptBR } from "@mui/x-data-grid/locales";
import { IconUpload, IconEdit, IconTrash, IconRefresh } from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import ParentCard from "@/app/components/shared/ParentCard";
import { operationsApi, linesApi, terminalsApi } from "@/lib/api";
import { minToHHMM } from "@/lib/format";

interface Trip {
  id: number;
  tripId: number;
  lineCode?: string;
  startTime: number;
  endTime: number;
  duration: number;
  originId: number;
  destinationId: number;
  distanceKm: number;
  direction?: string;
}

interface Line {
  id: number;
  lineId: string;
  name: string;
  isActive: boolean;
}

interface Terminal {
  id: number;
  terminalId: string;
  name: string;
}

interface TripFormState {
  lineCode: string;
  startTime: string;
  endTime: string;
  duration: number;
  originId: number;
  destinationId: number;
  distanceKm: number;
  direction: string;
}

const EMPTY_TRIP: TripFormState = {
  lineCode: "",
  startTime: "06:00",
  endTime: "14:00",
  duration: 0,
  originId: 0,
  destinationId: 0,
  distanceKm: 0,
  direction: "IDA",
};

function hhmmToMin(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

function normalizeLegWindow(startTime: string, endTime: string) {
  const s = hhmmToMin(startTime);
  let e = hhmmToMin(endTime);
  while (e < s) e += 1440;
  return { startTime: s, endTime: e, duration: e - s };
}

function toHHMM(min: number): string {
  const h = Math.floor(min / 60).toString().padStart(2, "0");
  const m = (min % 60).toString().padStart(2, "0");
  return `${h}:${m}`;
}

export default function OperationsDataPage() {
  const [loading, setLoading] = useState(false);
  const [sortModel, setSortModel] = useState<GridSortModel>([]);
  const [uploading, setUploading] = useState(false);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [terminals, setTerminals] = useState<Terminal[]>([]);
  const [notification, setNotification] = useState({
    open: false,
    message: "",
    severity: "success" as "success" | "error" | "info" | "warning",
  });

  const [tripDialog, setTripDialog] = useState(false);
  const [editingTrip, setEditingTrip] = useState<Trip | null>(null);
  const [tripForm, setTripForm] = useState<TripFormState>(EMPTY_TRIP);

  const notify = (msg: string, severity: "success" | "error" | "info" | "warning" = "success") =>
    setNotification({ open: true, message: msg, severity });

  const fetchReferenceData = useCallback(async () => {
    try {
      const [linesData, terminalsData] = await Promise.all([
        linesApi.getAll(),
        terminalsApi.getAll(),
      ]);
      setLines(Array.isArray(linesData) ? linesData.filter((l: Line) => l.isActive) : []);
      setTerminals(Array.isArray(terminalsData) ? terminalsData : []);
    } catch {
      //
    }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await operationsApi.getTrips({ limit: 500 });
      setTrips(Array.isArray(data) ? data : (data as { data?: unknown[] }).data ?? []);
    } catch {
      notify("Erro ao carregar viagens.", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReferenceData();
  }, [fetchReferenceData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", "trips");
    try {
      const result = await operationsApi.upload(formData);
      const r = result as { inserted?: number; skipped?: number };
      const msg =
        r?.inserted !== undefined
          ? `Importados: ${r.inserted} registros${r.skipped ? `, ignorados: ${r.skipped}` : ""}`
          : "Upload concluído!";
      notify(msg);
      setSortModel([{ field: "tripId", sort: "desc" }]);
      fetchData();
    } catch (error: unknown) {
      const errData = (
        error as { response?: { data?: { errors?: string[]; message?: string } } }
      )?.response?.data;
      const msg =
        errData?.errors?.slice(0, 3).join(" | ") ?? errData?.message ?? "Erro no upload.";
      notify(msg, "error");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const openEditTrip = (row: Trip) => {
    setEditingTrip(row);
    setTripForm({
      lineCode: row.lineCode ?? "",
      startTime: toHHMM(row.startTime),
      endTime: toHHMM(row.endTime),
      duration: row.duration,
      originId: row.originId,
      destinationId: row.destinationId,
      distanceKm: row.distanceKm,
      direction: row.direction ?? "IDA",
    });
    setTripDialog(true);
  };

  const handleSaveTrip = async () => {
    const HHMM = /^([0-9]+):([0-5][0-9])$/;
    const parseHHMM = (s: string): number | null => {
      const m = HHMM.exec(s.trim());
      if (!m) return null;
      const h = Number(m[1]);
      const min = Number(m[2]);
      if (h < 0) return null;
      return h * 60 + min;
    };

    if (!tripForm.startTime || !tripForm.endTime) {
      notify("Início e fim são obrigatórios.", "error");
      return;
    }

    const sm = parseHHMM(tripForm.startTime);
    const em = parseHHMM(tripForm.endTime);
    if (sm === null || em === null) {
      notify("Horários inválidos. Use formato HH:MM.", "error");
      return;
    }

    let adjustedEnd = em;
    while (adjustedEnd < sm) adjustedEnd += 1440;
    const dur = adjustedEnd - sm;

    if (dur <= 0) {
      notify("Fim deve ser depois do início.", "error");
      return;
    }
    if (dur > 480) {
      notify("Duração > 8h. Verifique se está correto.", "error");
      return;
    }
    if (tripForm.originId === tripForm.destinationId) {
      notify("Origem e destino não podem ser iguais.", "error");
      return;
    }
    if (!tripForm.distanceKm || tripForm.distanceKm <= 0) {
      notify("Distância (km) deve ser > 0.", "error");
      return;
    }

    try {
      const window = normalizeLegWindow(tripForm.startTime, tripForm.endTime);
      const payload: Record<string, unknown> = {
        lineCode: tripForm.lineCode || undefined,
        startTime: window.startTime,
        endTime: window.endTime,
        duration: tripForm.duration > 0 ? tripForm.duration : window.duration,
        originId: tripForm.originId,
        destinationId: tripForm.destinationId,
        distanceKm: tripForm.distanceKm,
        direction: tripForm.direction || "IDA",
      };

      if (editingTrip) {
        await operationsApi.updateTrip(editingTrip.id, payload);
        notify("Viagem atualizada!");
      }
      setTripDialog(false);
      fetchData();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      notify(err?.response?.data?.message ?? "Erro ao salvar viagem.", "error");
    }
  };

  const handleDeleteTrip = async (id: number) => {
    if (!confirm("Excluir esta viagem? Esta ação não pode ser desfeita.")) return;
    try {
      await operationsApi.deleteTrip(id);
      notify("Viagem excluída.");
      fetchData();
    } catch {
      notify("Erro ao excluir viagem.", "error");
    }
  };

  const terminalMap = useMemo(
    () => new Map(terminals.map(t => [t.id, t.name || t.terminalId])),
    [terminals]
  );

  const tripColumns: GridColDef[] = useMemo(() => [
    { field: "tripId", headerName: "Trip ID", width: 80 },
    {
      field: "lineCode",
      headerName: "Linha",
      width: 100,
      renderCell: (p) =>
        p.value ? <Chip label={p.value} size="small" variant="outlined" /> : "—",
    },
    {
      field: "direction",
      headerName: "Sentido",
      width: 80,
      renderCell: (p) =>
        p.value ? (
          <Chip
            label={p.value}
            size="small"
            color={p.value === "IDA" ? "primary" : "secondary"}
          />
        ) : (
          "—"
        ),
    },
    {
      field: "startTime",
      headerName: "Início",
      width: 80,
      renderCell: (p: GridRenderCellParams) => minToHHMM(p.value ?? 0),
    },
    {
      field: "endTime",
      headerName: "Fim",
      width: 80,
      renderCell: (p: GridRenderCellParams) => minToHHMM(p.value ?? 0),
    },
    { field: "duration", headerName: "Dur. (min)", width: 85 },
    {
      field: "originId",
      headerName: "Origem",
      width: 120,
      renderCell: (p) => terminalMap.get(p.value) || `Terminal ${p.value}`,
    },
    {
      field: "destinationId",
      headerName: "Destino",
      width: 120,
      renderCell: (p) => terminalMap.get(p.value) || `Terminal ${p.value}`,
    },
    { field: "distanceKm", headerName: "Km", width: 65 },
    {
      field: "_actions",
      headerName: "Ações",
      width: 100,
      sortable: false,
      renderCell: (p: GridRenderCellParams) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar">
            <IconButton size="small" onClick={() => openEditTrip(p.row)}>
              <IconEdit size={16} />
            </IconButton>
          </Tooltip>
          <Tooltip title="Excluir">
            <IconButton
              size="small"
              color="error"
              onClick={() => handleDeleteTrip(p.row.id)}
            >
              <IconTrash size={16} />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ], [terminalMap]);

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Gestão de Dados Operacionais"
        subtitle="Importe e gerencie viagens"
      >
        <Stack spacing={3}>
          {/* Header com botão de refresh e import */}
          <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between" }}>
            <Tooltip title="Atualizar lista">
              <span>
                <IconButton onClick={fetchData} disabled={loading}>
                  <IconRefresh size={20} />
                </IconButton>
              </span>
            </Tooltip>
            <Button
              variant="contained"
              component="label"
              startIcon={
                uploading ? (
                  <CircularProgress size={18} color="inherit" />
                ) : (
                  <IconUpload size={18} />
                )
              }
              disabled={uploading}
            >
              {uploading ? "Processando..." : "Importar Viagens (CSV)"}
              <input
                type="file"
                hidden
                accept=".xlsx,.csv"
                onChange={handleFileUpload}
              />
            </Button>
          </Stack>

          {/* Grid */}
          <ParentCard title={`Viagens Carregadas (${trips.length})`}>
            <Box sx={{ height: 600, width: "100%", mt: 2 }}>
              <DataGrid
                rows={trips}
                columns={tripColumns}
                loading={loading}
                pageSizeOptions={[25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                sortModel={sortModel}
                onSortModelChange={setSortModel}
                disableRowSelectionOnClick
                localeText={ptBR.components.MuiDataGrid.defaultProps.localeText}
                sx={{ border: 0, "& .MuiDataGrid-columnHeaders": { backgroundColor: "action.hover" } }}
              />
            </Box>
          </ParentCard>
        </Stack>
      </DashboardCard>

      {/* Dialog de edição */}
      <Dialog open={tripDialog} onClose={() => setTripDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingTrip ? "Editar Viagem" : "Nova Viagem"}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Linha</InputLabel>
              <Select
                label="Linha"
                value={tripForm.lineCode}
                onChange={(e) => setTripForm((f) => ({ ...f, lineCode: e.target.value }))}
              >
                <MenuItem value="">— Sem linha —</MenuItem>
                {lines.map((l) => (
                  <MenuItem key={l.id} value={l.lineId}>
                    {l.lineId} — {l.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              fullWidth
              size="small"
              label="Início (HH:MM, ex: 06:00)"
              type="text"
              placeholder="HH:MM"
              value={tripForm.startTime}
              onChange={(e) =>
                setTripForm((f) => ({ ...f, startTime: e.target.value }))
              }
            />

            <TextField
              fullWidth
              size="small"
              label="Fim (HH:MM, ex: 14:00)"
              type="text"
              placeholder="HH:MM"
              value={tripForm.endTime}
              onChange={(e) => setTripForm((f) => ({ ...f, endTime: e.target.value }))}
            />

            <TextField
              fullWidth
              size="small"
              label="Duração (min)"
              type="number"
              value={tripForm.duration}
              onChange={(e) =>
                setTripForm((f) => ({ ...f, duration: Number(e.target.value) }))
              }
              helperText="Auto-calculada ao atualizar horários"
            />

            <TextField
              fullWidth
              size="small"
              label="Distância (km)"
              type="number"
              value={tripForm.distanceKm}
              onChange={(e) =>
                setTripForm((f) => ({ ...f, distanceKm: Number(e.target.value) }))
              }
            />

            <FormControl fullWidth size="small">
              <InputLabel>Origem</InputLabel>
              <Select
                label="Origem"
                value={tripForm.originId}
                onChange={(e) =>
                  setTripForm((f) => ({ ...f, originId: Number(e.target.value) }))
                }
              >
                <MenuItem value={0}>— Selecione —</MenuItem>
                {terminals.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    {t.terminalId} — {t.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small">
              <InputLabel>Destino</InputLabel>
              <Select
                label="Destino"
                value={tripForm.destinationId}
                onChange={(e) =>
                  setTripForm((f) => ({ ...f, destinationId: Number(e.target.value) }))
                }
              >
                <MenuItem value={0}>— Selecione —</MenuItem>
                {terminals.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    {t.terminalId} — {t.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small">
              <InputLabel>Sentido</InputLabel>
              <Select
                label="Sentido"
                value={tripForm.direction}
                onChange={(e) =>
                  setTripForm((f) => ({ ...f, direction: e.target.value }))
                }
              >
                <MenuItem value="IDA">IDA</MenuItem>
                <MenuItem value="VOLTA">VOLTA</MenuItem>
                <MenuItem value="CIRCULAR">CIRCULAR</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTripDialog(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleSaveTrip}>
            Salvar
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={() => setNotification((n) => ({ ...n, open: false }))}
      >
        <Alert severity={notification.severity} variant="filled" sx={{ width: "100%" }}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
