"use client";

import React, { useEffect, useRef, useState, useCallback, useMemo, Suspense } from "react";
import dynamic from "next/dynamic";
import {
  Box,
  Typography,
  Stack,
  Button,
  CircularProgress,
  Alert,
  Snackbar,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
} from "@mui/material";
import { IconSettings, IconBolt, IconRefresh, IconRobot } from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import { linesApi, terminalsApi, operationsApi, parametersApi } from "@/lib/api";
import { type TripIntervalPolicy } from "./_helpers/formatters";
import { getSessionUser } from "@/lib/api";

const AiCostDrawer = dynamic(
  () => import("./_components/AiCostDrawer").then((mod) => mod.AiCostDrawer),
  { ssr: false }
);

const DashboardKPIs = dynamic(
  () => import("@/app/components/shared/DashboardKPIs"),
  { ssr: false, loading: () => <Box sx={{ height: 80 }} /> }
);

const TabGantt = dynamic(
  () => import("./_components/TabGantt").then((mod) => mod.TabGantt),
  {
    ssr: false,
    loading: () => (
      <Box sx={{ p: 4, textAlign: "center" }}>
        <CircularProgress />
        <Typography sx={{ mt: 2 }}>Iniciando Motor Logístico...</Typography>
      </Box>
    ),
  }
);

const DynamicRulesEditor = dynamic(
  () => import("./_components/DynamicRulesEditor").then((mod) => mod.DynamicRulesEditor),
  { ssr: false, loading: () => <Box sx={{ height: 40 }} /> }
);

const ALGORITHMS = [
  { value: "hybrid_pipeline", label: "Pipeline Híbrido VSP+CSP (Recomendado)" },
  { value: "greedy", label: "Guloso (mais rápido)" },
  { value: "genetic", label: "Algoritmo Genético" },
  { value: "tabu_search", label: "Busca Tabu" },
  { value: "simulated_annealing", label: "Recozimento Simulado" },
  { value: "set_partitioning", label: "Set Partitioning (CSP)" },
  { value: "mcnf", label: "MCNF (Fluxo de Custo Mínimo)" },
  { value: "joint_solver", label: "Solver Integrado" },
  { value: "vcsp_pulp", label: "VCSP PuLP — ILP Integrado (Experimental)" },
];

