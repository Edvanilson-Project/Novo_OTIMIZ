'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Grid, IconButton, MenuItem, Select, Snackbar, Alert, Stack,
  TextField, Tooltip, InputLabel, FormControl, InputAdornment,
} from '@mui/material';
import { DataGrid, type GridColDef, type GridRenderCellParams } from '@mui/x-data-grid';
import {
  IconEdit, IconEye, IconEyeOff, IconPlus, IconRefresh, IconTrash, IconUser,
} from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { usersApi, companiesApi } from '@/lib/api';

// ─── Tipos ───────────────────────────────────────────────────────────────────
type UserRole = 'super_admin' | 'company_admin' | 'analyst' | 'operator';
type UserStatus = 'active' | 'inactive';

interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  companyId?: number;
  companyName?: string;
  lastLoginAt?: string;
}

interface Company { id: number; name: string; }

interface FormState {
  name: string;
  email: string;
  password: string;
  role: UserRole;
  status: UserStatus;
  companyId: string;
}

const EMPTY_FORM: FormState = {
  name: '', email: '', password: '', role: 'operator', status: 'active', companyId: '',
};

const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: 'Super Admin',
  company_admin: 'Admin da Empresa',
  analyst: 'Analista',
  operator: 'Operador',
};

const ROLE_COLORS: Record<UserRole, 'error' | 'warning' | 'info' | 'default'> = {
  super_admin: 'error',
  company_admin: 'warning',
  analyst: 'info',
  operator: 'default',
};

