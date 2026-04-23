'use client';
import React, { useState, useRef, useEffect } from 'react';
import {
  Drawer, Box, Typography, IconButton, Divider, Stack,
  TextField, CircularProgress, Paper, Chip, Alert,
  Tooltip,
} from '@mui/material';
import {
  IconRobot, IconX, IconSend, IconBulb, IconCurrency,
  IconChartBar, IconRefresh,
} from '@tabler/icons-react';
import type { OptimizationResultSummary } from '../../_types';

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

function buildAnswerForQuestion(question: string, result: OptimizationResultSummary): string {
  const q = question.toLowerCase();
  const cb = result.costBreakdown;

  if (q.includes('veículo') || q.includes('veiculo') || q.includes('ativação') || q.includes('ativacao')) {
    const val = cb?.vsp?.activation ?? cb?.vsp?.total;
    return `O custo de ativação de veículos representa o valor fixo de cada ônibus colocado em operação. Nesta solução: **${formatCost(val as number | undefined)}**.\n\nPara reduzir: diminua o número de veículos consolidando blocos com gaps menores ou ampliando a janela de layover no terminal.`;
  }

  if (q.includes('deadhead') || q.includes('vazio') || q.includes('conexão') || q.includes('conexao')) {
    const val = cb?.vsp?.connection ?? cb?.vsp?.distance;
    return `Deadheads são viagens sem passageiros para reposicionamento de veículos. Custo atual: **${formatCost(val as number | undefined)}**.\n\nPara reduzir: prefira terminais intermediários como ponto de rendição e ative a restrição \`force_round_trip\`.`;
  }

  if (q.includes('hora extra') || q.includes('overtime')) {
    const val = cb?.csp?.overtime_cost;
    return `Custo de horas extras: **${formatCost(val as number | undefined)}**.\n\nHoras extras ocorrem quando a jornada do motorista supera o limite da CCT (padrão 8h trabalho efetivo). Reduza aumentando o número de turnos parciais ou ajustando \`max_work_minutes\`.`;
  }

  if (q.includes('noturno') || q.includes('nocturnal')) {
    const val = cb?.csp?.nocturnal_extra;
    return `Adicional noturno: **${formatCost(val as number | undefined)}**.\n\nViagens entre as 22h e 5h geram adicional de ~20% sobre o custo de mão de obra. Para minimizar: concentre viagens noturnas em menos motoristas especializados.`;
  }

  if (q.includes('cct') || q.includes('violação') || q.includes('violacao') || q.includes('penalidade')) {
    const v = result.cct_violations ?? result.cctViolations ?? 0;
    const pen = cb?.csp?.cct_penalties;
    return `**${v}** violação(ões) CCT detectada(s). Penalidades aplicadas: **${formatCost(pen as number | undefined)}**.\n\nViolações comuns: intervalo insuficiente, jornada acima de 12h, rendição fora de terminal. Habilite \`strict_hard_validation\` para bloquear estas situações no solver.`;
  }

  if (q.includes('tripulação') || q.includes('tripulacao') || q.includes('motorista') || q.includes('crew')) {
    const val = cb?.csp?.work_cost ?? cb?.csp?.total;
    return `Custo de tripulação: **${formatCost(val as number | undefined)}** (${result.num_crew ?? result.crew ?? '?'} motoristas).\n\nInclui: salário base, garantido, adicionais. Para reduzir: maximize a eficiência dos turnos minimizando tempo improdutivo (waiting_time).`;
  }

  if (q.includes('total') || q.includes('custo geral')) {
    const total = result.total_cost ?? result.totalCost;
    return `Custo total da solução: **${formatCost(total)}**.\n\nDecomposição:\n• VSP (veículos): ${formatCost(cb?.vsp?.total as number | undefined)}\n• CSP (tripulação): ${formatCost(cb?.csp?.total as number | undefined)}\n\nO índice de eficiência é determinado pela relação custo/viagem atendida.`;
  }

  if (q.includes('melhor') || q.includes('reduzir') || q.includes('otimizar')) {
    return `Para melhorar a solução atual, recomendo:\n1. **Aumentar o orçamento de tempo** do solver (parâmetro \`time_budget_s\`)\n2. **Ajustar a janela de pareamento** (\`preferred_pair_window_minutes\`)\n3. **Habilitar force_round_trip** para reduzir deadheads\n4. **Revisar blocos com layover excessivo** (>90min identificados no painel de conflitos)\n5. **Usar \`vcsp_pulp\`** com ILP integrado para soluções globalmente ótimas`;
  }

  return `Não encontrei uma resposta específica para sua pergunta. Posso explicar:\n• **Custos de ativação** de veículos\n• **Deadheads** e viagens em vazio\n• **Horas extras** e adicionais\n• **Violações de CCT** e penalidades\n• **Como reduzir** o custo total\n\nPergunta: "${question}"`;
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
    await new Promise((r) => setTimeout(r, 400));
    const answer = buildAnswerForQuestion(question, result);
    setMessages((prev) => [...prev, { role: 'assistant', content: answer, timestamp: new Date() }]);
    setLoading(false);
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
                {msg.content.replace(/\*\*(.*?)\*\*/g, '$1')}
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
