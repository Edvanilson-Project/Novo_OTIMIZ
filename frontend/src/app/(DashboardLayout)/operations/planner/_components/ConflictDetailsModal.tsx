'use client';
import React, { useMemo, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Stack, Box,
  Typography, Chip, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper, Alert, Divider,
  Menu, MenuItem,
} from '@mui/material';
import { IconAlertTriangle, IconX, IconBlockquote, IconDownload } from '@tabler/icons-react';
import type { OptimizationResultSummary } from '../../_types';
import { detectOperationalConflicts } from '../_helpers/operational-conflicts';
import { exportConflicts, downloadExport } from '../_helpers/export-conflicts';

export interface ConflictDetailsModalProps {
  res: OptimizationResultSummary;
  open: boolean;
  onClose: () => void;
}

/**
 * Modal expandido para visualizar detalhes de conflitos operacionais
 * Mostra: tipos de conflito, blocos afetados, mensagens detalhadas
 */
export function ConflictDetailsModal({ res, open, onClose }: ConflictDetailsModalProps) {
  const conflicts = useMemo(() => detectOperationalConflicts(res), [res]);
  const [exportAnchor, setExportAnchor] = useState<null | HTMLElement>(null);
  const [filterType, setFilterType] = useState<string | null>(null);

  const filteredConflicts = filterType 
    ? conflicts.filter(c => c.type === filterType)
    : conflicts;

  const getBadgeColor = (severity: 'error' | 'warning') => {
    return severity === 'error' ? 'error' : 'warning';
  };

  const conflictLabel: Record<string, string> = {
    'overlap': 'Sobreposição',
    'time-violation': 'Violação de Horário',
    'no-return': 'Sem Retorno à Garagem',
    'break-violation': 'Violação de Intervalo',
    'unrealistic': 'Intervalo Irrealista',
    'paired-orphan': 'Viagem Pareada Orphã',
    'layover-violation': 'Layover Irregular',
  };

  const getConflictLabel = (type: string) => conflictLabel[type] ?? type.replace(/-/g, ' ').toUpperCase();

  if (!open || (conflicts.length === 0 && open)) {
    if (!open) return null;
    return (
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 800 }}>
          <IconBlockquote size={20} />
          Análise de Conflitos
        </DialogTitle>
        <DialogContent>
          <Alert severity="success" sx={{ mt: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>Nenhum conflito operacional detectado ✓</Typography>
            <Typography variant="body2">A solução de otimização é viável e operacionalmente válida.</Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} variant="contained">Fechar</Button>
        </DialogActions>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontWeight: 800 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconAlertTriangle size={22} />
          Detalhes de Conflitos Operacionais ({conflicts.length})
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<IconDownload size={16} />}
            onClick={(e) => setExportAnchor(e.currentTarget)}
            sx={{ fontWeight: 700 }}
          >
            Exportar
          </Button>
          <Menu
            anchorEl={exportAnchor}
            open={Boolean(exportAnchor)}
            onClose={() => setExportAnchor(null)}
          >
            <MenuItem
              onClick={() => {
                downloadExport(exportConflicts(res, 'csv'));
                setExportAnchor(null);
              }}
            >
              💾 CSV
            </MenuItem>
            <MenuItem
              onClick={() => {
                downloadExport(exportConflicts(res, 'json'));
                setExportAnchor(null);
              }}
            >
              📋 JSON
            </MenuItem>
            <MenuItem
              onClick={() => {
                downloadExport(exportConflicts(res, 'html'));
                setExportAnchor(null);
              }}
            >
              🌐 HTML (Relatório)
            </MenuItem>
          </Menu>
          <Button onClick={onClose} size="small" variant="text">
          <IconX size={18} />
        </Button>
        </Box>
      </DialogTitle>

      <Divider />

      <DialogContent sx={{ pt: 2 }}>
        {/* Resumo por tipo */}
        <Stack spacing={1.5} sx={{ mb: 2.5 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Tipos de Conflito Detectados</Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {Array.from(new Set(conflicts.map(c => c.type))).map(type => {
              const count = conflicts.filter(c => c.type === type).length;
              const isFiltered = filterType === type;
              return (
                <Chip
                  key={type}
                  label={`${getConflictLabel(type)} (${count})`}
                  onClick={() => setFilterType(isFiltered ? null : type)}
                  variant={isFiltered ? 'filled' : 'outlined'}
                  color={conflicts.find(c => c.type === type)?.severity === 'error' ? 'error' : 'warning'}
                  size="small"
                  sx={{ cursor: 'pointer', fontWeight: 700 }}
                />
              );
            })}
          </Box>
        </Stack>

        <Divider sx={{ my: 2 }} />

        {/* Tabela de conflitos */}
        <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: 'action.hover' }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 800, width: '15%' }}>Bloco</TableCell>
                <TableCell sx={{ fontWeight: 800, width: '20%' }}>Tipo</TableCell>
                <TableCell sx={{ fontWeight: 800, width: '60%' }}>Mensagem</TableCell>
                <TableCell sx={{ fontWeight: 800, width: '5%', textAlign: 'center' }}>Sev.</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredConflicts.map((c, i) => (
                <TableRow key={i} hover sx={{ opacity: filterType ? (c.type === filterType ? 1 : 0.5) : 1 }}>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.875rem' }}>
                    {c.blockId ? `#${c.blockId}` : '—'}
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.875rem' }}>
                    <Chip
                      label={getConflictLabel(c.type)}
                      size="small"
                      variant="outlined"
                      sx={{ fontWeight: 700, fontSize: '0.7rem' }}
                    />
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.8rem' }}>
                    <Typography variant="body2">{c.message}</Typography>
                  </TableCell>
                  <TableCell sx={{ textAlign: 'center' }}>
                    <Chip
                      label={c.severity === 'error' ? 'ERR' : 'WRN'}
                      size="small"
                      color={getBadgeColor(c.severity)}
                      variant="filled"
                      sx={{ fontWeight: 800, fontSize: '0.65rem', height: 22 }}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Recomendações */}
        <Alert severity="info" sx={{ mt: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>Recomendações de Ação</Typography>
          <Stack component="ul" spacing={0.5} sx={{ mb: 0, pl: 1.5 }}>
            <Typography component="li" variant="body2">
              • Revise os blocos com erro (severidade ERR) antes de executar.
            </Typography>
            <Typography component="li" variant="body2">
              • Para avisos (WRN), considere ajustar parâmetros de otimização.
            </Typography>
            <Typography component="li" variant="body2">
              • Use as informações de rastreabilidade para identificar blocos problemáticos.
            </Typography>
          </Stack>
        </Alert>
      </DialogContent>

      <Divider sx={{ mt: 2 }} />

      <DialogActions sx={{ p: 2 }}>
        <Button onClick={() => setFilterType(null)} variant="text" size="small">
          Limpar Filtro
        </Button>
        <Button onClick={onClose} variant="contained" color="primary">
          Fechar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
