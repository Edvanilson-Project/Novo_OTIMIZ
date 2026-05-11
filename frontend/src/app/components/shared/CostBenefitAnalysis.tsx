'use client';

import React, { useEffect, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Typography,
  Stack,
  CircularProgress,
  Alert,
  Paper,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
} from '@mui/material';
import { IconTrendingDown, IconCheck, IconAlertCircle } from '@tabler/icons-react';
import { apiClient } from '@/lib/api';

interface CostBenefitData {
  period: {
    startDate: Date;
    endDate: Date;
  };
  reportCount: number;
  averageCost: number;
  averageUtilization: number;
  costTrend: number;
  utilizationTrend: number;
  bestDay: {
    generatedAt: Date;
    metrics: {
      totalCost: number;
      averageUtilization: number;
      vehiclesUsed: number;
    };
  };
  worstDay: {
    generatedAt: Date;
    metrics: {
      totalCost: number;
      averageUtilization: number;
      vehiclesUsed: number;
    };
  };
}

interface CostBenefitAnalysisProps {
  scheduleId: number;
}

const CostBenefitAnalysis: React.FC<CostBenefitAnalysisProps> = ({ scheduleId }) => {
  const [data, setData] = useState<CostBenefitData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCostBenefitData();
  }, [scheduleId]);

  const fetchCostBenefitData = async () => {
    try {
      setLoading(true);
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 30);
      const endDate = new Date();

      const result = await apiClient
        .get(`/operations/reporting/compare/${scheduleId}`, {
          params: { startDate: startDate.toISOString(), endDate: endDate.toISOString() },
        })
        .then((r) => r.data);

      if (result) {
        setData({
          ...result,
          period: {
            startDate: new Date(result.period.startDate),
            endDate: new Date(result.period.endDate),
          },
          bestDay: {
            ...result.bestDay,
            generatedAt: new Date(result.bestDay.generatedAt),
          },
          worstDay: {
            ...result.worstDay,
            generatedAt: new Date(result.worstDay.generatedAt),
          },
        });
      } else {
        setError('Sem dados disponíveis para análise');
      }
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setError('Sem dados disponíveis para análise');
      } else {
        setError('Erro ao carregar análise de custo-benefício');
      }
    } finally {
      setLoading(false);
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
    return <Alert severity="warning">{error}</Alert>;
  }

  if (!data) {
    return <Alert severity="warning">Sem dados disponíveis para análise</Alert>;
  }

  const monthlyPotentialSavings = data.costTrend < 0 ? Math.abs(data.costTrend) : 0;
  const utilizationImprovement = data.utilizationTrend > 0 ? data.utilizationTrend : 0;

  return (
    <Box>
      {/* Overview Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                Economia Observada
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                  R$ {monthlyPotentialSavings.toLocaleString('pt-BR')}
                </Typography>
                <Typography variant="caption" sx={{ color: '#2e7d32' }}>
                  últimos 30 dias
                </Typography>
              </Box>
            </Stack>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                Melhoria de Utilização
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                  +{utilizationImprovement.toFixed(1)}%
                </Typography>
                <Typography variant="caption" sx={{ color: '#2e7d32' }}>
                  vs. início do período
                </Typography>
              </Box>
            </Stack>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                Custo Médio
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  R$ {data.averageCost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                </Typography>
              </Box>
            </Stack>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                Utilização Média
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {data.averageUtilization.toFixed(1)}%
                </Typography>
              </Box>
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      {/* Cost Benefit Analysis */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Análise Detalhada de Custo-Benefício" />
        <CardContent>
          <Stack spacing={3}>
            {/* Savings Breakdown */}
            <Box sx={{ p: 2, backgroundColor: '#e8f5e9', borderRadius: 1 }}>
              <Stack spacing={1}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <IconTrendingDown size={20} color="#2e7d32" />
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    Economia Potencial Mensal
                  </Typography>
                </Box>
                <Typography variant="h5" sx={{ fontWeight: 700, color: '#2e7d32', ml: 4 }}>
                  R$ {monthlyPotentialSavings.toLocaleString('pt-BR')}
                </Typography>
                <Typography variant="body2" color="textSecondary" sx={{ ml: 4 }}>
                  Baseado em tendência de {data.costTrend.toFixed(1)} R$ em últimos 30 dias
                </Typography>
              </Stack>
            </Box>

            <Divider />

            {/* Best vs Worst Day Comparison */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                Comparação: Melhor vs Pior Dia
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <Paper variant="outlined" sx={{ p: 2, backgroundColor: '#e8f5e9' }}>
                    <Stack spacing={1}>
                      <Chip label="Melhor Dia" color="success" size="small" />
                      <Typography variant="caption" color="textSecondary">
                        {new Date(data.bestDay.generatedAt).toLocaleDateString('pt-BR')}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Custo:</strong>{' '}
                        R${' '}
                        {data.bestDay.metrics.totalCost.toLocaleString('pt-BR', {
                          maximumFractionDigits: 0,
                        })}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Utilização:</strong> {data.bestDay.metrics.averageUtilization.toFixed(1)}%
                      </Typography>
                      <Typography variant="body2">
                        <strong>Veículos:</strong> {data.bestDay.metrics.vehiclesUsed}
                      </Typography>
                    </Stack>
                  </Paper>
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <Paper variant="outlined" sx={{ p: 2, backgroundColor: '#ffebee' }}>
                    <Stack spacing={1}>
                      <Chip label="Pior Dia" color="error" size="small" />
                      <Typography variant="caption" color="textSecondary">
                        {new Date(data.worstDay.generatedAt).toLocaleDateString('pt-BR')}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Custo:</strong>{' '}
                        R${' '}
                        {data.worstDay.metrics.totalCost.toLocaleString('pt-BR', {
                          maximumFractionDigits: 0,
                        })}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Utilização:</strong> {data.worstDay.metrics.averageUtilization.toFixed(1)}%
                      </Typography>
                      <Typography variant="body2">
                        <strong>Veículos:</strong> {data.worstDay.metrics.vehiclesUsed}
                      </Typography>
                    </Stack>
                  </Paper>
                </Grid>
              </Grid>

              <Alert severity="info" sx={{ mt: 2 }}>
                <Typography variant="body2">
                  Diferença de custo entre melhor e pior dia: R${' '}
                  {(data.worstDay.metrics.totalCost - data.bestDay.metrics.totalCost).toLocaleString(
                    'pt-BR',
                    { maximumFractionDigits: 0 }
                  )}
                </Typography>
              </Alert>
            </Box>

            <Divider />

            {/* Benefits Summary */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                Benefícios Alcançados
              </Typography>
              <List dense>
                <ListItem>
                  <ListItemIcon>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Redução de Custos"
                    secondary={`Economia média de R$ ${Math.abs(data.costTrend).toLocaleString('pt-BR')} no período`}
                    slotProps={{ secondary: { variant: 'caption', component: 'div' } }}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Melhoria de Eficiência"
                    secondary={`Utilização aumentou em ${utilizationImprovement.toFixed(1)}% no período`}
                    slotProps={{ secondary: { variant: 'caption', component: 'div' } }}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Consistência Operacional"
                    secondary={`${data.reportCount} dias analisados com dados consistentes`}
                    slotProps={{ secondary: { variant: 'caption', component: 'div' } }}
                  />
                </ListItem>
              </List>
            </Box>

            <Divider />

            {/* Recommendations */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                Recomendações de Melhoria
              </Typography>
              <Stack spacing={1}>
                <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#f5f5f5' }}>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <IconAlertCircle size={18} color="#f57c00" style={{ flexShrink: 0, marginTop: 2 }} />
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        Manter Tendência de Redução de Custo
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        Continue implementando otimizações que geraram economia observada
                      </Typography>
                    </Box>
                  </Box>
                </Paper>
                <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#f5f5f5' }}>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <IconAlertCircle size={18} color="#f57c00" style={{ flexShrink: 0, marginTop: 2 }} />
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        Replicar Padrão do Melhor Dia
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        Analise operações do melhor dia para identificar padrões de sucesso
                      </Typography>
                    </Box>
                  </Box>
                </Paper>
                <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#f5f5f5' }}>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <IconAlertCircle size={18} color="#f57c00" style={{ flexShrink: 0, marginTop: 2 }} />
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        Aumentar Utilização Progressivamente
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        Meta: atingir 95% utilização média para máxima eficiência
                      </Typography>
                    </Box>
                  </Box>
                </Paper>
              </Stack>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Financial Impact */}
      <Card>
        <CardHeader title="Impacto Financeiro Projetado" />
        <CardContent>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={1}>
                  <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                    Economia Mensal (30 dias)
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                    R$ {monthlyPotentialSavings.toLocaleString('pt-BR')}
                  </Typography>
                </Stack>
              </Paper>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={1}>
                  <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                    Economia Anual Projetada
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                    R$ {(monthlyPotentialSavings * 12).toLocaleString('pt-BR')}
                  </Typography>
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
    </Box>
  );
};

export default CostBenefitAnalysis;
