'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Container,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  FormControlLabel,
  Grid,
  Checkbox,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';

interface VehicleType {
  id: number;
  name: string;
  capacity: number;
  costPerDay: number;
  accessible: boolean;
  description?: string;
}

interface Vehicle {
  id: number;
  vehicleId: string;
  typeId: number;
  depotId: number;
  isActive: boolean;
  licensePlate?: string;
  odometer?: number;
  lastMaintenanceDate?: string;
}

export default function FleetManagementPage() {
  const [vehicleTypes, setVehicleTypes] = useState<VehicleType[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [openTypeDialog, setOpenTypeDialog] = useState(false);
  const [openVehicleDialog, setOpenVehicleDialog] = useState(false);
  const [editingType, setEditingType] = useState<VehicleType | null>(null);
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null);

  const [typeForm, setTypeForm] = useState({
    name: '',
    capacity: 40,
    costPerDay: 800,
    accessible: false,
    description: '',
  });

  const [vehicleForm, setVehicleForm] = useState({
    vehicleId: '',
    typeId: 1,
    depotId: 1,
    isActive: true,
    licensePlate: '',
    odometer: 0,
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [typesRes, vehiclesRes] = await Promise.all([
        fetch('/api/vehicles/types'),
        fetch('/api/vehicles'),
      ]);

      if (typesRes.ok) {
        setVehicleTypes(await typesRes.json());
      }
      if (vehiclesRes.ok) {
        setVehicles(await vehiclesRes.json());
      }
    } catch (error) {
      console.error('Erro ao carregar dados:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddVehicleType = async () => {
    try {
      const res = await fetch('/api/vehicles/types', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(typeForm),
      });

      if (res.ok) {
        setTypeForm({ name: '', capacity: 40, costPerDay: 800, accessible: false, description: '' });
        setOpenTypeDialog(false);
        fetchData();
      }
    } catch (error) {
      console.error('Erro ao criar tipo de veículo:', error);
    }
  };

  const handleAddVehicle = async () => {
    try {
      const res = await fetch('/api/vehicles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vehicleForm),
      });

      if (res.ok) {
        setVehicleForm({ vehicleId: '', typeId: 1, depotId: 1, isActive: true, licensePlate: '', odometer: 0 });
        setOpenVehicleDialog(false);
        fetchData();
      }
    } catch (error) {
      console.error('Erro ao criar veículo:', error);
    }
  };

  const getVehicleTypeName = (typeId: number) => {
    const type = vehicleTypes.find(t => t.id === typeId);
    return type?.name || 'Desconhecido';
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" sx={{ mb: 4 }}>
        Gerenciamento de Frota
      </Typography>

      <Grid container spacing={3}>
        {/* Vehicle Types Section */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardHeader
              title="Tipos de Veículos"
              action={
                <Button
                  variant="contained"
                  startIcon={<AddIcon />}
                  onClick={() => setOpenTypeDialog(true)}
                  size="small"
                >
                  Novo Tipo
                </Button>
              }
            />
            <CardContent>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                      <TableCell><strong>Nome</strong></TableCell>
                      <TableCell align="right"><strong>Capacidade</strong></TableCell>
                      <TableCell align="right"><strong>Custo/Dia</strong></TableCell>
                      <TableCell align="center"><strong>Ações</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vehicleTypes.map(type => (
                      <TableRow key={type.id}>
                        <TableCell>{type.name}</TableCell>
                        <TableCell align="right">{type.capacity} pass.</TableCell>
                        <TableCell align="right">R$ {type.costPerDay.toFixed(2)}</TableCell>
                        <TableCell align="center">
                          <Button size="small" variant="outlined" startIcon={<EditIcon />}>
                            Editar
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {vehicleTypes.length === 0 && !loading && (
                <Typography variant="body2" color="textSecondary" sx={{ mt: 2, textAlign: 'center' }}>
                  Nenhum tipo de veículo configurado
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Vehicles Section */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardHeader
              title="Veículos da Frota"
              action={
                <Button
                  variant="contained"
                  startIcon={<AddIcon />}
                  onClick={() => setOpenVehicleDialog(true)}
                  size="small"
                >
                  Novo Veículo
                </Button>
              }
            />
            <CardContent>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                      <TableCell><strong>ID</strong></TableCell>
                      <TableCell><strong>Tipo</strong></TableCell>
                      <TableCell><strong>Placa</strong></TableCell>
                      <TableCell align="center"><strong>Status</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vehicles.map(vehicle => (
                      <TableRow key={vehicle.id}>
                        <TableCell>{vehicle.vehicleId}</TableCell>
                        <TableCell>{getVehicleTypeName(vehicle.typeId)}</TableCell>
                        <TableCell>{vehicle.licensePlate || '-'}</TableCell>
                        <TableCell align="center">
                          <Typography
                            variant="body2"
                            sx={{
                              color: vehicle.isActive ? 'green' : 'red',
                              fontWeight: 'bold',
                            }}
                          >
                            {vehicle.isActive ? 'Ativo' : 'Inativo'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {vehicles.length === 0 && !loading && (
                <Typography variant="body2" color="textSecondary" sx={{ mt: 2, textAlign: 'center' }}>
                  Nenhum veículo cadastrado
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Vehicle Type Dialog */}
      <Dialog open={openTypeDialog} onClose={() => setOpenTypeDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Novo Tipo de Veículo</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            fullWidth
            label="Nome"
            value={typeForm.name}
            onChange={e => setTypeForm({ ...typeForm, name: e.target.value })}
            margin="normal"
            placeholder="Ex: BUS, MINIBUS, COACH"
          />
          <TextField
            fullWidth
            label="Capacidade (passageiros)"
            type="number"
            value={typeForm.capacity}
            onChange={e => setTypeForm({ ...typeForm, capacity: parseInt(e.target.value) })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Custo por Dia (R$)"
            type="number"
            value={typeForm.costPerDay}
            onChange={e => setTypeForm({ ...typeForm, costPerDay: parseFloat(e.target.value) })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Descrição"
            value={typeForm.description}
            onChange={e => setTypeForm({ ...typeForm, description: e.target.value })}
            margin="normal"
            multiline
            rows={2}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={typeForm.accessible}
                onChange={e => setTypeForm({ ...typeForm, accessible: e.target.checked })}
              />
            }
            label="Acessível (PCD)"
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenTypeDialog(false)}>Cancelar</Button>
          <Button onClick={handleAddVehicleType} variant="contained">
            Salvar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Vehicle Dialog */}
      <Dialog open={openVehicleDialog} onClose={() => setOpenVehicleDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Novo Veículo</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            fullWidth
            label="ID do Veículo"
            value={vehicleForm.vehicleId}
            onChange={e => setVehicleForm({ ...vehicleForm, vehicleId: e.target.value })}
            margin="normal"
            placeholder="Ex: BUS-001, COACH-005"
          />
          <FormControl fullWidth margin="normal">
            <InputLabel>Tipo de Veículo</InputLabel>
            <Select
              value={vehicleForm.typeId}
              label="Tipo de Veículo"
              onChange={e => setVehicleForm({ ...vehicleForm, typeId: e.target.value as number })}
            >
              {vehicleTypes.map(type => (
                <MenuItem key={type.id} value={type.id}>
                  {type.name} ({type.capacity} pass.)
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            fullWidth
            label="Placa"
            value={vehicleForm.licensePlate}
            onChange={e => setVehicleForm({ ...vehicleForm, licensePlate: e.target.value })}
            margin="normal"
            placeholder="Ex: ABC-1234"
          />
          <TextField
            fullWidth
            label="Odômetro (km)"
            type="number"
            value={vehicleForm.odometer}
            onChange={e => setVehicleForm({ ...vehicleForm, odometer: parseFloat(e.target.value) })}
            margin="normal"
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={vehicleForm.isActive}
                onChange={e => setVehicleForm({ ...vehicleForm, isActive: e.target.checked })}
              />
            }
            label="Ativo"
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenVehicleDialog(false)}>Cancelar</Button>
          <Button onClick={handleAddVehicle} variant="contained">
            Salvar
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
