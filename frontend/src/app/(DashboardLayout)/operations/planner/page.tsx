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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  List,
  ListItem,
  ListItemText,
} from "@mui/material";
import { IconSettings, IconBolt, IconRefresh, IconRobot, IconShieldCheck, IconHelp } from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import { linesApi, terminalsApi, operationsApi, parametersApi, auditApi } from "@/lib/api";
import type {
  Line,
  Terminal,
  OptimizationParameters,
  OptimizationResultSummary,
  ScheduleValidationResult,
  ScheduleValidationIssue,
  OperationalQualityDecision,
  OperationalQualityMode,
} from "../_types";
import type { Socket } from "socket.io-client";
import { type TripIntervalPolicy } from "./_helpers/formatters";
import type { DynamicRule } from "./_components/DynamicRulesEditor";
import { getSessionUser } from "@/lib/api";
import { TripReassignmentModal } from "@/app/components/shared/TripReassignmentModal";

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
  const [schedule, setSchedule] = useState<OptimizationResultSummary | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [terminals, setTerminals] = useState<Terminal[]>([]);
  const [depots, setDepots] = useState<Terminal[]>([]);
  const [parameters, setParameters] = useState<OptimizationParameters | null>(null);
  const [selectedAlgorithm, setSelectedAlgorithm] = useState("hybrid_pipeline");
  const [selectedOperationalQualityMode, setSelectedOperationalQualityMode] = useState<OperationalQualityMode>("balanced");
  const [selectedDepotIds, setSelectedDepotIds] = useState<number[]>([]);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<ScheduleValidationResult | null>(null);
  const [validationOpen, setValidationOpen] = useState(false);
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
  const [reassignmentModalOpen, setReassignmentModalOpen] = useState(false);
  const [selectedTripForReassignment, setSelectedTripForReassignment] = useState<{ tripId: number; code?: string } | null>(null);

  const companyId = useMemo(() => getSessionUser()?.companyId ?? 0, []);

  interface SocketModuleRef {
    socket: Socket;
    disconnectSocket: () => void;
    reconnectSocket: () => void;
    getSocketDiagnostics: () => { connected: boolean; id: string | null };
  }
  const socketRef = useRef<SocketModuleRef | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optimizingRef = useRef(false);

  const handleOpenReassignmentModal = useCallback((tripId: number, tripCode?: string) => {
    setSelectedTripForReassignment({ tripId, code: tripCode });
    setReassignmentModalOpen(true);
  }, []);

  const dynamicRules = useMemo(() => parameters?.dynamic_rules || [], [parameters?.dynamic_rules]);
  const operationalQualityDecision = useMemo<OperationalQualityDecision | null>(() => {
    const summary = schedule?.resultSummary ?? {};
    return (
      summary.operationalQualityDecision ??
      summary.operational_quality_decision ??
      null
    );
  }, [schedule]);

  const hardConstraintReport = useMemo<Record<string, unknown> | null>(() => {
    return (
      schedule?.hard_constraint_report ??
      schedule?.resultSummary?.hardConstraintReport ??
      null
    );
  }, [schedule]);

  const intervalPolicy: TripIntervalPolicy = useMemo(
    () => {
      const summary = (schedule?.resultSummary ?? {}) as Record<string, unknown>;
      const meta = (summary.metadata ?? summary.meta ?? {}) as Record<string, unknown>;
      const input = (meta.input ?? summary.resolved_params ?? {}) as Record<string, unknown>;
      const cct = (input.cct_params ?? input.cct ?? {}) as Record<string, unknown>;
      const vsp = (input.vsp_params ?? input.vsp ?? {}) as Record<string, unknown>;
      return {
        minBreakMinutes: (cct.min_break_minutes as number | undefined) ?? parameters?.min_break_minutes ?? 30,
        mealBreakMinutes: (cct.meal_break_minutes as number | undefined) ?? parameters?.meal_break_minutes ?? 60,
        minLayoverMinutes: (vsp.min_layover_minutes as number | undefined) ?? (cct.min_layover_minutes as number | undefined) ?? parameters?.min_layover_minutes ?? 8,
        connectionToleranceMinutes: (cct.connection_tolerance_minutes as number | undefined) ?? parameters?.connection_tolerance_minutes ?? 0,
        pulloutMinutes: (vsp.pullout_minutes as number | undefined) ?? (cct.pullout_minutes as number | undefined) ?? parameters?.pullout_minutes ?? 0,
        pullbackMinutes: (vsp.pullback_minutes as number | undefined) ?? (cct.pullback_minutes as number | undefined) ?? parameters?.pullback_minutes ?? 0,
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
      const [scheduleRes, linesRes, terminalsRes, depotsRes, paramsRes] = await Promise.all([
        operationsApi.getLatestSchedule(),
        linesApi.getAll({ companyId }),
        terminalsApi.getAll({ companyId }),
        terminalsApi.getDepots().catch(() => []),
        parametersApi.get().catch(() => null),
      ]);

      setSchedule(scheduleRes);
      setLines(linesRes);
      setTerminals(terminalsRes);
      setDepots(depotsRes);
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

      const handleQueued = (data: Record<string, unknown>) => {
        setOptimizing(true);
        setOptimizationProgress({
          taskId: (data?.taskId as string | null) ?? null,
          scheduleId: (data?.scheduleId as number | null) ?? null,
          phase: "queued",
          phaseLabel: "Otimização enfileirada.",
          progressPct: 0,
        });
      };

      const handleProgress = (data: Record<string, unknown>) => {
        setOptimizing(true);
        setOptimizationProgress({
          taskId: (data?.taskId as string | null) ?? null,
          scheduleId: (data?.scheduleId as number | null) ?? null,
          phase: (data?.phase as string) ?? "processing",
          phaseLabel: (data?.phaseLabel as string) ?? "Otimização em andamento...",
          progressPct: (data?.progressPct as number | null) ?? null,
        });
      };

      const handleFinished = () => {
        stopOptimizationFallbacks();
        setOptimizing(false);
        setOptimizationProgress(null);
        setNotification({ open: true, message: "Otimização concluída!", severity: "success" });
        fetchData();
      };

      const handleFailed = (data: Record<string, unknown>) => {
        stopOptimizationFallbacks();
        setOptimizing(false);
        setOptimizationProgress(null);
        setNotification({
          open: true,
          message: "Falha na otimização: " + ((data?.error as string) || "Erro desconhecido"),
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
        ...(selectedDepotIds.length > 0 ? { depot_ids: selectedDepotIds } : {}),
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
    } catch (error) {
      stopOptimizationFallbacks();
      setOptimizing(false);
      setOptimizationProgress(null);
      const axiosError = error as { response?: { status?: number; data?: { message?: string } } };
      if (axiosError.response?.status === 409) {
        setNotification({
          open: true,
          message: axiosError.response?.data?.message || "Otimização já em andamento.",
          severity: "warning",
        });
        fetchData();
        return;
      }
      setNotification({
        open: true,
        message: axiosError.response?.data?.message || "Erro ao disparar otimização.",
        severity: "error",
      });
    }
  };

  const handleValidate = async () => {
    if (!schedule?.id) return;
    setValidating(true);
    try {
      const result = await auditApi.validateSchedule(schedule.id);
      setValidationResult(result);
      setValidationOpen(true);
    } catch (e) {
      const axiosError = e as { response?: { data?: { message?: string } } };
      setNotification({
        open: true,
        message: axiosError?.response?.data?.message || 'Erro ao validar escala.',
        severity: 'error',
      });
    } finally {
      setValidating(false);
    }
  };

  const handleWhatIfUpdate = (newCost: number | null) => {
    if (newCost !== null && schedule) {
      setSchedule((prev) => (prev ? { ...prev, totalCost: newCost } : prev));
    }
  };

  if (!mounted) return null;

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <DashboardKPIs schedule={schedule} />

        <DynamicRulesEditor
          initialRules={dynamicRules as DynamicRule[]}
          onSaved={(rules) => setParameters((p) => ({ ...(p ?? {}), dynamic_rules: rules }))}
        />

        <DashboardCard
          title="Gantt Planner"
          subtitle={
            schedule
              ? `Escala de ${new Date(schedule.createdAt ?? '').toLocaleDateString("pt-BR")} — Planejamento Integrado VSP + CSP`
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

            {!optimizing && schedule?.status === "failed" && (() => {
              const hasBlocks = Array.isArray(schedule.blocks) && schedule.blocks.length > 0;
              const isHardViolation = schedule?.error_code === 'HARD_CONSTRAINT_OUTPUT' || schedule?.error_code === 'OPTIMIZER_RESULT_INVALID';
              if (hasBlocks && isHardViolation) {
                return (
                  <Alert severity="warning" variant="outlined">
                    <strong>Resultado com violações hard.</strong> Esta escala contém violações de restrições obrigatórias e não deve ser usada operacionalmente sem correção. Revise os problemas no Gantt antes de aplicar.
                  </Alert>
                );
              }
              return (
                <Alert severity="error" variant="outlined">
                  <strong>Última otimização falhou.</strong>
                  {schedule?.error_message && (
                    <> {schedule.error_message}</>
                  )}
                  {schedule?.error_code && (
                    <Typography component="span" variant="caption" sx={{ ml: 1, opacity: 0.7 }}>
                      [{schedule.error_code}]
                    </Typography>
                  )}
                </Alert>
              );
            })()}

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

                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Tooltip title="Define como o produto escolhe entre o plano atual e o cenário com +1 jornada/motorista.">
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
                  <Tooltip
                    title={
                      <Box sx={{ p: 1 }}>
                        <Typography variant="caption" sx={{ display: 'block', fontWeight: 700, mb: 0.5 }}>Modos de Qualidade Operacional:</Typography>
                        <Typography variant="caption" sx={{ display: 'block', mb: 1 }}>
                          <strong>Sem exceções críticas:</strong> Hard Issues = 0. Plano com ZERO violações obrigatórias (CCT, segurança, continuidade).
                        </Typography>
                        <Typography variant="caption" sx={{ display: 'block', mb: 1 }}>
                          <strong>Equilibrado:</strong> Balanço entre custo e qualidade operacional. Pode ter soft issues (preferências não críticas).
                        </Typography>
                        <Typography variant="caption" sx={{ display: 'block' }}>
                          <strong>Mais barato:</strong> Prioriza custo mínimo. Pode ter soft issues e restrições relaxadas.
                        </Typography>
                      </Box>
                    }
                    arrow
                  >
                    <IconHelp size={18} style={{ marginTop: 4, cursor: 'help', opacity: 0.6 }} />
                  </Tooltip>
                </Box>

                {depots.length > 0 && (
                  <Tooltip title="Selecione garagens específicas para otimização multi-depot. Vazio = todas as garagens.">
                    <FormControl size="small" sx={{ minWidth: 200, maxWidth: 280, flex: { xs: 1, md: 'none' } }}>
                      <InputLabel>Garagens (opcional)</InputLabel>
                      <Select
                        multiple
                        value={selectedDepotIds}
                        label="Garagens (opcional)"
                        onChange={(e) => {
                          const v = e.target.value;
                          setSelectedDepotIds(typeof v === 'string' ? v.split(',').map(Number) : v as number[]);
                        }}
                        disabled={optimizing}
                        renderValue={(selected) =>
                          (selected as number[])
                            .map((id) => depots.find((d) => d.id === id)?.name ?? id)
                            .join(', ')
                        }
                      >
                        {depots.map((depot) => (
                          <MenuItem key={depot.id} value={depot.id}>
                            {depot.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Tooltip>
                )}

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
                  <Tooltip title={!schedule?.id ? "Execute uma otimização para ativar" : "Audita erros e avisos da escala atual"}>
                    <span>
                      <Button
                        variant="outlined"
                        color="warning"
                        startIcon={validating ? <CircularProgress size={16} color="inherit" /> : <IconShieldCheck size={18} />}
                        onClick={handleValidate}
                        disabled={!schedule?.id || optimizing || validating}
                      >
                        {validating ? "Validando..." : "Validar Escala"}
                      </Button>
                    </span>
                  </Tooltip>
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
                      Cenário escolhido: {operationalQualityDecision.chosen_title || operationalQualityDecision.chosen_scenario || "N/D"}
                    </Typography>
                    {operationalQualityDecision.mode && (
                      <Chip
                        label={`Modo: ${operationalQualityDecision.mode}`}
                        color="info"
                        size="small"
                        variant="outlined"
                        sx={{ fontWeight: 600 }}
                      />
                    )}
                    <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                      {(operationalQualityDecision.available_scenarios || [])
                        .find((item) => item.scenario_id === operationalQualityDecision.chosen_scenario)
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
                  {(operationalQualityDecision.trade_offs ?? []).length > 0 && (
                    <Stack spacing={0.5}>
                      <Typography variant="caption" sx={{ fontWeight: 700, color: "warning.main" }}>
                        Trade-offs do cenário escolhido:
                      </Typography>
                      {(operationalQualityDecision.trade_offs ?? []).map((line) => (
                        <Typography key={line} variant="caption" color="text.secondary">
                          • {line}
                        </Typography>
                      ))}
                    </Stack>
                  )}
                </Stack>
              </Alert>
            )}

            {schedule?.status === "completed" && hardConstraintReport && (
              (() => {
                const output = (hardConstraintReport.output ?? {}) as { soft_issues?: string[]; hard_issues?: string[] };
                const softIssues: string[] = output.soft_issues ?? [];
                const hardIssues: string[] = output.hard_issues ?? [];
                if (hardIssues.length === 0 && softIssues.length === 0) return null;
                return (
                  <Alert severity={hardIssues.length > 0 ? "error" : "warning"} variant="outlined">
                    <Stack spacing={0.5}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        Relatório de Restrições Críticas
                      </Typography>
                      {hardIssues.map((issue) => (
                        <Typography key={issue} variant="caption" color="error.main">
                          ✗ {issue}
                        </Typography>
                      ))}
                      {softIssues.map((issue) => (
                        <Typography key={issue} variant="caption" color="warning.main">
                          ⚠ {issue}
                        </Typography>
                      ))}
                    </Stack>
                  </Alert>
                );
              })()
            )}

            <Suspense fallback={<CircularProgress />}>
              <TabGantt
                key={schedule?.id ?? 'no-schedule'}
                res={schedule && (schedule.status === 'completed' || (schedule.status === 'failed' && Array.isArray(schedule.blocks) && schedule.blocks.length > 0)) ? schedule : null}
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

      <Dialog
        open={validationOpen}
        onClose={() => setValidationOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconShieldCheck size={20} />
          Validação da Escala
          {validationResult && (
            <Chip
              label={validationResult.valid ? "Válida" : `${validationResult.errorCount} erro(s)`}
              color={validationResult.valid ? "success" : "error"}
              size="small"
              sx={{ ml: 1 }}
            />
          )}
        </DialogTitle>
        <DialogContent dividers>
          {validationResult && (
            <Stack spacing={2}>
              <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
                {[
                  { label: 'Viagens', value: validationResult.stats?.totalTrips ?? '—' },
                  { label: 'Alocadas', value: validationResult.stats?.allocatedTrips ?? '—' },
                  { label: 'Veículos', value: validationResult.stats?.totalVehicles ?? '—' },
                  { label: 'Jornadas', value: validationResult.stats?.totalDuties ?? '—' },
                  { label: 'Horas op.', value: validationResult.stats?.totalOperatorHours != null ? `${validationResult.stats.totalOperatorHours}h` : '—' },
                  { label: 'Alocação', value: validationResult.stats?.allocationPercentage != null ? `${validationResult.stats.allocationPercentage.toFixed(1)}%` : '—' },
                ].map(({ label, value }) => (
                  <Box key={label} sx={{ textAlign: 'center', minWidth: 72 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>{value}</Typography>
                    <Typography variant="caption" color="text.secondary">{label}</Typography>
                  </Box>
                ))}
              </Stack>

              {(validationResult.errors?.length ?? 0) > 0 && validationResult.errors && (
                <>
                  <Divider />
                  <Typography variant="subtitle2" color="error.main">
                    Erros ({validationResult.errors.length})
                  </Typography>
                  <List dense disablePadding>
                    {validationResult.errors.map((e: ScheduleValidationIssue, i: number) => (
                      <ListItem key={i} disablePadding sx={{ py: 0.25 }}>
                        <ListItemText
                          primary={<Typography variant="body2" color="error.main">{e.detail}</Typography>}
                          secondary={e.suggestedFix ? <Typography variant="caption">Sugestão: {e.suggestedFix}</Typography> : undefined}
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
              )}

              {(validationResult.warnings?.length ?? 0) > 0 && validationResult.warnings && (
                <>
                  <Divider />
                  <Typography variant="subtitle2" color="warning.main">
                    Avisos ({validationResult.warnings.length})
                  </Typography>
                  <List dense disablePadding>
                    {validationResult.warnings.map((w: ScheduleValidationIssue, i: number) => (
                      <ListItem key={i} disablePadding sx={{ py: 0.25 }}>
                        <ListItemText
                          primary={<Typography variant="body2" color="warning.dark">{w.detail}</Typography>}
                          secondary={w.suggestedFix ? <Typography variant="caption">Sugestão: {w.suggestedFix}</Typography> : undefined}
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
              )}

              {validationResult.valid && validationResult.warnings?.length === 0 && (
                <Alert severity="success">Escala válida — nenhum erro ou aviso encontrado.</Alert>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setValidationOpen(false)}>Fechar</Button>
        </DialogActions>
      </Dialog>

      {schedule && (
        <TripReassignmentModal
          open={reassignmentModalOpen}
          onClose={() => {
            setReassignmentModalOpen(false);
            setSelectedTripForReassignment(null);
          }}
          onSuccess={() => {
            setNotification({
              open: true,
              message: "Viagem reatribuída com sucesso!",
              severity: "success",
            });
          }}
          scheduleId={schedule.id ?? 0}
          tripId={selectedTripForReassignment?.tripId ?? 0}
          tripCode={selectedTripForReassignment?.code}
        />
      )}
    </Box>
  );
}
