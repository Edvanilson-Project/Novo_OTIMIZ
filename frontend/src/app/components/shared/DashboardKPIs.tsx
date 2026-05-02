"use client";

import React from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
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

interface KPIProps {
  schedule: any;
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

  let totalMinutes = 0;
  let totalTrips = schedule?.totalTrips ?? schedule?.resultSummary?.total_trips ?? 0;
  schedule?.blocks?.forEach((b: any) => {
    // Suporta tanto b.trips (hidratado) quanto b.metadata?.trips (legado)
    const trips = b.trips || b.metadata?.trips || [];
    if (!schedule?.totalTrips && !schedule?.resultSummary?.total_trips) {
      totalTrips += trips.length;
    }
    trips.forEach((t: any) => {
      const start = t.start_time ?? t.startTime ?? 0;
      const end = t.end_time ?? t.endTime ?? 0;
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
        <KPICard
          title="Hard Issues"
          value={`${hardIssueCount}`}
          changeKey={`hard-issues-${hardIssueCount}-${scheduleVersion}`}
          icon={<IconAlertTriangle size="24" />}
          color={hardIssueCount > 0 ? theme.palette.error.main : theme.palette.text.secondary}
          isError={hardIssueCount > 0}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <KPICard
          title="Soft Issues"
          value={`${softIssueCount}`}
          changeKey={`soft-issues-${softIssueCount}-${scheduleVersion}`}
          icon={<IconAlertTriangle size="24" />}
          color={softIssueCount > 0 ? theme.palette.warning.main : theme.palette.text.secondary}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <KPICard
          title="Trip Groups Split"
          value={`${splitGroups}`}
          changeKey={`split-groups-${splitGroups}-${scheduleVersion}`}
          icon={<IconRoute size="24" />}
          color={splitGroups > 0 ? theme.palette.error.main : theme.palette.success.main}
          isError={splitGroups > 0}
        />
      </Grid>
    </Grid>
  );
};

export default DashboardKPIs;