export default function PlannerPage() {
  const [mounted, setMounted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [schedule, setSchedule] = useState<any>(null);
  const [lines, setLines] = useState<any[]>([]);
  const [terminals, setTerminals] = useState<any[]>([]);
  const [parameters, setParameters] = useState<any>(null);
  const [selectedAlgorithm, setSelectedAlgorithm] = useState("hybrid_pipeline");
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [notification, setNotification] = useState({
    open: false,
    message: "",
    severity: "info" as "info" | "success" | "warning" | "error",
  });

  const companyId = useMemo(() => getSessionUser()?.companyId ?? 0, []);
  const socketRef = useRef<any>(null);

  const dynamicRules = useMemo(() => parameters?.dynamic_rules || [], [parameters?.dynamic_rules]);

  const intervalPolicy: TripIntervalPolicy = useMemo(
    () => ({
      minBreakMinutes: parameters?.min_break_minutes ?? 30,
      mealBreakMinutes: parameters?.meal_break_minutes ?? 60,
      minLayoverMinutes: parameters?.min_layover_minutes ?? 8,
      connectionToleranceMinutes: parameters?.connection_tolerance_minutes ?? 0,
    }),
    [parameters]
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [scheduleRes, linesRes, terminalsRes, paramsRes] = await Promise.all([
        operationsApi.getLatestSchedule(),
        linesApi.getAll({ companyId }),
        terminalsApi.getAll({ companyId }),
        parametersApi.get().catch(() => null),
      ]);

      setSchedule(scheduleRes);
      setLines(linesRes);
      setTerminals(terminalsRes);
      if (paramsRes) {
        setParameters(paramsRes);
        if (paramsRes.preferred_algorithm) {
          setSelectedAlgorithm(paramsRes.preferred_algorithm);
        }
      }

      if (scheduleRes?.status === "processing") {
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

    // Socket loaded lazily inside useEffect — safe from SSR
    import("@/lib/socket").then(({ getSocket, disconnectSocket }) => {
      const socket = getSocket(companyId);
      socketRef.current = { socket, disconnectSocket };

      socket.on("optimization_finished", () => {
        setOptimizing(false);
        setNotification({ open: true, message: "Otimização concluída!", severity: "success" });
        fetchData();
      });

      socket.on("optimization_failed", (data: any) => {
        setOptimizing(false);
        setNotification({
          open: true,
          message: "Falha na otimização: " + (data?.error || "Erro desconhecido"),
          severity: "error",
        });
      });
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.socket.off("optimization_finished");
        socketRef.current.socket.off("optimization_failed");
        socketRef.current.disconnectSocket();
        socketRef.current = null;
      }
    };
  }, [mounted, companyId, fetchData]);

  const handleOptimize = async () => {
    setOptimizing(true);
    try {
      await operationsApi.optimize({ algorithm: selectedAlgorithm });
      setNotification({
        open: true,
        message: `Otimização disparada com algoritmo "${ALGORITHMS.find((a) => a.value === selectedAlgorithm)?.label}"...`,
        severity: "info",
      });
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
        <DashboardKPIs schedule={schedule} />

        <DynamicRulesEditor
          initialRules={dynamicRules}
          onSaved={(rules) => setParameters((p: any) => ({ ...p, dynamic_rules: rules }))}
        />

        <DashboardCard
          title="Gantt Planner"
          subtitle={
            schedule
              ? `Escala de ${new Date(schedule.createdAt).toLocaleDateString("pt-BR")} — Planejamento Integrado VSP + CSP`
              : "Planejamento Integrado de Frota e Tripulação"
          }
        >
          <Stack spacing={2.5}>
            {optimizing && (
              <Alert
                severity="info"
                variant="outlined"
                icon={<CircularProgress size={18} />}
                sx={{ fontWeight: 500 }}
              >
                Motor de otimização em execução. Novas otimizações e movimentos manuais estão bloqueados até a conclusão.
              </Alert>
            )}

            <Paper
              variant="outlined"
              sx={{
                px: 2,
                py: 1.5,
                bgcolor: "background.default",
                borderRadius: 2,
              }}
            >
              <Stack
                direction={{ xs: "column", md: "row" }}
                spacing={1.5}
                sx={{ alignItems: { md: "center" }, justifyContent: "space-between" }}
              >
                <Tooltip title="Escolha o algoritmo de otimização. 'Pipeline Híbrido' é recomendado para uso operacional.">
                  <FormControl size="small" sx={{ minWidth: 260, maxWidth: 340, flex: { xs: 1, md: 'none' } }}>
                    <InputLabel>Algoritmo</InputLabel>
                    <Select
                      value={selectedAlgorithm}
                      label="Algoritmo"
                      onChange={(e) => setSelectedAlgorithm(e.target.value)}
                      disabled={optimizing}
                      startAdornment={<IconSettings size={16} style={{ marginRight: 4, opacity: 0.6 }} />}
                    >
                      {ALGORITHMS.map((a) => (
                        <MenuItem key={a.value} value={a.value}>
                          {a.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Tooltip>

                <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
                  <Button
                    variant="text"
                    size="small"
                    startIcon={<IconRefresh size={16} />}
                    onClick={fetchData}
                    disabled={loading || optimizing}
                  >
                    Atualizar
                  </Button>
                  <Tooltip title={schedule?.status !== 'completed' ? "Execute uma otimização para ativar" : "Copiloto de Análise de Custos"}>
                    <span>
                      <Button
                        variant="outlined"
                        size="small"
                        color="secondary"
                        startIcon={<IconRobot size={16} />}
                        onClick={() => setAiDrawerOpen(true)}
                        disabled={schedule?.status !== 'completed'}
                      >
                        IA de Custos
                      </Button>
                    </span>
                  </Tooltip>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={
                      optimizing ? (
                        <CircularProgress size={16} color="inherit" />
                      ) : (
                        <IconBolt size={16} />
                      )
                    }
                    onClick={handleOptimize}
                    disabled={optimizing}
                    color="primary"
                    sx={{ fontWeight: 700 }}
                  >
                    {optimizing ? "Otimizando..." : "Otimizar"}
                  </Button>
                </Stack>
              </Stack>
            </Paper>

            <Box sx={{ minHeight: 600 }}>
              {loading && !schedule ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", p: 10 }}>
                  <CircularProgress />
                </Box>
              ) : schedule ? (
                <Suspense
                  fallback={
                    <Box sx={{ p: 4, textAlign: "center" }}>
                      <CircularProgress />
                      <Typography sx={{ mt: 2 }}>Carregando Inteligência Operacional...</Typography>
                    </Box>
                  }
                >
                  <TabGantt
                    res={schedule}
                    lines={lines}
                    terminals={terminals}
                    intervalPolicy={intervalPolicy}
                    onWhatIfUpdate={handleWhatIfUpdate}
                  />
                </Suspense>
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

      <AiCostDrawer
        open={aiDrawerOpen}
        onClose={() => setAiDrawerOpen(false)}
        result={schedule?.resultSummary ?? (schedule?.status === 'completed' ? schedule : null)}
      />
    </Box>
  );
}
