"use client";

import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Grid,
  Stack,
  Switch,
  TextField,
  Button,
  Skeleton,
  FormControlLabel,
  Alert,
  Snackbar,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  Tooltip,
  InputAdornment,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import {
  IconChevronDown,
  IconCurrencyReal,
  IconClock,
  IconShieldCheck,
  IconMoon,
  IconScale,
  IconSettings,
  IconRoute,
  IconBolt,
} from "@tabler/icons-react";
import DashboardCard from "@/app/components/shared/DashboardCard";
import { parametersApi } from "@/lib/api";

interface CompanyParameters {
  // Custos
  driver_cost_per_minute: number;
  collector_cost_per_minute: number;
  vehicle_fixed_cost: number;
  cost_vehicle: number;
  cost_km: number;
  cost_duty: number;
  // Flags
  force_round_trip: boolean;
  allow_vehicle_swap: boolean;
  // Solver
  time_budget_s: number | null;
  random_seed: number | null;
  max_vehicle_shift_minutes: number | null;
  max_vehicles: number | null;
  deadhead_cost_per_minute: number | null;
  idle_cost_per_minute: number | null;
  allow_multi_line_block: boolean | null;
  allow_vehicle_split_shifts: boolean | null;
  split_shift_min_gap_minutes: number | null;
  split_shift_max_gap_minutes: number | null;
  max_simultaneous_chargers: number | null;
  enable_column_generation: boolean | null;
  pricing_enabled: boolean | null;
  use_set_covering: boolean | null;
  min_workpiece_minutes: number | null;
  max_workpiece_minutes: number | null;
  min_trips_per_piece: number | null;
  max_trips_per_piece: number | null;
  peak_energy_cost_per_kwh: number | null;
  offpeak_energy_cost_per_kwh: number | null;
  preferred_pair_window_minutes: number | null;
  preserve_preferred_pairs: boolean | null;
  pair_break_penalty: number | null;
  paired_trip_bonus: number | null;
  max_connection_cost_for_reuse_ratio: number | null;
  max_candidate_successors_per_task: number | null;
  max_generated_columns: number | null;
  max_pricing_iterations: number | null;
  max_pricing_additions: number | null;
  vehicle_idle_gap_behavior: string | null;
  vehicle_idle_gap_threshold_minutes: number | null;
  // Jornada Base
  max_driving_time_minutes: number;
  meal_break_minutes: number;
  max_shift_minutes: number;
  // CCT Completo
  max_work_minutes: number | null;
  min_work_minutes: number | null;
  min_shift_minutes: number | null;
  overtime_limit_minutes: number | null;
  max_driving_minutes: number | null;
  min_break_minutes: number | null;
  connection_tolerance_minutes: number | null;
  mandatory_break_after_minutes: number | null;
  split_break_first_minutes: number | null;
  split_break_second_minutes: number | null;
  inter_shift_rest_minutes: number | null;
  weekly_rest_minutes: number | null;
  reduced_weekly_rest_minutes: number | null;
  allow_reduced_weekly_rest: boolean | null;
  daily_driving_limit_minutes: number | null;
  extended_daily_driving_limit_minutes: number | null;
  max_extended_driving_days_per_week: number | null;
  weekly_driving_limit_minutes: number | null;
  fortnight_driving_limit_minutes: number | null;
  min_layover_minutes: number | null;
  pullout_minutes: number | null;
  pullback_minutes: number | null;
  idle_time_is_paid: boolean | null;
  waiting_time_pay_pct: number | null;
  min_guaranteed_work_minutes: number | null;
  max_unpaid_break_minutes: number | null;
  max_total_unpaid_break_minutes: number | null;
  long_unpaid_break_limit_minutes: number | null;
  long_unpaid_break_penalty_weight: number | null;
  allow_relief_points: boolean | null;
  enforce_same_depot_start_end: boolean | null;
  fairness_weight: number | null;
  fairness_target_work_minutes: number | null;
  fairness_tolerance_minutes: number | null;
  operator_change_terminals_only: boolean | null;
  enforce_trip_groups_hard: boolean | null;
  operator_pairing_hard: boolean | null;
  sunday_off_weight: number | null;
  holiday_extra_pct: number | null;
  enforce_single_line_duty: boolean | null;
  operator_single_vehicle_only: boolean | null;
  nocturnal_start_hour: number | null;
  nocturnal_end_hour: number | null;
  nocturnal_factor: number | null;
  nocturnal_extra_pct: number | null;
  apply_cct: boolean | null;
  strict_hard_validation: boolean | null;
  strict_union_rules: boolean | null;
  terminal_location_ids: number[];
  goal_weights: Record<string, number> | null;
  dynamic_rules: any[] | null;
}

