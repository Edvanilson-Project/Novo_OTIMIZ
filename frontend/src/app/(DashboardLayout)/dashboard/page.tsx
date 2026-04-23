"use client";

import React, { useEffect, useState } from "react";
import {
  Box, Grid, Card, CardContent, Typography, Stack, Chip,
  CircularProgress, Divider, Button, Alert,
} from "@mui/material";
import {
  IconRoute, IconUsers, IconCalendarStats, IconTrendingDown,
  IconClock, IconRefresh, IconAlertTriangle,
} from "@tabler/icons-react";
import Link from "next/link";
import DashboardCard from "@/app/components/shared/DashboardCard";
import { operationsApi } from "@/lib/api";
import { minToHHMM } from "@/lib/format";

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  color?: "primary" | "success" | "warning" | "error" | "info";
  loading?: boolean;
}

function KPICard({ title, value, subtitle, icon, color = "primary", loading }: KPICardProps) {
  const colorMap = {
    primary: "#1976d2", success: "#2e7d32", warning: "#e65100",
    error: "#c62828", info: "#0277bd",
  };
  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent>
        <Stack direction="row" sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
              {title}
            </Typography>
            {loading ? (
              <CircularProgress size={24} sx={{ mt: 1 }} />
            ) : (
              <Typography variant="h4" sx={{ fontWeight: 700, mt: 0.5, color: colorMap[color] }}>
                {value}
              </Typography>
            )}
            {subtitle && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                {subtitle}
              </Typography>
            )}
          </Box>
          <Box sx={{
            p: 1.5, borderRadius: 2, backgroundColor: `${colorMap[color]}15`,
            color: colorMap[color], display: "flex", alignItems: "center",
          }}>
            {icon}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

interface ScheduleData {
  id: number;
  status: string;
  algorithm?: string;
  totalCost?: number;
  totalBlocks?: number;
  totalTrips?: number;
  computationTimeS?: number;
  createdAt?: string;
}

