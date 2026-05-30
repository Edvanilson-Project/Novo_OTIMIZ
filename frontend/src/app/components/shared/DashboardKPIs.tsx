"use client";

import React from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
  Tooltip,
  Typography,
  Stack,
  useTheme,
  keyframes,
} from "@mui/material";
import {
  IconBus,
  IconClock,
  IconCurrencyDollar,
  IconAlertTriangle,
  IconRoute,
  IconScale,
  IconCar,
  IconBolt,
} from "@tabler/icons-react";

const pulseGlow = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(93, 135, 255, 0.4); }
  50% { box-shadow: 0 0 16px 4px rgba(93, 135, 255, 0.6); }
  100% { box-shadow: 0 0 0 0 rgba(93, 135, 255, 0); }
`;

const pulseError = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.4); }
  50% { box-shadow: 0 0 16px 4px rgba(211, 47, 47, 0.6); }
  100% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); }
`;

/**
 * Schedule é polimórfico por design — vem de múltiplas fontes (latest-schedule,
 * resultSummary, metadata) com aliases camelCase e snake_case e estrutura
 * aninhada que muda entre versões do solver. Tipá-lo exaustivamente quebra
 * mais do que protege. Os tipos concretos vivem nos loops internos abaixo.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ScheduleLike = any;

interface KPIProps {
  schedule: ScheduleLike;
}

/**
 * KPI card that flashes when its value changes.
 * Uses a `key` based on the raw value so React remounts the card,
 * restarting the CSS animation without any setState-in-effect.
 */
