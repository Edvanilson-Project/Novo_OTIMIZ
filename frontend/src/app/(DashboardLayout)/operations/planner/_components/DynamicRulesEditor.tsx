'use client';
import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Typography, Stack, Button, IconButton, Paper,
  TextField, Select, MenuItem, FormControl, InputLabel,
  Chip, Collapse, Alert, CircularProgress,
  Divider, Tooltip,
} from '@mui/material';
import {
  IconPlus, IconTrash, IconChevronDown, IconChevronUp, IconDeviceFloppy,
} from '@tabler/icons-react';
import { parametersApi } from '@/lib/api';

// ─── Tipos de regra (compatíveis com Python rule_engine.py) ──────────────────

export interface DynamicRule {
  condition: {
    field: string;
    op: '==' | '!=' | '<' | '>' | '<=' | '>=';
    value: string | number | boolean;
  };
  action: {
    target: 'overtime_cost' | 'work_cost' | 'idle_cost' | 'guaranteed_cost' | 'waiting_cost' | 'relief_cost' | 'deadhead_cost';
    type: 'multiply' | 'add' | 'subtract' | 'set';
    value: number;
  };
}

const CONDITION_FIELDS = [
  { value: 'is_holiday', label: 'É feriado' },
  { value: 'overtime_minutes', label: 'Minutos extras' },
  { value: 'work_minutes', label: 'Minutos trabalhados' },
  { value: 'spread_minutes', label: 'Spread (jornada total)' },
  { value: 'nocturnal', label: 'Período noturno' },
  { value: 'is_sunday', label: 'É domingo' },
];

const CONDITION_OPS = [
  { value: '==', label: '= (igual)' },
  { value: '!=', label: '≠ (diferente)' },
  { value: '>', label: '> (maior que)' },
  { value: '>=', label: '≥ (maior ou igual)' },
  { value: '<', label: '< (menor que)' },
  { value: '<=', label: '≤ (menor ou igual)' },
];

const ACTION_TARGETS = [
  { value: 'overtime_cost', label: 'Custo de hora extra' },
  { value: 'work_cost', label: 'Custo de trabalho' },
  { value: 'idle_cost', label: 'Custo de ociosidade' },
  { value: 'guaranteed_cost', label: 'Custo garantido' },
  { value: 'waiting_cost', label: 'Custo de espera' },
  { value: 'relief_cost', label: 'Custo de alívio' },
  { value: 'deadhead_cost', label: 'Custo de percurso vazio' },
];

const ACTION_TYPES = [
  { value: 'multiply', label: 'Multiplicar por' },
  { value: 'add', label: 'Somar' },
  { value: 'subtract', label: 'Subtrair' },
  { value: 'set', label: 'Definir como' },
];

