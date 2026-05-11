'use client';

import React, { useState, useEffect } from 'react';
import { Alert, AlertTitle, Box, Container, Tabs, Tab, Typography, Button, Stack } from '@mui/material';
import { IconRefresh, IconFlask } from '@tabler/icons-react';
import OperationReportViewer from '../../../components/shared/OperationReportViewer';
import KPITrendAnalytics from '../../../components/shared/KPITrendAnalytics';
import CostBenefitAnalysis from '../../../components/shared/CostBenefitAnalysis';
import FairnessHistogram from '../../../components/shared/FairnessHistogram';
import { operationsApi } from '@/lib/api';

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
      id={`reporting-tabpanel-${index}`}
      aria-labelledby={`reporting-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

export default function ReportingPage() {
  const [tabValue, setTabValue] = useState(0);
  const [scheduleId, setScheduleId] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    operationsApi.getLatestSchedule()
      .then((s: any) => { if (s?.id) setScheduleId(s.id); })
      .catch((err) => {
        console.error('[Reporting] failed to load latest schedule', err);
      });
  }, []);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
            Analytics & Relatórios
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Analise tendências, compare cenários e acompanhe o ROI da otimização
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<IconRefresh size={18} />}
          onClick={handleRefresh}
        >
          Atualizar Dados
        </Button>
      </Stack>

      {/* Banner — dados reais agora vêm da tabela optimization_runs */}
      <Alert severity="info" icon={<IconFlask size={18} />} sx={{ mb: 3 }}>
        <AlertTitle>Dados reais</AlertTitle>
        Histórico, tendências e best/worst day agora leem de <code>optimization_runs</code> persistidas
        no banco. Dias sem otimização não aparecem (não há valores fabricados). Execute novos cenários
        em <strong>Otimização Avançada</strong> para popular o histórico.
      </Alert>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          aria-label="Abas de relatório"
          sx={{
            '& .MuiTab-root': {
              textTransform: 'none',
              fontSize: '0.95rem',
              fontWeight: 500,
            },
          }}
        >
          <Tab label="Relatório de Operação" id="reporting-tab-0" />
          <Tab label="Tendências KPI" id="reporting-tab-1" />
          <Tab label="Análise Custo-Benefício" id="reporting-tab-2" />
        </Tabs>
      </Box>

      {/* Tab Panels */}
      {scheduleId === null ? (
        <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
          Nenhuma otimização encontrada. Execute uma otimização primeiro.
        </Box>
      ) : (
        <>
          <TabPanel value={tabValue} index={0}>
            <OperationReportViewer key={refreshKey} scheduleId={scheduleId} />
          </TabPanel>
          <TabPanel value={tabValue} index={1}>
            <KPITrendAnalytics key={refreshKey} scheduleId={scheduleId} days={30} />
          </TabPanel>
          <TabPanel value={tabValue} index={2}>
            <CostBenefitAnalysis key={refreshKey} scheduleId={scheduleId} />
          </TabPanel>
        </>
      )}
    </Container>
  );
}
