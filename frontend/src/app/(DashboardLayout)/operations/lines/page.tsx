'use client';
import React, { useEffect, useState, useCallback } from 'react';
import {
  Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, Snackbar, Alert, Stack, TextField, Tooltip, Switch,
  FormControlLabel, FormControl, InputLabel, Select, MenuItem, Divider, Typography, Grid,
} from '@mui/material';
import { type GridColDef, type GridRenderCellParams } from '@mui/x-data-grid';
import AppDataGrid from '@/components/AppDataGrid';
import { IconEdit, IconPlus, IconRefresh, IconTrash, IconRoute, IconBusStop, IconCarGarage } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { linesApi, terminalsApi } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────────────
interface Terminal { id: number; terminalId: string; name: string; }

interface Line {
  id: number;
  lineId: string;
  name: string;
  description?: string;
  isActive: boolean;
  originTerminalId?: number;
  destinationTerminalId?: number;
  distanceKm?: number;
  returnDistanceKm?: number;
  avgTripDurationMinutes?: number;
  avgReturnDurationMinutes?: number;
  garageTerminalId?: number;
  garageDistanceKm?: number;
  solturaMinutes?: number;
  recolhimentoDistanceKm?: number;
  recolhimentoMinutes?: number;
}

interface FormState {
  lineId: string;
  name: string;
  description: string;
  isActive: boolean;
  // Terminais operacionais
  originTerminalId: number;
  destinationTerminalId: number;
  // IDA
  distanceKm: number;
  avgTripDurationMinutes: number;
  // VOLTA
  returnDistanceKm: number;
  avgReturnDurationMinutes: number;
  // Garagem / Soltura / Recolhimento
  garageTerminalId: number;
  garageDistanceKm: number;
  solturaMinutes: number;
  recolhimentoDistanceKm: number;
  recolhimentoMinutes: number;
}

const EMPTY: FormState = {
  lineId: '', name: '', description: '', isActive: true,
  originTerminalId: 0, destinationTerminalId: 0,
  distanceKm: 0, avgTripDurationMinutes: 0,
  returnDistanceKm: 0, avgReturnDurationMinutes: 0,
  garageTerminalId: 0, garageDistanceKm: 0, solturaMinutes: 0,
  recolhimentoDistanceKm: 0, recolhimentoMinutes: 0,
};

