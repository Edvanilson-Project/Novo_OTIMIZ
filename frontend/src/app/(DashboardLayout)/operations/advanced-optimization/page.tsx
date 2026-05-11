'use client';

import React, { useState, useEffect } from 'react';
import { Box, Container, Grid, Tabs, Tab, Typography, Button, Stack } from '@mui/material';
import { IconRefresh } from '@tabler/icons-react';
import { operationsApi, operationReportingApi } from '@/lib/api';
import ScenarioComparison from '../../../components/shared/ScenarioComparison';
import WhatIfPanel from '../../../components/shared/WhatIfPanel';
import OptimizationExplainer from '../../../components/shared/OptimizationExplainer';
import RealtimeOptimizationMonitor from '../../../components/shared/RealtimeOptimizationMonitor';

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
  const [reportMetrics, setReportMetrics] = useState<any>(null);

  useEffect(() => {
    operationsApi.getLatestSchedule()
      .then((s: any) => {
        if (s?.id) {
          setScheduleId(s.id);
          if (s?.totalCost) setOriginalCost(Number(s.totalCost));
          return operationReportingApi.generate(s.id);
        }
      })
      .then((report: any) => {
        if (report) setReportMetrics(report);
      })
      .catch((err) => {
        console.error('[AdvancedOptimization] failed to load report', err);
      });
  }, []);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleRunOptimization = () => {
    setIsOptimizing(true);
    // Optimization would complete in RealtimeOptimizationMonitor
    setTimeout(() => {
      setIsOptimizing(false);
    }, 30000);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
            Otimização Avançada
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Explore cenários, simule mudanças e acompanhe a otimização em tempo real
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<IconRefresh size={18} />}
          onClick={handleRunOptimization}
          disabled={isOptimizing}
        >
          {isOptimizing ? 'Otimizando...' : 'Executar Otimização'}
        </Button>
      </Stack>

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
            {scheduleId ? (
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
            {scheduleId ? (
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
