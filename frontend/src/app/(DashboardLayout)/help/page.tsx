'use client';

import React, { useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Chip, Divider, Stack, Typography,
} from '@mui/material';
import { IconChevronDown, IconChartBar, IconCurrencyReal, IconMoon, IconClock, IconRoute } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';

// ─── Dicionário de Parâmetros ─────────────────────────────────────────────────
// Fonte única de verdade — usada tanto no FAQ quanto no FAB (QuickHelpModal)
const PARAM_DICTIONARY = [
  // ── Operação & Viagem ──
  {
    category: 'Operação & Viagem',
    items: [
      {
        term: 'Gap (Tempo de Espera)',
        definition: 'Tempo em que o veículo fica parado e ocioso entre o fim de uma viagem e o início da próxima.',
      },
      {
        term: 'Avanço de Dia (+1)',
        definition: 'Indica que esta viagem cruza a meia-noite e só terminará no dia seguinte. Ex: 23:30 → 00:30 +1.',
      },
      {
        term: 'Anchor Date (Data Base)',
        definition: 'A data de referência usada pelo sistema para calcular e alinhar todos os horários do painel. Fixada internamente em 2000-01-01.',
      },
      {
        term: 'Pull-out (Saída da Garagem)',
        definition: 'Tempo e distância que o veículo leva da garagem até o ponto de início da primeira viagem do turno.',
      },
      {
        term: 'Pull-in (Retorno à Garagem)',
        definition: 'Tempo e distância do ponto final da última viagem de volta para a garagem.',
      },
      {
        term: 'Deadhead (Deslocamento Vazio)',
        definition: 'Viagem sem passageiros que o veículo faz para reposicionamento entre duas viagens comerciais.',
      },
      {
        term: 'Layover (Espera no Terminal)',
        definition: 'Tempo mínimo que o veículo aguarda no terminal entre duas viagens consecutivas para garantir pontualidade.',
      },
    ],
  },
  // ── Custo & Otimização ──
  {
    category: 'Custo & Otimização',
    items: [
      {
        term: 'Custo Fixo por Veículo',
        definition: 'O valor fixo diário gasto apenas para disponibilizar um veículo na frota, independentemente de quanto ele rode.',
      },
      {
        term: 'Custo por Km (Variável)',
        definition: 'O custo estimado para cada quilômetro rodado: combustível, pneu, manutenção. Afeta a penalidade de deadheads longos.',
      },
      {
        term: 'Custo por Dever (cost_duty)',
        definition: 'Penalidade aplicada a cada jornada de motorista criada. Quanto maior, mais o solver tenta consolidar tripulantes.',
      },
      {
        term: 'Duração Máxima da Jornada',
        definition: 'Limite máximo de horas que um motorista pode operar antes de violar as regras da CCT (Convenção Coletiva de Trabalho).',
      },
      {
        term: 'Horas Extras (Overtime)',
        definition: 'Minutos trabalhados além do limite da jornada normal. Sujeitos a adicional percentual conforme a CCT.',
      },
      {
        term: 'Período Noturno',
        definition: 'Intervalo de horas (padrão 22h–5h) onde o motorista recebe adicional noturno sobre a hora trabalhada.',
      },
    ],
  },
  // ── Gráfico de Gantt ──
  {
    category: 'Gráfico de Gantt',
    items: [
      {
        term: 'Bloco de Veículo',
        definition: 'Sequência de viagens atribuídas a um único veículo ao longo do dia. Representado como uma linha horizontal no Gantt.',
      },
      {
        term: 'Barra Hachurada (Deadhead/Apoio)',
        definition: 'Bloco com fundo tracejado indica um deslocamento vazio (sem passageiros) ou período de espera do veículo.',
      },
      {
        term: 'Linha Tracejada Vertical (Meia-Noite)',
        definition: 'Divisor visual que marca o momento da virada do dia (00:00). Viagens à direita dessa linha são do dia seguinte.',
      },
      {
        term: 'Zoom (Escala)',
        definition: 'Controla a densidade visual do Gantt. Zoom alto comprime mais horas na tela; zoom baixo estica para ver detalhes.',
      },
      {
        term: 'What-If (Arrastar e Soltar)',
        definition: 'Ao arrastar uma viagem para outro veículo, o sistema calcula em tempo real o impacto no custo e nas regras de CCT.',
      },
    ],
  },
];

