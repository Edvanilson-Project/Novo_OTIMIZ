'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  Stack,
  Typography,
} from '@mui/material';
import { IconPlus, IconCalendar, IconTrash } from '@tabler/icons-react';
import { vehiclesApi } from '@/lib/api';

interface Maintenance {
  id: number;
  vehicleId: number;
  maintenanceDate: string;
  maintenanceType: string;
  estimatedDurationHours: number;
  cost: number;
  status: string;
  description?: string;
}

interface MaintenanceSchedulerProps {
  vehicleId: number;
  vehicleLabel: string;
}

const MaintenanceScheduler: React.FC<MaintenanceSchedulerProps> = ({
  vehicleId,
  vehicleLabel,
}) => {
  const [maintenance, setMaintenance] = useState<Maintenance[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  const [formData, setFormData] = useState({
    maintenanceDate: new Date().toISOString().split('T')[0],
    maintenanceType: 'preventive',
    estimatedDurationHours: 4,
    cost: 500,
    description: '',
  });

  useEffect(() => {
    fetchMaintenance();
  }, [vehicleId]);

  const fetchMaintenance = async () => {
    try {
      setLoading(true);
      const data = await vehiclesApi.getMaintenance(vehicleId);
      setMaintenance(data);
    } catch (err) {
      setError('Erro ao carregar manutenções');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDialog = () => {
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setFormData({
      maintenanceDate: new Date().toISOString().split('T')[0],
      maintenanceType: 'preventive',
      estimatedDurationHours: 4,
      cost: 500,
      description: '',
    });
  };

  const handleSubmit = async () => {
    try {
      setError(null);
      await vehiclesApi.createMaintenance(vehicleId, formData);
      await fetchMaintenance();
      handleCloseDialog();
    } catch (err: any) {
      setError(err?.response?.data?.message || 'Erro ao agendar manutenção');
    }
  };

  const handleDelete = async (maintenanceId: number) => {
    try {
      setDeleting(maintenanceId);
      await vehiclesApi.updateMaintenance(vehicleId, maintenanceId, { status: 'cancelled' });
      await fetchMaintenance();
    } catch (err) {
      setError('Erro ao cancelar manutenção');
    } finally {
      setDeleting(null);
    }
  };

  const getStatusColor = (status: string): 'success' | 'warning' | 'error' | 'default' => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'in_progress':
        return 'warning';
      case 'cancelled':
        return 'error';
      default:
        return 'default';
    }
  };

  const getStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
      scheduled: 'Agendada',
      in_progress: 'Em Progresso',
      completed: 'Concluída',
      cancelled: 'Cancelada',
    };
    return labels[status] || status;
  };

  return (
    <Card>
      <CardHeader
        title="Agendamento de Manutenção"
        avatar={<IconCalendar size={20} />}
        action={
          <Button
            variant="contained"
            size="small"
            startIcon={<IconPlus size={16} />}
            onClick={handleOpenDialog}
          >
            Agendar
          </Button>
        }
        subheader={vehicleLabel}
      />
      <CardContent>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}

          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress />
            </Box>
          ) : maintenance.length === 0 ? (
            <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 3 }}>
              Nenhuma manutenção agendada
            </Typography>
          ) : (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                    <TableCell><strong>Data</strong></TableCell>
                    <TableCell><strong>Tipo</strong></TableCell>
                    <TableCell align="right"><strong>Duração (h)</strong></TableCell>
                    <TableCell align="right"><strong>Custo</strong></TableCell>
                    <TableCell><strong>Status</strong></TableCell>
                    <TableCell align="center"><strong>Ações</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {maintenance.map((m) => (
                    <TableRow key={m.id} hover>
                      <TableCell>
                        {new Date(m.maintenanceDate).toLocaleDateString('pt-BR')}
                      </TableCell>
                      <TableCell sx={{ textTransform: 'capitalize' }}>
                        {m.maintenanceType === 'preventive' && 'Preventiva'}
                        {m.maintenanceType === 'corrective' && 'Corretiva'}
                        {m.maintenanceType === 'inspection' && 'Inspeção'}
                      </TableCell>
                      <TableCell align="right">{m.estimatedDurationHours}</TableCell>
                      <TableCell align="right">R$ {m.cost.toFixed(2)}</TableCell>
                      <TableCell>
                        <Chip
                          label={getStatusLabel(m.status)}
                          color={getStatusColor(m.status)}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Button
                          size="small"
                          color="error"
                          onClick={() => handleDelete(m.id)}
                          disabled={deleting === m.id || m.status === 'completed'}
                          startIcon={
                            deleting === m.id ? (
                              <CircularProgress size={16} />
                            ) : (
                              <IconTrash size={16} />
                            )
                          }
                        >
                          Cancelar
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Stack>
      </CardContent>

      {/* Schedule Maintenance Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Agendar Manutenção</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Stack spacing={2}>
            <TextField
              fullWidth
              label="Data da Manutenção"
              type="date"
              value={formData.maintenanceDate}
              onChange={(e) =>
                setFormData({ ...formData, maintenanceDate: e.target.value })
              }
              slotProps={{ inputLabel: { shrink: true } }}
            />

            <FormControl fullWidth>
              <InputLabel>Tipo de Manutenção</InputLabel>
              <Select
                value={formData.maintenanceType}
                label="Tipo de Manutenção"
                onChange={(e) =>
                  setFormData({ ...formData, maintenanceType: e.target.value })
                }
              >
                <MenuItem value="preventive">Preventiva</MenuItem>
                <MenuItem value="corrective">Corretiva</MenuItem>
                <MenuItem value="inspection">Inspeção</MenuItem>
              </Select>
            </FormControl>

            <TextField
              fullWidth
              label="Duração Estimada (horas)"
              type="number"
              value={formData.estimatedDurationHours}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  estimatedDurationHours: parseInt(e.target.value) || 0,
                })
              }
            />

            <TextField
              fullWidth
              label="Custo Estimado (R$)"
              type="number"
              value={formData.cost}
              onChange={(e) =>
                setFormData({ ...formData, cost: parseFloat(e.target.value) || 0 })
              }
            />

            <TextField
              fullWidth
              label="Descrição"
              multiline
              rows={3}
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              placeholder="Detalhes da manutenção..."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancelar</Button>
          <Button onClick={handleSubmit} variant="contained">
            Agendar
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default MaintenanceScheduler;
