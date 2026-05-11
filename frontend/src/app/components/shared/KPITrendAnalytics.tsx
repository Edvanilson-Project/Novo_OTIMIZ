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
      const data = await operationReportingApi.getHistorical(scheduleId, days);
      setTrends(data.map((r: any) => ({
        date: new Date(r.generatedAt),
        cost: r.metrics.totalCost,
        utilization: r.metrics.averageUtilization,
        vehicles: r.metrics.vehiclesUsed,
        assignedTrips: r.metrics.assignedTrips,
      })));

      if (data.length > 0) {
        const costs = data.map((r: any) => r.metrics.totalCost);
        const utilizations = data.map((r: any) => r.metrics.averageUtilization);
        const vehicleUsage = data.map((r: any) => r.metrics.vehiclesUsed);

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
              {/* Cost Trend Chart Placeholder */}
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                  Custo Total
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1, height: 200 }}>
                  {trends.slice(-14).map((trend, idx) => {
                    const minCost = Math.min(...trends.map((t) => t.cost));
                    const maxCost = Math.max(...trends.map((t) => t.cost));
                    const normalized = ((trend.cost - minCost) / (maxCost - minCost)) * 100;

                    return (
                      <Box
                        key={idx}
                        sx={{
                          flex: 1,
                          height: `${normalized}%`,
                          backgroundColor: '#1976d2',
                          borderRadius: '4px 4px 0 0',
                          transition: 'all 0.3s ease',
                          '&:hover': {
                            backgroundColor: '#1565c0',
                            cursor: 'pointer',
                          },
                        }}
                        title={`${trend.date.toLocaleDateString('pt-BR')}: R$ ${trend.cost.toLocaleString('pt-BR')}`}
                      />
                    );
                  })}
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                  <Typography variant="caption" color="textSecondary">
                    {trends.length > 0 && trends[0].date.toLocaleDateString('pt-BR')}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {trends.length > 0 && trends[trends.length - 1].date.toLocaleDateString('pt-BR')}
                  </Typography>
                </Box>
              </Box>

              {/* Utilization Trend Chart Placeholder */}
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                  Utilização Média
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1, height: 150 }}>
                  {trends.slice(-14).map((trend, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        flex: 1,
                        height: `${trend.utilization}%`,
                        backgroundColor: trend.utilization > 80 ? '#2e7d32' : '#f57c00',
                        borderRadius: '4px 4px 0 0',
                        transition: 'all 0.3s ease',
                        '&:hover': {
                          opacity: 0.8,
                          cursor: 'pointer',
                        },
                      }}
                      title={`${trend.date.toLocaleDateString('pt-BR')}: ${trend.utilization.toFixed(1)}%`}
                    />
                  ))}
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                  <Typography variant="caption" color="textSecondary">
                    {trends.length > 0 && trends[0].date.toLocaleDateString('pt-BR')}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {trends.length > 0 && trends[trends.length - 1].date.toLocaleDateString('pt-BR')}
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