// ─── FAQ por categoria ────────────────────────────────────────────────────────
const FAQ_SECTIONS = [
  {
    title: 'Como funciona o Gráfico de Gantt',
    icon: <IconChartBar size={20} />,
    color: 'primary' as const,
    questions: [
      {
        q: 'O que cada linha do Gantt representa?',
        a: 'Cada linha horizontal representa um veículo (bloco). As barras coloridas dentro dela são as viagens atribuídas a esse veículo. O eixo horizontal é o tempo — da esquerda (início do dia) para a direita (fim do dia ou madrugada).',
      },
      {
        q: 'Como posso mover uma viagem para outro veículo?',
        a: 'Clique e arraste qualquer barra colorida (viagem) para a linha de outro veículo. O sistema irá calcular automaticamente se o movimento é válido pelas regras da CCT e mostrará o impacto no custo total. Se inválido, a viagem voltará para o local original.',
      },
      {
        q: 'O que são as barras hachuradas (tracejadas)?',
        a: 'Representam períodos ociosos ou deslocamentos vazios (deadhead) — quando o veículo se desloca sem passageiros para reposicionamento. Elas são exibidas automaticamente pelo sistema e não podem ser movidas manualmente.',
      },
      {
        q: 'Como usar o Zoom?',
        a: 'Use os botões "+" e "–" da barra de ferramentas. No zoom mínimo (1x) você vê o dia inteiro comprimido. No zoom máximo (8x) você consegue ver detalhes de viagens curtas. O padrão de 2,5x é ideal para visão geral do dia.',
      },
    ],
  },
  {
    title: 'O que significam os Custos',
    icon: <IconCurrencyReal size={20} />,
    color: 'success' as const,
    questions: [
      {
        q: 'Por que há um "Custo Fixo por Veículo" mesmo que ele não rode?',
        a: 'Todo veículo ativado no turno gera custos fixos: seguro, depreciação, salário do motorista em standby. Esse parâmetro (cost_vehicle) penaliza o uso de veículos extras, incentivando o solver a consolidar viagens.',
      },
      {
        q: 'Qual a diferença entre Custo de Frota e Custo de Tripulação?',
        a: 'Custo de Frota = número de veículos × custo fixo + km rodado × custo/km. Custo de Tripulação = número de jornadas de motorista × custo/hora trabalhada. O sistema minimiza os dois ao mesmo tempo.',
      },
      {
        q: 'O que é a penalidade de Violação CCT?',
        a: 'Quando uma solução viola uma regra trabalhista (ex: jornada acima do limite), o sistema aplica uma penalidade financeira alta (padrão R$ 500 por violação) no custo total. Isso força o solver a priorizar soluções legais.',
      },
      {
        q: 'O que é o "Custo de Horas Extras"?',
        a: 'Minutos trabalhados além da jornada contratual recebem um multiplicador (padrão +50%). Exemplo: se a hora normal custa R$ 25, a hora extra custa R$ 37,50.',
      },
    ],
  },
  {
    title: 'Entendendo a Virada da Meia-Noite (+1)',
    icon: <IconMoon size={20} />,
    color: 'warning' as const,
    questions: [
      {
        q: 'O que significa o "+1" no horário de uma viagem?',
        a: 'O sistema representa o tempo como minutos contínuos desde o início do dia. 1440 minutos = 24:00 (meia-noite). Uma viagem que começa às 23:30 e dura 60 minutos termina às 00:30 do dia seguinte — exibido como "00:30 +1".',
      },
      {
        q: 'Como o Gantt mostra viagens que cruzam a meia-noite?',
        a: 'O Gantt se estende além dos 1440 minutos (até 1800 min = 06:00 do dia seguinte). A linha vertical tracejada vertical no Gantt marca exatamente a meia-noite. Viagens à direita dessa linha estão no dia seguinte.',
      },
      {
        q: 'O tempo entre viagens (gap) é calculado corretamente para viagens de madrugada?',
        a: 'Sim. O sistema sempre calcula gap = início da próxima viagem − fim da viagem atual, usando minutos absolutos. Uma viagem terminando às 23:50 (1430 min) e outra começando às 00:30 +1 (1470 min) têm gap = 40 minutos, nunca negativo.',
      },
      {
        q: 'Por que não usar módulo (% 24h) para o cálculo de tempo?',
        a: 'Se usássemos % 1440, uma viagem de 00:30 +1 pareceria estar no início do mesmo dia, sobrepondo-se a viagens da manhã. O tempo linear garante que o solver enxergue o fluxo real da operação.',
      },
    ],
  },
  {
    title: 'Configurações e Parâmetros CCT',
    icon: <IconClock size={20} />,
    color: 'info' as const,
    questions: [
      {
        q: 'O que é a CCT e por que ela importa?',
        a: 'CCT (Convenção Coletiva de Trabalho) é o acordo entre sindicatos que define regras trabalhistas: jornada máxima, intervalo mínimo, adicional noturno, etc. O sistema usa esses parâmetros para garantir que todas as escalas geradas sejam legalmente válidas.',
      },
      {
        q: 'Qual a diferença entre Jornada Máxima e Tempo Máximo de Condução?',
        a: 'Jornada Máxima (spread time) é o tempo total desde o início até o fim do turno, incluindo esperas. Tempo Máximo de Condução é apenas o tempo que o motorista fica efetivamente dirigindo. Um motorista pode ter jornada de 8h mas dirigir no máximo 6h.',
      },
      {
        q: 'Como o parâmetro "Tolerância de Conexão" funciona?',
        a: 'Se duas viagens têm 3 minutos de gap mas a regra exige 5 minutos de descanso, normalmente seria uma violação. Com tolerância de 2 minutos, o sistema aceita essa conexão como válida, acomodando pequenos atrasos operacionais.',
      },
    ],
  },
];

