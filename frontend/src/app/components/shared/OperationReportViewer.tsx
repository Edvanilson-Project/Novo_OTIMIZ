'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Typography,
  Alert,
  Stack,
  Chip,
  Button,
  CircularProgress,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  IconFileDownload,
  IconAlertTriangle,
  IconCheck,
  IconTrendingDown,
} from '@tabler/icons-react';
import { operationReportingApi, apiClient } from '@/lib/api';

interface ReportMetrics {
  totalTrips: number;
  assignedTrips: number;
  unassignedTrips: number;
  totalCost: number;
  costPerTrip: number;
  vehiclesUsed: number;
  averageUtilization: number;
  maintenanceIssues: number;
}

interface OperationReport {
  id: string;
  scheduleId: number;
  generatedAt: Date;
  period: {
    startDate: Date;
    endDate: Date;
  };
  metrics: ReportMetrics;
  scenarioComparison: {
    current: ReportMetrics;
    optimized: ReportMetrics;
    savings: number;
    savingsPercent: number;
  };
  recommendations: string[];
  issues: {
    severity: 'critical' | 'warning' | 'info';
    message: string;
  }[];
}

interface OperationReportViewerProps {
  scheduleId: number;
}

const OperationReportViewer: React.FC<OperationReportViewerProps> = ({ scheduleId }) => {
  const [report, setReport] = useState<OperationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReport();
  }, [scheduleId]);

  const fetchReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await operationReportingApi.generate(scheduleId);
      setReport({
        ...data,
        generatedAt: new Date(data.generatedAt),
        period: {
          startDate: new Date(data.period.startDate),
          endDate: new Date(data.period.endDate),
        },
      });
    } catch (err) {
      setError('Erro ao gerar relatório');
    } finally {
      setLoading(false);
    }
  };

  const downloadBlob = async (path: string, filename: string) => {
    try {
      const response = await apiClient.get(path, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Erro ao exportar', err);
    }
  };

  const handleExportPDF = () =>
    downloadBlob(`/operations/reporting/export-pdf/${scheduleId}`, `relatorio_${scheduleId}.pdf`);

  const handleExportExcel = () =>
    downloadBlob(`/operations/reporting/export-excel/${scheduleId}`, `relatorio_${scheduleId}.xlsx`);

  const getSeverityColor = (severity: 'critical' | 'warning' | 'info') => {
    switch (severity) {
      case 'critical':
        return '#d32f2f';
      case 'warning':
        return '#f57c00';
      default:
        return '#1976d2';
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!report) {
    return <Alert severity="warning">Nenhum relatório disponível</Alert>;
  }

  if (!report.metrics || !report.scenarioComparison?.current || !report.scenarioComparison?.optimized) {
    return <Alert severity="warning">Relatório com dados incompletos. Execute uma nova otimização para gerar métricas completas.</Alert>;
  }

  return (
    <Box>
      {/* Header */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Relatório de Operação" />
        <CardContent>
          <Stack spacing={2}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  Gerado em: {new Date(report.generatedAt).toLocaleDateString('pt-BR')}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Período: {new Date(report.period.startDate).toLocaleDateString('pt-BR')} até{' '}
                  {new Date(report.period.endDate).toLocaleDateString('pt-BR')}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<IconFileDownload size={16} />}
                  onClick={handleExportPDF}
                >
                  PDF
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<IconFileDownload size={16} />}
                  onClick={handleExportExcel}
                >
                  Excel
                </Button>
              </Stack>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Issues Section */}
      {(report.issues?.length ?? 0) > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardHeader title="Questões Identificadas" />
          <CardContent>
            <Stack spacing={1}>
              {report.issues.map((issue, idx) => (
                <Alert
                  key={idx}
                  severity={issue.severity === 'critical' ? 'error' : issue.severity}
                  icon={<IconAlertTriangle size={20} />}
                >
                  {issue.message}
                </Alert>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Current Metrics */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Métricas Atuais" />
        <CardContent>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Total De Viagens
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {report.metrics.totalTrips}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#e8f5e9', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Viagens Atribuídas
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                  {report.metrics.assignedTrips}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: report.metrics.unassignedTrips === 0 ? '#e8f5e9' : '#ffebee', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Não Atribuídas
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: report.metrics.unassignedTrips === 0 ? '#2e7d32' : '#d32f2f' }}>
                  {report.metrics.unassignedTrips}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Custo Total
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  R$ {report.metrics.totalCost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Custo Por Viagem
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  R$ {report.metrics.costPerTrip.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Veículos Usados
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {report.metrics.vehiclesUsed}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Utilização Média
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {(report.metrics.averageUtilization ?? 0).toFixed(1)}%
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Problemas De Manutenção
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {report.metrics.maintenanceIssues}
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Scenario Comparison */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Comparação De Cenários" />
        <CardContent>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell sx={{ fontWeight: 700 }}>Métrica</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>
                    Atual
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>
                    Otimizado
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>
                    Diferença
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  <TableCell>Custo Total</TableCell>
                  <TableCell align="right">
                    R$ {report.scenarioComparison.current.totalCost.toLocaleString('pt-BR')}
                  </TableCell>
                  <TableCell align="right">
                    R$ {report.scenarioComparison.optimized.totalCost.toLocaleString('pt-BR')}
                  </TableCell>
                  <TableCell align="right" sx={{ color: report.scenarioComparison.savings > 0 ? '#2e7d32' : '#d32f2f', fontWeight: 600 }}>
                    {report.scenarioComparison.savings > 0 ? '-' : '+'}R$ {Math.abs(report.scenarioComparison.savings).toLocaleString('pt-BR')}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Viagens Atribuídas</TableCell>
                  <TableCell align="right">{report.scenarioComparison.current.assignedTrips}</TableCell>
                  <TableCell align="right">{report.scenarioComparison.optimized.assignedTrips}</TableCell>
                  <TableCell align="right" sx={{ color: '#2e7d32', fontWeight: 600 }}>
                    +{report.scenarioComparison.optimized.assignedTrips - report.scenarioComparison.current.assignedTrips}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Veículos Usados</TableCell>
                  <TableCell align="right">{report.scenarioComparison.current.vehiclesUsed}</TableCell>
                  <TableCell align="right">{report.scenarioComparison.optimized.vehiclesUsed}</TableCell>
                  <TableCell align="right" sx={{ color: '#2e7d32', fontWeight: 600 }}>
                    {report.scenarioComparison.optimized.vehiclesUsed - report.scenarioComparison.current.vehiclesUsed}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Utilização Média</TableCell>
                  <TableCell align="right">
                    {(report.scenarioComparison.current.averageUtilization ?? 0).toFixed(1)}%
                  </TableCell>
                  <TableCell align="right">
                    {(report.scenarioComparison.optimized.averageUtilization ?? 0).toFixed(1)}%
                  </TableCell>
                  <TableCell align="right" sx={{ color: '#2e7d32', fontWeight: 600 }}>
                    +{((report.scenarioComparison.optimized.averageUtilization ?? 0) - (report.scenarioComparison.current.averageUtilization ?? 0)).toFixed(1)}%
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>

          <Alert severity="success" sx={{ mt: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
              Economia Potencial
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              R$ {(report.scenarioComparison.savings ?? 0).toLocaleString('pt-BR')}{' '}
              <Typography component="span" variant="body2">
                ({(report.scenarioComparison.savingsPercent ?? 0).toFixed(1)}%)
              </Typography>
            </Typography>
          </Alert>
        </CardContent>
      </Card>

      {/* Recommendations */}
      {(report.recommendations?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Recomendações" />
          <CardContent>
            <List>
              {report.recommendations.map((rec, idx) => (
                <ListItem key={idx}>
                  <ListItemIcon>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText primary={rec} />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default OperationReportViewer;
