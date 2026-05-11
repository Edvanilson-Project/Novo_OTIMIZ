'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  LinearProgress,
  Typography,
  Chip,
  Stack,
  Alert,
  CircularProgress,
} from '@mui/material';
import { IconHeartHandshake, IconAlertCircle, IconCheck } from '@tabler/icons-react';
import { vehiclesApi } from '@/lib/api';

interface VehicleHealth {
  vehicleId: string;
  healthScore: number; // 0-100
  lastMaintenanceDate?: string;
  nextMaintenanceDate?: string;
  odometer?: number;
  utilizationRate: number; // 0-100
  maintenanceStatus: 'good' | 'warning' | 'critical';
  issues: string[];
}

interface VehicleHealthStatusProps {
  vehicleId: number;
}

const VehicleHealthStatus: React.FC<VehicleHealthStatusProps> = ({ vehicleId }) => {
  const [health, setHealth] = useState<VehicleHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVehicleHealth();
  }, [vehicleId]);

  const fetchVehicleHealth = async () => {
    try {
      setLoading(true);
      const vehicle = await vehiclesApi.getById(vehicleId);
      const calculatedHealth = calculateHealth(vehicle);
      setHealth(calculatedHealth);
    } catch (err) {
      setError('Erro ao carregar saúde do veículo');
    } finally {
      setLoading(false);
    }
  };

  const calculateHealth = (vehicle: any): VehicleHealth => {
    let score = 100;
    const issues: string[] = [];

    if (!vehicle.isActive) {
      score -= 50;
      issues.push('Veículo inativo');
    }

    if (vehicle.lastMaintenanceDate) {
      const lastMaint = new Date(vehicle.lastMaintenanceDate);
      const daysSinceLastMaint = Math.floor(
        (new Date().getTime() - lastMaint.getTime()) / (1000 * 60 * 60 * 24)
      );

      if (daysSinceLastMaint > 180) {
        score -= 20;
        issues.push('Manutenção vencida (> 180 dias)');
      } else if (daysSinceLastMaint > 90) {
        score -= 10;
        issues.push('Manutenção em breve recomendada');
      }
    }

    if (vehicle.odometer && vehicle.odometer > 300000) {
      score -= 15;
      issues.push('Quilometragem alta (> 300k km)');
    }

    return {
      vehicleId: vehicle.vehicleId,
      healthScore: Math.max(0, score),
      lastMaintenanceDate: vehicle.lastMaintenanceDate,
      odometer: vehicle.odometer,
      utilizationRate: Math.random() * 100, // Placeholder
      maintenanceStatus:
        score >= 80 ? 'good' : score >= 60 ? 'warning' : 'critical',
      issues,
    };
  };

  const getHealthColor = (score: number): string => {
    if (score >= 80) return '#4caf50'; // green
    if (score >= 60) return '#ff9800'; // orange
    return '#f44336'; // red
  };

  const getStatusIcon = (status: string): React.ReactElement | undefined => {
    switch (status) {
      case 'good':
        return <IconCheck size={20} color="#4caf50" />;
      case 'warning':
        return <IconAlertCircle size={20} color="#ff9800" />;
      case 'critical':
        return <IconAlertCircle size={20} color="#f44336" />;
      default:
        return undefined;
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

  if (error || !health) {
    return <Alert severity="error">{error || 'Dados indisponíveis'}</Alert>;
  }

  return (
    <Card>
      <CardHeader
        title="Status de Saúde do Veículo"
        avatar={<IconHeartHandshake size={20} />}
        subheader={health.vehicleId}
      />
      <CardContent>
        <Stack spacing={3}>
          {/* Health Score */}
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                Score de Saúde
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  color: getHealthColor(health.healthScore),
                }}
              >
                {health.healthScore}/100
              </Typography>
            </Box>
            <LinearProgress
              variant="determinate"
              value={health.healthScore}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: '#e0e0e0',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: getHealthColor(health.healthScore),
                },
              }}
            />
          </Box>

          {/* Status Chips */}
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Stack spacing={1}>
                <Typography variant="caption" color="textSecondary">
                  Status de Manutenção
                </Typography>
                <Chip
                  label={
                    health.maintenanceStatus === 'good'
                      ? 'Bom'
                      : health.maintenanceStatus === 'warning'
                        ? 'Aviso'
                        : 'Crítico'
                  }
                  icon={getStatusIcon(health.maintenanceStatus)}
                  color={
                    health.maintenanceStatus === 'good'
                      ? 'success'
                      : health.maintenanceStatus === 'warning'
                        ? 'warning'
                        : 'error'
                  }
                  variant="outlined"
                />
              </Stack>
            </Grid>

            <Grid size={{ xs: 12, sm: 6 }}>
              <Stack spacing={1}>
                <Typography variant="caption" color="textSecondary">
                  Taxa de Utilização
                </Typography>
                <Chip
                  label={`${Math.round(health.utilizationRate)}%`}
                  color="primary"
                  variant="outlined"
                />
              </Stack>
            </Grid>
          </Grid>

          {/* Issues */}
          {health.issues.length > 0 && (
            <Alert severity="warning">
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Problemas Detectados:
              </Typography>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {health.issues.map((issue, idx) => (
                  <li key={idx}>
                    <Typography variant="body2">{issue}</Typography>
                  </li>
                ))}
              </ul>
            </Alert>
          )}

          {/* Maintenance Info */}
          <Box sx={{ p: 1.5, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="caption" color="textSecondary">
                  Última Manutenção
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {health.lastMaintenanceDate
                    ? new Date(health.lastMaintenanceDate).toLocaleDateString('pt-BR')
                    : 'Não registrada'}
                </Typography>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="caption" color="textSecondary">
                  Quilometragem
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {health.odometer ? `${health.odometer.toLocaleString('pt-BR')} km` : 'N/A'}
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default VehicleHealthStatus;
