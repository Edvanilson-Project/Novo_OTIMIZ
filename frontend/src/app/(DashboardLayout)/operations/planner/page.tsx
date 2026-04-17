"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  Box,
  Typography,
  Stack,
  Button,
  CircularProgress,
  Alert,
  Snackbar,
  Paper,
  Grid,
} from "@mui/material";
import { IconBolt, IconRefresh } from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import DashboardKPIs from "@/app/components/shared/DashboardKPIs";
import { TabGantt } from "./_components/TabGantt";
import { getSocket, disconnectSocket } from "@/lib/socket";
import { linesApi, terminalsApi, operationsApi } from "@/lib/api";
import { type TripIntervalPolicy } from "./_helpers/formatters";


export default function PlannerPage() {
  const [mounted, setMounted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [schedule, setSchedule] = useState<any>(null);
  const [lines, setLines] = useState<any[]>([]);
  const [terminals, setTerminals] = useState<any[]>([]);
  const [notification, setNotification] = useState({
    open: false,
    message: "",
    severity: "info" as "info" | "success" | "warning" | "error",
  });
  const companyId = 1; // Dev: bypass auth

  const intervalPolicy: TripIntervalPolicy = useMemo(() => ({
    minBreakMinutes: 30,
    mealBreakMinutes: 60,
    minLayoverMinutes: 8,
    connectionToleranceMinutes: 0
  }), []);

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [scheduleRes, linesRes, terminalsRes] = await Promise.all([
        operationsApi.getLatestSchedule(),
        linesApi.getAll({ companyId }),
        terminalsApi.getAll({ companyId })
      ]);

      setSchedule(scheduleRes);
      setLines(linesRes);
      setTerminals(terminalsRes);

      if (scheduleRes.data?.status === "processing") {
        setOptimizing(true);
      }
    } catch (error) {
      console.error("Erro ao buscar dados do planejador:", error);
      setNotification({
        open: true,
        message: "Erro ao carregar dados iniciais.",
        severity: "error",
      });
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    if (!mounted) return;
    fetchData();

    const socket = getSocket(companyId);

    socket.on("optimization_finished", () => {
      setOptimizing(false);
      setNotification({ open: true, message: "Otimização concluída!", severity: "success" });
      fetchData();
    });

    socket.on("optimization_failed", (data: any) => {
      setOptimizing(false);
      setNotification({ open: true, message: "Falha na otimização: " + data.error, severity: "error" });
    });

    return () => {
      disconnectSocket();
    };
  }, [mounted, companyId, fetchData]);

  const handleOptimize = async () => {
    setOptimizing(true);
    try {
      await operationsApi.optimize({});
      setNotification({ open: true, message: "Otimização disparada no servidor...", severity: "info" });
    } catch (error: any) {
      setOptimizing(false);
      if (error.response?.status === 409) {
        setNotification({
          open: true,
          message: error.response?.data?.message || "Otimização já em andamento.",
          severity: "warning",
        });
        fetchData(); 
        return;
      }
      setNotification({
        open: true,
        message: error.response?.data?.message || "Erro ao disparar otimização.",
        severity: "error",
      });
    }
  };

  const handleWhatIfUpdate = (newCost: number | null) => {
    if (newCost !== null && schedule) {
      setSchedule((prev: any) => ({ ...prev, totalCost: newCost }));
    }
  };

  if (!mounted) return null;

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        {/* Painel de KPIs Reativos */}
        <DashboardKPIs schedule={schedule} />

        <DashboardCard
          title="Gantt Planner"
          subtitle="Planejamento Integrado de Frota e Tripulação"
        >
          <Stack spacing={3}>
            {optimizing && (
              <Alert 
                severity="info" 
                variant="outlined" 
                icon={<CircularProgress size={20} />}
                sx={{ fontWeight: 500 }}
              >
                O motor de otimização está processando a escala da sua empresa. 
                Novas otimizações e movimentos manuais estão bloqueados até a conclusão.
              </Alert>
            )}

            <Paper variant="outlined" sx={{ p: 2, backgroundColor: "background.default" }}>
              <Grid container spacing={2} sx={{ alignItems: "center" }}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    Escala Diária Operacional
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Data de Referência:{" "}
                    {schedule ? new Date(schedule.createdAt).toLocaleDateString("pt-BR") : "Nenhuma"}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }} sx={{ textAlign: "right" }}>
                  <Stack direction="row" spacing={2} sx={{ justifyContent: "flex-end" }}>
                    <Button
                      variant="outlined"
                      startIcon={<IconRefresh size={18} />}
                      onClick={fetchData}
                      disabled={loading || optimizing}
                    >
                      Atualizar
                    </Button>
                    <Button
                      variant="contained"
                      startIcon={
                        optimizing ? (
                          <CircularProgress size={18} color="inherit" />
                        ) : (
                          <IconBolt size={18} />
                        )
                      }
                      onClick={handleOptimize}
                      disabled={optimizing}
                      color="primary"
                    >
                      {optimizing ? "Otimizando..." : "Iniciar Otimização"}
                    </Button>
                  </Stack>
                </Grid>
              </Grid>
            </Paper>

            <Box sx={{ minHeight: 600 }}>
              {loading && !schedule ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", p: 10 }}>
                  <CircularProgress />
                </Box>
              ) : schedule && lines.length > 0 && terminals.length > 0 ? (
                <TabGantt
                  res={schedule}
                  lines={lines}
                  terminals={terminals}
                  intervalPolicy={intervalPolicy}
                  onWhatIfUpdate={handleWhatIfUpdate}
                />
              ) : schedule ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", p: 10 }}>
                  <CircularProgress />
                  <Typography variant="body2" sx={{ ml: 2 }} color="textSecondary">
                    Carregando metadados (linhas e terminais)...
                  </Typography>
                </Box>
              ) : (
                <Alert severity="info">
                  Nenhuma escala encontrada. Clique em &quot;Iniciar Otimização&quot; para gerar resultados.
                </Alert>
              )}
            </Box>
          </Stack>
        </DashboardCard>
      </Stack>

      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={() => setNotification((n) => ({ ...n, open: false }))}
      >
        <Alert severity={notification.severity} sx={{ width: "100%" }}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
