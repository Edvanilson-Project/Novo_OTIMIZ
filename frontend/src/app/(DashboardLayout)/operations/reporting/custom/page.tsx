'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardActions,
  Checkbox,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  FormGroup,
  Grid,
  IconButton,
  Slider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { IconPlus, IconPlayerPlay, IconDownload, IconEdit, IconTrash, IconRefresh } from '@tabler/icons-react';
import { customReportsApi, CustomReportTemplate, apiClient } from '@/lib/api';

const METRIC_LABELS: Record<string, string> = {
  totalRuns: 'Total de execuções',
  completedRuns: 'Execuções concluídas',
  failedRuns: 'Execuções com falha',
  successRate: 'Taxa de sucesso (%)',
  totalTrips: 'Total de viagens',
  totalLines: 'Total de linhas',
  avgVehicles: 'Média de veículos',
  avgCrew: 'Média de crew',
  avgCost: 'Custo médio (R$)',
  trend7d: 'Tendência 7d (%)',
  recentRuns: 'Execuções recentes (lista)',
};

interface FormState {
  id?: number;
  name: string;
  description: string;
  metrics: string[];
  dateRangeDays: number;
}

const EMPTY_FORM: FormState = {
  name: '',
  description: '',
  metrics: [],
  dateRangeDays: 30,
};

