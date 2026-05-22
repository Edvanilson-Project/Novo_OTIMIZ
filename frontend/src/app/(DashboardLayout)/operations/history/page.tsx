'use client';
import React, { useEffect, useState, useCallback } from 'react';
import {
  Box, CircularProgress, Chip, Pagination, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip,
  Typography,
} from '@mui/material';
import { IconRefresh } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { operationsApi } from '@/lib/api';

interface ScheduleItem {
  id: number;
  status: string;
  referenceDate: string;
  createdAt: string;
  totalCost: number | null;
  cctViolations: number;
  vehicles: number | null;
  crew: number | null;
  algorithm: string | null;
  elapsedMs: number | null;
}

interface HistoryResponse {
  items: ScheduleItem[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export default function ScheduleHistoryPage() {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const days = 30;
  const limit = 50;
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await operationsApi.getScheduleHistory({
        days,
        page,
        limit,
      });
      setData(result);
    } catch {
      setError('Erro ao carregar histórico de escalas.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, page, limit]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, newPage: number) => {
    setPage(newPage);
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed': return 'success';
      case 'processing': return 'warning';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const statusLabel = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed': return 'Concluída';
      case 'processing': return 'Processando';
      case 'failed': return 'Falhou';
      default: return status;
    }
  };

  return (
    <DashboardCard title="Histórico de Escalas" action={<Tooltip title="Atualizar"><IconRefresh size={20} cursor="pointer" onClick={fetchData} /></Tooltip>}>
      <Box sx={{ width: '100%' }}>
        {error && (
          <Box sx={{ p: 2, mb: 2, bgcolor: '#ffebee', borderRadius: 1 }}>
            <Typography color="error">{error}</Typography>
          </Box>
        )}

        {loading && !data ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        ) : data && data.items.length > 0 ? (
          <>
            <TableContainer component={Paper} sx={{ mb: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#f5f5f5' }}>
                    <TableCell><strong>ID</strong></TableCell>
                    <TableCell><strong>Data de Criação</strong></TableCell>
                    <TableCell><strong>Data Ref.</strong></TableCell>
                    <TableCell align="center"><strong>Status</strong></TableCell>
                    <TableCell align="right"><strong>Veículos</strong></TableCell>
                    <TableCell align="right"><strong>Tripulação</strong></TableCell>
                    <TableCell align="right"><strong>Custo (R$)</strong></TableCell>
                    <TableCell align="right"><strong>Violações CCT</strong></TableCell>
                    <TableCell><strong>Algoritmo</strong></TableCell>
                    <TableCell align="right"><strong>Tempo (ms)</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.items.map((item) => (
                    <TableRow key={item.id} hover>
                      <TableCell>{item.id}</TableCell>
                      <TableCell>{new Date(item.createdAt).toLocaleString('pt-BR')}</TableCell>
                      <TableCell>{new Date(item.referenceDate).toLocaleDateString('pt-BR')}</TableCell>
                      <TableCell align="center">
                        <Chip
                          label={statusLabel(item.status)}
                          color={getStatusColor(item.status) as any}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">{item.vehicles ?? '-'}</TableCell>
                      <TableCell align="right">{item.crew ?? '-'}</TableCell>
                      <TableCell align="right">{item.totalCost ? `R$ ${item.totalCost.toFixed(2)}` : '-'}</TableCell>
                      <TableCell align="right">{item.cctViolations}</TableCell>
                      <TableCell>{item.algorithm ?? '-'}</TableCell>
                      <TableCell align="right">{item.elapsedMs ? `${(item.elapsedMs / 1000).toFixed(1)}s` : '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <Stack direction="row" justifyContent="center" sx={{ mt: 2 }}>
              <Pagination
                count={data.pages}
                page={page}
                onChange={handlePageChange}
                color="primary"
              />
            </Stack>

            <Typography variant="caption" sx={{ mt: 2, display: 'block', color: 'text.secondary' }}>
              Mostrando {data.items.length} de {data.total} registros
            </Typography>
          </>
        ) : (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <Typography color="textSecondary">Nenhuma escala encontrada nos últimos {days} dias.</Typography>
          </Box>
        )}
      </Box>
    </DashboardCard>
  );
}
