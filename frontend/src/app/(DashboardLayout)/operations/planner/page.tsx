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
  Chip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
} from "@mui/material";
import { IconSettings, IconBolt, IconRefresh, IconRobot } from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import { linesApi, terminalsApi, operationsApi, parametersApi } from "@/lib/api";
import type { OperationalQualityDecision, OperationalQualityMode } from "../_types";
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

const OPERATIONAL_QUALITY_MODES: Array<{ value: OperationalQualityMode; label: string }> = [
  { value: "strict", label: "Sem excecoes criticas" },
  { value: "balanced", label: "Equilibrado" },
  { value: "optimized", label: "Mais barato" },
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
  const [selectedOperationalQualityMode, setSelectedOperationalQualityMode] = useState<OperationalQualityMode>("balanced");
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [notification, setNotification] = useState({
    open: false,
    message: "",
    severity: "info" as "info" | "success" | "warning" | "error",
  });
  const [optimizationProgress, setOptimizationProgress] = useState<{
    taskId?: string | null;
    scheduleId?: number | null;
    phase?: string | null;
    phaseLabel?: string | null;
    progressPct?: number | null;
  } | null>(null);

  const companyId = useMemo(() => getSessionUser()?.companyId ?? 0, []);
  const socketRef = useRef<any>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optimizingRef = useRef(false);

  const dynamicRules = useMemo(() => parameters?.dynamic_rules || [], [parameters?.dynamic_rules]);
  const operationalQualityDecision = useMemo<OperationalQualityDecision | null>(() => {
    const summary = schedule?.resultSummary ?? {};
    return (
      summary.operationalQualityDecision ??
      summary.operational_quality_decision ??
      null
    );
  }, [schedule]);

  const intervalPolicy: TripIntervalPolicy = useMemo(
    () => {
      const summary = schedule?.resultSummary ?? {};
      const meta = summary.metadata ?? summary.meta ?? {};
      const input = meta.input ?? summary.resolved_params ?? {};
      const cct = input.cct_params ?? input.cct ?? {};
      const vsp = input.vsp_params ?? input.vsp ?? {};
      return {
        minBreakMinutes: cct.min_break_minutes ?? parameters?.min_break_minutes ?? 30,
        mealBreakMinutes: cct.meal_break_minutes ?? parameters?.meal_break_minutes ?? 60,
        minLayoverMinutes: vsp.min_layover_minutes ?? cct.min_layover_minutes ?? parameters?.min_layover_minutes ?? 8,
        connectionToleranceMinutes: cct.connection_tolerance_minutes ?? parameters?.connection_tolerance_minutes ?? 0,
      };
    },
    [parameters, schedule]
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const storedMode = String(parameters?.operational_quality_mode || "balanced").toLowerCase();
    if (storedMode === "strict" || storedMode === "balanced" || storedMode === "optimized") {
      setSelectedOperationalQualityMode(storedMode);
    }
  }, [parameters?.operational_quality_mode]);

  useEffect(() => {
    optimizingRef.current = optimizing;
  }, [optimizing]);

  const stopOptimizationFallbacks = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
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
        const preferredAlgorithm = paramsRes.algorithm_preference || paramsRes.preferred_algorithm;
        if (preferredAlgorithm) {
          setSelectedAlgorithm(preferredAlgorithm);
        }
      }

      if (scheduleRes?.status === "processing") {
        setOptimizationProgress((prev) => ({
          taskId: prev?.taskId ?? null,
          scheduleId: scheduleRes?.id ?? prev?.scheduleId ?? null,
          phase: prev?.phase ?? "queued",
          phaseLabel: prev?.phaseLabel ?? "Otimização em andamento...",
          progressPct: prev?.progressPct ?? 0,
        }));
      } else {
        setOptimizationProgress(null);
      }

      setOptimizing(scheduleRes?.status === "processing");

      if (scheduleRes?.status !== "processing") {
        stopOptimizationFallbacks();
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
  }, [companyId, stopOptimizationFallbacks]);

  useEffect(() => {
    if (!mounted) return;
    fetchData();

    import("@/lib/socket").then(({ getSocket, disconnectSocket, reconnectSocket, getSocketDiagnostics }) => {
      const socket = getSocket(companyId);
      socketRef.current = { socket, disconnectSocket, reconnectSocket, getSocketDiagnostics };

      const handleQueued = (data: any) => {
        setOptimizing(true);
        setOptimizationProgress({
          taskId: data?.taskId ?? null,
          scheduleId: data?.scheduleId ?? null,
          phase: "queued",
          phaseLabel: "Otimização enfileirada.",
          progressPct: 0,
        });
      };

      const handleProgress = (data: any) => {
        setOptimizing(true);
        setOptimizationProgress({
          taskId: data?.taskId ?? null,
          scheduleId: data?.scheduleId ?? null,
          phase: data?.phase ?? "processing",
          phaseLabel: data?.phaseLabel ?? "Otimização em andamento...",
          progressPct: data?.progressPct ?? null,
        });
      };

      const handleFinished = () => {
        stopOptimizationFallbacks();
        setOptimizing(false);
        setOptimizationProgress(null);
        setNotification({ open: true, message: "Otimização concluída!", severity: "success" });
        fetchData();
      };

      const handleFailed = (data: any) => {
        stopOptimizationFallbacks();
        setOptimizing(false);
        setOptimizationProgress(null);
        setNotification({
          open: true,
          message: "Falha na otimização: " + (data?.error || "Erro desconhecido"),
          severity: "error",
        });
      };

      const handleStale = () => {
        setNotification({
          open: true,
          message: "A otimização demorou além do esperado. Recarregando status...",
          severity: "warning",
        });
      };

      const handleDisconnect = (reason: string) => {
        console.warn("[planner] websocket disconnected", { reason, diagnostics: getSocketDiagnostics() });
      };

      const handleConnectError = (error: Error) => {
        console.warn("[planner] websocket connect_error", { message: error.message, diagnostics: getSocketDiagnostics() });
      };

      socket.on("optimization_queued", handleQueued);
      socket.on("optimization_progress", handleProgress);
      socket.on("optimization_finished", handleFinished);
      socket.on("optimization_failed", handleFailed);
      socket.on("optimization_stale", handleStale);
      socket.on("disconnect", handleDisconnect);
      socket.on("connect_error", handleConnectError);
      reconnectSocket();
    });

    return () => {
      stopOptimizationFallbacks();
      if (socketRef.current) {
        socketRef.current.socket.off("optimization_queued");
        socketRef.current.socket.off("optimization_progress");
        socketRef.current.socket.off("optimization_finished");
        socketRef.current.socket.off("optimization_failed");
        socketRef.current.socket.off("optimization_stale");
        socketRef.current.socket.off("disconnect");
        socketRef.current.socket.off("connect_error");
        socketRef.current.disconnectSocket();
        socketRef.current = null;
      }
    };
  }, [mounted, companyId, fetchData, stopOptimizationFallbacks]);

  const handleOptimize = async () => {
    stopOptimizationFallbacks();
    setOptimizing(true);
    setOptimizationProgress({
      taskId: null,
      scheduleId: schedule?.id ?? null,
      phase: "submitting",
      phaseLabel: "Enviando otimização para o backend...",
      progressPct: 0,
    });

    pollingRef.current = setInterval(() => {
      if (!optimizingRef.current) return;
      fetchData();
    }, 5000);

    timeoutRef.current = setTimeout(async () => {
      if (!optimizingRef.current) return;
      await fetchData();
      if (!optimizingRef.current) return;
      stopOptimizationFallbacks();
      setOptimizing(false);
      setOptimizationProgress(null);
      setNotification({
        open: true,
        message: "A atualização em tempo real falhou. O status foi recarregado manualmente.",
        severity: "warning",
      });
    }, 120000);

    try {
      const optimizeResponse = await operationsApi.optimize({
        algorithm: selectedAlgorithm,
        operational_quality_mode: selectedOperationalQualityMode,
      });
      setOptimizationProgress((prev) => ({
        taskId: optimizeResponse?.taskId ?? optimizeResponse?.task_id ?? prev?.taskId ?? null,
        scheduleId: optimizeResponse?.scheduleId ?? prev?.scheduleId ?? null,
        phase: "queued",
        phaseLabel: "Otimização aceita e aguardando processamento...",
        progressPct: 5,
      }));
      await fetchData();
      setNotification({
        open: true,
        message: `Otimização disparada com algoritmo "${ALGORITHMS.find((a) => a.value === selectedAlgorithm)?.label}"...`,
        severity: "info",
      });
    } catch (error: any) {
      stopOptimizationFallbacks();
      setOptimizing(false);
      setOptimizationProgress(null);
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
                <Stack spacing={0.5}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {optimizationProgress?.phaseLabel || "Motor de otimização em execução."}
                  </Typography>
                  {optimizationProgress?.taskId && (
                    <Typography variant="caption" color="text.secondary">
                      Task: {optimizationProgress.taskId}
                    </Typography>
                  )}
                  {typeof optimizationProgress?.progressPct === "number" && (
                    <Typography variant="caption" color="text.secondary">
                      Progresso: {optimizationProgress.progressPct}%
                    </Typography>
                  )}
                  <Typography variant="caption" color="text.secondary">
                    Novas otimizações e movimentos manuais estão bloqueados até a conclusão.
                  </Typography>
                </Stack>
              </Alert>
            )}

            {!optimizing && schedule?.status === "processing" && (
              <Alert severity="warning" variant="outlined">
                Há uma otimização marcada como PROCESSING no backend. Recarregue os dados ou aguarde a próxima atualização automática.
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
                      {ALGORITHMS.map((algorithm) => (
                        <MenuItem key={algorithm.value} value={algorithm.value}>
                          {algorithm.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Tooltip>

                <Tooltip title="Define como o produto escolhe entre o plano atual e o cenario com +1 duty/crew.">
                  <FormControl size="small" sx={{ minWidth: 240, maxWidth: 300, flex: { xs: 1, md: 'none' } }}>
                    <InputLabel>Qualidade Operacional</InputLabel>
                    <Select
                      value={selectedOperationalQualityMode}
                      label="Qualidade Operacional"
                      onChange={(e) => setSelectedOperationalQualityMode(e.target.value as OperationalQualityMode)}
                      disabled={optimizing}
                    >
                      {OPERATIONAL_QUALITY_MODES.map((mode) => (
                        <MenuItem key={mode.value} value={mode.value}>
                          {mode.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Tooltip>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <Button
                    variant="outlined"
                    startIcon={<IconRefresh size={18} />}
                    onClick={fetchData}
                    disabled={loading}
                  >
                    Atualizar
                  </Button>
                  <Button
                    variant="contained"
                    startIcon={optimizing ? <CircularProgress size={16} color="inherit" /> : <IconBolt size={18} />}
                    onClick={handleOptimize}
                    disabled={optimizing}
                  >
                    {optimizing ? "Otimizando..." : "Executar Otimização"}
                  </Button>
                  <Tooltip title={schedule?.status !== 'completed' ? "Execute uma otimização para ativar" : "Copiloto de Análise de Custos"}>
                    <span>
                      <Button
                        variant="outlined"
                        color="secondary"
                        startIcon={<IconRobot size={18} />}
                        onClick={() => setAiDrawerOpen(true)}
                        disabled={schedule?.status !== 'completed'}
                      >
                        AI Cost Copilot
                      </Button>
                    </span>
                  </Tooltip>
                </Stack>
              </Stack>
            </Paper>

            {schedule?.status === "completed" && operationalQualityDecision && (
              <Alert severity="info" variant="outlined">
                <Stack spacing={1}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ alignItems: { md: "center" } }}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      Cenario escolhido: {operationalQualityDecision.chosen_title || operationalQualityDecision.chosen_scenario || "N/D"}
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                      {(operationalQualityDecision.available_scenarios || [])
                        .find((item) => item.scenario_id === (operationalQualityDecision.chosen_scenario || ""))
                        ?.labels?.map((label) => (
                          <Chip key={label} label={label} color="primary" size="small" variant="outlined" />
                        ))}
                    </Stack>
                  </Stack>
                  {(operationalQualityDecision.justification || []).map((line) => (
                    <Typography key={line} variant="caption" color="text.secondary">
                      {line}
                    </Typography>
                  ))}
                </Stack>
              </Alert>
            )}

            <Suspense fallback={<CircularProgress />}>
              <TabGantt
                key={schedule?.id ?? 'no-schedule'}
                res={schedule?.status === 'completed' ? schedule : null}
                lines={lines}
                terminals={terminals}
                intervalPolicy={intervalPolicy}
                onWhatIfUpdate={handleWhatIfUpdate}
              />
            </Suspense>
          </Stack>
        </DashboardCard>
      </Stack>

      <AiCostDrawer
        open={aiDrawerOpen}
        onClose={() => setAiDrawerOpen(false)}
        result={schedule?.resultSummary ?? null}
      />

      <Snackbar
        open={notification.open}
        autoHideDuration={4000}
        onClose={() => setNotification((prev) => ({ ...prev, open: false }))}
      >
        <Alert
          onClose={() => setNotification((prev) => ({ ...prev, open: false }))}
          severity={notification.severity}
          sx={{ width: "100%" }}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
