'use client';
import React, { useEffect, useState, useCallback } from 'react';
import {
  Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, IconButton, Snackbar, Alert, Stack, Switch, TextField, Tooltip,
} from '@mui/material';
import { DataGrid, type GridColDef, type GridRenderCellParams } from '@mui/x-data-grid';
import { IconEdit, IconPlus, IconRefresh, IconTrash, IconMapPin } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { terminalsApi } from '@/lib/api';

interface Terminal { id: number; terminalId: string; name: string; city?: string; latitude?: number; longitude?: number; isDepot: boolean; }
type FormState = Omit<Terminal, 'id'>;
const EMPTY: FormState = { terminalId: '', name: '', city: '', latitude: undefined, longitude: undefined, isDepot: false };

export default function TerminalsPage() {
  const [rows, setRows] = useState<Terminal[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Terminal | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [notify, setNotify] = useState<{ msg: string; sev: 'success' | 'error' } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try { setRows(await terminalsApi.getAll()); } catch { setRows([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openCreate = () => { setEditing(null); setForm(EMPTY); setFormError(null); setOpen(true); };
  const openEdit = (row: Terminal) => {
    setEditing(row);
    setForm({ terminalId: row.terminalId, name: row.name, city: row.city ?? '', latitude: row.latitude, longitude: row.longitude, isDepot: row.isDepot ?? false });
    setFormError(null);
    setOpen(true);
  };

  const handleSave = async () => {
    if (!form.terminalId || !form.name) { setFormError('Código e Nome do Terminal são obrigatórios.'); return; }
    setFormError(null);
    setSaving(true);
    try {
      const payload = { ...form, latitude: form.latitude ? Number(form.latitude) : undefined, longitude: form.longitude ? Number(form.longitude) : undefined };
      editing ? await terminalsApi.update(editing.id, payload) : await terminalsApi.create(payload);
      setNotify({ msg: editing ? 'Terminal atualizado!' : 'Terminal criado!', sev: 'success' });
      setOpen(false); fetchData();
    } catch { setNotify({ msg: 'Erro ao salvar.', sev: 'error' }); } finally { setSaving(false); }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Excluir o terminal "${name}"?`)) return;
    try { await terminalsApi.delete(id); setNotify({ msg: 'Terminal excluído.', sev: 'success' }); fetchData(); }
    catch { setNotify({ msg: 'Não foi possível excluir.', sev: 'error' }); }
  };

  const columns: GridColDef<Terminal>[] = [
    { field: 'terminalId', headerName: 'Código', width: 120 },
    { field: 'name', headerName: 'Nome do Terminal', flex: 1.5 },
    { field: 'city', headerName: 'Cidade', flex: 1 },
    {
      field: 'isDepot', headerName: 'Tipo', width: 120,
      renderCell: (p: GridRenderCellParams<Terminal>) => (
        p.row.isDepot
          ? <Chip label="Garagem" color="primary" size="small" />
          : <Chip label="Terminal" variant="outlined" size="small" />
      ),
    },
    { field: 'latitude', headerName: 'Lat', width: 100 },
    { field: 'longitude', headerName: 'Lng', width: 100 },
    { field: 'actions', headerName: 'Ações', width: 100, sortable: false,
      renderCell: (p: GridRenderCellParams<Terminal>) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar"><IconButton size="small" onClick={() => openEdit(p.row)}><IconEdit size={16} /></IconButton></Tooltip>
          <Tooltip title="Excluir"><IconButton size="small" color="error" onClick={() => handleDelete(p.row.id, p.row.name)}><IconTrash size={16} /></IconButton></Tooltip>
        </Stack>
      ) },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard title="Cadastro de Terminais" subtitle="Gerencie os terminais e pontos de origem/destino das viagens"
        action={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<IconRefresh size={16} />} onClick={fetchData} disabled={loading}>Atualizar</Button>
            <Button variant="contained" startIcon={<IconPlus size={16} />} onClick={openCreate}>Novo Terminal</Button>
          </Stack>
        }>
        <Box sx={{ height: 520, mt: 1 }}>
          <DataGrid rows={rows} columns={columns} loading={loading} pageSizeOptions={[10, 25, 50]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }} disableRowSelectionOnClick
            localeText={{ noRowsLabel: 'Nenhum terminal cadastrado.' }} />
        </Box>
      </DashboardCard>

      <Dialog open={open} onClose={() => { setOpen(false); setFormError(null); }} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconMapPin size={20} /> {editing ? `Editar: ${editing.name}` : 'Novo Terminal'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            <TextField label="Código do Terminal *" size="small" fullWidth value={form.terminalId}
              onChange={e => setForm(f => ({ ...f, terminalId: e.target.value }))} helperText="Ex: TER-001, GARAGEM-SP" />
            <TextField label="Nome do Terminal *" size="small" fullWidth value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <TextField label="Cidade" size="small" fullWidth value={form.city ?? ''}
              onChange={e => setForm(f => ({ ...f, city: e.target.value }))} />
            <Stack direction="row" spacing={2}>
              <TextField label="Latitude" size="small" fullWidth type="number"
                value={form.latitude ?? ''} onChange={e => setForm(f => ({ ...f, latitude: e.target.value ? Number(e.target.value) : undefined }))} />
              <TextField label="Longitude" size="small" fullWidth type="number"
                value={form.longitude ?? ''} onChange={e => setForm(f => ({ ...f, longitude: e.target.value ? Number(e.target.value) : undefined }))} />
            </Stack>
            <Tooltip title="Garagens são usadas como pontos de origem/destino de veículos na otimização multi-depot">
              <FormControlLabel
                control={<Switch checked={form.isDepot} onChange={e => setForm(f => ({ ...f, isDepot: e.target.checked }))} />}
                label="É uma garagem/depósito de veículos"
              />
            </Tooltip>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>{saving ? 'Salvando...' : editing ? 'Atualizar' : 'Criar Terminal'}</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!notify} autoHideDuration={4000} onClose={() => setNotify(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity={notify?.sev} onClose={() => setNotify(null)}>{notify?.msg}</Alert>
      </Snackbar>
    </Box>
  );
}
