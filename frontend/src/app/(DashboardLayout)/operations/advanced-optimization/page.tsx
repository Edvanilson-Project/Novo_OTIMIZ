'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Alert, AlertTitle, Box, Container, Grid, Tabs, Tab, Typography, Button, Stack, CircularProgress } from '@mui/material';
import { IconRefresh, IconFlask } from '@tabler/icons-react';
import { operationsApi, operationReportingApi } from '@/lib/api';
import ScenarioComparison from '../../../components/shared/ScenarioComparison';
import WhatIfPanel from '../../../components/shared/WhatIfPanel';
import OptimizationExplainer from '../../../components/shared/OptimizationExplainer';
import RealtimeOptimizationMonitor from '../../../components/shared/RealtimeOptimizationMonitor';

interface ComparisonSide {
  totalCost?: number;
  vehiclesUsed?: number;
  averageUtilization?: number;
}

interface ReportMetrics {
  scenarioComparison?: { savingsPercent?: number; optimized?: ComparisonSide; current?: ComparisonSide };
  metrics?: { totalCost?: number; vehiclesUsed?: number; averageUtilization?: number; totalTrips?: number };
}

interface LatestScheduleLike {
  id?: number | string | null;
  scheduleId?: number | string | null;
  totalCost?: number | string | null;
  resultSummary?: {
    run_id?: number | string | null;
    totalCost?: number | string | null;
  };
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`optimization-tabpanel-${index}`}
      aria-labelledby={`optimization-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

export default function AdvancedOptimizationPage() {
  const [tabValue, setTabValue] = useState(0);
  const [scheduleId, setScheduleId] = useState<number | null>(null);
  const [originalCost, setOriginalCost] = useState<number>(0);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [reportMetrics, setReportMetrics] = useState<ReportMetrics | null>(null);
  const [loadingLatestSchedule, setLoadingLatestSchedule] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loadedReportScheduleIdRef = useRef<number | null>(null);

  const resolveScheduleId = (schedule: LatestScheduleLike | null): number | null => {
    const candidate = Number(
      schedule?.id ?? schedule?.scheduleId ?? schedule?.resultSummary?.run_id ?? null,
    );
    return Number.isFinite(candidate) && candidate > 0 ? candidate : null;
  };

  const resolveScheduleCost = (schedule: LatestScheduleLike | null): number => {
    const candidate = Number(schedule?.totalCost ?? schedule?.resultSummary?.totalCost ?? 0);
    return Number.isFinite(candidate) ? candidate : 0;
  };

  const loadAdvancedData = useCallback(async () => {
    setLoadingLatestSchedule(true);
    setLoadError(null);

    try {
      const latest = await operationsApi.getLatestSchedule() as LatestScheduleLike | null;
      const nextScheduleId = resolveScheduleId(latest);
      const nextOriginalCost = resolveScheduleCost(latest);

      setScheduleId(nextScheduleId);
      setOriginalCost(nextOriginalCost);

      if (!nextScheduleId) {
        setReportMetrics(null);
        loadedReportScheduleIdRef.current = null;
        return;
      }

      if (loadedReportScheduleIdRef.current !== nextScheduleId) {
        const report = await operationReportingApi.generate(nextScheduleId) as ReportMetrics;
        setReportMetrics(report);
        loadedReportScheduleIdRef.current = nextScheduleId;
      }
    } catch (err) {
      console.error('[AdvancedOptimization] failed to load latest schedule', err);
      setLoadError('Erro ao carregar a última otimização.');
      setScheduleId(null);
      setReportMetrics(null);
      loadedReportScheduleIdRef.current = null;
    } finally {
      setLoadingLatestSchedule(false);
    }
  }, []);

  useEffect(() => {
    void loadAdvancedData();
  }, [loadAdvancedData]);

  useEffect(() => {
    const handleFocus = () => {
      void loadAdvancedData();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void loadAdvancedData();
      }
    };

    window.addEventListener('focus', handleFocus);
    window.addEventListener('pageshow', handleFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('focus', handleFocus);
      window.removeEventListener('pageshow', handleFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [loadAdvancedData]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleRunOptimization = async () => {
    if (!scheduleId) return;
    setIsOptimizing(true);
    try {
      await operationsApi.optimize({});
      // Poll GET /operations/optimize/status until completed or failed (max 3 min)
      const maxWaitMs = 180_000;
      const pollIntervalMs = 4_000;
      const deadline = Date.now() + maxWaitMs;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, pollIntervalMs));
        const s = await operationsApi.getOptimizeStatus().catch(() => null);
        if (s?.status === 'completed' || s?.status === 'failed') break;
      }
      loadedReportScheduleIdRef.current = null;
      await loadAdvancedData();
    } catch (err) {
      console.error('[AdvancedOptimization] optimize failed', err);
    } finally {
      setIsOptimizing(false);
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
            Otimização Avançada
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Explore cenários reais, simule mudanças e acompanhe a otimização em tempo real
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={loadingLatestSchedule ? <CircularProgress size={18} color="inherit" /> : <IconRefresh size={18} />}
          onClick={() => void loadAdvancedData()}
          disabled={loadingLatestSchedule || isOptimizing}
        >
          {loadingLatestSchedule ? 'Atualizando...' : 'Atualizar Dados'}
        </Button>
        <Button
          variant="contained"
          startIcon={<IconRefresh size={18} />}
          onClick={handleRunOptimization}
          disabled={isOptimizing || loadingLatestSchedule || !scheduleId}
        >
          {isOptimizing ? 'Otimizando...' : 'Executar Otimização'}
        </Button>
      </Stack>

      {/* Banner — informa o que é real vs heurística */}
      <Alert
        severity="info"
        icon={<IconFlask size={18} />}
        sx={{ mb: 3 }}
      >
        <AlertTitle>Cenários e What-If chamam o motor real</AlertTitle>
        <strong>Cenários</strong> (VCSP, MCNF, Hybrid) e <strong>What-If → Reotimização Real</strong> chamam o motor de otimização Python.
        Tempo típico: 30–120s. O modo <em>heurístico escalar</em> do What-If continua disponível para estimativas rápidas (marcado claramente).
      </Alert>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          aria-label="Abas de otimização"
          sx={{
            '& .MuiTab-root': {
              textTransform: 'none',
              fontSize: '0.95rem',
              fontWeight: 500,
            },
          }}
        >
          <Tab label="Cenários" id="optimization-tab-0" />
          <Tab label="What-If Simulator" id="optimization-tab-1" />
          <Tab label="Explicador" id="optimization-tab-2" />
          <Tab label="Monitor em Tempo Real" id="optimization-tab-3" />
        </Tabs>
      </Box>

      {/* Tab Panels */}
      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12 }}>
            {loadingLatestSchedule ? (
              <Box sx={{ py: 6, display: 'flex', justifyContent: 'center' }}>
                <CircularProgress />
              </Box>
            ) : loadError ? (
              <Alert severity="error">{loadError}</Alert>
            ) : scheduleId ? (
              <ScenarioComparison scheduleId={scheduleId} />
            ) : (
              <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
                Nenhuma otimização encontrada. Execute uma otimização primeiro.
              </Box>
            )}
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12 }}>
            {loadingLatestSchedule ? (
              <Box sx={{ py: 6, display: 'flex', justifyContent: 'center' }}>
                <CircularProgress />
              </Box>
            ) : loadError ? (
              <Alert severity="error">{loadError}</Alert>
            ) : scheduleId ? (
              <WhatIfPanel scheduleId={scheduleId} originalCost={originalCost} />
            ) : (
              <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
                Nenhuma otimização encontrada. Execute uma otimização primeiro.
              </Box>
            )}
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12 }}>
            <OptimizationExplainer
              scenarioName="Cenário Otimizado por Custo"
              scenarioDescription="Este cenário foi otimizado para minimizar custos operacionais mantendo todas as restrições."
              metrics={reportMetrics ? [
                {
                  name: 'Custo Total',
                  value: Math.round(reportMetrics.scenarioComparison?.optimized?.totalCost ?? reportMetrics.metrics?.totalCost ?? 0),
                  unit: 'R$',
                  change: -(reportMetrics.scenarioComparison?.savingsPercent ?? 0),
                  changeType: (reportMetrics.scenarioComparison?.savingsPercent ?? 0) > 0 ? 'positive' : 'neutral',
                },
                {
                  name: 'Veículos',
                  value: reportMetrics.scenarioComparison?.optimized?.vehiclesUsed ?? reportMetrics.metrics?.vehiclesUsed ?? 0,
                  unit: 'un.',
                  change: (reportMetrics.scenarioComparison?.optimized?.vehiclesUsed ?? 0) - (reportMetrics.scenarioComparison?.current?.vehiclesUsed ?? 0),
                  changeUnit: ' un.',
                  changeType: ((reportMetrics.scenarioComparison?.optimized?.vehiclesUsed ?? 0) - (reportMetrics.scenarioComparison?.current?.vehiclesUsed ?? 0)) < 0 ? 'positive' : 'neutral',
                },
                {
                  name: 'Utilização',
                  value: reportMetrics.scenarioComparison?.optimized?.averageUtilization ?? reportMetrics.metrics?.averageUtilization ?? 0,
                  unit: '%',
                  change: (reportMetrics.scenarioComparison?.optimized?.averageUtilization ?? 0) - (reportMetrics.scenarioComparison?.current?.averageUtilization ?? 0),
                  changeUnit: '%',
                  changeType: 'neutral',
                },
                {
                  name: 'Viagens',
                  value: reportMetrics.metrics?.totalTrips ?? 0,
                  unit: 'un.',
                  change: 0,
                  changeUnit: ' un.',
                  changeType: 'neutral',
                },
              ] : [
                { name: 'Custo Total', value: 0, unit: 'R$', change: 0, changeType: 'neutral' },
                { name: 'Veículos', value: 0, unit: 'un.', change: 0, changeType: 'neutral' },
                { name: 'Utilização', value: 0, unit: '%', change: 0, changeType: 'neutral' },
                { name: 'Viagens', value: 0, unit: 'un.', change: 0, changeType: 'neutral' },
              ]}
            />
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12 }}>
            <RealtimeOptimizationMonitor scheduleId={scheduleId ?? 0} isRunning={isOptimizing} />
          </Grid>
        </Grid>
      </TabPanel>
    </Container>
  );
}
