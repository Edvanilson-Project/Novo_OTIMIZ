'use client';
import React, { useState, useRef, useEffect } from 'react';
import {
  Drawer, Box, Typography, IconButton, Divider, Stack,
  TextField, CircularProgress, Paper, Chip, Alert,
  Tooltip,
} from '@mui/material';
import { IconRobot, IconX, IconSend, IconBulb, IconCurrency, IconChartBar, IconRefresh } from '@tabler/icons-react';
import type { OptimizationResultSummary } from '../../_types';
import { operationsApi } from '@/lib/api';

export interface AiCostDrawerProps {
  open: boolean;
  onClose: () => void;
  result: OptimizationResultSummary | null;
}

interface ChatMessage {
  role: 'assistant' | 'user';
  content: string;
  timestamp: Date;
}

function formatCost(v?: number | null) {
  if (v == null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
}

function buildInitialInsight(result: OptimizationResultSummary): string {
  const insight = result.aiCopilotInsight ?? result.ai_copilot_insight;
  if (insight) return insight;

  const vehicles = result.num_vehicles ?? result.vehicles ?? '?';
  const crew = result.num_crew ?? result.crew ?? '?';
  const cost = result.total_cost ?? result.totalCost;
  const violations = result.cct_violations ?? result.cctViolations ?? 0;
  const cb = result.costBreakdown;

  const lines: string[] = [
    `**Resumo da Otimização:**`,
    `• ${vehicles} veículos e ${crew} motoristas alocados`,
    cost != null ? `• Custo total: **${formatCost(cost)}**` : '',
    violations > 0
      ? `• ⚠️ ${violations} violação(ões) de CCT detectada(s)`
      : `• ✅ Sem violações de CCT`,
  ].filter(Boolean);

  if (cb?.vsp) {
    const vsp = cb.vsp as Record<string, number | undefined>;
    if (vsp.activation) lines.push(`• Ativação de veículos: ${formatCost(vsp.activation)}`);
    if (vsp.connection) lines.push(`• Deadheads (viagens em vazio): ${formatCost(vsp.connection)}`);
  }

  if (cb?.csp) {
    const csp = cb.csp as Record<string, number | undefined>;
    if (csp.work_cost) lines.push(`• Custo de trabalho de tripulação: ${formatCost(csp.work_cost)}`);
    if (csp.overtime_cost) lines.push(`• Horas extras: ${formatCost(csp.overtime_cost)}`);
    if (csp.nocturnal_extra) lines.push(`• Adicional noturno: ${formatCost(csp.nocturnal_extra)}`);
    if (csp.cct_penalties) lines.push(`• Penalidades CCT: ${formatCost(csp.cct_penalties)}`);
  }

  lines.push('', 'Pergunte-me sobre qualquer componente de custo ou como melhorar o resultado!');
  return lines.join('\n');
}


export function AiCostDrawer({ open, onClose, result }: AiCostDrawerProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && result && messages.length === 0) {
      setMessages([{
        role: 'assistant',
        content: buildInitialInsight(result),
        timestamp: new Date(),
      }]);
    }
    if (!open) setMessages([]);
  }, [open, result]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function handleReset() {
    if (!result) return;
    setMessages([{
      role: 'assistant',
      content: buildInitialInsight(result),
      timestamp: new Date(),
    }]);
  }

  async function handleSend() {
    if (!input.trim() || !result) return;
    const question = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: question, timestamp: new Date() }]);
    setLoading(true);

    try {
      // Chamar a IA real através da API do Backend
      const response = await operationsApi.aiChat({
        metrics: {
          vehicles: result.num_vehicles ?? result.vehicles,
          crew: result.num_crew ?? result.crew,
          total_cost: result.total_cost ?? result.totalCost,
          covered_trips: result.total_trips ?? 0,
          total_trips: result.total_trips,
          cct_violations: result.cct_violations ?? result.cctViolations,
          cost_breakdown: result.costBreakdown,
        },
        question
      });

      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: response.answer,
        timestamp: new Date()
      }]);
    } catch (err) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: 'Desculpe, tive um problema ao me conectar com o motor de IA. Tente novamente em instantes.',
        timestamp: new Date()
      }]);
    } finally {
      setLoading(false);
    }
  }

  const quickQuestions = [
    'Por que o custo de ativação é alto?',
    'Como reduzir deadheads?',
    'O que são violações de CCT?',
    'Como melhorar a solução?',
  ];

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: { xs: '100%', sm: 420 }, display: 'flex', flexDirection: 'column' } } }}
    >
      {/* Header */}
      <Box sx={{ p: 2, bgcolor: 'primary.main', color: 'white', display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <IconRobot size={24} />
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1.2 }}>
            IA de Custos
          </Typography>
          <Typography variant="caption" sx={{ opacity: 0.85 }}>
            Copiloto de Análise de Escalas
          </Typography>
        </Box>
        <Tooltip title="Reiniciar chat">
          <IconButton size="small" sx={{ color: 'white' }} onClick={handleReset}>
            <IconRefresh size={18} />
          </IconButton>
        </Tooltip>
        <IconButton size="small" sx={{ color: 'white' }} onClick={onClose}>
          <IconX size={20} />
        </IconButton>
      </Box>

      <Divider />

      {/* KPI Summary Bar */}
      {result && (
        <Box sx={{ px: 2, py: 1, bgcolor: 'action.hover', display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip
            icon={<IconChartBar size={14} />}
            label={`${result.num_vehicles ?? result.vehicles ?? '?'} veíc.`}
            size="small"
            variant="outlined"
          />
          <Chip
            icon={<IconCurrency size={14} />}
            label={formatCost(result.total_cost ?? result.totalCost)}
            size="small"
            color="primary"
            variant="outlined"
          />
          {(result.cct_violations ?? result.cctViolations ?? 0) > 0 && (
            <Chip
              label={`${result.cct_violations ?? result.cctViolations} violações CCT`}
              size="small"
              color="warning"
              variant="filled"
            />
          )}
        </Box>
      )}

      {!result && (
        <Alert severity="info" sx={{ m: 2 }}>
          Execute uma otimização para ativar o Copiloto de Custos.
        </Alert>
      )}

      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: 'auto', p: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        {messages.map((msg, i) => (
          <Box
            key={i}
            sx={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              gap: 1,
              alignItems: 'flex-start',
            }}
          >
            {msg.role === 'assistant' && (
              <Box sx={{
                width: 28, height: 28, borderRadius: '50%', bgcolor: 'primary.main',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, mt: 0.5,
              }}>
                <IconRobot size={16} color="white" />
              </Box>
            )}
            <Paper
              elevation={0}
              sx={{
                p: 1.5,
                maxWidth: '85%',
                bgcolor: msg.role === 'user' ? 'primary.main' : 'background.paper',
                color: msg.role === 'user' ? 'white' : 'text.primary',
                border: msg.role === 'assistant' ? '1px solid' : 'none',
                borderColor: 'divider',
                borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
              }}
            >
              <Typography
                variant="body2"
                sx={{ whiteSpace: 'pre-wrap', fontSize: '0.82rem', lineHeight: 1.55 }}
              >
                {msg.content}
              </Typography>
            </Paper>
          </Box>
        ))}

        {loading && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Box sx={{
              width: 28, height: 28, borderRadius: '50%', bgcolor: 'primary.main',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <IconRobot size={16} color="white" />
            </Box>
            <Paper elevation={0} sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: '12px 12px 12px 2px' }}>
              <CircularProgress size={16} />
            </Paper>
          </Box>
        )}
        <div ref={bottomRef} />
      </Box>

      {/* Quick Questions */}
      {result && messages.length <= 1 && (
        <Box sx={{ px: 2, pb: 1 }}>
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
            {quickQuestions.map((q) => (
              <Chip
                key={q}
                label={q}
                size="small"
                icon={<IconBulb size={12} />}
                onClick={() => { setInput(q); }}
                sx={{ cursor: 'pointer', fontSize: '0.7rem', mb: 0.5 }}
                variant="outlined"
              />
            ))}
          </Stack>
        </Box>
      )}

      <Divider />

      {/* Input */}
      <Box sx={{ p: 2, display: 'flex', gap: 1, alignItems: 'flex-end' }}>
        <TextField
          fullWidth
          size="small"
          multiline
          maxRows={3}
          placeholder={result ? 'Pergunte sobre os custos...' : 'Execute uma otimização primeiro'}
          value={input}
          disabled={!result || loading}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
          }}
          sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
        />
        <IconButton
          color="primary"
          disabled={!result || !input.trim() || loading}
          onClick={handleSend}
          sx={{ bgcolor: 'primary.main', color: 'white', '&:hover': { bgcolor: 'primary.dark' }, '&:disabled': { bgcolor: 'action.disabledBackground' } }}
        >
          <IconSend size={18} />
        </IconButton>
      </Box>
    </Drawer>
  );
}
