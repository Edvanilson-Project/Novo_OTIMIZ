'use client';

import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  TextField,
  Button,
  Alert,
  Stack,
  Typography,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Grid,
  Divider,
  Chip,
} from '@mui/material';
import { IconWand, IconAlertTriangle, IconCheck, IconBolt, IconRefresh } from '@tabler/icons-react';
import { scenariosApi } from '@/lib/api';

interface WhatIfScenario {
  type: 'vehicle_type_change' | 'time_shift' | 'trip_removal' | 'trip_addition' | 'parameter_change';
  description: string;
  affectedElements: string[];
}

interface WhatIfResult {
  scenario: WhatIfScenario;
  originalCost: number;
  newCost: number;
  costDifference: number;
  costDifferencePercent: number;
  feasible: boolean;
  warnings: string[];
  recommendations: string[];
}

interface WhatIfPanelProps {
  scheduleId: number;
  originalCost: number;
}

const WhatIfPanel: React.FC<WhatIfPanelProps> = ({ scheduleId, originalCost }) => {
  const [simulationType, setSimulationType] = useState<string>('vehicle_type_change');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reotimização REAL — chama POST /whatif/run-real e polla o resultado.
  const [realAlgorithm, setRealAlgorithm] = useState<string>('hybrid_pipeline');
  const [realTimeBudget, setRealTimeBudget] = useState<string>('60');
  const [realCctPenalty, setRealCctPenalty] = useState<string>('500');
  const [realCostVehicle, setRealCostVehicle] = useState<string>('1000');
  const [realCostKm, setRealCostKm] = useState<string>('1.0');
  const [realLoading, setRealLoading] = useState(false);
  const [realError, setRealError] = useState<string | null>(null);
  const [realRun, setRealRun] = useState<any | null>(null);
  const [realScenarioId, setRealScenarioId] = useState<string | null>(null);

  // Polling enquanto run real está running/pending
  React.useEffect(() => {
    if (!realScenarioId || !realRun) return;
    if (realRun.status !== 'running' && realRun.status !== 'pending') return;
    const t = setInterval(async () => {
      try {
        const updated = await scenariosApi.getScenarioRun(scheduleId, realScenarioId);
        if (updated) setRealRun(updated);
      } catch {
        // ignore — silencioso para polling
      }
    }, 5000);
    return () => clearInterval(t);
  }, [realScenarioId, realRun, scheduleId]);

  const handleRunReal = async () => {
    setRealLoading(true);
    setRealError(null);
    setRealRun(null);
    setRealScenarioId(null);
    try {
      const paramsOverride: Record<string, any> = {
        time_budget_s: Number(realTimeBudget) || 60,
        cct_violation_penalty: Number(realCctPenalty) || 500,
        cost_vehicle: Number(realCostVehicle) || 1000,
        cost_km: Number(realCostKm) || 1,
      };
      const submission = await scenariosApi.whatIfRunReal(scheduleId, {
        paramsOverride,
        label: 'panel',
        algorithm: realAlgorithm,
      });
      setRealScenarioId(submission.scenarioId);
      setRealRun(submission);
    } catch (err: any) {
      setRealError(err?.response?.data?.message || 'Falha ao enfileirar reotimização real.');
    } finally {
      setRealLoading(false);
    }
  };

  // Vehicle type change parameters
  const [fromTypeId, setFromTypeId] = useState('1');
  const [toTypeId, setToTypeId] = useState('2');
  const [fromTypeCost, setFromTypeCost] = useState('800');
  const [toTypeCost, setToTypeCost] = useState('1200');
  const [tripCount, setTripCount] = useState('5');

  // Time shift parameters
  const [shiftMinutes, setShiftMinutes] = useState('0');
  const [shiftTripCount, setShiftTripCount] = useState('5');

  // Trip removal parameters
  const [tripCost, setTripCost] = useState('500');
  const [vehicleFixedCost, setVehicleFixedCost] = useState('800');
  const [vehicleUsageCount, setVehicleUsageCount] = useState('1');

  // Trip addition parameters
  const [newTripCost, setNewTripCost] = useState('300');
  const [willNeedNewVehicle, setWillNeedNewVehicle] = useState('false');
  const [newVehicleFixedCost, setNewVehicleFixedCost] = useState('800');

  // Parameter change parameters
  const [parameterName, setParameterName] = useState('min_break_minutes');
  const [oldValue, setOldValue] = useState('15');
  const [newValue, setNewValue] = useState('30');

  const handleSimulate = async () => {
    try {
      setLoading(true);
      setError(null);
      let data;
      switch (simulationType) {
        case 'vehicle_type_change':
          data = await scenariosApi.whatIfVehicleType({
            originalCost,
            fromTypeId: parseInt(fromTypeId),
            toTypeId: parseInt(toTypeId),
            fromTypeCost: parseFloat(fromTypeCost),
            toTypeCost: parseFloat(toTypeCost),
            tripCount: parseInt(tripCount),
          });
          break;
        case 'time_shift':
          data = await scenariosApi.whatIfTimeShift({
            originalCost,
            shiftMinutes: parseInt(shiftMinutes),
            tripCount: parseInt(shiftTripCount),
          });
          break;
        case 'trip_removal':
          data = await scenariosApi.whatIfTripRemoval({
            originalCost,
            tripCost: parseFloat(tripCost),
            vehicleFixedCost: parseFloat(vehicleFixedCost),
            vehicleUsageCount: parseInt(vehicleUsageCount),
          });
          break;
        case 'trip_addition':
          data = await scenariosApi.whatIfTripAddition({
            originalCost,
            newTripCost: parseFloat(newTripCost),
            willNeedNewVehicle: willNeedNewVehicle === 'true',
            newVehicleFixedCost: parseFloat(newVehicleFixedCost),
          });
          break;
        case 'parameter_change':
          data = await scenariosApi.whatIfParameterChange({
            originalCost,
            parameter: parameterName,
            oldValue: isNaN(Number(oldValue)) ? oldValue : Number(oldValue),
            newValue: isNaN(Number(newValue)) ? newValue : Number(newValue),
          });
          break;
        default:
          setError('Tipo de simulação inválido');
          return;
      }

      setResult(data);
    } catch (err) {
      setError('Erro ao executar simulação');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      {/* Reotimização Real — chama o motor de otimização Python com overrides. Não é heurística. */}
      <Card sx={{ mb: 3, border: '2px solid #1976d2' }}>
        <CardHeader
          title="Reotimização Real (chama o motor)"
          avatar={<IconBolt size={20} />}
          subheader="Enfileira uma nova execução completa do solver com os parâmetros abaixo. Tempo: 30–120s."
        />
        <CardContent>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <FormControl fullWidth size="small">
                <InputLabel>Algoritmo</InputLabel>
                <Select
                  label="Algoritmo"
                  value={realAlgorithm}
                  onChange={(e) => setRealAlgorithm(e.target.value)}
                >
                  <MenuItem value="hybrid_pipeline">hybrid_pipeline (recomendado)</MenuItem>
                  <MenuItem value="mcnf">mcnf (rápido, VSP puro)</MenuItem>
                  <MenuItem value="vcsp_pulp">vcsp_pulp (ILP exato)</MenuItem>
                  <MenuItem value="sa">sa (simulated annealing)</MenuItem>
                  <MenuItem value="ts">ts (tabu search)</MenuItem>
                  <MenuItem value="genetic">genetic (GA)</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <TextField
                fullWidth
                size="small"
                label="Time budget (s)"
                type="number"
                value={realTimeBudget}
                onChange={(e) => setRealTimeBudget(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <TextField
                fullWidth
                size="small"
                label="Penalty CCT"
                type="number"
                value={realCctPenalty}
                onChange={(e) => setRealCctPenalty(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <TextField
                fullWidth
                size="small"
                label="Custo veículo R$"
                type="number"
                value={realCostVehicle}
                onChange={(e) => setRealCostVehicle(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 3, md: 2 }}>
              <TextField
                fullWidth
                size="small"
                label="Custo/km R$"
                type="number"
                value={realCostKm}
                onChange={(e) => setRealCostKm(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 1 }}>
              <Button
                fullWidth
                variant="contained"
                startIcon={realLoading ? <CircularProgress size={14} /> : <IconBolt size={18} />}
                onClick={handleRunReal}
                disabled={realLoading || (realRun && (realRun.status === 'running' || realRun.status === 'pending'))}
              >
                {realLoading ? '...' : 'Rodar'}
              </Button>
            </Grid>
          </Grid>

          {realError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {realError}
            </Alert>
          )}

          {realRun && (
            <Box sx={{ mt: 3 }}>
              <Stack spacing={1}>
                <Stack sx={{ flexDirection: 'row', alignItems: 'center', gap: 1 }}>
                  <Chip
                    label={realRun.status}
                    size="small"
                    color={
                      realRun.status === 'completed'
                        ? 'success'
                        : realRun.status === 'failed'
                          ? 'error'
                          : 'warning'
                    }
                    icon={
                      realRun.status === 'completed' ? (
                        <IconCheck size={14} />
                      ) : realRun.status === 'failed' ? (
                        <IconAlertTriangle size={14} />
                      ) : (
                        <IconRefresh size={14} />
                      )
                    }
                  />
                  <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                    run #{realRun.optimizationRunId ?? realRun.id} · {realRun.algorithm ?? realAlgorithm}
                  </Typography>
                  {realRun.inputFingerprint && (
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      fp: {String(realRun.inputFingerprint).slice(0, 12)}
                    </Typography>
                  )}
                </Stack>

                {realRun.status === 'completed' && realRun.metrics && (
                  <Grid container spacing={2}>
                    <Grid size={{ xs: 6, sm: 3 }}>
                      <Typography variant="caption" color="textSecondary">
                        Custo total
                      </Typography>
                      <Typography variant="h6">
                        R$ {Number(realRun.metrics.totalCost ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
                      </Typography>
                      {originalCost > 0 && (
                        <Typography
                          variant="caption"
                          sx={{
                            color:
                              Number(realRun.metrics.totalCost ?? 0) < originalCost ? 'success.main' : 'error.main',
                          }}
                        >
                          {Number(realRun.metrics.totalCost ?? 0) < originalCost ? '−' : '+'}R${' '}
                          {Math.abs(Number(realRun.metrics.totalCost ?? 0) - originalCost).toLocaleString('pt-BR', {
                            maximumFractionDigits: 2,
                          })}{' '}
                          vs baseline
                        </Typography>
                      )}
                    </Grid>
                    <Grid size={{ xs: 6, sm: 3 }}>
                      <Typography variant="caption" color="textSecondary">
                        Veículos
                      </Typography>
                      <Typography variant="h6">{realRun.metrics.numVehicles ?? '—'}</Typography>
                    </Grid>
                    <Grid size={{ xs: 6, sm: 3 }}>
                      <Typography variant="caption" color="textSecondary">
                        Duties / órfãs
                      </Typography>
                      <Typography variant="h6">
                        {realRun.metrics.numDuties ?? '—'} / {realRun.metrics.unassignedTrips ?? 0}
                      </Typography>
                    </Grid>
                    <Grid size={{ xs: 6, sm: 3 }}>
                      <Typography variant="caption" color="textSecondary">
                        Gini / Violações CCT
                      </Typography>
                      <Typography variant="h6">
                        {realRun.metrics.fairnessGini ?? '—'} / {realRun.metrics.cctViolations ?? 0}
                      </Typography>
                    </Grid>
                  </Grid>
                )}
                {realRun.status === 'failed' && (
                  <Alert severity="error">{realRun.errorMessage || 'Falha desconhecida.'}</Alert>
                )}
                {(realRun.status === 'running' || realRun.status === 'pending') && (
                  <Alert severity="info" icon={<IconRefresh size={18} />}>
                    Otimizador Python rodando… polling a cada 5s.
                  </Alert>
                )}
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="What-If Simulator (heurística rápida)"
          avatar={<IconWand size={20} />}
          subheader="Estimativa escalar — NÃO chama o solver. Use para sentir o impacto. Para resultado real, use o card acima."
        />
        <CardContent>
          <Stack spacing={3}>
            <FormControl fullWidth>
              <InputLabel>Tipo de Simulação</InputLabel>
              <Select
                value={simulationType}
                onChange={(e) => {
                  setSimulationType(e.target.value);
                  setResult(null);
                }}
                label="Tipo de Simulação"
              >
                <MenuItem value="vehicle_type_change">Mudança de Tipo de Veículo</MenuItem>
                <MenuItem value="time_shift">Adiamento de Horário</MenuItem>
                <MenuItem value="trip_removal">Remoção de Viagem</MenuItem>
                <MenuItem value="trip_addition">Adição de Viagem</MenuItem>
                <MenuItem value="parameter_change">Mudança de Parâmetro</MenuItem>
              </Select>
            </FormControl>

            {simulationType === 'vehicle_type_change' && (
              <Stack spacing={2}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Tipo De Veículo (De)"
                      type="number"
                      value={fromTypeId}
                      onChange={(e) => setFromTypeId(e.target.value)}
                      slotProps={{ htmlInput: { min: 1 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Tipo De Veículo (Para)"
                      type="number"
                      value={toTypeId}
                      onChange={(e) => setToTypeId(e.target.value)}
                      slotProps={{ htmlInput: { min: 1 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Custo Do Tipo 1 (R$/dia)"
                      type="number"
                      value={fromTypeCost}
                      onChange={(e) => setFromTypeCost(e.target.value)}
                      slotProps={{ htmlInput: { step: '0.01', min: 0 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Custo Do Tipo 2 (R$/dia)"
                      type="number"
                      value={toTypeCost}
                      onChange={(e) => setToTypeCost(e.target.value)}
                      slotProps={{ htmlInput: { step: '0.01', min: 0 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12 }}>
                    <TextField
                      fullWidth
                      label="Quantidade De Viagens"
                      type="number"
                      value={tripCount}
                      onChange={(e) => setTripCount(e.target.value)}
                      slotProps={{ htmlInput: { min: 1 } }}
                    />
                  </Grid>
                </Grid>
              </Stack>
            )}

            {simulationType === 'time_shift' && (
              <Stack spacing={2}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Adiamento (Minutos)"
                      type="number"
                      value={shiftMinutes}
                      onChange={(e) => setShiftMinutes(e.target.value)}
                      helperText="Negativo = antecipação, Positivo = adiamento"
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Quantidade De Viagens"
                      type="number"
                      value={shiftTripCount}
                      onChange={(e) => setShiftTripCount(e.target.value)}
                      slotProps={{ htmlInput: { min: 1 } }}
                    />
                  </Grid>
                </Grid>
              </Stack>
            )}

            {simulationType === 'trip_removal' && (
              <Stack spacing={2}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Custo Da Viagem (R$)"
                      type="number"
                      value={tripCost}
                      onChange={(e) => setTripCost(e.target.value)}
                      slotProps={{ htmlInput: { step: '0.01', min: 0 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Custo Fixo Do Veículo (R$)"
                      type="number"
                      value={vehicleFixedCost}
                      onChange={(e) => setVehicleFixedCost(e.target.value)}
                      slotProps={{ htmlInput: { step: '0.01', min: 0 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12 }}>
                    <TextField
                      fullWidth
                      label="Uso Do Veículo (Contagem)"
                      type="number"
                      value={vehicleUsageCount}
                      onChange={(e) => setVehicleUsageCount(e.target.value)}
                      slotProps={{ htmlInput: { min: 1 } }}
                    />
                  </Grid>
                </Grid>
              </Stack>
            )}

            {simulationType === 'trip_addition' && (
              <Stack spacing={2}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Custo Da Nova Viagem (R$)"
                      type="number"
                      value={newTripCost}
                      onChange={(e) => setNewTripCost(e.target.value)}
                      slotProps={{ htmlInput: { step: '0.01', min: 0 } }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <FormControl fullWidth>
                      <InputLabel>Precisa De Novo Veículo?</InputLabel>
                      <Select
                        value={willNeedNewVehicle}
                        onChange={(e) => setWillNeedNewVehicle(e.target.value)}
                        label="Precisa De Novo Veículo?"
                      >
                        <MenuItem value="false">Não</MenuItem>
                        <MenuItem value="true">Sim</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid size={{ xs: 12 }}>
                    <TextField
                      fullWidth
                      label="Custo Fixo Do Novo Veículo (R$)"
                      type="number"
                      value={newVehicleFixedCost}
                      onChange={(e) => setNewVehicleFixedCost(e.target.value)}
                      slotProps={{ htmlInput: { step: '0.01', min: 0 } }}
                    />
                  </Grid>
                </Grid>
              </Stack>
            )}

            {simulationType === 'parameter_change' && (
              <Stack spacing={2}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <FormControl fullWidth>
                      <InputLabel>Parâmetro</InputLabel>
                      <Select
                        value={parameterName}
                        onChange={(e) => setParameterName(e.target.value)}
                        label="Parâmetro"
                      >
                        <MenuItem value="min_break_minutes">Minutos Mínimo De Pausa</MenuItem>
                        <MenuItem value="vehicle_preference">Preferência De Veículo</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Valor Antigo"
                      value={oldValue}
                      onChange={(e) => setOldValue(e.target.value)}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      fullWidth
                      label="Novo Valor"
                      value={newValue}
                      onChange={(e) => setNewValue(e.target.value)}
                    />
                  </Grid>
                </Grid>
              </Stack>
            )}

            <Button
              variant="contained"
              size="large"
              onClick={handleSimulate}
              disabled={loading}
              fullWidth
            >
              {loading ? <CircularProgress size={24} /> : 'Simular'}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {error && <Alert severity="error">{error}</Alert>}

      {result && (
        <Card>
          <CardHeader title="Resultado da Simulação" />
          <CardContent>
            <Stack spacing={3}>
              <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  {result.scenario.description}
                </Typography>
                <Stack spacing={0.5}>
                  {result.scenario.affectedElements.map((elem, idx) => (
                    <Typography key={idx} variant="body2">
                      • {elem}
                    </Typography>
                  ))}
                </Stack>
              </Box>

              <Divider />

              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <Box>
                    <Typography variant="caption" color="textSecondary">
                      Custo Original
                    </Typography>
                    <Typography variant="h6">
                      R$ {result.originalCost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                    </Typography>
                  </Box>
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <Box>
                    <Typography variant="caption" color="textSecondary">
                      Novo Custo
                    </Typography>
                    <Typography variant="h6" sx={{ color: result.newCost < result.originalCost ? '#2e7d32' : '#d32f2f' }}>
                      R$ {result.newCost.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              <Alert
                severity={result.costDifference < 0 ? 'success' : 'warning'}
                icon={result.costDifference < 0 ? <IconCheck size={20} /> : <IconAlertTriangle size={20} />}
              >
                <Box sx={{ fontWeight: 600 }}>
                  {result.costDifference < 0 ? 'Economia: ' : 'Custo Adicional: '}
                  R$ {Math.abs(result.costDifference).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
                  <Typography component="div" variant="caption" sx={{ mt: 0.5 }}>
                    ({(result.costDifferencePercent ?? 0).toFixed(1)}%)
                  </Typography>
                </Box>
              </Alert>

              {!result.feasible && (
                <Alert severity="error">
                  Esta mudança não é viável operacionalmente.
                </Alert>
              )}

              {result.warnings.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    Advertências
                  </Typography>
                  <Stack spacing={1}>
                    {result.warnings.map((warning, idx) => (
                      <Chip key={idx} label={warning} variant="outlined" color="warning" />
                    ))}
                  </Stack>
                </Box>
              )}

              {result.recommendations.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    Recomendações
                  </Typography>
                  <Stack spacing={1}>
                    {result.recommendations.map((rec, idx) => (
                      <Typography key={idx} variant="body2">
                        ✓ {rec}
                      </Typography>
                    ))}
                  </Stack>
                </Box>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default WhatIfPanel;
