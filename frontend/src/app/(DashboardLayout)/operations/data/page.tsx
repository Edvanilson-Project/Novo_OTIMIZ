"use client";

import React, { useEffect, useState } from "react";
import {
  Box,
  Grid,
  Stack,
  Button,
  Tabs,
  Tab,
  Alert,
  Snackbar,
  CircularProgress,
  Paper,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import { IconUpload, IconFileSpreadsheet, IconUsers } from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import ParentCard from "@/app/components/shared/ParentCard";
import { operationsApi } from "@/lib/api";
import { minToHHMM } from "@/lib/format";

export default function OperationsDataPage() {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [trips, setTrips] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [notification, setNotification] = useState({ open: false, message: "", severity: "success" });

  useEffect(() => {
    fetchData();
  }, [activeTab]);

  const fetchData = async () => {
    setLoading(true);
    try {
      if (activeTab === 0) {
        const data = await operationsApi.getTrips();
        setTrips(Array.isArray(data) ? data : data.data ?? []);
      } else {
        const data = await operationsApi.getDrivers();
        setDrivers(Array.isArray(data) ? data : data.data ?? []);
      }
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", activeTab === 0 ? "trips" : "drivers");

    try {
      await operationsApi.upload(formData);
      setNotification({ open: true, message: "Upload concluído com sucesso!", severity: "success" });
      fetchData();
    } catch (error: any) {
      setNotification({
        open: true,
        message: error.response?.data?.message || "Erro no upload.",
        severity: "error",
      });
    } finally {
      setUploading(false);
    }
  };

  const tripColumns: GridColDef[] = [
    { field: "tripId", headerName: "ID Viagem", width: 120 },
    { field: "lineId", headerName: "Linha", width: 100 },
    { field: "startTime", headerName: "Início", width: 120, renderCell: (params) => minToHHMM(params.value) },
    { field: "endTime", headerName: "Fim", width: 120, renderCell: (params) => minToHHMM(params.value) },
    { field: "duration", headerName: "Duração (min)", width: 130 },
    { field: "originId", headerName: "Origem", width: 100 },
    { field: "destinationId", headerName: "Destino", width: 100 },
    { field: "distanceKm", headerName: "Distância (km)", width: 130 },
  ];

  const driverColumns: GridColDef[] = [
    { field: "driverId", headerName: "ID Registro", width: 150 },
    { field: "name", headerName: "Nome Completo", flex: 1 },
    { field: "role", headerName: "Função", width: 150 },
    { field: "maxHoursPerDay", headerName: "Limite Jornada (min)", width: 180 },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard title="Gestão de Dados Operacionais" subtitle="Injete as escalas brute para o motor de otimização">
        <Stack spacing={3}>
          {/* Header com Upload e Tabs */}
          <Paper variant="outlined" sx={{ p: 2, backgroundColor: "background.default" }}>
            <Grid container spacing={2} sx={{ alignItems: "center" }}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
                  <Tab icon={<IconFileSpreadsheet size={20} />} label="Viagens (Trips)" />
                  <Tab icon={<IconUsers size={20} />} label="Motoristas (Drivers)" />
                </Tabs>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }} sx={{ textAlign: "right" }}>
                <Button
                  variant="contained"
                  component="label"
                  startIcon={uploading ? <CircularProgress size={20} color="inherit" /> : <IconUpload size={20} />}
                  disabled={uploading}
                >
                  {uploading ? "Processando..." : `Importar ${activeTab === 0 ? "Viagens" : "Motoristas"}`}
                  <input type="file" hidden accept=".xlsx, .csv" onChange={handleFileUpload} />
                </Button>
              </Grid>
            </Grid>
          </Paper>

          {/* Área de Dados */}
          <ParentCard title={activeTab === 0 ? "Viagens Carregadas" : "Base de Motoristas"}>
            <Box sx={{ height: 600, width: "100%", mt: 2 }}>
              <DataGrid
                rows={activeTab === 0 ? trips : drivers}
                columns={activeTab === 0 ? tripColumns : driverColumns}
                loading={loading}
                pageSizeOptions={[10, 25, 50]}
                initialState={{
                  pagination: { paginationModel: { pageSize: 10 } },
                }}
                getRowId={(row) => row.id} // UUID do banco
                disableRowSelectionOnClick
                sx={{
                  border: 0,
                  "& .MuiDataGrid-columnHeaders": {
                    backgroundColor: "action.hover",
                  },
                }}
              />
            </Box>
          </ParentCard>
        </Stack>
      </DashboardCard>

      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={() => setNotification({ ...notification, open: false })}
      >
        <Alert severity={notification.severity as any} sx={{ width: "100%" }}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
