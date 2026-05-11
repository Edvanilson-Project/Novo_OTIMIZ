"use client";

import React, { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { IconScale, IconUsersGroup, IconAlertTriangle } from "@tabler/icons-react";
import { operationsApi } from "@/lib/api";

interface Props {
  scheduleId: number;
}

interface FairnessData {
  num_duties: number;
  work_time: {
    min: number;
    max: number;
    mean: number;
    median: number;
    stddev: number;
    cv: number;
    p5: number;
    p95: number;
    gini: number;
  };
  total_cost: {
    min: number;
    max: number;
    mean: number;
    stddev: number;
    cv: number;
    gini: number;
  };
  imbalance: {
    duties_below_50pct_avg: number;
    duties_above_150pct_avg: number;
  };
}

interface DutyWork {
  dutyId: number;
  workMinutes: number;
}

/**
 * Histograma de distribuição de tempo de trabalho (work_time) entre duties +
 * sumário de equidade (Gini, percentis, imbalance counts).
 *
 * Lê dados de:
 *  - schedule.resultSummary.costBreakdown.csp.fairness (Sprint E)
 *  - schedule.duties[*].work_time (para construir os bins)
 */
export default function FairnessHistogram({ scheduleId }: Props) {
  const theme = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fairness, setFairness] = useState<FairnessData | null>(null);
  const [duties, setDuties] = useState<DutyWork[]>([]);

  useEffect(() => {
    setLoading(true);
    operationsApi
      .getLatestSchedule()
      .then((schedule: any) => {
        const fb =
          schedule?.resultSummary?.costBreakdown?.csp?.fairness ??
          schedule?.metadata?.cost_breakdown?.csp?.fairness ??
          schedule?.cost_breakdown?.csp?.fairness ??
          null;
        if (!fb) {
          setError("Métricas de equidade indisponíveis para este schedule.");
          return;
        }
        setFairness(fb as FairnessData);
        const rawDuties: any[] = schedule?.duties ?? schedule?.resultSummary?.duties ?? [];
        const dutyWork: DutyWork[] = rawDuties.map((d) => ({
          dutyId: Number(d.duty_id ?? d.dutyId ?? 0),
          workMinutes: Number(d.work_time ?? d.workMinutes ?? 0),
        }));
        setDuties(dutyWork);
      })
      .catch((err: any) => {
        console.error("[FairnessHistogram] load failed", err);
        setError(err?.message || "Erro ao carregar dados.");
      })
      .finally(() => setLoading(false));
  }, [scheduleId]);

  if (loading) {
    return (
      <Box sx={{ py: 6, display: "flex", justifyContent: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !fairness) {
    return <Alert severity="info">{error ?? "Sem dados."}</Alert>;
  }

  // Bins de 30 minutos para o histograma
  const BIN_WIDTH = 30;
  const minWork = Math.floor(fairness.work_time.min / BIN_WIDTH) * BIN_WIDTH;
  const maxWork = Math.ceil(fairness.work_time.max / BIN_WIDTH) * BIN_WIDTH;
  const numBins = Math.max(1, Math.ceil((maxWork - minWork) / BIN_WIDTH));
  const bins: { range: string; count: number; lowEdge: number }[] = [];
  for (let i = 0; i < numBins; i++) {
    const lo = minWork + i * BIN_WIDTH;
    const hi = lo + BIN_WIDTH;
    bins.push({ range: `${lo}–${hi}min`, count: 0, lowEdge: lo });
  }
  duties.forEach((d) => {
    const idx = Math.min(numBins - 1, Math.max(0, Math.floor((d.workMinutes - minWork) / BIN_WIDTH)));
    bins[idx].count += 1;
  });
  const maxBinCount = Math.max(1, ...bins.map((b) => b.count));

  // Cor do Gini KPI
  const gini = fairness.work_time.gini;
  const giniColor =
    gini > 0.3 ? theme.palette.error.main : gini > 0.15 ? theme.palette.warning.main : theme.palette.success.main;

  return (
    <Stack spacing={3}>
      {/* KPIs resumo */}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconScale size={20} color={giniColor} />
                <Tooltip
                  arrow
                  title="Coeficiente de Gini sobre tempo de trabalho. 0 = perfeitamente igual entre todas as jornadas, > 0,3 = desigualdade alta."
                >
                  <Typography variant="body2" color="text.secondary" sx={{ cursor: "help" }}>
                    Equidade (Gini)
                  </Typography>
                </Tooltip>
              </Stack>
              <Typography variant="h4" sx={{ color: giniColor, fontWeight: 700, mt: 1 }}>
                {gini.toFixed(3)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <IconUsersGroup size={20} />
                <Typography variant="body2" color="text.secondary">
                  Jornadas analisadas
                </Typography>
              </Stack>
              <Typography variant="h4" sx={{ fontWeight: 700, mt: 1 }}>
                {fairness.num_duties}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Card variant="outlined">
            <CardContent>
              <Tooltip arrow title="Jornadas com tempo de trabalho abaixo de 50% da média — possíveis subutilizações.">
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", cursor: "help" }}>
                  <IconAlertTriangle size={20} color={theme.palette.warning.main} />
                  <Typography variant="body2" color="text.secondary">
                    Abaixo de 50% média
                  </Typography>
                </Stack>
              </Tooltip>
              <Typography
                variant="h4"
                sx={{
                  color:
                    fairness.imbalance.duties_below_50pct_avg > 0
                      ? theme.palette.warning.main
                      : theme.palette.success.main,
                  fontWeight: 700,
                  mt: 1,
                }}
              >
                {fairness.imbalance.duties_below_50pct_avg}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Card variant="outlined">
            <CardContent>
              <Tooltip arrow title="Jornadas com tempo de trabalho acima de 150% da média — possíveis sobrecargas.">
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", cursor: "help" }}>
                  <IconAlertTriangle size={20} color={theme.palette.error.main} />
                  <Typography variant="body2" color="text.secondary">
                    Acima de 150% média
                  </Typography>
                </Stack>
              </Tooltip>
              <Typography
                variant="h4"
                sx={{
                  color:
                    fairness.imbalance.duties_above_150pct_avg > 0
                      ? theme.palette.error.main
                      : theme.palette.success.main,
                  fontWeight: 700,
                  mt: 1,
                }}
              >
                {fairness.imbalance.duties_above_150pct_avg}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Estatísticas detalhadas */}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
            Distribuição de tempo de trabalho
          </Typography>
          <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", mb: 2 }}>
            <Chip label={`Min: ${fairness.work_time.min} min`} size="small" />
            <Chip label={`Mediana: ${fairness.work_time.median} min`} size="small" color="primary" />
            <Chip label={`Média: ${fairness.work_time.mean} min`} size="small" color="primary" />
            <Chip label={`Max: ${fairness.work_time.max} min`} size="small" />
            <Chip label={`P5: ${fairness.work_time.p5} min`} size="small" variant="outlined" />
            <Chip label={`P95: ${fairness.work_time.p95} min`} size="small" variant="outlined" />
            <Chip label={`Desvio padrão: ${fairness.work_time.stddev}`} size="small" variant="outlined" />
            <Chip label={`CV: ${(fairness.work_time.cv * 100).toFixed(1)}%`} size="small" variant="outlined" />
          </Stack>

          {/* Histograma — barras CSS, sem dependência adicional */}
          <Box sx={{ mt: 3 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              Frequência de jornadas por faixa de tempo de trabalho (bins de {BIN_WIDTH} min)
            </Typography>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: `repeat(${bins.length}, 1fr)`,
                gap: 0.5,
                alignItems: "end",
                height: 200,
                px: 1,
                py: 1,
                bgcolor: theme.palette.action.hover,
                borderRadius: 1,
              }}
            >
              {bins.map((bin) => {
                const heightPct = (bin.count / maxBinCount) * 100;
                return (
                  <Tooltip key={bin.range} arrow title={`${bin.count} jornada(s) entre ${bin.range}`}>
                    <Box
                      sx={{
                        height: `${heightPct}%`,
                        minHeight: bin.count > 0 ? 6 : 1,
                        bgcolor: bin.count > 0 ? theme.palette.primary.main : "transparent",
                        borderRadius: "3px 3px 0 0",
                        transition: "background-color 0.2s",
                        "&:hover": { bgcolor: theme.palette.primary.dark },
                      }}
                    />
                  </Tooltip>
                );
              })}
            </Box>
            <Stack direction="row" sx={{ justifyContent: "space-between", mt: 0.5, px: 1 }}>
              <Typography variant="caption" color="text.secondary">
                {minWork} min
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {maxWork} min
              </Typography>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      {/* Interpretação */}
      <Alert severity={gini > 0.3 ? "warning" : gini > 0.15 ? "info" : "success"}>
        {gini > 0.3 && (
          <>
            <strong>Distribuição desigual.</strong> O Gini de {gini.toFixed(3)} indica que algumas jornadas
            têm muito mais trabalho que outras. Considere ajustar `fairness_weight` em /settings/parameters
            ou revisar os parâmetros operacionais.
          </>
        )}
        {gini > 0.15 && gini <= 0.3 && (
          <>
            <strong>Distribuição moderada.</strong> Gini de {gini.toFixed(3)} mostra alguma variação no
            tempo de trabalho entre jornadas, dentro de faixa aceitável para operação fragmentada.
          </>
        )}
        {gini <= 0.15 && (
          <>
            <strong>Distribuição equilibrada.</strong> Gini de {gini.toFixed(3)} indica que o tempo de
            trabalho está bem distribuído entre as jornadas.
          </>
        )}
      </Alert>
    </Stack>
  );
}