// ─── Componente principal ─────────────────────────────────────────────────────
export default function HelpPage() {
  const [expanded, setExpanded] = useState<string | false>('gantt');

  const toggle = (panel: string) => (_: React.SyntheticEvent, isExpanded: boolean) => {
    setExpanded(isExpanded ? panel : false);
  };

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Central de Ajuda"
        subtitle="Entenda os conceitos, parâmetros e funcionalidades do sistema OTIMIZ"
      >
        <Stack spacing={3}>

          {/* ── FAQ por Seção ── */}
          {FAQ_SECTIONS.map((section, si) => (
            <Box key={si}>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 1.5 }}>
                <Box sx={{ color: `${section.color}.main` }}>{section.icon}</Box>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>{section.title}</Typography>
                <Chip label={`${section.questions.length} tópicos`} size="small" color={section.color} variant="outlined" />
              </Stack>

              {section.questions.map((item, qi) => (
                <Accordion
                  key={qi}
                  expanded={expanded === `${si}-${qi}`}
                  onChange={toggle(`${si}-${qi}`)}
                  disableGutters
                  elevation={0}
                  sx={{ border: '1px solid', borderColor: 'divider', mb: 0.5, borderRadius: '8px !important', '&:before': { display: 'none' } }}
                >
                  <AccordionSummary expandIcon={<IconChevronDown size={18} />} sx={{ borderRadius: 2 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.q}</Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ pt: 0, pb: 2 }}>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>{item.a}</Typography>
                  </AccordionDetails>
                </Accordion>
              ))}

              {si < FAQ_SECTIONS.length - 1 && <Divider sx={{ mt: 2 }} />}
            </Box>
          ))}

          {/* ── Dicionário de Termos ── */}
          <Divider />
          <Box>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
              <Box sx={{ color: 'secondary.main' }}><IconRoute size={20} /></Box>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>Dicionário de Parâmetros</Typography>
            </Stack>
            {PARAM_DICTIONARY.map((cat, ci) => (
              <Box key={ci} sx={{ mb: 3 }}>
                <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 700 }}>{cat.category}</Typography>
                <Stack spacing={1} sx={{ mt: 1 }}>
                  {cat.items.map((item, ii) => (
                    <Box key={ii} sx={{ p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }} gutterBottom>{item.term}</Typography>
                      <Typography variant="caption" color="text.secondary">{item.definition}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
            ))}
          </Box>

        </Stack>
      </DashboardCard>
    </Box>
  );
}