const DEFAULTS: CompanyParameters = {
  driver_cost_per_minute: 0.5,
  collector_cost_per_minute: 0.4,
  vehicle_fixed_cost: 800.0,
  cost_vehicle: 1000.0,
  cost_km: 1.0,
  cost_duty: 500.0,
  force_round_trip: true,
  allow_vehicle_swap: false,
  time_budget_s: null,
  random_seed: null,
  max_vehicle_shift_minutes: null,
  max_vehicles: null,
  deadhead_cost_per_minute: null,
  idle_cost_per_minute: null,
  allow_multi_line_block: null,
  allow_vehicle_split_shifts: null,
  split_shift_min_gap_minutes: null,
  split_shift_max_gap_minutes: null,
  max_simultaneous_chargers: null,
  enable_column_generation: null,
  pricing_enabled: null,
  use_set_covering: null,
  min_workpiece_minutes: null,
  max_workpiece_minutes: null,
  min_trips_per_piece: null,
  max_trips_per_piece: null,
  peak_energy_cost_per_kwh: null,
  offpeak_energy_cost_per_kwh: null,
  preferred_pair_window_minutes: null,
  preserve_preferred_pairs: true,
  pair_break_penalty: null,
  paired_trip_bonus: null,
  max_connection_cost_for_reuse_ratio: null,
  max_candidate_successors_per_task: null,
  max_generated_columns: null,
  max_pricing_iterations: null,
  max_pricing_additions: null,
  vehicle_idle_gap_behavior: 'solver_decides',
  vehicle_idle_gap_threshold_minutes: null,
  max_driving_time_minutes: 480,
  meal_break_minutes: 60,
  max_shift_minutes: 720,
  max_work_minutes: null,
  min_work_minutes: null,
  min_shift_minutes: null,
  overtime_limit_minutes: null,
  max_driving_minutes: null,
  min_break_minutes: null,
  connection_tolerance_minutes: null,
  mandatory_break_after_minutes: null,
  split_break_first_minutes: null,
  split_break_second_minutes: null,
  inter_shift_rest_minutes: null,
  weekly_rest_minutes: null,
  reduced_weekly_rest_minutes: null,
  allow_reduced_weekly_rest: null,
  daily_driving_limit_minutes: null,
  extended_daily_driving_limit_minutes: null,
  max_extended_driving_days_per_week: null,
  weekly_driving_limit_minutes: null,
  fortnight_driving_limit_minutes: null,
  min_layover_minutes: null,
  pullout_minutes: null,
  pullback_minutes: null,
  idle_time_is_paid: null,
  waiting_time_pay_pct: null,
  min_guaranteed_work_minutes: null,
  max_unpaid_break_minutes: null,
  max_total_unpaid_break_minutes: null,
  long_unpaid_break_limit_minutes: null,
  long_unpaid_break_penalty_weight: null,
  allow_relief_points: false,
  enforce_same_depot_start_end: false,
  fairness_weight: null,
  fairness_target_work_minutes: null,
  fairness_tolerance_minutes: null,
  operator_change_terminals_only: true,
  enforce_trip_groups_hard: true,
  operator_pairing_hard: true,
  sunday_off_weight: null,
  holiday_extra_pct: null,
  enforce_single_line_duty: false,
  operator_single_vehicle_only: true,
  nocturnal_start_hour: null,
  nocturnal_end_hour: null,
  nocturnal_factor: null,
  nocturnal_extra_pct: null,
  apply_cct: true,
  strict_hard_validation: true,
  strict_union_rules: true,
  terminal_location_ids: [],
  goal_weights: null,
  dynamic_rules: null,
};

const BOOLEAN_DEFAULTS: Partial<Record<keyof CompanyParameters, boolean>> = {
  force_round_trip: true,
  allow_vehicle_swap: false,
  preserve_preferred_pairs: true,
  allow_relief_points: false,
  enforce_same_depot_start_end: false,
  operator_change_terminals_only: true,
  enforce_trip_groups_hard: true,
  operator_pairing_hard: true,
  enforce_single_line_duty: false,
  operator_single_vehicle_only: true,
  apply_cct: true,
  strict_hard_validation: true,
  strict_union_rules: true,
};
const EMPTY_GOAL_WEIGHTS: Record<string, number> = {};
const EMPTY_DYNAMIC_RULES: any[] = [];

