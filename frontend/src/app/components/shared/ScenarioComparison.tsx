'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Button,
  CircularProgress,
  Alert,
  AlertTitle,
  LinearProgress,
  Chip,
  Typography,
  Stack,
  Tooltip,
} from '@mui/material';
import { IconGitCompare, IconCheck, IconRefresh, IconAlertCircle } from '@tabler/icons-react';
import { scenariosApi } from '@/lib/api';

interface Scenario {
  id: string;
  name: string;
  description: string;
  status: 'baseline' | 'pending' | 'running' | 'completed' | 'failed';
  totalCost: number | null;
  vehiclesUsed: number | null;
  tripsUnassigned: number | null;
  cctViolations: number | null;
  feasible: boolean;
  maintenanceWarnings: string[];
  optimizationRunId: number | null;
  resultScheduleId: number | null;
  inputFingerprint: string | null;
  algorithm: string | null;
  startedAt: string | null;
  completedAt: string | null;
  errorMessage: string | null;
}

interface ScenarioComparisonProps {
  scheduleId: number;
}

const POLL_INTERVAL_MS = 5000;

const statusChip = (status: Scenario['status']) => {
  switch (status) {
    case 'baseline':
      return <Chip label="Atual" size="small" color="default" variant="outlined" />;
    case 'running':
    case 'pending':
      return <Chip label="Otimizando..." size="small" color="warning" variant="outlined" />;
    case 'completed':
      return <Chip label="Pronto" size="small" color="success" icon={<IconCheck size={14} />} />;
    case 'failed':
      return <Chip label="Falhou" size="small" color="error" icon={<IconAlertCircle size={14} />} />;
    default:
      return null;
  }
};

