'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/app/hooks/useAuth';
import {
  Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Grid, IconButton, MenuItem, Select, Snackbar, Alert, Stack,
  TextField, Tooltip, InputLabel, FormControl,
} from '@mui/material';
import { DataGrid, type GridColDef, type GridRenderCellParams } from '@mui/x-data-grid';
import {
  IconBuilding, IconEdit, IconPlus, IconTrash, IconRefresh,
} from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { companiesApi } from '@/lib/api';

// ─── Tipos ───────────────────────────────────────────────────────────────────
interface Company {
  id: number;
  name: string;
  tradeName?: string;
  cnpj: string;
  status: 'active' | 'inactive';
  address?: string;
  city?: string;
  state?: string;
  phone?: string;
}

type FormState = Omit<Company, 'id'>;

const EMPTY_FORM: FormState = {
  name: '',
  tradeName: '',
  cnpj: '',
  status: 'active',
  address: '',
  city: '',
  state: '',
  phone: '',
};

// ─── Formatadores ─────────────────────────────────────────────────────────────
function fmtCnpj(v: string | null | undefined) {
  if (!v) return '';
  const d = v.replace(/\D/g, '').slice(0, 14);
  return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
}

// ─── Página ───────────────────────────────────────────────────────────────────
export default function CompaniesPage() {
  const { checked } = useAuth('super_admin');
  const [rows, setRows] = useState<Company[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [notify, setNotify] = useState<{ msg: string; sev: 'success' | 'error' } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await companiesApi.getAll();
      const raw = Array.isArray(data) ? data : data.data ?? [];
      setRows(raw.map((c: Company & { isActive?: boolean }) => ({ ...c, status: c.isActive ? 'active' : 'inactive' })));
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setOpen(true); };
  const openEdit = (row: Company) => { setEditing(row); setForm({ name: row.name, tradeName: row.tradeName ?? '', cnpj: row.cnpj, status: row.status, address: row.address ?? '', city: row.city ?? '', state: row.state ?? '', phone: row.phone ?? '' }); setOpen(true); };

  const handleSave = async () => {
    if (!form.name || !form.cnpj) {
      setNotify({ msg: 'Razão Social e CNPJ são obrigatórios.', sev: 'error' });
      return;
    }
    setSaving(true);
    try {
      const payload = { ...form, isActive: form.status === 'active' };
      if (editing) {
        await companiesApi.update(editing.id, payload);
        setNotify({ msg: 'Empresa atualizada com sucesso!', sev: 'success' });
      } else {
        await companiesApi.create(payload);
        setNotify({ msg: 'Empresa criada com sucesso!', sev: 'success' });
      }
      setOpen(false);
      fetchData();
    } catch {
      setNotify({ msg: 'Erro ao salvar. Verifique os dados e tente novamente.', sev: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Excluir a empresa "${name}"? Esta ação não pode ser desfeita.`)) return;
    try {
      await companiesApi.delete(id);
      setNotify({ msg: 'Empresa excluída.', sev: 'success' });
      fetchData();
    } catch {
      setNotify({ msg: 'Não foi possível excluir. A empresa pode ter dados vinculados.', sev: 'error' });
    }
  };

  const columns: GridColDef<Company>[] = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'name', headerName: 'Razão Social', flex: 1.5, minWidth: 180 },
    { field: 'tradeName', headerName: 'Nome Fantasia', flex: 1, minWidth: 140 },
    { field: 'cnpj', headerName: 'CNPJ', width: 160, valueFormatter: (v: string) => fmtCnpj(v) },
    { field: 'city', headerName: 'Cidade', width: 120 },
    { field: 'state', headerName: 'UF', width: 70 },
    {
      field: 'status', headerName: 'Status', width: 100,
      renderCell: (p: GridRenderCellParams) => (
        <Chip label={p.value === 'active' ? 'Ativo' : 'Inativo'} color={p.value === 'active' ? 'success' : 'default'} size="small" />
      ),
    },
    {
      field: 'actions', headerName: 'Ações', width: 110, sortable: false,
      renderCell: (p: GridRenderCellParams<Company>) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar empresa">
            <IconButton size="small" onClick={() => openEdit(p.row)}><IconEdit size={16} /></IconButton>
          </Tooltip>
          <Tooltip title="Excluir empresa">
            <IconButton size="small" color="error" onClick={() => handleDelete(p.row.id, p.row.name)}><IconTrash size={16} /></IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  const field = (key: keyof FormState, label: string, tip: string, props?: object) => (
    <Tooltip title={tip} arrow placement="top">
      <TextField
        label={label}
        fullWidth size="small"
        value={(form[key] as string) ?? ''}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        {...props}
      />
    </Tooltip>
  );

  if (!checked) return null;

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Cadastro de Empresas"
        subtitle="Gerencie as empresas de transporte cadastradas no sistema"
        action={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<IconRefresh size={16} />} onClick={fetchData} disabled={loading}>
              Atualizar
            </Button>
            <Button variant="contained" startIcon={<IconPlus size={16} />} onClick={openCreate}>
              Nova Empresa
            </Button>
          </Stack>
        }
      >
        <Box sx={{ height: 520, width: '100%', mt: 1 }}>
          <DataGrid
            rows={rows}
            columns={columns}
            loading={loading}
            pageSizeOptions={[10, 25, 50]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            disableRowSelectionOnClick
            localeText={{
              noRowsLabel: 'Nenhuma empresa cadastrada.',
            }}
          />
        </Box>
      </DashboardCard>

      {/* ── Dialog: Criar / Editar ── */}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconBuilding size={20} />
          {editing ? `Editar: ${editing.name}` : 'Nova Empresa'}
        </DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={{ xs: 12 }}>
              {field('name', 'Razão Social *', 'Nome jurídico completo da empresa conforme CNPJ.')}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field('tradeName', 'Nome Fantasia', 'Nome comercial pelo qual a empresa é conhecida.')}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field('cnpj', 'CNPJ *', 'Cadastro Nacional da Pessoa Jurídica (14 dígitos).', { placeholder: '00.000.000/0001-00' })}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field('phone', 'Telefone', 'Telefone de contato principal da empresa.')}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title="Define se a empresa está operando ativamente no sistema." arrow placement="top">
                <FormControl fullWidth size="small">
                  <InputLabel>Status</InputLabel>
                  <Select label="Status" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value as 'active' | 'inactive' }))}>
                    <MenuItem value="active">Ativo</MenuItem>
                    <MenuItem value="inactive">Inativo</MenuItem>
                  </Select>
                </FormControl>
              </Tooltip>
            </Grid>
            <Grid size={{ xs: 12 }}>
              {field('address', 'Endereço da Garagem', 'Endereço completo onde os veículos são guardados (Pull-in / Pull-out).')}
            </Grid>
            <Grid size={{ xs: 12, sm: 8 }}>
              {field('city', 'Cidade', 'Município onde a garagem está localizada.')}
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              {field('state', 'UF', 'Sigla do estado (ex: SP, RJ, MG).', { slotProps: { htmlInput: { maxLength: 2 } } })}
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setOpen(false)} disabled={saving}>Cancelar</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? 'Salvando...' : editing ? 'Salvar Alterações' : 'Criar Empresa'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Notificações ── */}
      <Snackbar open={Boolean(notify)} autoHideDuration={4000} onClose={() => setNotify(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {notify ? <Alert severity={notify.sev} variant="filled" sx={{ fontWeight: 700 }}>{notify.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}
