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
} from '@mui/material';
import { IconTrendingUp, IconTrendingDown, IconActivity } from '@tabler/icons-react';
import { operationReportingApi } from '@/lib/api';

interface TrendMetric {
  date: Date;
  cost: number;
  utilization: number;
  vehicles: number;
  assignedTrips: number;
}

interface KPITrendAnalyticsProps {
  scheduleId: number;
  days?: number;
}

const KPITrendAnalytics: React.FC<KPITrendAnalyticsProps> = ({ scheduleId, days = 30 }) => {
  const [trends, setTrends] = useState<TrendMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statistics, setStatistics] = useState({
    avgCost: 0,
    costTrend: 0,
    avgUtilization: 0,
    utilizationTrend: 0,
    avgVehicles: 0,
    vehicleTrend: 0,
  });

  useEffect(() => {
    fetchTrends();
  }, [scheduleId, days]);

  const fetchTrends = async () => {
    try {
      setLoading(true);
      type HistoricalRow = {
        generatedAt: string;
        metrics: {
          totalCost: number;
          averageUtilization: number;
          vehiclesUsed: number;
          assignedTrips: number;
        };
      };
      const data = (await operationReportingApi.getHistorical(scheduleId, days)) as HistoricalRow[];
      setTrends(data.map((r) => ({
        date: new Date(r.generatedAt),
        cost: r.metrics.totalCost,
        utilization: r.metrics.averageUtilization,
        vehicles: r.metrics.vehiclesUsed,
        assignedTrips: r.metrics.assignedTrips,
      })));

      if (data.length > 0) {
        const costs = data.map((r) => r.metrics.totalCost);
        const utilizations = data.map((r) => r.metrics.averageUtilization);
        const vehicleUsage = data.map((r) => r.metrics.vehiclesUsed);

        const avgCost = costs.reduce((a: number, b: number) => a + b, 0) / costs.length;
        const costTrend = costs[costs.length - 1] - costs[0];
        const avgUtil = utilizations.reduce((a: number, b: number) => a + b, 0) / utilizations.length;
        const utilTrend = utilizations[utilizations.length - 1] - utilizations[0];
        const avgVeh = vehicleUsage.reduce((a: number, b: number) => a + b, 0) / vehicleUsage.length;
        const vehTrend = vehicleUsage[vehicleUsage.length - 1] - vehicleUsage[0];

        setStatistics({
          avgCost,
          costTrend,
          avgUtilization: avgUtil,
          utilizationTrend: utilTrend,
          avgVehicles: avgVeh,
          vehicleTrend: vehTrend,
        });
      }
    } catch (err) {
      setError('Erro ao carregar tendências');
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
    return <Alert severity="error">{error}</Alert>;
  }

  if (trends.length === 0) {
    return (
      <Alert severity="info">
        Nenhum histórico de otimização encontrado nos últimos {days} dias para este schedule.
        Execute novos cenários em <strong>Otimização Avançada</strong> para popular o histórico.
      </Alert>
    );
  }

  const TrendCard = ({
    title,
    value,
    unit,
    trend,
    color = '#1976d2',
  }: {
    title: string;
    value: number;
    unit: string;
    trend: number;
    color?: string;
  }) => {
    const isPositive = trend < 0;
    const TrendIcon = isPositive ? IconTrendingDown : IconTrendingUp;

    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
              {title}
            </Typography>
            <TrendIcon
              size={18}
              color={isPositive ? '#2e7d32' : '#d32f2f'}
            />
          </Box>
          <Typography variant="h6" sx={{ fontWeight: 700, color }}>
            {value.toFixed(1)} <Typography component="span" variant="caption">{unit}</Typography>
          </Typography>
          <Typography
            variant="caption"
            sx={{
              color: isPositive ? '#2e7d32' : '#d32f2f',
              fontWeight: 600,
            }}
          >
            {isPositive ? '↓ ' : '↑ '} {Math.abs(trend).toFixed(1)} {unit}
          </Typography>
        </Stack>
      </Paper>
    );
  };

  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="Análise de Tendências KPI"
          avatar={<IconActivity size={20} />}
          subheader={`Últimos ${days} dias`}
        />
        <CardContent>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TrendCard
                title="Custo Médio"
                value={statistics.avgCost}
                unit="R$"
                trend={statistics.costTrend}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TrendCard
                title="Utilização Média"
                value={statistics.avgUtilization}
                unit="%"
                trend={statistics.utilizationTrend}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TrendCard
                title="Veículos Usados"
                value={statistics.avgVehicles}
                unit="un."
                trend={statistics.vehicleTrend}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack spacing={1}>
                  <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                    Dias Analisados
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {trends.length}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    período completo
                  </Typography>
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Detailed Trend Data */}
      <Card>
        <CardHeader title="Evolução Diária" />
        <CardContent>
          {trends.length > 0 ? (
            <Stack spacing={2}>
              {/* Custo Total — barras com rótulo de valor ao hover */}
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    Custo Total (R$)
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    R$ {Math.min(...trends.map((t) => t.cost)).toLocaleString('pt-BR', { maximumFractionDigits: 0 })} –{' '}
                    R$ {Math.max(...trends.map((t) => t.cost)).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: 180, borderBottom: '1px solid #ccc', borderLeft: '1px solid #ccc', px: 0.5 }}>
                  {trends.slice(-14).map((trend, idx) => {
                    const minCost = Math.min(...trends.map((t) => t.cost));
                    const maxCost = Math.max(...trends.map((t) => t.cost));
                    const range = maxCost - minCost || 1;
                    const normalized = ((trend.cost - minCost) / range) * 100;
                    return (
                      <Box
                        key={idx}
                        sx={{
                          flex: 1,
                          minWidth: 8,
                          height: `${Math.max(normalized, 4)}%`,
                          backgroundColor: '#1976d2',
                          borderRadius: '3px 3px 0 0',
                          transition: 'background-color 0.2s',
                          cursor: 'default',
                          position: 'relative',
                          '&:hover': { backgroundColor: '#1565c0' },
                          '&:hover .bar-tooltip': { display: 'block' },
                        }}
                        title={`${trend.date.toLocaleDateString('pt-BR')}: R$ ${trend.cost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`}
                      >
                        <Box className="bar-tooltip" sx={{
                          display: 'none', position: 'absolute', bottom: '110%', left: '50%',
                          transform: 'translateX(-50%)', backgroundColor: 'rgba(0,0,0,0.78)',
                          color: '#fff', borderRadius: 1, px: 1, py: 0.5, whiteSpace: 'nowrap', zIndex: 10,
                        }}>
                          <Typography variant="caption">{trend.date.toLocaleDateString('pt-BR')}</Typography>
                          <br />
                          <Typography variant="caption" sx={{ fontWeight: 700 }}>
                            R$ {trend.cost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                          </Typography>
                        </Box>
                      </Box>
                    );
                  })}
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                  <Typography variant="caption" color="textSecondary">
                    {trends[Math.max(0, trends.length - 14)].date.toLocaleDateString('pt-BR')}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {trends[trends.length - 1].date.toLocaleDateString('pt-BR')}
                  </Typography>
                </Box>
              </Box>

              {/* Utilização Média — barra colorida por nível */}
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    Utilização Média (%)
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Verde ≥ 80% · Laranja {'<'} 80%
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: 130, borderBottom: '1px solid #ccc', borderLeft: '1px solid #ccc', px: 0.5 }}>
                  {trends.slice(-14).map((trend, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        flex: 1,
                        minWidth: 8,
                        height: `${Math.max(trend.utilization, 2)}%`,
                        backgroundColor: trend.utilization >= 80 ? '#2e7d32' : '#f57c00',
                        borderRadius: '3px 3px 0 0',
                        transition: 'opacity 0.2s',
                        cursor: 'default',
                        position: 'relative',
                        '&:hover': { opacity: 0.75 },
                        '&:hover .bar-tooltip': { display: 'block' },
                      }}
                      title={`${trend.date.toLocaleDateString('pt-BR')}: ${trend.utilization.toFixed(1)}%`}
                    >
                      <Box className="bar-tooltip" sx={{
                        display: 'none', position: 'absolute', bottom: '110%', left: '50%',
                        transform: 'translateX(-50%)', backgroundColor: 'rgba(0,0,0,0.78)',
                        color: '#fff', borderRadius: 1, px: 1, py: 0.5, whiteSpace: 'nowrap', zIndex: 10,
                      }}>
                        <Typography variant="caption">{trend.date.toLocaleDateString('pt-BR')}</Typography>
                        <br />
                        <Typography variant="caption" sx={{ fontWeight: 700 }}>{trend.utilization.toFixed(1)}%</Typography>
                      </Box>
                    </Box>
                  ))}
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                  <Typography variant="caption" color="textSecondary">
                    {trends[Math.max(0, trends.length - 14)].date.toLocaleDateString('pt-BR')}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {trends[trends.length - 1].date.toLocaleDateString('pt-BR')}
                  </Typography>
                </Box>
              </Box>

              {/* Summary */}
              <Alert severity="info">
                <Stack spacing={1}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    Resumo das Tendências
                  </Typography>
                  <Typography variant="body2">
                    • Custo médio: R$ {statistics.avgCost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                  </Typography>
                  <Typography variant="body2">
                    • Utilização média: {statistics.avgUtilization.toFixed(1)}%
                  </Typography>
                  <Typography variant="body2">
                    • Frota média: {statistics.avgVehicles.toFixed(1)} veículos
                  </Typography>
                </Stack>
              </Alert>
            </Stack>
          ) : (
            <Alert severity="warning">Sem dados de tendência disponíveis</Alert>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default KPITrendAnalytics;
