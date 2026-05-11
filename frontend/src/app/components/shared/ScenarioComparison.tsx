'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Button,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Typography,
  Stack,
} from '@mui/material';
import { IconGitCompare, IconCheck } from '@tabler/icons-react';
import { scenariosApi } from '@/lib/api';

interface Scenario {
  id: string;
  name: string;
  description: string;
  totalCost: number;
  vehiclesUsed: number;
  tripsUnassigned: number;
  feasible: boolean;
  maintenanceWarnings: string[];
}

interface ScenarioComparisonProps {
  scheduleId: number;
}

const ScenarioComparison: React.FC<ScenarioComparisonProps> = ({ scheduleId }) => {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedScenarios, setSelectedScenarios] = useState<[string, string] | null>(null);
  const [comparison, setComparison] = useState<any>(null);

  useEffect(() => {
    fetchScenarios();
  }, [scheduleId]);

  const fetchScenarios = async () => {
    try {
      setLoading(true);
      const data = await scenariosApi.generate(scheduleId);
      setScenarios(data);
    } catch (err) {
      setError('Erro ao carregar cenários');
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async (s1Id: string, s2Id: string) => {
    try {
      const data = await scenariosApi.compare(scheduleId, s1Id, s2Id);
      setComparison(data);
      setSelectedScenarios([s1Id, s2Id]);
    } catch (err) {
      setError('Erro ao comparar cenários');
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

  return (
    <Box>
      {/* Scenario Overview */}
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="Comparação de Cenários"
          avatar={<IconGitCompare size={20} />}
          subheader="Avalie múltiplas opções de otimização"
        />
        <CardContent>
          <Grid container spacing={2}>
            {scenarios.map((scenario) => (
              <Grid size={{ xs: 12, sm: 6, md: 3 }} key={scenario.id}>
                <Card
                  variant={
                    selectedScenarios?.includes(scenario.id)
                      ? 'elevation'
                      : 'outlined'
                  }
                  sx={{
                    cursor: 'pointer',
                    border: selectedScenarios?.includes(scenario.id)
                      ? '2px solid #1976d2'
                      : undefined,
                    transition: 'all 0.2s',
                    '&:hover': { boxShadow: 2 },
                  }}
                >
                  <CardContent>
                    <Stack spacing={1}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        {scenario.name}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        {scenario.description}
                      </Typography>

                      <Typography variant="h6" sx={{ fontWeight: 700, mt: 1 }}>
                        R$ {scenario.totalCost.toLocaleString('pt-BR', {
                          maximumFractionDigits: 0,
                        })}
                      </Typography>

                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        <Chip
                          label={`${scenario.vehiclesUsed} veículos`}
                          size="small"
                          variant="outlined"
                        />
                        {scenario.feasible && (
                          <Chip
                            label="Viável"
                            size="small"
                            color="success"
                            icon={<IconCheck size={14} />}
                          />
                        )}
                      </Box>

                      {scenario.maintenanceWarnings.length > 0 && (
                        <Alert severity="warning" sx={{ py: 0.5, fontSize: '0.75rem' }}>
                          {scenario.maintenanceWarnings[0]}
                        </Alert>
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
                      Custo: R${' '}
                      {comparison.scenario1.totalCost.toLocaleString('pt-BR', {
                        maximumFractionDigits: 0,
                      })}
                    </Typography>
                    <Typography variant="body2">
                      Veículos: {comparison.scenario1.vehiclesUsed}
                    </Typography>
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
                      Custo: R${' '}
                      {comparison.scenario2.totalCost.toLocaleString('pt-BR', {
                        maximumFractionDigits: 0,
                      })}
                    </Typography>
                    <Typography variant="body2">
                      Veículos: {comparison.scenario2.vehiclesUsed}
                    </Typography>
                  </Stack>
                </Box>
              </Grid>

              <Grid size={{ xs: 12 }}>
                <Alert
                  severity={comparison.savings > 0 ? 'success' : 'info'}
                  sx={{ fontSize: '1.1rem' }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    {comparison.savings > 0 ? 'Economia:' : 'Custo Adicional:'}{' '}
                    <span style={{ fontSize: '1.3em' }}>
                      R$ {Math.abs(comparison.savings).toLocaleString('pt-BR', {
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  </Typography>
                </Alert>
              </Grid>

              {comparison.differences.length > 0 && (
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

      {/* Quick Compare Buttons */}
      {scenarios.length > 1 && (
        <Box sx={{ mt: 3, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {scenarios.map((s1) =>
            scenarios.map((s2) =>
              s1.id < s2.id ? (
                <Button
                  key={`${s1.id}-${s2.id}`}
                  variant="outlined"
                  size="small"
                  onClick={() => handleCompare(s1.id, s2.id)}
                >
                  {s1.name} vs {s2.name}
                </Button>
              ) : null
            )
          )}
        </Box>
      )}
    </Box>
  );
};

export default ScenarioComparison;
