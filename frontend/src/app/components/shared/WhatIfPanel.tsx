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
import { IconWand, IconAlertTriangle, IconCheck } from '@tabler/icons-react';
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
      <Card sx={{ mb: 3 }}>
        <CardHeader
          title="What-If Simulator"
          avatar={<IconWand size={20} />}
          subheader="Simule mudanças e veja o impacto nos custos"
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
