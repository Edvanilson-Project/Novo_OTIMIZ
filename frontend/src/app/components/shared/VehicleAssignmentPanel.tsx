'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  CircularProgress,
  Alert,
  Stack,
  Typography,
  Chip,
} from '@mui/material';
import { IconCheck, IconX, IconTruck } from '@tabler/icons-react';

interface Vehicle {
  id: number;
  vehicleId: string;
  typeId: number;
  isActive: boolean;
  licensePlate?: string;
}

interface VehicleType {
  id: number;
  name: string;
  capacity: number;
  costPerDay: number;
}

interface Block {
  id: number;
  blockId: number;
  vehicleId?: number;
  cost?: number;
}

interface VehicleAssignmentPanelProps {
  block: Block;
  vehicleTypes: VehicleType[];
  onAssignmentChange: (blockId: number, vehicleId: number | null) => Promise<void>;
}

const VehicleAssignmentPanel: React.FC<VehicleAssignmentPanelProps> = ({
  block,
  vehicleTypes,
  onAssignmentChange,
}) => {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<number | null>(block.vehicleId || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchVehicles();
  }, []);

  const fetchVehicles = async () => {
    try {
      const response = await fetch('/api/vehicles/active');
      if (response.ok) {
        const data = await response.json();
        setVehicles(data);
      }
    } catch (err) {
      setError('Erro ao carregar veículos');
    }
  };

  const handleAssignment = async () => {
    if (selectedVehicle === null) {
      setError('Selecione um veículo');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await onAssignmentChange(block.id, selectedVehicle);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao atribuir veículo');
    } finally {
      setLoading(false);
    }
  };

  const handleUnassign = async () => {
    try {
      setLoading(true);
      setError(null);
      await onAssignmentChange(block.id, null);
      setSelectedVehicle(null);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao desatribuir veículo');
    } finally {
      setLoading(false);
    }
  };

  const currentVehicle = vehicles.find((v) => v.id === selectedVehicle);
  const currentVehicleType = currentVehicle
    ? vehicleTypes.find((t) => t.id === currentVehicle.typeId)
    : null;

  return (
    <Card>
      <CardHeader
        title={`Bloco ${block.blockId}`}
        avatar={<IconTruck size={20} />}
        subheader={`Custo: R$ ${(block.cost || 0).toFixed(2)}`}
      />
      <CardContent>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          {success && <Alert severity="success">Veículo atribuído com sucesso!</Alert>}

          {currentVehicle && (
            <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
              <Typography variant="caption" color="textSecondary">
                Veículo Atualmente Atribuído
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {currentVehicle.vehicleId}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Chip
                  label={currentVehicleType?.name || 'Desconhecido'}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={`${currentVehicleType?.capacity || 0} pass.`}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={`R$ ${currentVehicleType?.costPerDay.toFixed(0)}/dia`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              </Stack>
            </Box>
          )}

          <FormControl fullWidth>
            <InputLabel>Selecionar Veículo</InputLabel>
            <Select
              value={selectedVehicle || ''}
              label="Selecionar Veículo"
              onChange={(e) => setSelectedVehicle(e.target.value ? Number(e.target.value) : null)}
              disabled={loading}
            >
              <MenuItem value="">Sem atribuição</MenuItem>
              {vehicles.map((vehicle) => {
                const vtype = vehicleTypes.find((t) => t.id === vehicle.typeId);
                return (
                  <MenuItem key={vehicle.id} value={vehicle.id}>
                    {vehicle.vehicleId} ({vtype?.name || 'Desconhecido'})
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>

          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              color="primary"
              onClick={handleAssignment}
              disabled={loading || selectedVehicle === block.vehicleId}
              startIcon={loading ? <CircularProgress size={20} /> : <IconCheck size={20} />}
              fullWidth
            >
              {loading ? 'Atribuindo...' : 'Atribuir'}
            </Button>
            {block.vehicleId && (
              <Button
                variant="outlined"
                color="error"
                onClick={handleUnassign}
                disabled={loading}
                startIcon={<IconX size={20} />}
              >
                Desatribuir
              </Button>
            )}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default VehicleAssignmentPanel;