function normalizeParameters(data: Partial<CompanyParameters>): CompanyParameters {
  const merged = { ...DEFAULTS, ...data } as CompanyParameters;
  for (const [key, fallback] of Object.entries(BOOLEAN_DEFAULTS) as [keyof CompanyParameters, boolean][]) {
    if (merged[key] === null || merged[key] === undefined) {
      (merged as any)[key] = fallback;
    }
  }
  return merged;
}

// Helpers
function numField(
  params: CompanyParameters,
  setParams: React.Dispatch<React.SetStateAction<CompanyParameters>>,
  key: keyof CompanyParameters,
  label: string,
  tooltip: string,
  unit?: string,
  isFloat?: boolean,
  step?: string
) {
  const value = params[key];
  return (
    <Tooltip title={tooltip} arrow placement="top">
      <TextField
        label={label}
        type="number"
        fullWidth
        size="small"
        value={value === null || value === undefined ? "" : value}
        onChange={(e) => {
          const raw = e.target.value;
          let parsed = raw === "" ? null : isFloat ? parseFloat(raw) : parseInt(raw);
          
          // Validação: Impedir valores negativos
          if (parsed !== null && parsed < 0) parsed = 0;
          
          setParams((prev) => ({ ...prev, [key]: parsed }));
        }}
        slotProps={{
          htmlInput: { step: step || (isFloat ? '0.01' : '1') },
          input: {
            endAdornment: unit ? <InputAdornment position="end">{unit}</InputAdornment> : undefined,
          },
        }}
      />
    </Tooltip>
  );
}

function intArrayField(
  params: CompanyParameters,
  setParams: React.Dispatch<React.SetStateAction<CompanyParameters>>,
  key: "terminal_location_ids",
  label: string,
  tooltip: string
) {
  const value = Array.isArray(params[key]) ? params[key].join(", ") : "";
  return (
    <Tooltip title={tooltip} arrow placement="top">
      <TextField
        label={label}
        fullWidth
        size="small"
        value={value}
        onChange={(e) => {
          const raw = e.target.value.trim();
          const parsed = raw
            ? raw.split(/[,\s]+/).map((item) => Number.parseInt(item, 10)).filter((item) => Number.isFinite(item))
            : [];
          setParams((prev) => ({ ...prev, [key]: parsed }));
        }}
        helperText="IDs separados por virgula"
      />
    </Tooltip>
  );
}

function JsonField({
  label,
  tooltip,
  value,
  onChange,
  fallback,
}: {
  label: string;
  tooltip: string;
  value: unknown;
  onChange: (value: any) => void;
  fallback: unknown;
}) {
  const [text, setText] = useState(() => JSON.stringify(value ?? fallback, null, 2));
  const [error, setError] = useState("");

  return (
    <Tooltip title={tooltip} arrow placement="top">
      <TextField
        label={label}
        fullWidth
        multiline
        minRows={3}
        size="small"
        value={text}
        error={Boolean(error)}
        helperText={error || "JSON valido"}
        onChange={(e) => {
          const nextText = e.target.value;
          setText(nextText);
          try {
            onChange(nextText.trim() ? JSON.parse(nextText) : fallback);
            setError("");
          } catch {
            setError("JSON invalido, corrija antes de salvar");
          }
        }}
      />
    </Tooltip>
  );
}

function boolField(
  params: CompanyParameters,
  setParams: React.Dispatch<React.SetStateAction<CompanyParameters>>,
  key: keyof CompanyParameters,
  label: string,
  tooltip: string
) {
  const value = params[key];
  return (
    <Tooltip title={tooltip} arrow placement="top">
      <FormControlLabel
        control={
          <Switch
            checked={value === true}
            onChange={(e) => setParams((prev) => ({ ...prev, [key]: e.target.checked }))}
            color="primary"
          />
        }
        label={label}
      />
    </Tooltip>
  );
}

