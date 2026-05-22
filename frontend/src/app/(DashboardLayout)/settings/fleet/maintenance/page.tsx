'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Grid,
  Typography,
  Tab,
  Tabs,
  Card,
  CardContent,
  CircularProgress,
  Alert,
} from '@mui/material';
import MaintenanceScheduler from '@/app/components/shared/MaintenanceScheduler';
import VehicleHealthStatus from '@/app/components/shared/VehicleHealthStatus';
import { vehiclesApi } from '@/lib/api';

interface Vehicle {
  id: number;
  vehicleId: string;
  typeId: number;
  isActive: boolean;
}

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
      id={`maintenance-tabpanel-${index}`}
      aria-labelledby={`maintenance-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

export default function VehicleMaintenancePage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState(0);

  useEffect(() => {
    fetchVehicles();
  }, []);

  const fetchVehicles = async () => {
    try {
      setLoading(true);
      const data = await vehiclesApi.getActive();
      setVehicles(data);
    } catch (err) {
      setError('Erro ao carregar veículos');
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setSelectedTab(newValue);
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error">{error}</Alert>
      </Container>
    );
  }

  if (vehicles.length === 0) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="info">Nenhum veículo ativo para gerenciar manutenção</Alert>
      </Container>
    );
  }

  const selectedVehicle = vehicles[selectedTab];

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" sx={{ mb: 4 }}>
        Gerenciamento de Manutenção
      </Typography>

      <Card sx={{ mb: 4 }}>
        <Tabs
          value={selectedTab}
          onChange={handleTabChange}
          aria-label="vehicle maintenance tabs"
          variant="scrollable"
          scrollButtons="auto"
        >
          {vehicles.map((vehicle, index) => (
            <Tab
              key={vehicle.id}
              label={vehicle.vehicleId}
              id={`maintenance-tab-${index}`}
              aria-controls={`maintenance-tabpanel-${index}`}
            />
          ))}
        </Tabs>
      </Card>

      {selectedVehicle && (
        <Grid container spacing={3}>
          {/* Health Status */}
          <Grid size={{ xs: 12, md: 6 }}>
            <VehicleHealthStatus vehicleId={selectedVehicle.id} />
          </Grid>

          {/* Maintenance Scheduler */}
          <Grid size={{ xs: 12, md: 6 }}>
            <MaintenanceScheduler
              vehicleId={selectedVehicle.id}
              vehicleLabel={selectedVehicle.vehicleId}
            />
          </Grid>
        </Grid>
      )}
    </Container>
  );
}
