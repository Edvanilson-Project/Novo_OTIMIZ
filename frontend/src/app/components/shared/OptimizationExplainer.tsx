'use client';

import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography,
  Stack,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Grid,
  Divider,
} from '@mui/material';
import { IconChevronDown, IconTarget, IconTrendingDown, IconAlertCircle, IconCheck } from '@tabler/icons-react';

interface OptimizationMetric {
  name: string;
  value: number | string;
  unit: string;
  change?: number;
  changeUnit?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
}

interface OptimizationExplainerProps {
  scenarioName: string;
  scenarioDescription: string;
  metrics: OptimizationMetric[];
}

const OptimizationExplainer: React.FC<OptimizationExplainerProps> = ({
  scenarioName,
  scenarioDescription,
  metrics,
}) => {
  const [expandedPanel, setExpandedPanel] = useState<string | false>(false);

  const handleAccordionChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedPanel(isExpanded ? panel : false);
  };

  const optimizationStrategies = {
    'cost-optimized': [
      {
        title: 'Consolidação de Viagens',
        description: 'Agrupa viagens similares em um mesmo veículo para reduzir custos operacionais',
        impact: '-5% a -8%',
      },
      {
        title: 'Otimização de Rotas',
        description: 'Reordena viagens para minimizar distância total e tempo de deadhead',
        impact: '-3% a -5%',
      },
      {
        title: 'Seleção de Veículos',
        description: 'Escolhe tipos de veículos mais econômicos mantendo capacidade necessária',
        impact: '-2% a -3%',
      },
    ],
    'service-optimized': [
      {
        title: 'Minimização de Mudanças de Veículos',
        description: 'Mantém passageiros no mesmo veículo quando possível para melhorar experiência',
        impact: '+2% a +5%',
      },
      {
        title: 'Redução de Transferências',
        description: 'Diminui número de trocas de veículos durante a jornada',
        impact: '+1% a +3%',
      },
    ],
    'maintenance-aware': [
      {
        title: 'Evitar Conflitos de Manutenção',
        description: 'Redistribui viagens para evitar veículos em manutenção programada',
        impact: '+1% a +3%',
      },
      {
        title: 'Balanceamento de Utilização',
        description: 'Distribui carga de trabalho para não sobrecarregar veículos saudáveis',
        impact: '+0.5% a +2%',
      },
    ],
  };

  const getStrategies = () => {
    const key = scenarioName.toLowerCase().replace(/\s+/g, '-');
    return optimizationStrategies[key as keyof typeof optimizationStrategies] || [];
  };

  const getColorForChange = (change?: number, changeType?: string) => {
    if (changeType === 'positive') return '#2e7d32';
    if (changeType === 'negative') return '#d32f2f';
    if (change !== undefined) {
      return change < 0 ? '#2e7d32' : '#d32f2f';
    }
    return '#1976d2';
  };

  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="Explicador de Otimização"
          avatar={<IconTarget size={20} />}
          subheader="Entenda como este cenário foi otimizado"
        />
        <CardContent>
          <Stack spacing={3}>
            {/* Scenario Overview */}
            <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                {scenarioName}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {scenarioDescription}
              </Typography>
            </Box>

            {/* Metrics Grid */}
            {metrics.length > 0 && (
              <>
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  Métricas Principais
                </Typography>
                <Grid container spacing={2}>
                  {metrics.map((metric, idx) => (
                    <Grid size={{ xs: 12, sm: 6, md: 3 }} key={idx}>
                      <Box sx={{ p: 2, backgroundColor: '#fafafa', borderRadius: 1, border: '1px solid #e0e0e0' }}>
                        <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 0.5 }}>
                          {metric.name}
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                          <Typography variant="h6" sx={{ fontWeight: 700 }}>
                            {metric.value}
                          </Typography>
                          <Typography variant="caption">{metric.unit}</Typography>
                        </Box>
                        {metric.change !== undefined && (
                          <Typography
                            variant="caption"
                            sx={{
                              color: getColorForChange(metric.change, metric.changeType),
                              display: 'block',
                              mt: 0.5,
                              fontWeight: 500,
                            }}
                          >
                            {metric.change >= 0 ? '+' : ''}
                            {metric.change.toFixed(1)}{metric.changeUnit ?? '%'}
                          </Typography>
                        )}
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              </>
            )}

            <Divider />

            {/* Optimization Strategies */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                Estratégias de Otimização Aplicadas
              </Typography>
              <Stack spacing={1}>
                {getStrategies().map((strategy, idx) => (
                  <Accordion key={idx}>
                    <AccordionSummary expandIcon={<IconChevronDown size={20} />}>
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', width: '100%' }}>
                        <IconTrendingDown size={18} color="#1976d2" />
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {strategy.title}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            Impacto: {strategy.impact}
                          </Typography>
                        </Box>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={2}>
                        <Typography variant="body2">{strategy.description}</Typography>
                        <Box sx={{ p: 1, backgroundColor: '#f5f5f5', borderRadius: 0.5 }}>
                          <Typography variant="caption" sx={{ fontWeight: 600 }}>
                            Impacto Esperado: {strategy.impact}
                          </Typography>
                        </Box>
                      </Stack>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Stack>
            </Box>

            <Divider />

            {/* Key Benefits */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                Benefícios Principais
              </Typography>
              <List dense>
                <ListItem>
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Redução de Custos"
                    secondary="Economia através de melhor utilização de recursos e consolidação de viagens"
                    slotProps={{ secondary: { variant: 'caption', component: 'div' } }}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Manutenção da Qualidade"
                    secondary="Restrições operacionais e de segurança sempre respeitadas"
                    slotProps={{ secondary: { variant: 'caption', component: 'div' } }}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    <IconCheck size={20} color="#2e7d32" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Viabilidade Operacional"
                    secondary="Solução pode ser implementada com recursos atuais"
                    slotProps={{ secondary: { variant: 'caption', component: 'div' } }}
                  />
                </ListItem>
              </List>
            </Box>

            <Divider />

            {/* Implementation Considerations */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
                Considerações de Implementação
              </Typography>
              <Stack spacing={1}>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <IconAlertCircle size={18} color="#f57c00" style={{ flexShrink: 0, marginTop: 4 }} />
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      Período de Transição
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Recomenda-se implementação gradual para testar viabilidade
                    </Typography>
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <IconAlertCircle size={18} color="#f57c00" style={{ flexShrink: 0, marginTop: 4 }} />
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      Validação de Restrições
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Verificar conflitos com restrições operacionais antes de executar
                    </Typography>
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <IconAlertCircle size={18} color="#f57c00" style={{ flexShrink: 0, marginTop: 4 }} />
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      Comunicação com Operadores
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Notificar equipes sobre mudanças significativas no plano
                    </Typography>
                  </Box>
                </Box>
              </Stack>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default OptimizationExplainer;