function fmtDate(iso?: string) {
  if (!iso) return '--';
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

// ─── Página ───────────────────────────────────────────────────────────────────
export default function UsersPage() {
  const [rows, setRows] = useState<User[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [showPwd, setShowPwd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notify, setNotify] = useState<{ msg: string; sev: 'success' | 'error' } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [usersData, companiesData] = await Promise.all([
        usersApi.getAll().catch(() => []),
        companiesApi.getAll().catch(() => []),
      ]);
      const usersList: User[] = Array.isArray(usersData) ? usersData : usersData.data ?? [];
      const companiesList: Company[] = Array.isArray(companiesData) ? companiesData : companiesData.data ?? [];
      const companyMap = new Map(companiesList.map((c: Company) => [c.id, c.name]));
      setRows(usersList.map((u: User) => ({ ...u, companyName: u.companyId ? companyMap.get(u.companyId) : undefined })));
      setCompanies(companiesList);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setShowPwd(false); setOpen(true); };
  const openEdit = (row: User) => {
    setEditing(row);
    setForm({ name: row.name, email: row.email, password: '', role: row.role, status: row.status, companyId: row.companyId?.toString() ?? '' });
    setShowPwd(false);
    setOpen(true);
  };

  const handleSave = async () => {
    if (!form.name || !form.email) { setNotify({ msg: 'Nome e E-mail são obrigatórios.', sev: 'error' }); return; }
    if (!editing && !form.password) { setNotify({ msg: 'Senha é obrigatória para novos usuários.', sev: 'error' }); return; }
    setSaving(true);
    try {
      const payload = {
        ...form,
        companyId: form.companyId ? Number(form.companyId) : undefined,
        ...(editing && !form.password ? { password: undefined } : {}),
      };
      if (editing) {
        await usersApi.update(editing.id, payload);
        setNotify({ msg: 'Usuário atualizado com sucesso!', sev: 'success' });
      } else {
        await usersApi.create(payload);
        setNotify({ msg: 'Usuário criado com sucesso!', sev: 'success' });
      }
      setOpen(false);
      fetchData();
    } catch {
      setNotify({ msg: 'Erro ao salvar. Verifique os dados.', sev: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Excluir o usuário "${name}"?`)) return;
    try {
      await usersApi.delete(id);
      setNotify({ msg: 'Usuário excluído.', sev: 'success' });
      fetchData();
    } catch {
      setNotify({ msg: 'Não foi possível excluir o usuário.', sev: 'error' });
    }
  };

  const columns: GridColDef<User>[] = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'name', headerName: 'Nome', flex: 1, minWidth: 160 },
    { field: 'email', headerName: 'E-mail', flex: 1.2, minWidth: 180 },
    {
      field: 'role', headerName: 'Nível de Acesso', width: 160,
      renderCell: (p: GridRenderCellParams) => (
        <Chip label={ROLE_LABELS[p.value as UserRole] ?? p.value} color={ROLE_COLORS[p.value as UserRole] ?? 'default'} size="small" />
      ),
    },
    { field: 'companyName', headerName: 'Empresa', flex: 1, minWidth: 140, valueFormatter: (v: string) => v ?? '--' },
    {
      field: 'status', headerName: 'Status', width: 100,
      renderCell: (p: GridRenderCellParams) => (
        <Chip label={p.value === 'active' ? 'Ativo' : 'Inativo'} color={p.value === 'active' ? 'success' : 'default'} size="small" />
      ),
    },
    { field: 'lastLoginAt', headerName: 'Último Acesso', width: 150, valueFormatter: fmtDate },
    {
      field: 'actions', headerName: 'Ações', width: 110, sortable: false,
      renderCell: (p: GridRenderCellParams<User>) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Editar usuário">
            <IconButton size="small" onClick={() => openEdit(p.row)}><IconEdit size={16} /></IconButton>
          </Tooltip>
          <Tooltip title="Excluir usuário">
            <IconButton size="small" color="error" onClick={() => handleDelete(p.row.id, p.row.name)}><IconTrash size={16} /></IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Cadastro de Usuários"
        subtitle="Gerencie os usuários e seus níveis de acesso ao sistema"
        action={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<IconRefresh size={16} />} onClick={fetchData} disabled={loading}>Atualizar</Button>
            <Button variant="contained" startIcon={<IconPlus size={16} />} onClick={openCreate}>Novo Usuário</Button>
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
              noRowsLabel: 'Nenhum usuário cadastrado.',
            }}
          />
        </Box>
      </DashboardCard>

      {/* ── Dialog: Criar / Editar ── */}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconUser size={20} />
          {editing ? `Editar: ${editing.name}` : 'Novo Usuário'}
        </DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title="Nome completo do usuário." arrow placement="top">
                <TextField label="Nome *" fullWidth size="small" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </Tooltip>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title="E-mail usado para login no sistema." arrow placement="top">
                <TextField label="E-mail *" type="email" fullWidth size="small" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
              </Tooltip>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title={editing ? 'Deixe em branco para manter a senha atual.' : 'Senha de acesso ao sistema. Mínimo 8 caracteres.'} arrow placement="top">
                <TextField
                  label={editing ? 'Nova Senha (opcional)' : 'Senha *'}
                  type={showPwd ? 'text' : 'password'}
                  fullWidth size="small"
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  slotProps={{
                    input: {
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton size="small" onClick={() => setShowPwd(v => !v)}>
                            {showPwd ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    },
                  }}
                />
              </Tooltip>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title="Nível de acesso: Admin gerencia a empresa, Analista vê relatórios, Operador usa o Gantt." arrow placement="top">
                <FormControl fullWidth size="small">
                  <InputLabel>Nível de Acesso</InputLabel>
                  <Select label="Nível de Acesso" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value as UserRole }))}>
                    {(Object.entries(ROLE_LABELS) as [UserRole, string][]).map(([v, l]) => (
                      <MenuItem key={v} value={v}>{l}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Tooltip>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title="Empresa à qual este usuário pertence." arrow placement="top">
                <FormControl fullWidth size="small">
                  <InputLabel>Empresa</InputLabel>
                  <Select label="Empresa" value={form.companyId} onChange={e => setForm(f => ({ ...f, companyId: e.target.value }))}>
                    <MenuItem value="">— Sem empresa —</MenuItem>
                    {companies.map(c => <MenuItem key={c.id} value={c.id.toString()}>{c.name}</MenuItem>)}
                  </Select>
                </FormControl>
              </Tooltip>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Tooltip title="Usuários inativos não conseguem fazer login." arrow placement="top">
                <FormControl fullWidth size="small">
                  <InputLabel>Status</InputLabel>
                  <Select label="Status" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value as UserStatus }))}>
                    <MenuItem value="active">Ativo</MenuItem>
                    <MenuItem value="inactive">Inativo</MenuItem>
                  </Select>
                </FormControl>
              </Tooltip>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setOpen(false)} disabled={saving}>Cancelar</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? 'Salvando...' : editing ? 'Salvar Alterações' : 'Criar Usuário'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={Boolean(notify)} autoHideDuration={4000} onClose={() => setNotify(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {notify ? <Alert severity={notify.sev} variant="filled" sx={{ fontWeight: 700 }}>{notify.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}