const EMPTY_RULE: DynamicRule = {
  condition: { field: 'is_holiday', op: '==', value: true },
  action: { target: 'overtime_cost', type: 'multiply', value: 1.5 },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  initialRules?: DynamicRule[];
  onSaved?: (rules: DynamicRule[]) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function DynamicRulesEditor({ initialRules = [], onSaved }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [rules, setRules] = useState<DynamicRule[]>(initialRules);
  // Sync when parent loads rules from API (only on initial non-empty load, not on every onSaved call)
  const initializedRef = useRef(false);
  useEffect(() => {
    if (!initializedRef.current && initialRules.length > 0) {
      initializedRef.current = true;
      setRules(initialRules);
    }
  }, [initialRules]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const addRule = () => {
    setRules((prev) => [...prev, JSON.parse(JSON.stringify(EMPTY_RULE))]);
  };

  const removeRule = (index: number) => {
    setRules((prev) => prev.filter((_, i) => i !== index));
  };

  const updateCondition = (index: number, field: string, value: unknown) => {
    setRules((prev) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        condition: { ...next[index].condition, [field]: value },
      };
      return next;
    });
  };

  const updateAction = (index: number, field: string, value: unknown) => {
    setRules((prev) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        action: { ...next[index].action, [field]: value },
      };
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      await parametersApi.update({ dynamic_rules: rules });
      setSuccess(true);
      if (onSaved) onSaved(rules);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      setError(err?.response?.data?.message ?? 'Erro ao salvar regras. Tente novamente.');
    } finally {
      setSaving(false);
    }
  };

  const getConditionValueHint = (field: string) => {
    if (field === 'is_holiday' || field === 'nocturnal' || field === 'is_sunday') return 'true / false';
    return 'Número (ex: 60)';
  };

  return (
    <Paper variant="outlined" sx={{ p: 0, overflow: 'hidden' }}>
      {/* Header colapsável */}
      <Stack
        direction="row"
        spacing={1}
        sx={{
          px: 2, py: 1.5,
          cursor: 'pointer',
          bgcolor: 'background.default',
          alignItems: 'center',
          '&:hover': { bgcolor: 'action.hover' },
        }}
        onClick={() => setExpanded((v) => !v)}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          Regras Dinâmicas de Custo
        </Typography>
        {rules.length > 0 && (
          <Chip size="small" label={`${rules.length} regra${rules.length !== 1 ? 's' : ''}`} color="primary" />
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
          Aplicadas na próxima otimização
        </Typography>
        <IconButton size="small">
          {expanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
        </IconButton>
      </Stack>

      <Collapse in={expanded}>
        <Divider />
        <Box sx={{ p: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Defina condições que modificam os pesos de custo durante a otimização.
            As regras são enviadas ao motor Python via <code>cct_params.dynamic_rules</code>.
          </Typography>

          {rules.length === 0 && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Nenhuma regra configurada. Clique em &quot;Adicionar Regra&quot; para começar.
            </Alert>
          )}

          <Stack spacing={2}>
            {rules.map((rule, i) => (
              <Paper key={i} variant="outlined" sx={{ p: 2, position: 'relative' }}>
                <Stack direction="row" spacing={1} sx={{ mb: 1.5, alignItems: 'center' }}>
                  <Chip size="small" label={`Regra ${i + 1}`} variant="outlined" />
                  <Box sx={{ flexGrow: 1 }} />
                  <Tooltip title="Remover regra">
                    <IconButton size="small" color="error" onClick={() => removeRule(i)}>
                      <IconTrash size={16} />
                    </IconButton>
                  </Tooltip>
                </Stack>

                <Typography variant="caption" color="text.secondary" sx={{ mb: 1, fontWeight: 700, display: 'block' }}>
                  SE (condição)
                </Typography>
                <Stack direction="row" spacing={1.5} sx={{ mb: 2, flexWrap: 'wrap' }}>
                  <FormControl size="small" sx={{ minWidth: 180 }}>
                    <InputLabel>Campo</InputLabel>
                    <Select
                      value={rule.condition.field}
                      label="Campo"
                      onChange={(e) => updateCondition(i, 'field', e.target.value)}
                    >
                      {CONDITION_FIELDS.map((f) => (
                        <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <FormControl size="small" sx={{ minWidth: 140 }}>
                    <InputLabel>Operador</InputLabel>
                    <Select
                      value={rule.condition.op}
                      label="Operador"
                      onChange={(e) => updateCondition(i, 'op', e.target.value)}
                    >
                      {CONDITION_OPS.map((o) => (
                        <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <TextField
                    size="small"
                    label="Valor"
                    placeholder={getConditionValueHint(rule.condition.field)}
                    value={String(rule.condition.value)}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const parsed =
                        raw === 'true' ? true : raw === 'false' ? false : isNaN(Number(raw)) ? raw : Number(raw);
                      updateCondition(i, 'value', parsed);
                    }}
                    sx={{ width: 140 }}
                  />
                </Stack>

                <Typography variant="caption" color="text.secondary" sx={{ mb: 1, fontWeight: 700, display: 'block' }}>
                  ENTÃO (ação)
                </Typography>
                <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap' }}>
                  <FormControl size="small" sx={{ minWidth: 200 }}>
                    <InputLabel>Componente de Custo</InputLabel>
                    <Select
                      value={rule.action.target}
                      label="Componente de Custo"
                      onChange={(e) => updateAction(i, 'target', e.target.value)}
                    >
                      {ACTION_TARGETS.map((t) => (
                        <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <FormControl size="small" sx={{ minWidth: 140 }}>
                    <InputLabel>Operação</InputLabel>
                    <Select
                      value={rule.action.type}
                      label="Operação"
                      onChange={(e) => updateAction(i, 'type', e.target.value)}
                    >
                      {ACTION_TYPES.map((t) => (
                        <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <TextField
                    size="small"
                    label="Valor"
                    type="number"
                    value={rule.action.value}
                    onChange={(e) => updateAction(i, 'value', Number(e.target.value))}
                    slotProps={{ htmlInput: { step: 0.1, min: 0, max: 100000 } }}
                    sx={{ width: 120 }}
                  />
                </Stack>
              </Paper>
            ))}
          </Stack>

          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          {success && <Alert severity="success" sx={{ mt: 2 }}>Regras salvas! Serão aplicadas na próxima otimização.</Alert>}

          <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
            <Button
              startIcon={<IconPlus size={16} />}
              variant="outlined"
              size="small"
              onClick={addRule}
              disabled={rules.length >= 50}
            >
              Adicionar Regra
            </Button>
            <Box sx={{ flexGrow: 1 }} />
            <Button
              startIcon={saving ? <CircularProgress size={16} /> : <IconDeviceFloppy size={16} />}
              variant="contained"
              size="small"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Salvando…' : 'Salvar Regras'}
            </Button>
          </Stack>
        </Box>
      </Collapse>
    </Paper>
  );
}