const ScenarioComparison: React.FC<ScenarioComparisonProps> = ({ scheduleId }) => {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedScenarios, setSelectedScenarios] = useState<[string, string] | null>(null);
  interface ComparisonResult {
    scenario1: { name: string; totalCost?: number; vehiclesUsed?: number; algorithm?: string };
    scenario2: { name: string; totalCost?: number; vehiclesUsed?: number; algorithm?: string };
    savings: number;
    savingsPercent?: number | null;
    differences?: string[];
  }
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const readErrorMessage = (err: unknown, fallback: string) => {
    const axiosErr = err as { response?: { data?: { message?: string } } };
    return axiosErr?.response?.data?.message ?? fallback;
  };

  const triggerScenarios = useCallback(async () => {
    try {
      setLoading(true);
      const data = await scenariosApi.generate(scheduleId);
      setScenarios(data);
      setError(null);
    } catch (err) {
      setError(
        readErrorMessage(err, 'Erro ao gerar cenários avançados.'),
      );
    } finally {
      setLoading(false);
    }
  }, [scheduleId]);

  const loadScenarios = useCallback(async () => {
    try {
      setLoading(true);
      const data = await scenariosApi.list(scheduleId);
      setScenarios(data);
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, 'Erro ao carregar cenários.'));
    } finally {
      setLoading(false);
    }
  }, [scheduleId]);

  const refreshScenarios = useCallback(async () => {
    try {
      setRefreshing(true);
      const data = await scenariosApi.list(scheduleId);
      setScenarios(data);
    } catch (err) {
      // silencioso no polling
    } finally {
      setRefreshing(false);
    }
  }, [scheduleId]);

  // Carga inicial: leitura idempotente, sem enfileirar runs automaticamente.
  useEffect(() => {
    void loadScenarios();
  }, [loadScenarios]);

  // Polling enquanto algum cenário está running/pending
  useEffect(() => {
    const anyPending = scenarios.some((s) => s.status === 'running' || s.status === 'pending');
    if (!anyPending) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }
    if (pollingRef.current) return; // já tem polling ativo
    pollingRef.current = setInterval(refreshScenarios, POLL_INTERVAL_MS);
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [scenarios, refreshScenarios]);

  const handleCompare = async (s1Id: string, s2Id: string) => {
    try {
      const data = await scenariosApi.compare(scheduleId, s1Id, s2Id);
      setComparison(data);
      setSelectedScenarios([s1Id, s2Id]);
    } catch (err) {
      setError('Erro ao comparar cenários');
    }
  };

  if (loading && scenarios.length === 0) {
    return (
      <Card>
        <CardContent sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  const pendingCount = scenarios.filter((s) => s.status === 'running' || s.status === 'pending').length;
  const completedCount = scenarios.filter((s) => s.status === 'completed').length;
  const failedCount = scenarios.filter((s) => s.status === 'failed').length;
  // Comparáveis: baseline + completed
  const comparable = scenarios.filter((s) => s.status === 'baseline' || s.status === 'completed');
  const hasGeneratedScenarios = scenarios.some((s) => s.id !== 'current');
  const reloadLabel = hasGeneratedScenarios ? 'Recarregar' : 'Gerar cenários';

  return (
    <Box>
      {!hasGeneratedScenarios && !loading && !error && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Nenhum cenário avançado foi gerado ainda. Clique em &quot;{reloadLabel}&quot; para enfileirar cenários com as viagens atualmente carregadas.
        </Alert>
      )}

      {/* Status global do conjunto de cenários */}
      {pendingCount > 0 && (
        <Alert severity="info" icon={<IconRefresh size={20} />} sx={{ mb: 2 }}>
          <AlertTitle>{pendingCount} cenário(s) ainda otimizando</AlertTitle>
          Os cenários chamam o motor de otimização Python real (VCSP/MCNF/Hybrid). Tempo típico: 30–120s por cenário.
          A página atualiza sozinha a cada {POLL_INTERVAL_MS / 1000}s.
          <LinearProgress sx={{ mt: 1 }} />
        </Alert>
      )}
      {failedCount > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {failedCount} cenário(s) com falha — veja detalhes nos cards. Você pode tentar novamente clicando em &quot;Recarregar&quot;.
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="Comparação de Cenários"
          avatar={<IconGitCompare size={20} />}
          subheader={`${comparable.length} pronto(s) • ${pendingCount} otimizando • ${failedCount} com falha`}
          action={
            <Button
              variant="outlined"
              size="small"
              startIcon={<IconRefresh size={16} />}
              onClick={triggerScenarios}
              disabled={refreshing || loading}
            >
              {reloadLabel}
            </Button>
          }
        />
        <CardContent>
          <Grid container spacing={2}>
            {scenarios.map((scenario) => (
              <Grid size={{ xs: 12, sm: 6, md: 3 }} key={scenario.id}>
                <Card
                  variant={selectedScenarios?.includes(scenario.id) ? 'elevation' : 'outlined'}
                  sx={{
                    border: selectedScenarios?.includes(scenario.id) ? '2px solid #1976d2' : undefined,
                    transition: 'all 0.2s',
                    '&:hover': { boxShadow: 2 },
                    opacity: scenario.status === 'running' || scenario.status === 'pending' ? 0.85 : 1,
                  }}
                >
                  <CardContent>
                    <Stack spacing={1}>
                      <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600, flex: 1, pr: 1 }}>
                          {scenario.name}
                        </Typography>
                        {statusChip(scenario.status)}
                      </Stack>
                      <Typography variant="caption" color="textSecondary">
                        {scenario.description}
                      </Typography>
                      {scenario.algorithm && (
                        <Tooltip title="Algoritmo de otimização usado neste cenário">
                          <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
                            algo: {scenario.algorithm}
                          </Typography>
                        </Tooltip>
                      )}

                      {scenario.status === 'completed' || scenario.status === 'baseline' ? (
                        <>
                          <Typography variant="h6" sx={{ fontWeight: 700, mt: 1 }}>
                            R$ {(scenario.totalCost ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                            <Chip label={`${scenario.vehiclesUsed ?? '?'} veículos`} size="small" variant="outlined" />
                            {(scenario.tripsUnassigned ?? 0) === 0 ? (
                              <Chip label="Sem trips órfãs" size="small" color="success" variant="outlined" />
                            ) : (
                              <Chip
                                label={`${scenario.tripsUnassigned} órfãs`}
                                size="small"
                                color="error"
                                variant="outlined"
                              />
                            )}
                            {(scenario.cctViolations ?? 0) > 0 && (
                              <Chip
                                label={`${scenario.cctViolations} violações CCT`}
                                size="small"
                                color="warning"
                                variant="outlined"
                              />
                            )}
                          </Box>
                        </>
                      ) : scenario.status === 'failed' ? (
                        <Alert severity="error" sx={{ py: 0.5, fontSize: '0.75rem', mt: 1 }}>
                          {scenario.errorMessage || 'Falha ao otimizar.'}
                        </Alert>
                      ) : (
                        <Box sx={{ mt: 1 }}>
                          <LinearProgress />
                          <Typography variant="caption" color="textSecondary" sx={{ mt: 0.5, display: 'block' }}>
                            Otimizador Python rodando…
                          </Typography>
                        </Box>
                      )}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Comparison Details */}
      {comparison && selectedScenarios && (
        <Card>
          <CardHeader title="Detalhes da Comparação" />
          <CardContent>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    {comparison.scenario1.name}
                  </Typography>
                  <Stack spacing={0.5}>
                    <Typography variant="body2">
                      Custo: R$ {(comparison.scenario1.totalCost ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                    </Typography>
                    <Typography variant="body2">Veículos: {comparison.scenario1.vehiclesUsed ?? '?'}</Typography>
                    {comparison.scenario1.algorithm && (
                      <Typography variant="caption" color="textSecondary">
                        algo: {comparison.scenario1.algorithm}
                      </Typography>
                    )}
                  </Stack>
                </Box>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Box sx={{ p: 2, backgroundColor: '#e8f5e9', borderRadius: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    {comparison.scenario2.name}
                  </Typography>
                  <Stack spacing={0.5}>
                    <Typography variant="body2">
                      Custo: R$ {(comparison.scenario2.totalCost ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                    </Typography>
                    <Typography variant="body2">Veículos: {comparison.scenario2.vehiclesUsed ?? '?'}</Typography>
                    {comparison.scenario2.algorithm && (
                      <Typography variant="caption" color="textSecondary">
                        algo: {comparison.scenario2.algorithm}
                      </Typography>
                    )}
                  </Stack>
                </Box>
              </Grid>
              <Grid size={{ xs: 12 }}>
                <Alert severity={comparison.savings > 0 ? 'success' : 'info'} sx={{ fontSize: '1.05rem' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    {comparison.savings > 0 ? 'Economia: ' : 'Custo Adicional: '}
                    <span style={{ fontSize: '1.2em' }}>
                      R$ {Math.abs(comparison.savings ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
                    </span>
                    {comparison.savingsPercent !== null && comparison.savingsPercent !== undefined && (
                      <span style={{ marginLeft: 8, fontSize: '0.95em' }}>
                        ({comparison.savingsPercent > 0 ? '−' : '+'}
                        {Math.abs(comparison.savingsPercent).toFixed(1)}%)
                      </span>
                    )}
                  </Typography>
                </Alert>
              </Grid>
              {(comparison.differences?.length ?? 0) > 0 && comparison.differences && (
                <Grid size={{ xs: 12 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    Diferenças
                  </Typography>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {comparison.differences.map((diff: string, idx: number) => (
                      <li key={idx}>
                        <Typography variant="body2">{diff}</Typography>
                      </li>
                    ))}
                  </ul>
                </Grid>
              )}
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Quick Compare Buttons — só entre cenários comparáveis (completed/baseline) */}
      {comparable.length > 1 && (
        <Box sx={{ mt: 3, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {comparable.map((s1) =>
            comparable.map((s2) =>
              s1.id < s2.id ? (
                <Button
                  key={`${s1.id}-${s2.id}`}
                  variant="outlined"
                  size="small"
                  onClick={() => handleCompare(s1.id, s2.id)}
                >
                  {s1.name} vs {s2.name}
                </Button>
              ) : null,
            ),
          )}
        </Box>
      )}
    </Box>
  );
};

export default ScenarioComparison;