const KPICard: React.FC<{
  title: string;
  value: string;
  changeKey: string;
  icon: React.ReactNode;
  color: string;
  isError?: boolean;
}> = ({ title, value, changeKey, icon, color, isError }) => {
  const theme = useTheme();

  return (
    <Card
      key={changeKey}
      elevation={0}
      sx={{
        backgroundColor: theme.palette.mode === "dark" ? "#252b48" : "#f0f5ff",
        borderRadius: "12px",
        transition: "all 0.3s ease",
        animation: `${isError ? pulseError : pulseGlow} 0.6s ease-in-out 2`,
        border: `2px solid transparent`,
      }}
    >
      <CardContent>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
          <Box
            sx={{
              width: 48,
              height: 48,
              backgroundColor:
                theme.palette.mode === "dark"
                  ? "rgba(255,255,255,0.05)"
                  : "white",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color,
            }}
          >
            {icon}
          </Box>
          <Box>
            <Typography variant="subtitle2" color="textSecondary" gutterBottom>
              {title}
            </Typography>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>
              {value}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
};

const DashboardKPIs: React.FC<KPIProps> = ({ schedule }) => {
  const theme = useTheme();

  const numVehicles = schedule?.blocks?.length || 0;
  const totalCost = schedule?.totalCost ?? schedule?.resultSummary?.totalCost ?? 0;
  const hardIssueCount = schedule?.hardIssueCount ?? schedule?.hard_issue_count ?? schedule?.resultSummary?.hardIssueCount ?? 0;
  const softIssueCount = schedule?.softIssueCount ?? schedule?.soft_issue_count ?? schedule?.resultSummary?.softIssueCount ?? 0;
  const splitGroups =
    schedule?.trip_group_audit?.split_groups ??
    schedule?.tripGroupAudit?.split_groups ??
    schedule?.resultSummary?.tripGroupAudit?.split_groups ??
    schedule?.resultSummary?.trip_group_audit?.split_groups ??
    0;

  // Equidade entre motoristas (Gini sobre work_time): 0 = perfeitamente igual, 1 = desigual.
  // costBreakdown vem em vários caminhos dependendo de onde a schedule é carregada
  // (latest-schedule hidrata em resultSummary.costBreakdown; alguns flows passam direto).
  const fairness =
    schedule?.resultSummary?.costBreakdown?.csp?.fairness ??
    schedule?.metadata?.cost_breakdown?.csp?.fairness ??
    schedule?.cost_breakdown?.csp?.fairness ??
    null;
  const fairnessGini = fairness?.work_time?.gini ?? null;
  const dutiesBelow50 = fairness?.imbalance?.duties_below_50pct_avg ?? 0;

  // Gap de otimalidade: melhor lower bound disponível (Bodin & Golden, Lagrangian ou Bundle).
  // Mesmos caminhos do fairness — depende de onde o schedule foi hidratado.
  const optimality =
    schedule?.resultSummary?.costBreakdown?.optimality ??
    schedule?.metadata?.cost_breakdown?.optimality ??
    schedule?.cost_breakdown?.optimality ??
    null;
  const optimalityGapPct = optimality?.vsp_gap_pct ?? null;
  const optimalityLbMethod = optimality?.lb_method ?? null;
  const optimalityLb = optimality?.vsp_lower_bound ?? null;
  const optimalityUb = optimality?.vsp_actual ?? null;
  const optimalityCertified = optimality?.is_optimal_certified ?? false;
  // Bodin & Golden é o lower bound de concorrência (trips simultâneas): sempre disponível,
  // mas frouxo para VSP com deadhead/depot — o ótimo real (ex.: provado por MCNF) fica acima.
  // Quando o gap é medido só contra ele, é teórico, não subotimalidade real.
  const optimalityLooseBound =
    !optimalityCertified &&
    optimalityGapPct !== null &&
    (optimalityLbMethod === 'bodin_golden' ||
      optimalityLbMethod === 'none' ||
      optimalityLbMethod == null); // formato legado (sem lb_method) = bound de concorrência

  // Rendições de motoristas (ReliefVehicleEstimator)
  const reliefEst =
    schedule?.metadata?.relief_vehicle_estimate ??
    schedule?.resultSummary?.metadata?.relief_vehicle_estimate ??
    null;
  const reliefEvents = reliefEst?.total_events ?? null;
  const reliefVehicles = reliefEst?.min_vehicles ?? null;
  const reliefPeakHour = reliefEst?.peak_hour != null ? `${reliefEst.peak_hour}h` : null;

  // EV SoC report
  const evSoc =
    schedule?.metadata?.ev_soc_report ??
    schedule?.resultSummary?.metadata?.ev_soc_report ??
    null;
  const evEnergyKwh = evSoc?.total_energy_kwh ?? null;
  const evBlocksMidCharge = evSoc?.blocks_needing_mid_charge ?? null;

  type BlockLike = {
    trips?: Array<Record<string, unknown>>;
    metadata?: { trips?: Array<Record<string, unknown>> };
  };
  let totalMinutes = 0;
  let totalTrips = Number(schedule?.totalTrips ?? schedule?.resultSummary?.total_trips ?? 0);
  schedule?.blocks?.forEach((b: BlockLike) => {
    // Suporta tanto b.trips (hidratado) quanto b.metadata?.trips (legado)
    const trips = (b.trips || b.metadata?.trips || []) as Array<Record<string, unknown>>;
    if (!schedule?.totalTrips && !schedule?.resultSummary?.total_trips) {
      totalTrips += trips.length;
    }
    trips.forEach((t) => {
      const start = Number(t.start_time ?? t.startTime ?? 0);
      const end = Number(t.end_time ?? t.endTime ?? 0);
      totalMinutes += end - start;
    });
  });
  const totalHours = (totalMinutes / 60).toFixed(1);

  // Usar o schedule como key-seed: quando o schedule muda (drag-drop -> fetchSchedule),
  // os cards remontam e a animacao CSS reinicia automaticamente.
  const scheduleVersion = schedule?.updatedAt || schedule?.createdAt || "none";

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <KPICard
          title="Frota Utilizada"
          value={`${numVehicles} Veículos`}
          changeKey={`vehicles-${numVehicles}-${scheduleVersion}`}
          icon={<IconBus size="24" />}
          color={theme.palette.primary.main}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <KPICard
          title="Total de Viagens"
          value={`${totalTrips} Viagens`}
          changeKey={`trips-${totalTrips}-${scheduleVersion}`}
          icon={<IconRoute size="24" />}
          color={theme.palette.secondary.main}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <KPICard
          title="Custo Total"
          value={`R$ ${totalCost.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`}
          changeKey={`cost-${totalCost}-${scheduleVersion}`}
          icon={<IconCurrencyDollar size="24" />}
          color={theme.palette.success.main}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <KPICard
          title="Horas de Condução"
          value={`${totalHours}h`}
          changeKey={`hours-${totalHours}-${scheduleVersion}`}
          icon={<IconClock size="24" />}
          color={theme.palette.info.main}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <Tooltip
          arrow
          title={
            <Box>
              <Typography variant="caption" sx={{ display: 'block' }}>
                <strong>Hard Issues</strong> — Violações obrigatórias das restrições.
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                Exemplos: jornada acima do CCT máximo, viagem sem cobertura de veículo, conflito de horário.
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                0 = agendamento viável e válido.
              </Typography>
            </Box>
          }
        >
          <Box>
            <KPICard
              title="Hard Issues"
              value={`${hardIssueCount}`}
              changeKey={`hard-issues-${hardIssueCount}-${scheduleVersion}`}
              icon={<IconAlertTriangle size="24" />}
              color={hardIssueCount > 0 ? theme.palette.error.main : theme.palette.text.secondary}
              isError={hardIssueCount > 0}
            />
          </Box>
        </Tooltip>
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <Tooltip
          arrow
          title={
            <Box>
              <Typography variant="caption" sx={{ display: 'block' }}>
                <strong>Soft Issues</strong> — Violações de preferências e heurísticas.
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                Exemplos: pausa de repouso desconfortável, rodízio desequilibrado, custo marginal alto.
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                Não invalidam a solução, mas indicam oportunidades de melhoria.
              </Typography>
            </Box>
          }
        >
          <Box>
            <KPICard
              title="Soft Issues"
              value={`${softIssueCount}`}
              changeKey={`soft-issues-${softIssueCount}-${scheduleVersion}`}
              icon={<IconAlertTriangle size="24" />}
              color={softIssueCount > 0 ? theme.palette.warning.main : theme.palette.text.secondary}
            />
          </Box>
        </Tooltip>
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <Tooltip
          arrow
          title={
            <Box>
              <Typography variant="caption" sx={{ display: 'block' }}>
                <strong>Trip Groups Split</strong> — Quantidade de viagens fragmentadas.
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                Uma viagem "split" é aquela que deveria ser um grupo contíguo, mas foi dividida entre múltiplas jornadas.
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                0 = todas as viagens mantêm continuidade. Mais splits = menos eficiência operacional.
              </Typography>
            </Box>
          }
        >
          <Box>
            <KPICard
              title="Trip Groups Split"
              value={`${splitGroups}`}
              changeKey={`split-groups-${splitGroups}-${scheduleVersion}`}
              icon={<IconRoute size="24" />}
              color={splitGroups > 0 ? theme.palette.error.main : theme.palette.success.main}
              isError={splitGroups > 0}
            />
          </Box>
        </Tooltip>
      </Grid>
      {fairnessGini !== null && (
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <Tooltip
            arrow
            title={
              <Box>
                <Typography variant="caption" sx={{ display: 'block' }}>
                  <strong>Coeficiente de Gini</strong> sobre tempo de trabalho.
                </Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>
                  0 = perfeitamente igual entre todas as jornadas.
                </Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>
                  &gt; 0,3 = desigualdade alta (alguns motoristas com muito mais trabalho).
                </Typography>
                {dutiesBelow50 > 0 && (
                  <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                    {dutiesBelow50} jornada(s) abaixo de 50% da média.
                  </Typography>
                )}
              </Box>
            }
          >
            <Box>
              <KPICard
                title="Equidade (Gini)"
                value={Number(fairnessGini).toFixed(3)}
                changeKey={`fairness-${fairnessGini}-${scheduleVersion}`}
                icon={<IconScale size="24" />}
                color={
                  Number(fairnessGini) > 0.3
                    ? theme.palette.error.main
                    : Number(fairnessGini) > 0.15
                    ? theme.palette.warning.main
                    : theme.palette.success.main
                }
                isError={Number(fairnessGini) > 0.3}
              />
            </Box>
          </Tooltip>
        </Grid>
      )}
      {optimality !== null && (
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <Tooltip
            arrow
            title={
              <Box>
                {optimalityGapPct === null ? (
                  <>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      <strong>Otimalidade desconhecida</strong> — sem certificado de lower bound.
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                      Não é possível calcular o gap de otimalidade sem um lower bound válido.
                    </Typography>
                  </>
                ) : (
                  <>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      <strong>Gap de Otimalidade</strong> = (UB − LB) / LB × 100.
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      LB = {optimalityLb} (método: {optimalityLbMethod}) · UB = {optimalityUb} veículos.
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                      Calculado usando o melhor lower bound disponível entre Bodin &amp; Golden,
                      Lagrangian e Bundle — quanto menor, mais próximo do ótimo provado.
                    </Typography>
                    {optimalityLooseBound && (
                      <Typography variant="caption" sx={{ display: 'block', mt: 0.5, fontWeight: 'bold' }}>
                        Bound teórico (concorrência): a frota mínima viável fica acima dele por
                        restrições operacionais reais (deadhead, depósito, jornada). Não indica
                        subotimalidade — é o limite inferior frouxo, não o ótimo alcançável.
                      </Typography>
                    )}
                    {optimalityCertified && (
                      <Typography variant="caption" sx={{ display: 'block', mt: 0.5, fontWeight: 'bold' }}>
                        ✓ Ótimo certificado (gap = 0).
                      </Typography>
                    )}
                  </>
                )}
              </Box>
            }
          >
            <Box>
              <KPICard
                title="Gap de Otimalidade"
                value={
                  optimalityGapPct === null
                    ? 'Desconhecida'
                    : optimalityCertified
                    ? '0% (Ótimo)'
                    : optimalityLooseBound
                    ? `≤ ${Number(optimalityGapPct).toFixed(1)}% (teórico)`
                    : `${Number(optimalityGapPct).toFixed(1)}%`
                }
                changeKey={`opt-gap-${optimalityGapPct}-${scheduleVersion}`}
                icon={<IconScale size="24" />}
                color={
                  optimalityGapPct === null
                    ? theme.palette.text.secondary
                    : optimalityCertified || Number(optimalityGapPct) < 5
                    ? theme.palette.success.main
                    : optimalityLooseBound
                    ? theme.palette.info.main
                    : Number(optimalityGapPct) < 15
                    ? theme.palette.warning.main
                    : theme.palette.error.main
                }
                isError={optimalityGapPct !== null && !optimalityLooseBound && Number(optimalityGapPct) >= 15}
              />
            </Box>
          </Tooltip>
        </Grid>
      )}
      {reliefEvents !== null && (
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <Tooltip
            arrow
            title={
              <Box>
                <Typography variant="caption" sx={{ display: 'block' }}>
                  <strong>Rendições de motoristas</strong> detectadas nas jornadas.
                </Typography>
                <Typography variant="caption" sx={{ display: 'block' }}>
                  {reliefVehicles} veículo(s) de apoio estimado(s) (greedy earliest-finish).
                </Typography>
                {reliefPeakHour && (
                  <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                    Pico de rendições: {reliefPeakHour}.
                  </Typography>
                )}
              </Box>
            }
          >
            <Box>
              <KPICard
                title="Rendições"
                value={`${reliefEvents} (${reliefVehicles} apoio)`}
                changeKey={`relief-${reliefEvents}-${scheduleVersion}`}
                icon={<IconCar size="24" />}
                color={reliefEvents > 0 ? theme.palette.warning.main : theme.palette.success.main}
              />
            </Box>
          </Tooltip>
        </Grid>
      )}
      {evEnergyKwh !== null && (
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <Tooltip
            arrow
            title={
              <Box>
                <Typography variant="caption" sx={{ display: 'block' }}>
                  <strong>Energia consumida</strong> pela frota elétrica.
                </Typography>
                {evBlocksMidCharge != null && evBlocksMidCharge > 0 && (
                  <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: "orange" }}>
                    ⚠ {evBlocksMidCharge} bloco(s) precisam de recarga intermediária.
                  </Typography>
                )}
              </Box>
            }
          >
            <Box>
              <KPICard
                title="Energia EV"
                value={`${Number(evEnergyKwh).toFixed(1)} kWh`}
                changeKey={`ev-${evEnergyKwh}-${scheduleVersion}`}
                icon={<IconBolt size="24" />}
                color={
                  evBlocksMidCharge != null && evBlocksMidCharge > 0
                    ? theme.palette.warning.main
                    : theme.palette.info.main
                }
                isError={evBlocksMidCharge != null && evBlocksMidCharge > 0}
              />
            </Box>
          </Tooltip>
        </Grid>
      )}
    </Grid>
  );
};

export default DashboardKPIs;