function terminalLabel(terminals: Terminal[], id?: number) {
  if (!id) return '—';
  const t = terminals.find(t => t.id === id);
  return t ? `${t.terminalId} — ${t.name}` : String(id);
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LinesPage() {
  const [rows, setRows] = useState<Line[]>([]);
  const [terminals, setTerminals] = useState<Terminal[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Line | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [notify, setNotify] = useState<{ msg: string; sev: 'success' | 'error' } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const set = (field: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [field]: e.target.value }));

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [linesData, terminalsData] = await Promise.all([linesApi.getAll(), terminalsApi.getAll()]);
      setRows(Array.isArray(linesData) ? linesData : []);
      setTerminals(Array.isArray(terminalsData) ? terminalsData : []);
    } catch { setRows([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const rowToForm = (row: Line): FormState => ({
    lineId: row.lineId ?? '',
    name: row.name ?? '',
    description: row.description ?? '',
    isActive: row.isActive ?? true,
    originTerminalId: row.originTerminalId ?? 0,
    destinationTerminalId: row.destinationTerminalId ?? 0,
    distanceKm: row.distanceKm ?? 0,
    avgTripDurationMinutes: row.avgTripDurationMinutes ?? 0,
    returnDistanceKm: row.returnDistanceKm ?? 0,
    avgReturnDurationMinutes: row.avgReturnDurationMinutes ?? 0,
    garageTerminalId: row.garageTerminalId ?? 0,
    garageDistanceKm: row.garageDistanceKm ?? 0,
    solturaMinutes: row.solturaMinutes ?? 0,
    recolhimentoDistanceKm: row.recolhimentoDistanceKm ?? 0,
    recolhimentoMinutes: row.recolhimentoMinutes ?? 0,
  });

  const openCreate = () => { setEditing(null); setForm(EMPTY); setFormError(null); setOpen(true); };
  const openEdit = (row: Line) => { setEditing(row); setForm(rowToForm(row)); setFormError(null); setOpen(true); };

  const handleSave = async () => {
    if (!form.lineId || !form.name) { setFormError('Código e Nome da Linha são obrigatórios.'); return; }
    setFormError(null);
    setSaving(true);
    try {
      const payload = {
        ...form,
        originTerminalId: form.originTerminalId || null,
        destinationTerminalId: form.destinationTerminalId || null,
        garageTerminalId: form.garageTerminalId || null,
        distanceKm: form.distanceKm || null,
        returnDistanceKm: form.returnDistanceKm || null,
        avgTripDurationMinutes: form.avgTripDurationMinutes || null,
        avgReturnDurationMinutes: form.avgReturnDurationMinutes || null,
        garageDistanceKm: form.garageDistanceKm || null,
        solturaMinutes: form.solturaMinutes || null,
        recolhimentoDistanceKm: form.recolhimentoDistanceKm || null,
        recolhimentoMinutes: form.recolhimentoMinutes || null,
      };
      editing ? await linesApi.update(editing.id, payload) : await linesApi.create(payload);
      setNotify({ msg: editing ? 'Linha atualizada!' : 'Linha criada!', sev: 'success' });
      setOpen(false); fetchData();
    } catch { setNotify({ msg: 'Erro ao salvar.', sev: 'error' }); } finally { setSaving(false); }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Excluir a linha "${name}"?`)) return;
    try { await linesApi.delete(id); setNotify({ msg: 'Linha excluída.', sev: 'success' }); fetchData(); }
    catch { setNotify({ msg: 'Não foi possível excluir.', sev: 'error' }); }
  };

  const TerminalSelect = ({ label, field, value }: { label: string; field: keyof FormState; value: number }) => (
    <FormControl fullWidth size="small">
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value}
        onChange={e => setForm(f => ({ ...f, [field]: Number(e.target.value) }))}>
        <MenuItem value={0}><em>— Não definido —</em></MenuItem>
        {terminals.map(t => <MenuItem key={t.id} value={t.id}>{t.terminalId} — {t.name}</MenuItem>)}
      </Select>
    </FormControl>
  );

  const columns: GridColDef<Line>[] = [
    { field: 'lineId', headerName: 'Código', width: 110 },
    { field: 'name', headerName: 'Nome', flex: 1 },
    {
      field: 'originTerminalId', headerName: 'Origem (IDA)', width: 160,
      renderCell: (p: GridRenderCellParams) => terminalLabel(terminals, p.value) || '—',
    },
    {
      field: 'destinationTerminalId', headerName: 'Destino (IDA)', width: 160,
      renderCell: (p: GridRenderCellParams) => terminalLabel(terminals, p.value) || '—',
    },
    { field: 'distanceKm', headerName: 'Km IDA', width: 90, renderCell: p => p.value ? `${p.value} km` : '—' },
    { field: 'solturaMinutes', headerName: 'Soltura (min)', width: 110, renderCell: p => p.value ? `${p.value} min` : '—' },
    { field: 'recolhimentoMinutes', headerName: 'Recolh. (min)', width: 110, renderCell: p => p.value ? `${p.value} min` : '—' },
    {
      field: 'isActive', headerName: 'Status', width: 90,
      renderCell: (p: GridRenderCellParams) => <Chip label={p.value ? 'Ativa' : 'Inativa'} color={p.value ? 'success' : 'default'} size="small" />,
    },
    {
      field: 'actions', headerName: 'Ações', width: 90, sortable: false,
      renderCell: (p: GridRenderCellParams<Line>) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar"><IconButton size="small" onClick={() => openEdit(p.row)}><IconEdit size={16} /></IconButton></Tooltip>
          <Tooltip title="Excluir"><IconButton size="small" color="error" onClick={() => handleDelete(p.row.id, p.row.name)}><IconTrash size={16} /></IconButton></Tooltip>
        </Stack>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Cadastro de Linhas"
        subtitle="Gerencie linhas operacionais — terminais, distâncias, soltura e recolhimento"
        action={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<IconRefresh size={16} />} onClick={fetchData} disabled={loading}>Atualizar</Button>
            <Button variant="contained" startIcon={<IconPlus size={16} />} onClick={openCreate}>Nova Linha</Button>
          </Stack>
        }
      >
        <Box sx={{ height: 520, mt: 1 }}>
          <AppDataGrid searchable rows={rows} columns={columns} loading={loading}
            pageSizeOptions={[10, 25, 50]} initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            disableRowSelectionOnClick localeText={{ noRowsLabel: 'Nenhuma linha cadastrada.' }} />
        </Box>
      </DashboardCard>

      {/* ── Dialog ── */}
      <Dialog open={open} onClose={() => { setOpen(false); setFormError(null); }} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconRoute size={20} /> {editing ? `Editar: ${editing.name}` : 'Nova Linha'}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3} sx={{ mt: 1 }}>
            {formError && <Alert severity="error" variant="filled">{formError}</Alert>}

            {/* ── Identificação ── */}
            <Grid container spacing={2}>
              <Grid size={{ xs: 4 }}>
                <TextField label="Código *" size="small" fullWidth value={form.lineId}
                  onChange={set('lineId')} helperText="Ex: 101-A, BRT-5, L-007" />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Nome da Linha *" size="small" fullWidth value={form.name} onChange={set('name')} />
              </Grid>
              <Grid size={{ xs: 2 }} sx={{ display: 'flex', alignItems: 'center' }}>
                <FormControlLabel control={<Switch checked={form.isActive} onChange={e => setForm(f => ({ ...f, isActive: e.target.checked }))} />} label="Ativa" />
              </Grid>
              <Grid size={{ xs: 12 }}>
                <TextField label="Descrição" size="small" fullWidth multiline rows={2}
                  value={form.description} onChange={set('description')} />
              </Grid>
            </Grid>

            <Divider>
              <Chip icon={<IconBusStop size={14} />} label="Sentido IDA" size="small" color="primary" />
            </Divider>

            {/* ── IDA ── */}
            <Grid container spacing={2}>
              <Grid size={{ xs: 6 }}>
                <TerminalSelect label="Terminal Origem (IDA)" field="originTerminalId" value={form.originTerminalId} />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TerminalSelect label="Terminal Destino (IDA)" field="destinationTerminalId" value={form.destinationTerminalId} />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Distância IDA (km)" size="small" fullWidth type="number"
                  value={form.distanceKm || ''} onChange={e => setForm(f => ({ ...f, distanceKm: Number(e.target.value) }))} />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Duração média IDA (min)" size="small" fullWidth type="number"
                  value={form.avgTripDurationMinutes || ''} onChange={e => setForm(f => ({ ...f, avgTripDurationMinutes: Number(e.target.value) }))} />
              </Grid>
            </Grid>

            <Divider>
              <Chip icon={<IconBusStop size={14} />} label="Sentido VOLTA (Origem↔Destino invertidos)" size="small" color="secondary" />
            </Divider>

            {/* ── VOLTA ── */}
            <Grid container spacing={2}>
              <Grid size={{ xs: 6 }}>
                <TextField label="Distância VOLTA (km)" size="small" fullWidth type="number"
                  value={form.returnDistanceKm || ''} onChange={e => setForm(f => ({ ...f, returnDistanceKm: Number(e.target.value) }))}
                  helperText="Deixe 0 para usar a mesma distância IDA" />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Duração média VOLTA (min)" size="small" fullWidth type="number"
                  value={form.avgReturnDurationMinutes || ''} onChange={e => setForm(f => ({ ...f, avgReturnDurationMinutes: Number(e.target.value) }))}
                  helperText="Deixe 0 para usar a mesma duração IDA" />
              </Grid>
            </Grid>

            <Divider>
              <Chip icon={<IconCarGarage size={14} />} label="Garagem — Soltura e Recolhimento" size="small" color="warning" />
            </Divider>

            {/* ── Garagem ── */}
            <Grid container spacing={2}>
              <Grid size={{ xs: 12 }}>
                <TerminalSelect label="Terminal da Garagem" field="garageTerminalId" value={form.garageTerminalId} />
              </Grid>

              {/* Soltura: garagem → primeiro terminal */}
              <Grid size={{ xs: 12 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: 'block', mb: 0.5 }}>
                  Soltura — Garagem → Primeiro terminal da linha
                </Typography>
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Distância Soltura (km)" size="small" fullWidth type="number"
                  value={form.garageDistanceKm || ''} onChange={e => setForm(f => ({ ...f, garageDistanceKm: Number(e.target.value) }))}
                  helperText="Km da garagem até o primeiro terminal" />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Duração Soltura (min)" size="small" fullWidth type="number"
                  value={form.solturaMinutes || ''} onChange={e => setForm(f => ({ ...f, solturaMinutes: Number(e.target.value) }))}
                  helperText="Minutos da garagem até o primeiro terminal" />
              </Grid>

              {/* Recolhimento: último terminal → garagem */}
              <Grid size={{ xs: 12 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: 'block', mb: 0.5 }}>
                  Recolhimento — Último terminal → Garagem
                </Typography>
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Distância Recolhimento (km)" size="small" fullWidth type="number"
                  value={form.recolhimentoDistanceKm || ''} onChange={e => setForm(f => ({ ...f, recolhimentoDistanceKm: Number(e.target.value) }))}
                  helperText="Km do último terminal até a garagem" />
              </Grid>
              <Grid size={{ xs: 6 }}>
                <TextField label="Duração Recolhimento (min)" size="small" fullWidth type="number"
                  value={form.recolhimentoMinutes || ''} onChange={e => setForm(f => ({ ...f, recolhimentoMinutes: Number(e.target.value) }))}
                  helperText="Minutos do último terminal até a garagem" />
              </Grid>
            </Grid>

          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? 'Salvando...' : editing ? 'Atualizar' : 'Criar Linha'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!notify} autoHideDuration={4000} onClose={() => setNotify(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity={notify?.sev} onClose={() => setNotify(null)}>{notify?.msg}</Alert>
      </Snackbar>
    </Box>
  );
}