export default function DashboardPage() {
  const [trips, setTrips] = useState<any[]>([]);
  const [drivers, setDrivers] = useState<any[]>([]);
  const [schedule, setSchedule] = useState<ScheduleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [tripsData, driversData, scheduleData] = await Promise.allSettled([
        operationsApi.getTrips({ limit: 500 }),
        operationsApi.getDrivers(),
        operationsApi.getLatestSchedule(),
      ]);

      if (tripsData.status === "fulfilled") {
        const d = tripsData.value;
        setTrips(Array.isArray(d) ? d : (d as any).data ?? []);
      }
      if (driversData.status === "fulfilled") {
        const d = driversData.value;
        setDrivers(Array.isArray(d) ? d : (d as any).data ?? []);
      }
      if (scheduleData.status === "fulfilled") {
        setSchedule(scheduleData.value as ScheduleData);
      }
    } catch {
      setError("Erro ao carregar dados do dashboard.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const totalDuration = trips.reduce((acc, t) => acc + (t.duration || 0), 0);
  const avgDuration = trips.length > 0 ? Math.round(totalDuration / trips.length) : 0;

  const statusColor = (s: string) => {
    if (s === "completed") return "success";
    if (s === "failed") return "error";
    if (s === "running") return "warning";
    return "default";
  };

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Visão Geral — OTIMIZ"
        subtitle="Resumo operacional do sistema de otimização de frota e tripulação"
        action={
          <Button size="small" startIcon={<IconRefresh size={16} />} onClick={fetchAll} disabled={loading}>
            Atualizar
          </Button>
        }
      >
        <Stack spacing={3}>
          {error && <Alert severity="error">{error}</Alert>}

          {/* ── KPIs principais ── */}
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <KPICard
                title="Viagens Carregadas"
                value={trips.length}
                subtitle="na escala atual"
                icon={<IconRoute size={24} />}
                color="primary"
                loading={loading}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <KPICard
                title="Motoristas Cadastrados"
                value={drivers.length}
                subtitle="disponíveis"
                icon={<IconUsers size={24} />}
                color="info"
                loading={loading}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <KPICard
                title="Duração Média"
                value={avgDuration > 0 ? minToHHMM(avgDuration) : "—"}
                subtitle="por viagem"
                icon={<IconClock size={24} />}
                color="success"
                loading={loading}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <KPICard
                title="Blocos na Última Otimização"
                value={schedule?.totalBlocks ?? "—"}
                subtitle={schedule ? `Custo: R$ ${schedule.totalCost?.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) ?? "—"}` : "Sem otimização"}
                icon={<IconCalendarStats size={24} />}
                color={schedule?.status === "completed" ? "success" : "warning"}
                loading={loading}
              />
            </Grid>
          </Grid>

          {/* ── Última Otimização ── */}
          {schedule && (
            <Card variant="outlined">
              <CardContent>
                <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 2 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Última Otimização
                  </Typography>
                  <Chip
                    label={schedule.status}
                    color={statusColor(schedule.status) as any}
                    size="small"
                  />
                </Stack>
                <Divider sx={{ mb: 2 }} />
                <Grid container spacing={2}>
                  <Grid size={{ xs: 6, sm: 3 }}>
                    <Typography variant="caption" color="text.secondary">Algoritmo</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{schedule.algorithm ?? "—"}</Typography>
                  </Grid>
                  <Grid size={{ xs: 6, sm: 3 }}>
                    <Typography variant="caption" color="text.secondary">Blocos gerados</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{schedule.totalBlocks ?? "—"}</Typography>
                  </Grid>
                  <Grid size={{ xs: 6, sm: 3 }}>
                    <Typography variant="caption" color="text.secondary">Viagens cobertas</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{schedule.totalTrips ?? "—"}</Typography>
                  </Grid>
                  <Grid size={{ xs: 6, sm: 3 }}>
                    <Typography variant="caption" color="text.secondary">Custo total</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: "success.main" }}>
                      {schedule.totalCost != null
                        ? `R$ ${schedule.totalCost.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
                        : "—"}
                    </Typography>
                  </Grid>
                  {schedule.computationTimeS != null && (
                    <Grid size={{ xs: 6, sm: 3 }}>
                      <Typography variant="caption" color="text.secondary">Tempo de cálculo</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{schedule.computationTimeS.toFixed(1)}s</Typography>
                    </Grid>
                  )}
                  {schedule.createdAt && (
                    <Grid size={{ xs: 6, sm: 3 }}>
                      <Typography variant="caption" color="text.secondary">Gerado em</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {new Date(schedule.createdAt).toLocaleString("pt-BR")}
                      </Typography>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
          )}

          {/* ── Atalhos ── */}
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>Acesso Rápido</Typography>
              <Grid container spacing={2}>
                {[
                  { label: "Carregar Viagens", href: "/operations/data", icon: <IconRoute size={20} />, color: "primary.main" },
                  { label: "Executar Otimização", href: "/operations/planner", icon: <IconCalendarStats size={20} />, color: "success.main" },
                  { label: "Gerenciar Empresas", href: "/settings/companies", icon: <IconUsers size={20} />, color: "info.main" },
                  { label: "Parâmetros CCT", href: "/settings/parameters", icon: <IconTrendingDown size={20} />, color: "warning.main" },
                ].map((item) => (
                  <Grid key={item.href} size={{ xs: 12, sm: 6, md: 3 }}>
                    <Button
                      component={Link}
                      href={item.href}
                      variant="outlined"
                      fullWidth
                      startIcon={item.icon}
                      sx={{ py: 1.5, justifyContent: "flex-start", color: item.color, borderColor: item.color }}
                    >
                      {item.label}
                    </Button>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>

          {/* ── Alerta se sem dados ── */}
          {!loading && trips.length === 0 && (
            <Alert
              severity="warning"
              icon={<IconAlertTriangle size={20} />}
              action={
                <Button component={Link} href="/operations/data" size="small" color="warning">
                  Importar agora
                </Button>
              }
            >
              Nenhuma viagem carregada. Importe um arquivo CSV/XLSX para iniciar a otimização.
            </Alert>
          )}
        </Stack>
      </DashboardCard>
    </Box>
  );
}
