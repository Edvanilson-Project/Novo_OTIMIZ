'use client';
import React from 'react';
import { Box, Chip, Typography, Stack, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Alert } from '@mui/material';
import { IconShieldCheck, IconShieldX, IconShieldHalf } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { useAuth } from '@/app/hooks/useAuth';

const roles = [
  { key: 'super_admin', label: 'Super Admin', color: 'error' as const, desc: 'Acesso total ao sistema e todas as empresas' },
  { key: 'company_admin', label: 'Admin da Empresa', color: 'warning' as const, desc: 'Gerencia usuários e dados da sua empresa' },
  { key: 'analyst', label: 'Analista', color: 'info' as const, desc: 'Executa otimizações e analisa resultados' },
  { key: 'operator', label: 'Operador', color: 'default' as const, desc: 'Visualiza dados e relatórios' },
];

type Permission = 'full' | 'partial' | 'read' | 'none';

const matrix: { module: string; permissions: Record<string, Permission> }[] = [
  { module: 'Dashboard', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'read' } },
  { module: 'Ingestão de Dados (Viagens)', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'read' } },
  { module: 'Ingestão de Dados (Motoristas)', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'none' } },
  { module: 'Cadastro de Linhas', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'read', operator: 'read' } },
  { module: 'Cadastro de Terminais', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'read', operator: 'read' } },
  { module: 'Gantt Planner — Visualização', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'read' } },
  { module: 'Gantt Planner — Otimização', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'none' } },
  { module: 'Gantt Planner — Movimentos Manuais', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'partial', operator: 'none' } },
  { module: 'Copiloto IA de Custos', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'none' } },
  { module: 'Regras Dinâmicas de Custo', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'partial', operator: 'none' } },
  { module: 'Parâmetros CCT', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'read', operator: 'read' } },
  { module: 'Cadastro de Empresas', permissions: { super_admin: 'full', company_admin: 'none', analyst: 'none', operator: 'none' } },
  { module: 'Cadastro de Usuários', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'none', operator: 'none' } },
  { module: 'Controle de Acesso', permissions: { super_admin: 'full', company_admin: 'read', analyst: 'none', operator: 'none' } },
  { module: 'Ajustes do Sistema', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'partial', operator: 'none' } },
  { module: 'Relatórios e KPIs', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'full', operator: 'read' } },
  { module: 'Audit Log', permissions: { super_admin: 'full', company_admin: 'full', analyst: 'none', operator: 'none' } },
];

function PermIcon({ perm }: { perm: Permission }) {
  if (perm === 'full') return <IconShieldCheck size={18} color="#2e7d32" />;
  if (perm === 'partial') return <IconShieldHalf size={18} color="#e65100" />;
  if (perm === 'read') return <IconShieldHalf size={18} color="#0277bd" />;
  return <IconShieldX size={18} color="#c62828" />;
}

function PermLabel({ perm }: { perm: Permission }) {
  const map = { full: 'Completo', partial: 'Parcial', read: 'Leitura', none: '—' };
  const colors = { full: 'success', partial: 'warning', read: 'info', none: 'default' } as const;
  return <Chip icon={<PermIcon perm={perm} />} label={map[perm]} color={colors[perm]} size="small" variant="outlined" />;
}

export default function AccessControlPage() {
  const { checked, user } = useAuth('company_admin');
  if (!checked) return null;

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard title="Controle de Acesso" subtitle="Matriz de permissões por perfil de usuário no sistema OTIMIZ">
        <Stack spacing={3}>
          <Alert severity="info">
            Permissões são aplicadas automaticamente no frontend (sidebar) e backend (API). O <strong>Super Admin</strong> sempre ignora qualquer restrição de role.
          </Alert>

          {/* Cards de roles */}
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 2 }}>
            {roles.map(r => (
              <Paper key={r.key} variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
                  <Chip label={r.label} color={r.color} size="small" />
                </Stack>
                <Typography variant="body2" color="text.secondary">{r.desc}</Typography>
              </Paper>
            ))}
          </Box>

          {/* Legenda */}
          <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}><IconShieldCheck size={16} color="#2e7d32" /><Typography variant="caption">Completo — criar, editar, excluir</Typography></Stack>
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}><IconShieldHalf size={16} color="#e65100" /><Typography variant="caption">Parcial — ações limitadas</Typography></Stack>
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}><IconShieldHalf size={16} color="#0277bd" /><Typography variant="caption">Leitura — somente visualizar</Typography></Stack>
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}><IconShieldX size={16} color="#c62828" /><Typography variant="caption">Sem acesso</Typography></Stack>
          </Stack>

          {/* Matriz */}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow sx={{ '& th': { fontWeight: 700, backgroundColor: 'background.default' } }}>
                  <TableCell>Módulo / Funcionalidade</TableCell>
                  {roles.map(r => <TableCell key={r.key} align="center"><Chip label={r.label} color={r.color} size="small" /></TableCell>)}
                </TableRow>
              </TableHead>
              <TableBody>
                {matrix.map((row, i) => (
                  <TableRow key={i} sx={{ '&:hover': { backgroundColor: 'action.hover' } }}>
                    <TableCell><Typography variant="body2">{row.module}</Typography></TableCell>
                    {roles.map(r => (
                      <TableCell key={r.key} align="center"><PermLabel perm={row.permissions[r.key]} /></TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {user && (
            <Alert severity="success">
              Você está logado como <strong>{user.name}</strong> com perfil <strong>{user.role}</strong>.
            </Alert>
          )}
        </Stack>
      </DashboardCard>
    </Box>
  );
}