export default function ParametersPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [params, setParams] = useState<CompanyParameters>({ ...DEFAULTS });
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    severity: "success" | "error";
  }>({
    open: false,
    message: "",
    severity: "success",
  });

  useEffect(() => {
    fetchParameters();
  }, []);

  const fetchParameters = async () => {
    try {
      const data = await parametersApi.get();
      setParams(normalizeParameters(data));
    } catch (error) {
      console.error("Erro ao buscar parametros:", error);
      setNotification({ open: true, message: "Erro ao carregar parametros. Usando valores padrao.", severity: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await parametersApi.update(params);
      setNotification({ open: true, message: "Configuracoes salvas com sucesso!", severity: "success" });
    } catch (error) {
      console.error("Erro ao salvar parametros:", error);
      setNotification({ open: true, message: "Erro ao salvar configuracoes.", severity: "error" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Skeleton variant="rectangular" width="100%" height={400} sx={{ borderRadius: 2 }} />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Parametros Operacionais e CCT"
        subtitle="Todos os parametros do motor de otimizacao. Campos vazios usam o valor padrao do solver."
      >
        <Stack spacing={2}>
          {/* ═══════════ SECAO 1: Custos Operacionais ═══════════ */}
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconCurrencyReal size={20} />
                <Typography sx={{ fontWeight: 600 }}>Custos Operacionais</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "driver_cost_per_minute", "Custo Motorista", "Custo por minuto do motorista em R$", "R$/min", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "collector_cost_per_minute", "Custo Cobrador", "Custo por minuto do cobrador em R$", "R$/min", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "vehicle_fixed_cost", "Custo Fixo Veiculo", "Custo fixo por veiculo ativado", "R$", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "cost_vehicle", "Peso por Veículo", "Influencia a redução da frota no solver", "peso", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "cost_km", "Custo por KM Morto/Produtivo", "Influencia a redução de quilometragem no solver", "peso", true, "0.1")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "cost_duty", "Custo por Jornada (Motorista)", "Influencia o número total de motoristas", "peso", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "waiting_time_pay_pct", "% Pagamento Espera", "Percentual do tempo de espera que e pago (0.0 a 1.0)", "%", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "holiday_extra_pct", "% Extra Feriado", "Adicional percentual sobre horas em feriado", "%", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "sunday_off_weight", "Peso Folga Domingo", "Peso para priorizar folga dominical no solver", "", true)}
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 2: Jornada e Limites de Tempo ═══════════ */}
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconClock size={20} />
                <Typography sx={{ fontWeight: 600 }}>Jornada e Limites de Tempo</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_shift_minutes", "Jornada Maxima", "Duracao maxima da escala (spread) em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "min_shift_minutes", "Jornada Minima", "Duracao minima da escala em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_work_minutes", "Trabalho Maximo", "Tempo maximo efetivo de trabalho em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "min_work_minutes", "Trabalho Minimo", "Tempo minimo efetivo de trabalho em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_driving_time_minutes", "Direcao Maxima (Base)", "Tempo maximo de direcao continua em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_driving_minutes", "Direcao Max (CCT)", "Limite CCT de direcao continua em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "overtime_limit_minutes", "Limite Hora Extra", "Maximo de hora extra permitida por jornada", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "min_guaranteed_work_minutes", "Trabalho Garantido", "Minimo garantido de trabalho pago", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "daily_driving_limit_minutes", "Direcao Diaria Limite", "Limite diario de direcao em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "extended_daily_driving_limit_minutes", "Direcao Diaria Estendida", "Limite estendido de direcao diaria", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_extended_driving_days_per_week", "Dias Estendidos/Semana", "Maximo de dias com direcao estendida por semana", "dias")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "weekly_driving_limit_minutes", "Direcao Semanal", "Limite de direcao semanal em minutos", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "fortnight_driving_limit_minutes", "Direcao Quinzenal", "Limite de direcao quinzenal em minutos", "min")}
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 3: Intervalos e Descanso ═══════════ */}
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconScale size={20} />
                <Typography sx={{ fontWeight: 600 }}>Intervalos e Descanso</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "meal_break_minutes", "Intervalo Refeicao", "Duracao do intervalo de refeicao", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "min_break_minutes", "Intervalo Minimo", "Duracao minima de intervalo", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "mandatory_break_after_minutes", "Pausa Obrigatoria Apos", "Tempo de trabalho continuo antes de pausa obrigatoria", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "split_break_first_minutes", "Pausa Fracionada 1a", "Primeira parte da pausa fracionada", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "split_break_second_minutes", "Pausa Fracionada 2a", "Segunda parte da pausa fracionada", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "inter_shift_rest_minutes", "Descanso Entre Jornadas", "Tempo minimo de descanso entre jornadas", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "weekly_rest_minutes", "Descanso Semanal", "Tempo de descanso semanal obrigatorio", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "reduced_weekly_rest_minutes", "Descanso Semanal Reduzido", "Tempo de descanso semanal reduzido (se permitido)", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_unpaid_break_minutes", "Pausa Nao Paga Max", "Duracao maxima de uma pausa nao remunerada", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "max_total_unpaid_break_minutes", "Total Pausas Nao Pagas", "Soma maxima de todas pausas nao remuneradas", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "long_unpaid_break_limit_minutes", "Limite Pausa Longa", "Duracao acima da qual a pausa e considerada longa", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "long_unpaid_break_penalty_weight", "Penalidade Pausa Longa", "Peso de penalizacao por pausas longas nao pagas", "", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {boolField(params, setParams, "allow_reduced_weekly_rest", "Permitir Descanso Reduzido", "Permite reduzir o descanso semanal")}
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 4: Operacao e Conexoes ═══════════ */}
          <Accordion>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconRoute size={20} />
                <Typography sx={{ fontWeight: 600 }}>Operacao e Conexoes</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "connection_tolerance_minutes", "Tolerancia Conexao", "Tempo maximo entre viagens para considerar conexao valida", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "min_layover_minutes", "Layover Minimo", "Tempo minimo de layover entre viagens", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "pullout_minutes", "Tempo Pull-out", "Tempo para retirada do veiculo da garagem", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "pullback_minutes", "Tempo Pull-back", "Tempo para retorno do veiculo a garagem", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "force_round_trip", "Forcar Viagem Ida e Volta", "Obriga que cada bloco tenha viagens de ida e volta")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "allow_vehicle_swap", "Permitir Troca de Veiculo", "Permite que o motorista troque de veiculo durante a jornada")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "allow_relief_points", "Permitir Pontos de Rendimento", "Permite rendicoes em pontos intermediarios das linhas")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "enforce_same_depot_start_end", "Forcar Mesmo Deposito", "Obriga inicio e fim da jornada no mesmo deposito")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "idle_time_is_paid", "Tempo Ocioso e Pago", "Se o tempo ocioso conta como hora trabalhada")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "operator_change_terminals_only", "Troca Apenas em Terminais", "Rendicoes de operador so nos terminais mapeados")}
                </Grid>
                <Grid size={{ xs: 12 }}>
                  {intArrayField(params, setParams, "terminal_location_ids", "IDs dos Terminais de Rendicao", "Locais autorizados para troca/rendicao de operador quando a regra de terminais estiver ativa")}
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 5: Regras de Escala e Fairness ═══════════ */}
          <Accordion>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconShieldCheck size={20} />
                <Typography sx={{ fontWeight: 600 }}>Regras de Escala e Equidade</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "fairness_weight", "Peso Equidade", "Peso da equidade na funcao objetivo do solver", "", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "fairness_target_work_minutes", "Alvo Trabalho Equidade", "Minutos alvo de trabalho para cada operador", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                  {numField(params, setParams, "fairness_tolerance_minutes", "Tolerancia Equidade", "Tolerancia em minutos para desvio do alvo", "min")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "enforce_trip_groups_hard", "Forcar Grupo de Viagens", "Obriga viagens do mesmo grupo a ficarem na mesma escala")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "operator_pairing_hard", "Forcar Pareamento Operador", "Obriga pareamento rigido de operadores")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "enforce_single_line_duty", "Escala de Linha Unica", "Obriga que cada escala opere em uma unica linha")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "operator_single_vehicle_only", "Operador em Unico Veiculo", "Restringe operador a um unico veiculo por jornada")}
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 6: Noturno ═══════════ */}
          <Accordion>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconMoon size={20} />
                <Typography sx={{ fontWeight: 600 }}>Adicional Noturno</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                  {numField(params, setParams, "nocturnal_start_hour", "Hora Inicio Noturno", "Hora de inicio do periodo noturno (ex: 22)", "h")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                  {numField(params, setParams, "nocturnal_end_hour", "Hora Fim Noturno", "Hora de fim do periodo noturno (ex: 5)", "h")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                  {numField(params, setParams, "nocturnal_factor", "Fator Noturno", "Multiplicador de custo para horas noturnas", "x", true)}
                </Grid>
                <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                  {numField(params, setParams, "nocturnal_extra_pct", "% Extra Noturno", "Percentual adicional sobre horas noturnas", "%", true)}
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 7: Validacao e Modo Estrito ═══════════ */}
          <Accordion>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconSettings size={20} />
                <Typography sx={{ fontWeight: 600 }}>Validacao e Controle</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "apply_cct", "Aplicar CCT", "Ativa todas as regras da Convencao Coletiva de Trabalho")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "strict_hard_validation", "Validacao Estrita", "Rejeita solucoes que violem restricoes hard")}
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  {boolField(params, setParams, "strict_union_rules", "Regras Sindicais Estritas", "Aplica regras sindicais em modo estrito")}
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <JsonField
                    label="Pesos do Objetivo"
                    tooltip="JSON de pesos consumido pelo optimizer, como fairness, overtime, spread e passive_transfer"
                    value={params.goal_weights}
                    fallback={EMPTY_GOAL_WEIGHTS}
                    onChange={(value) => setParams((prev) => ({ ...prev, goal_weights: value }))}
                  />
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <JsonField
                    label="Regras Dinamicas"
                    tooltip="Lista JSON de regras dinamicas de custo aplicadas pelo motor"
                    value={params.dynamic_rules}
                    fallback={EMPTY_DYNAMIC_RULES}
                    onChange={(value) => setParams((prev) => ({ ...prev, dynamic_rules: value }))}
                  />
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ SECAO 8: Motor do Solver ═══════════ */}
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<IconChevronDown />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconBolt size={20} />
                <Typography sx={{ fontWeight: 600 }}>Motor do Solver — Desempenho e Pareamento</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Alert severity="info" sx={{ mb: 1 }}>
                  Esses parâmetros controlam diretamente o algoritmo de otimização. Valores maiores de orçamento de tempo produzem soluções melhores, mas demoram mais.
                </Alert>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "time_budget_s", "Orçamento de Tempo (s)", "Tempo máximo em segundos que o solver pode rodar. Deixe vazio para usar o padrão do algoritmo. Recomendado: 60–300s para vcsp_pulp.", "s", true, "1")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "random_seed", "Seed Aleatoria", "Seed opcional para reduzir variacao em algoritmos estocasticos.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_vehicles", "Maximo de Veiculos", "Limite superior de veiculos que o VSP pode ativar.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_vehicle_shift_minutes", "Jornada Max Veiculo", "Duracao maxima de um bloco de veiculo em minutos.", "min")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "preferred_pair_window_minutes", "Janela de Pareamento (min)", "Intervalo máximo em minutos entre viagens para considerá-las um par preferencial (IDA+VOLTA). Clamped para [5, 90] pelo solver. Padrão: 30.", "min")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "pair_break_penalty", "Penalidade Quebra de Par", "Penalidade aplicada quando um par IDA+VOLTA preferencial e separado.", "peso", true)}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "paired_trip_bonus", "Bonus Par Preservado", "Bonus para manter pares IDA+VOLTA no mesmo bloco.", "peso", true)}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    {boolField(params, setParams, "preserve_preferred_pairs", "Preservar Pares Preferenciais", "Incentiva o solver a manter viagens IDA+VOLTA no mesmo bloco, reduzindo deadheads e melhorando a utilização dos veículos.")}
                  </Grid>
                  {/* Comportamento do veículo em intervalos longos */}
                  <Grid size={{ xs: 12 }}>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                      Comportamento do Veículo em Intervalos Longos
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                      Define o que acontece quando um veículo tem um intervalo longo entre viagens no mesmo bloco.
                    </Typography>
                    <ToggleButtonGroup
                      exclusive
                      size="small"
                      value={params.vehicle_idle_gap_behavior ?? 'solver_decides'}
                      onChange={(_, v) => { if (v) setParams(p => ({ ...p, vehicle_idle_gap_behavior: v })); }}
                    >
                      <ToggleButton value="solver_decides">Solver Decide</ToggleButton>
                      <ToggleButton value="stay_at_terminal">Ficar no Terminal</ToggleButton>
                      <ToggleButton value="return_to_garage">Recolher para Garagem</ToggleButton>
                    </ToggleButtonGroup>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                      {params.vehicle_idle_gap_behavior === 'stay_at_terminal' && '→ Veículo permanece no terminal indefinidamente (sem limite de intervalo).'}
                      {params.vehicle_idle_gap_behavior === 'return_to_garage' && '→ Acima do limite abaixo, o solver força um novo bloco (recolhimento + soltura).'}
                      {(!params.vehicle_idle_gap_behavior || params.vehicle_idle_gap_behavior === 'solver_decides') && '→ O solver decide com base nos custos operacionais (padrão: refeição + 180 min).'}
                    </Typography>
                  </Grid>
                  {params.vehicle_idle_gap_behavior === 'return_to_garage' && (
                    <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                      {numField(params, setParams, "vehicle_idle_gap_threshold_minutes", "Limite de Intervalo (min)", "Intervalo acima deste valor força o veículo a recolher e sair novamente. Ex: 300 = 5 horas.", "min")}
                    </Grid>
                  )}

                  <Grid size={{ xs: 12 }}>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                      VSP Avançado
                    </Typography>
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    {boolField(params, setParams, "allow_multi_line_block", "Permitir Bloco Multi-linha", "Permite que um mesmo veiculo execute viagens de linhas diferentes.")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    {boolField(params, setParams, "allow_vehicle_split_shifts", "Permitir Bloco Partido", "Permite dividir a operacao do veiculo em janelas separadas.")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "split_shift_min_gap_minutes", "Gap Min Bloco Partido", "Gap minimo para considerar bloco partido.", "min")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "split_shift_max_gap_minutes", "Gap Max Bloco Partido", "Gap maximo aceito para bloco partido.", "min")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "deadhead_cost_per_minute", "Custo Deadhead/min", "Custo por minuto de deslocamento improdutivo.", "R$/min", true)}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "idle_cost_per_minute", "Custo Ocioso/min", "Custo por minuto de ociosidade do veiculo.", "R$/min", true)}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_connection_cost_for_reuse_ratio", "Limite Reuso por Custo", "Razao maxima de custo de conexao para reusar o veiculo.", "", true, "0.01")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_candidate_successors_per_task", "Sucessores por Tarefa", "Maximo de sucessores candidatos por tarefa.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_generated_columns", "Max Colunas Geradas", "Limite de colunas geradas em formulacoes de coluna.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_pricing_iterations", "Iteracoes Pricing", "Limite de iteracoes do pricing.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_pricing_additions", "Adicoes Pricing", "Limite de colunas adicionadas por rodada de pricing.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    {boolField(params, setParams, "enable_column_generation", "Ativar Geração de Colunas", "Ativa geracao de colunas quando o algoritmo suportar.")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    {boolField(params, setParams, "pricing_enabled", "Ativar Pricing", "Ativa etapa de pricing para gerar alternativas.")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    {boolField(params, setParams, "use_set_covering", "Usar Set Covering", "Usa formulacao de cobertura quando disponivel.")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "min_workpiece_minutes", "Peca Minima", "Duracao minima de uma workpiece.", "min")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_workpiece_minutes", "Peca Maxima", "Duracao maxima de uma workpiece.", "min")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "min_trips_per_piece", "Viagens Min por Peca", "Quantidade minima de viagens por workpiece.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_trips_per_piece", "Viagens Max por Peca", "Quantidade maxima de viagens por workpiece.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "max_simultaneous_chargers", "Carregadores Simultaneos", "Capacidade maxima de carregadores EV simultaneos.", "")}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "peak_energy_cost_per_kwh", "Energia Pico/kWh", "Custo de energia EV em horario de pico.", "R$/kWh", true)}
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                    {numField(params, setParams, "offpeak_energy_cost_per_kwh", "Energia Fora Pico/kWh", "Custo de energia EV fora de pico.", "R$/kWh", true)}
                  </Grid>
                </Grid>
              </Stack>
            </AccordionDetails>
          </Accordion>

          {/* ═══════════ BOTAO SALVAR ═══════════ */}
          <Divider />
          <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
            <Button
              variant="contained"
              size="large"
              color="primary"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Salvando..." : "Salvar Todas as Configuracoes"}
            </Button>
          </Box>
        </Stack>
      </DashboardCard>

      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={() => setNotification({ ...notification, open: false })}
      >
        <Alert severity={notification.severity} sx={{ width: "100%" }}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