export default function CustomReportsPage() {
  const [templates, setTemplates] = useState<CustomReportTemplate[]>([]);
  const [supportedMetrics, setSupportedMetrics] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<Record<number, Record<string, any>>>({});
  const [runningId, setRunningId] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, metricsResp] = await Promise.all([
        customReportsApi.list(),
        customReportsApi.listMetrics(),
      ]);
      setTemplates(list);
      setSupportedMetrics(metricsResp.metrics);
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || 'Falha ao carregar.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function openCreate() {
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(t: CustomReportTemplate) {
    setForm({
      id: t.id,
      name: t.name,
      description: t.description ?? '',
      metrics: t.metrics ?? [],
      dateRangeDays: Number(t.filters?.dateRangeDays ?? 30),
    });
    setDialogOpen(true);
  }

  function toggleMetric(m: string) {
    setForm((f) => ({
      ...f,
      metrics: f.metrics.includes(m) ? f.metrics.filter((x) => x !== m) : [...f.metrics, m],
    }));
  }

  async function submit() {
    if (!form.name.trim() || form.metrics.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        metrics: form.metrics,
        filters: { dateRangeDays: form.dateRangeDays },
      };
      if (form.id) {
        await customReportsApi.update(form.id, payload);
      } else {
        await customReportsApi.create(payload);
      }
      setDialogOpen(false);
      setForm(EMPTY_FORM);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || 'Falha ao salvar.');
    } finally {
      setSubmitting(false);
    }
  }

  async function runTemplate(id: number) {
    setRunningId(id);
    setError(null);
    try {
      const data = await customReportsApi.run(id);
      setResults((prev) => ({ ...prev, [id]: data }));
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || 'Falha ao executar.');
    } finally {
      setRunningId(null);
    }
  }

  async function exportBlob(id: number, format: 'csv' | 'pdf') {
    try {
      const response = await apiClient.get(`/custom-reports/${id}/export.${format}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `report-${id}.${format}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || `Falha ao exportar ${format.toUpperCase()}.`);
    }
  }

  async function removeTemplate(id: number) {
    if (!confirm('Remover este template?')) return;
    try {
      await customReportsApi.remove(id);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.message || 'Falha ao remover.');
    }
  }

  const submitDisabled = useMemo(
    () => !form.name.trim() || form.metrics.length === 0 || submitting,
    [form, submitting],
  );

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            Relatórios Customizados
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Crie templates de relatório com as métricas e filtros que importam para sua operação.
          </Typography>
        </Box>
        <Stack sx={{ flexDirection: 'row', gap: 1 }}>
          <Button variant="outlined" startIcon={<IconRefresh size={18} />} onClick={load} disabled={loading}>
            Atualizar
          </Button>
          <Button variant="contained" startIcon={<IconPlus size={18} />} onClick={openCreate}>
            Novo Template
          </Button>
        </Stack>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Typography color="textSecondary">Carregando templates…</Typography>
      ) : templates.length === 0 ? (
        <Card variant="outlined">
          <CardContent>
            <Typography color="textSecondary">
              Nenhum template ainda. Clique em <strong>Novo Template</strong> para começar.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={2}>
          {templates.map((t) => {
            const result = results[t.id];
            return (
              <Grid key={t.id} size={{ xs: 12, md: 6 }}>
                <Card variant="outlined">
                  <CardContent>
                    <Stack sx={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Box>
                        <Typography variant="h6" sx={{ fontWeight: 600 }}>
                          {t.name}
                        </Typography>
                        {t.description && (
                          <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                            {t.description}
                          </Typography>
                        )}
                      </Box>
                      <Stack sx={{ flexDirection: 'row' }}>
                        <IconButton size="small" onClick={() => openEdit(t)} aria-label="Editar">
                          <IconEdit size={16} />
                        </IconButton>
                        <IconButton size="small" onClick={() => removeTemplate(t.id)} aria-label="Remover">
                          <IconTrash size={16} />
                        </IconButton>
                      </Stack>
                    </Stack>
                    <Typography variant="caption" color="textSecondary">
                      {t.metrics.length} métrica(s) · {t.filters?.dateRangeDays ?? 30} dias
                    </Typography>
                    <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {t.metrics.map((m) => (
                        <Box
                          key={m}
                          sx={{
                            px: 1,
                            py: 0.25,
                            borderRadius: 1,
                            bgcolor: 'action.hover',
                            fontSize: '0.75rem',
                          }}
                        >
                          {METRIC_LABELS[m] ?? m}
                        </Box>
                      ))}
                    </Box>
                    {result && (
                      <>
                        <Divider sx={{ my: 2 }} />
                        <Typography variant="overline" color="textSecondary">
                          Resultado
                        </Typography>
                        <Box
                          component="pre"
                          sx={{
                            mt: 1,
                            p: 1.5,
                            bgcolor: 'background.default',
                            borderRadius: 1,
                            fontSize: '0.8rem',
                            overflow: 'auto',
                            maxHeight: 320,
                          }}
                        >
                          {JSON.stringify(result, null, 2)}
                        </Box>
                      </>
                    )}
                  </CardContent>
                  <CardActions sx={{ px: 2, pb: 2 }}>
                    <Button
                      variant="contained"
                      size="small"
                      startIcon={<IconPlayerPlay size={16} />}
                      onClick={() => runTemplate(t.id)}
                      disabled={runningId === t.id}
                    >
                      {runningId === t.id ? 'Executando…' : 'Executar'}
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<IconDownload size={16} />}
                      onClick={() => exportBlob(t.id, 'csv')}
                    >
                      CSV
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<IconDownload size={16} />}
                      onClick={() => exportBlob(t.id, 'pdf')}
                    >
                      PDF
                    </Button>
                  </CardActions>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{form.id ? 'Editar Template' : 'Novo Template'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField
              label="Nome"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
            />
            <TextField
              label="Descrição (opcional)"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              fullWidth
              multiline
              minRows={2}
            />
            <Box>
              <Typography variant="body2" sx={{ mb: 1, fontWeight: 500 }}>
                Métricas
              </Typography>
              <FormGroup>
                {supportedMetrics.map((m) => (
                  <FormControlLabel
                    key={m}
                    control={
                      <Checkbox
                        checked={form.metrics.includes(m)}
                        onChange={() => toggleMetric(m)}
                        size="small"
                      />
                    }
                    label={METRIC_LABELS[m] ?? m}
                  />
                ))}
              </FormGroup>
            </Box>
            <Box>
              <Typography variant="body2" sx={{ mb: 1, fontWeight: 500 }}>
                Janela temporal: {form.dateRangeDays} dia(s)
              </Typography>
              <Slider
                value={form.dateRangeDays}
                onChange={(_, v) => setForm({ ...form, dateRangeDays: v as number })}
                min={1}
                max={180}
                step={1}
                marks={[
                  { value: 7, label: '7d' },
                  { value: 30, label: '30d' },
                  { value: 90, label: '90d' },
                  { value: 180, label: '180d' },
                ]}
              />
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button onClick={submit} variant="contained" disabled={submitDisabled}>
            {submitting ? 'Salvando…' : 'Salvar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
