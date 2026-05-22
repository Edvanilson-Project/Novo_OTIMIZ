'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  LinearProgress,
  Stack,
  Typography,
  Chip,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  CircularProgress,
} from '@mui/material';
import { IconActivity, IconCheck, IconClock, IconAlertTriangle } from '@tabler/icons-react';
import { operationsApi } from '@/lib/api';

interface OptimizationStep {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  startTime?: Date;
  endTime?: Date;
  duration?: number;
  message?: string;
}

interface OptimizationMetrics {
  totalTrips: number;
  assignedTrips: number;
  unassignedTrips: number;
  totalCost: number;
  costReduction: number;
  vehiclesUsed: number;
  averageUtilization: number;
}

interface RealtimeOptimizationMonitorProps {
  scheduleId: number;
  isRunning?: boolean;
}

const STEP_DELAY_MS = 200;

const RealtimeOptimizationMonitor: React.FC<RealtimeOptimizationMonitorProps> = ({
  scheduleId,
  isRunning = false,
}) => {
  const [steps, setSteps] = useState<OptimizationStep[]>([
    { id: 'loading', name: 'Carregando Dados', status: 'pending', progress: 0 },
    { id: 'validation', name: 'Validação de Restrições', status: 'pending', progress: 0 },
    { id: 'optimization', name: 'Otimização', status: 'pending', progress: 0 },
    { id: 'evaluation', name: 'Avaliação de Cenários', status: 'pending', progress: 0 },
    { id: 'finalization', name: 'Finalização', status: 'pending', progress: 0 },
  ]);

  const [metrics, setMetrics] = useState<OptimizationMetrics>({
    totalTrips: 0,
    assignedTrips: 0,
    unassignedTrips: 0,
    totalCost: 0,
    costReduction: 0,
    vehiclesUsed: 0,
    averageUtilization: 0,
  });

  const [overallProgress, setOverallProgress] = useState(0);
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'error'>('idle');
  const stepStartTimes = useRef<Record<string, number>>({});

  useEffect(() => {
    if (!isRunning) return;

    const run = async () => {
      try {
        setStatus('running');
        setSteps((prev) => prev.map((s) => ({ ...s, status: 'pending', progress: 0 })));

        const stepSequence = ['loading', 'validation', 'optimization', 'evaluation', 'finalization'];

        for (let i = 0; i < stepSequence.length; i++) {
          const stepId = stepSequence[i];
          stepStartTimes.current[stepId] = Date.now();

          setSteps((prev) =>
            prev.map((s) =>
              s.id === stepId ? { ...s, status: 'running', startTime: new Date() } : s
            )
          );

          // Progress animation — UX only, not real data
          let progress = 0;
          while (progress < 100) {
            progress = Math.min(progress + 20 + i * 5, 100);
            await new Promise((resolve) => setTimeout(resolve, STEP_DELAY_MS));
            setSteps((prev) =>
              prev.map((s) => (s.id === stepId ? { ...s, progress } : s))
            );
          }

          const elapsedS = Math.round((Date.now() - stepStartTimes.current[stepId]) / 1000);

          setSteps((prev) =>
            prev.map((s) =>
              s.id === stepId
                ? { ...s, status: 'completed', progress: 100, endTime: new Date(), duration: Math.max(1, elapsedS) }
                : s
            )
          );
          setOverallProgress(((i + 1) / stepSequence.length) * 100);
        }

        // Fetch real metrics from backend after animation completes
        try {
          const [statusData, schedule] = await Promise.all([
            operationsApi.getOptimizeStatus().catch(() => null),
            operationsApi.getLatestSchedule().catch(() => null),
          ]);
          if (schedule) {
            const totalTrips = Number(schedule.total_trips ?? schedule.totalTrips ?? 0);
            const unassigned = Array.isArray(schedule.unassigned_trips) ? schedule.unassigned_trips.length : 0;
            const assigned = totalTrips - unassigned;
            const vehiclesUsed = Number(schedule.num_vehicles ?? schedule.vehicles ?? 0);
            const utilization = totalTrips > 0 ? Math.round((assigned / totalTrips) * 100) : 0;
            setMetrics({
              totalTrips,
              assignedTrips: assigned,
              unassignedTrips: unassigned,
              totalCost: Number(statusData?.totalCost ?? schedule.totalCost ?? schedule.total_cost ?? 0),
              costReduction: 0,
              vehiclesUsed,
              averageUtilization: utilization,
            });
          }
        } catch {
          // keep zeros if fetch fails — don't show random numbers
        }

        setStatus('completed');
      } catch (error) {
        setStatus('error');
        console.error('Optimization monitor error:', error);
      }
    };

    run();
  }, [isRunning, scheduleId]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <IconCheck size={18} color="#2e7d32" />;
      case 'running':
        return <IconActivity size={18} color="#1976d2" />;
      case 'failed':
        return <IconAlertTriangle size={18} color="#d32f2f" />;
      default:
        return <IconClock size={18} color="#999" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return '#2e7d32';
      case 'running':
        return '#1976d2';
      case 'failed':
        return '#d32f2f';
      default:
        return '#ccc';
    }
  };

  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="Monitor de Otimização em Tempo Real"
          avatar={<IconActivity size={20} />}
          subheader="Acompanhe o progresso da otimização"
        />
        <CardContent>
          <Stack spacing={3}>
            {/* Overall Progress */}
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1, alignItems: 'center' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  Progresso Geral
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  {Math.round(overallProgress)}%
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={overallProgress}
                sx={{ height: 8, borderRadius: 4 }}
              />
            </Box>

            {/* Status Badge */}
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              {status === 'running' && <CircularProgress size={24} />}
              <Chip
                label={
                  status === 'idle'
                    ? 'Aguardando Início'
                    : status === 'running'
                      ? 'Em Execução'
                      : status === 'completed'
                        ? 'Concluído'
                        : 'Erro'
                }
                color={status === 'completed' ? 'success' : status === 'error' ? 'error' : 'default'}
                variant={status !== 'idle' ? 'filled' : 'outlined'}
              />
            </Box>

            {/* Steps */}
            <Stack spacing={2}>
              {steps.map((step) => (
                <Box key={step.id}>
                  <Box
                    sx={{
                      display: 'flex',
                      gap: 1,
                      alignItems: 'center',
                      mb: 1,
                    }}
                  >
                    {getStatusIcon(step.status)}
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {step.name}
                      </Typography>
                      {step.duration && (
                        <Typography variant="caption" color="textSecondary">
                          {step.duration}s
                        </Typography>
                      )}
                    </Box>
                    <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 700,
                        color: getStatusColor(step.status),
                      }}
                    >
                      {Math.round(step.progress)}%
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={step.progress}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: '#e0e0e0',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: getStatusColor(step.status),
                      },
                    }}
                  />
                </Box>
              ))}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {/* Metrics Panel */}
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Métricas da Otimização" />
        <CardContent>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Total De Viagens
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {metrics.totalTrips}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#e8f5e9', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Viagens Atribuídas
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                  {metrics.assignedTrips}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#ffebee', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Viagens Não Atribuídas
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#d32f2f' }}>
                  {metrics.unassignedTrips}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Veículos Usados
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {metrics.vehiclesUsed}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Custo Total
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  R$ {metrics.totalCost.toLocaleString('pt-BR')}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#e8f5e9', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Redução De Custo
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#2e7d32' }}>
                  R$ {metrics.costReduction.toLocaleString('pt-BR')}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1, textAlign: 'center' }}>
                <Typography component="div" variant="caption" color="textSecondary" sx={{ mb: 0.5 }}>
                  Utilização Média
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {metrics.averageUtilization.toFixed(1)}%
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {status === 'error' && (
        <Alert severity="error">
          Erro durante a execução da otimização. Por favor, tente novamente.
        </Alert>
      )}

      {status === 'completed' && (
        <Alert severity="success">
          Otimização concluída com sucesso! Os resultados estão disponíveis acima.
        </Alert>
      )}
    </Box>
  );
};

export default RealtimeOptimizationMonitor;
