"use client";

import React, { useEffect, useState } from "react";
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
} from "@mui/material";
import {
  IconTruck,
  IconCurrencyDollar,
} from "@tabler/icons-react";

interface VehicleType {
  id: number;
  name: string;
  capacity: number;
  costPerDay: number;
  accessible: boolean;
}

interface FleetStats {
  vehicleTypes: VehicleType[];
  totalVehiclesAvailable: number;
  totalFleetCost: number;
  averageCostPerVehicle: number;
}

interface FleetCostAnalysisProps {
  companyId?: number;
}

const FleetCostAnalysis: React.FC<FleetCostAnalysisProps> = ({ companyId }) => {
  const [stats, setStats] = useState<FleetStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFleetData();
  }, [companyId]);

  const fetchFleetData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch vehicle types
      const typesRes = await fetch("/api/vehicles/types");
      if (!typesRes.ok) throw new Error("Erro ao carregar tipos de veículos");
      const types: VehicleType[] = await typesRes.json();

      // Fetch active vehicles
      const vehiclesRes = await fetch("/api/vehicles/active");
      if (!vehiclesRes.ok) throw new Error("Erro ao carregar veículos");
      const vehicles = await vehiclesRes.json();

      // Calculate statistics
      const totalVehicles = vehicles.length;
      const totalCost = types.reduce((sum, type) => sum + (type.costPerDay || 0), 0);
      const avgCost = totalVehicles > 0 ? totalCost / types.length : 0;

      setStats({
        vehicleTypes: types,
        totalVehiclesAvailable: totalVehicles,
        totalFleetCost: totalCost,
        averageCostPerVehicle: avgCost,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!stats || stats.vehicleTypes.length === 0) {
    return (
      <Alert severity="info">
        Nenhum tipo de veículo configurado. Configure tipos de veículos nas configurações de frota.
      </Alert>
    );
  }

  return (
    <Grid container spacing={3}>
      {/* Fleet Overview Cards */}
      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box
                sx={{
                  p: 1.5,
                  backgroundColor: "#e3f2fd",
                  borderRadius: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <IconTruck size={24} color="#1976d2" />
              </Box>
              <Box>
                <Typography variant="caption" color="textSecondary">
                  Veículos Ativos
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>
                  {stats.totalVehiclesAvailable}
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box
                sx={{
                  p: 1.5,
                  backgroundColor: "#f3e5f5",
                  borderRadius: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <IconTruck size={24} color="#7b1fa2" />
              </Box>
              <Box>
                <Typography variant="caption" color="textSecondary">
                  Tipos de Veículos
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>
                  {stats.vehicleTypes.length}
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box
                sx={{
                  p: 1.5,
                  backgroundColor: "#e8f5e9",
                  borderRadius: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <IconCurrencyDollar size={24} color="#388e3c" />
              </Box>
              <Box>
                <Typography variant="caption" color="textSecondary">
                  Custo Total/Dia
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>
                  R$ {stats.totalFleetCost.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box
                sx={{
                  p: 1.5,
                  backgroundColor: "#fff3e0",
                  borderRadius: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <IconCurrencyDollar size={24} color="#f57c00" />
              </Box>
              <Box>
                <Typography variant="caption" color="textSecondary">
                  Custo Médio
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>
                  R$ {stats.averageCostPerVehicle.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Detailed Vehicle Types Table */}
      <Grid size={{ xs: 12 }}>
        <Card>
          <CardHeader title="Tipos de Veículos - Análise Detalhada" />
          <CardContent>
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                    <TableCell><strong>Tipo</strong></TableCell>
                    <TableCell align="right"><strong>Capacidade</strong></TableCell>
                    <TableCell align="right"><strong>Custo/Dia</strong></TableCell>
                    <TableCell align="right"><strong>Custo/Passageiro/Dia</strong></TableCell>
                    <TableCell align="center"><strong>Acessível</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stats.vehicleTypes.map(type => (
                    <TableRow key={type.id} hover>
                      <TableCell sx={{ fontWeight: 600 }}>{type.name}</TableCell>
                      <TableCell align="right">{type.capacity} pass.</TableCell>
                      <TableCell align="right">
                        R$ {type.costPerDay.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell align="right">
                        R$ {(type.costPerDay / type.capacity).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell align="center">
                        {type.accessible ? (
                          <Typography variant="body2" sx={{ color: "green", fontWeight: 600 }}>
                            Sim
                          </Typography>
                        ) : (
                          <Typography variant="body2" sx={{ color: "textSecondary" }}>
                            Não
                          </Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};

export default FleetCostAnalysis;
