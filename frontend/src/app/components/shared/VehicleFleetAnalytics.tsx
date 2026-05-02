'use client';

import React, { useEffect, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  Chip,
  LinearProgress,
} from '@mui/material';
import { IconAnalyze, IconAlertCircle } from '@tabler/icons-react';

interface VehicleMetrics {
  vehicleId: number;
  vehicleLabel: string;
  healthScore: number;
  maintenanceStatus: 'good' | 'warning' | 'critical';
  estimatedCostPerDay: number;
  odometer: number;
  utilizationRate: number;
  issues: string[];
  recommendations: string[];
}

const VehicleFleetAnalytics: React.FC = () => {
  const [metrics, setMetrics] = useState<VehicleMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFleetMetrics();
  }, []);

  const fetchFleetMetrics = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/vehicles/metrics/all');
      if (response.ok) {
        const data = await response.json();
        setMetrics(data);
      } else {
        setError('Erro ao carregar métricas da frota');
      }
    } catch (err) {
      setError('Erro ao carregar métricas da frota');
    } finally {
      setLoading(false);
    }
  };

  const getHealthColor = (score: number): 'success' | 'warning' | 'error' => {
    if (score >= 80) return 'success';
    if (score >= 60) return 'warning';
    return 'error';
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'good':
        return '#4caf50';
      case 'warning':
        return '#ff9800';
      case 'critical':
        return '#f44336';
      default:
        return '#999';
    }
  };

  const calculateFleetStats = () => {
    if (metrics.length === 0) {
      return { avgHealth: 0, totalCost: 0, criticalCount: 0 };
    }

    const avgHealth = Math.round(
      metrics.reduce((sum, m) => sum + m.healthScore, 0) / metrics.length
    );
    const totalCost = metrics.reduce((sum, m) => sum + m.estimatedCostPerDay, 0);
    const criticalCount = metrics.filter((m) => m.maintenanceStatus === 'critical').length;

    return { avgHealth, totalCost, criticalCount };
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

  const { avgHealth, totalCost, criticalCount } = calculateFleetStats();

  return (
    <Box>
      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Saúde Média
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: getStatusColor(avgHealth) }}>
                {avgHealth}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                de 100
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Custo/Dia
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                R$ {totalCost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                {metrics.length} veículos
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Críticos
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#f44336' }}>
                {criticalCount}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                requerem atenção
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Utilização Média
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {metrics.length > 0
                  ? Math.round(
                      metrics.reduce((sum, m) => sum + m.utilizationRate, 0) / metrics.length
                    )
                  : 0}
                %
              </Typography>
              <Typography variant="caption" color="textSecondary">
                da capacidade
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Detailed Table */}
      <Card>
        <CardHeader
          title="Análise Detalhada da Frota"
          avatar={<IconAnalyze size={20} />}
        />
        <CardContent>
          <TableContainer component={Paper} variant="outlined">
            <Table>
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell><strong>Veículo</strong></TableCell>
                  <TableCell align="center"><strong>Score</strong></TableCell>
                  <TableCell align="center"><strong>Status</strong></TableCell>
                  <TableCell align="right"><strong>Km</strong></TableCell>
                  <TableCell align="right"><strong>Utilização</strong></TableCell>
                  <TableCell align="right"><strong>Custo/Dia</strong></TableCell>
                  <TableCell><strong>Problemas</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {metrics.map((vehicle) => (
                  <TableRow key={vehicle.vehicleId} hover>
                    <TableCell sx={{ fontWeight: 600 }}>{vehicle.vehicleLabel}</TableCell>
                    <TableCell align="center">
                      <Chip
                        label={vehicle.healthScore}
                        color={getHealthColor(vehicle.healthScore)}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={
                          vehicle.maintenanceStatus === 'good'
                            ? 'Bom'
                            : vehicle.maintenanceStatus === 'warning'
                              ? 'Aviso'
                              : 'Crítico'
                        }
                        color={
                          vehicle.maintenanceStatus === 'good'
                            ? 'success'
                            : vehicle.maintenanceStatus === 'warning'
                              ? 'warning'
                              : 'error'
                        }
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {vehicle.odometer.toLocaleString('pt-BR')}
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                        <Box sx={{ width: 60 }}>
                          <LinearProgress
                            variant="determinate"
                            value={vehicle.utilizationRate}
                            sx={{
                              height: 4,
                              borderRadius: 2,
                            }}
                          />
                        </Box>
                        <Typography variant="caption" sx={{ minWidth: 30 }}>
                          {Math.round(vehicle.utilizationRate)}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      R$ {vehicle.estimatedCostPerDay.toFixed(0)}
                    </TableCell>
                    <TableCell>
                      {vehicle.issues.length > 0 ? (
                        <Chip
                          icon={<IconAlertCircle size={16} />}
                          label={`${vehicle.issues.length} problema(s)`}
                          size="small"
                          color="warning"
                          variant="outlined"
                        />
                      ) : (
                        <Typography variant="caption" color="textSecondary">
                          Sem problemas
                        </Typography>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Recommendations */}
      {metrics.some((m) => m.recommendations.length > 0) && (
        <Card sx={{ mt: 3 }}>
          <CardHeader
            title="Recomendações"
            subheader={`${metrics.filter((m) => m.recommendations.length > 0).length} veículo(s) requer atenção`}
          />
          <CardContent>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 2 }}>
              {metrics
                .filter((m) => m.recommendations.length > 0)
                .map((vehicle) => (
                  <Card key={vehicle.vehicleId} variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                        {vehicle.vehicleLabel}
                      </Typography>
                      <ul style={{ margin: 0, paddingLeft: 20, fontSize: '0.875rem' }}>
                        {vehicle.recommendations.map((rec, idx) => (
                          <li key={idx}>
                            <Typography variant="body2">{rec}</Typography>
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                ))}
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default VehicleFleetAnalytics;
