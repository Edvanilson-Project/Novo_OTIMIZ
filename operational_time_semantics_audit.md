# Operational Time Semantics Audit

## Escopo

Esta auditoria cobre apenas classificacao, calculo e explicacao de tempos operacionais no OTIMIZ.
Nao altera solver global, VSP global, chunking, heuristicas principais nem arquitetura SaaS.

## Semantica Formal

| Conceito | Definicao operacional | Campos/parametros | Impacto em custo | Impacto em jornada | Impacto em validacao |
| --- | --- | --- | --- | --- | --- |
| Tempo de trabalho ativo | Tempo produtivo em viagem comercial e outras atividades explicitamente dirigiveis. Nesta rodada, o motor mede principalmente `commercial_trip` e direcao agregada por tarefa. | `work_time`, `driving_time`, `task_drive_minutes` | Entra em `work_cost`, overtime e adicionais. | Compõe `work_time` e direcao acumulada. | Base para `MAX_DRIVING_EXCEEDED` e necessidade de `mandatory_rest`. |
| Ociosa | Gap positivo entre atividades que nao satisfaz pausa normal nem descanso obrigatorio. Nao deve virar descanso legal por inferencia. | gaps entre tasks, `idle_time`, `idle_time_is_paid`, `waiting_time_pay_pct` | Pode virar `waiting_cost` e `long_unpaid_break_penalty`. | Aumenta spread, nao reduz obrigacao de descanso. | Nao elimina `MANDATORY_REST_MISSING`. |
| Intervalo normal | Gap operacional aceitavel entre viagens/tasks, contado como pausa normal, mas sem validar descanso legal por si so. | `min_break_minutes` | Pode seguir como espera paga/nao paga conforme configuracao. | Aumenta spread. | Nao zera violacao de descanso obrigatorio se nao cumprir regra configuravel. |
| Descanso obrigatorio | Pausa valida no meio da jornada, com duracao minima configuravel e ocorrendo apos carga de trabalho suficiente antes da pausa. | `meal_break_minutes`, `mandatory_break_after_minutes`, `min_break_minutes` | Nao cria custo proprio, mas evita penalidade/violacao. | Segmenta jornada e reseta leitura semantica de descanso. | Gera `MANDATORY_REST_MISSING` quando ausente e `INVALID_REST_POSITION` quando so existe em soltura/recolhimento. |
| Soltura | Buffer operacional antes da primeira viagem. Pode representar saida da garagem ou preparacao. | `pullout_minutes`, `start_buffer_minutes`, `idle_before_minutes` | Entra em `idle_cost` do VSP e aparece em relatorio operacional. | Amplia a janela total da duty. | Nao conta como descanso obrigatorio. |
| Recolhimento | Buffer operacional apos a ultima viagem. Pode representar retorno a garagem ou fechamento operacional. | `pullback_minutes`, `end_buffer_minutes`, `idle_after_minutes` | Entra em `idle_cost` do VSP e aparece em relatorio operacional. | Amplia a janela total da duty. | Nao conta como descanso obrigatorio. |

## Regras Tecnicas Aplicadas

1. Gap interno `< min_break_minutes` => `idle`.
2. Gap interno `>= min_break_minutes` mas sem cumprir gatilho de descanso obrigatorio => `normal_break`.
3. Gap interno `>= max(min_break_minutes, meal_break_minutes)` e com `work_before >= mandatory_break_after_minutes` e trabalho apos a pausa => `mandatory_rest`.
4. `pullout` e `pullback` nunca validam descanso obrigatorio, mesmo quando longos.
5. Violacoes claras:
   - `MANDATORY_REST_MISSING`
   - `INVALID_REST_POSITION`
   - `MAX_DRIVING_EXCEEDED`

## Auditoria de Codigo

| Arquivo | Funcao/area | Status atual | Correto? | Ajuste feito | Risco restante |
| --- | --- | --- | --- | --- | --- |
| `optimizer/src/algorithms/csp/greedy.py` | `finalize_selected_duties`, `_continuous_drive_stats`, `_boundary_idle_minutes` | Misturava refeicao/descanso com qualquer gap longo e tratava pullout/pullback so como buffer. | Parcial | Passou a gerar `duty_time_segments` e `operational_time_report` por duty, com `idle`, `normal_break`, `mandatory_rest`, `pullout`, `pullback`. | O solver ainda monta tasks com heuristica antiga; a semantica final ficou correta, mas a construcao continua heuristica. |
| `optimizer/src/services/hard_constraint_validator.py` | `_audit_duty` | Usava `MEAL_BREAK_MISSING` e aceitava leitura simples de gap. | Nao | Trocado para `MANDATORY_REST_MISSING`, `INVALID_REST_POSITION` e `MAX_DRIVING_EXCEEDED`, lendo o relatorio semantico da duty. | Ainda ha soft/hard historico no agrupamento de issues. |
| `optimizer/src/algorithms/evaluator.py` | `vsp_cost_breakdown`, `csp_cost_breakdown` | Custos de idle/pull buffers ja existiam, mas sem separar semanticamente tipos de tempo. | Parcial | Mantido; a separacao agora aparece no relatorio sem reescrever o avaliador. | `unpaid_break_total_minutes` continua agregado como spread-work. |
| `optimizer/src/services/optimizer_service.py` | `_build_parameter_effect_report`, `_describe_issue`, `_build_recommendations` | Relatorio nao explicitava descanso obrigatorio, pullout/pullback nem classificacao de idle. | Nao | Adicionado impacto de `mandatory_rest`, `pullout`, `pullback` e `idle_classification`; mensagens e recomendacoes atualizadas. | Ainda nao ha tela dedicada no frontend para todos os segmentos. |
| `optimizer/src/domain/models.py` | `as_compact_dict`, `_compact_duty` | Payload compacto ocultava a semantica operacional fina. | Nao | Duty compacta agora expõe `segments` quando existirem e `meta.operational_time_report`. | Consumidores antigos podem ignorar os novos campos. |
| `backend/src/modules/operations/optimization.service.ts` | mapeamento de parametros e persistencia | Ja carregava `pullout_minutes`/`pullback_minutes`, mas persistia pouco contexto da duty. | Parcial | Sem mudanca estrutural nesta rodada; os novos campos passam via `meta`. | Persistencia relacional ainda nao indexa cada segmento operacional separadamente. |

## O Que Manter

- `pullout_minutes` e `pullback_minutes` como parametros configuraveis.
- `idle_cost_per_minute`, `waiting_time_pay_pct` e `idle_time_is_paid`.
- `mandatory_break_after_minutes`, `meal_break_minutes` e `min_break_minutes` como regras configuraveis por CCT.
- `hard_constraint_report`, `parameter_effect_report` e `solver_explanation`.

## O Que Revisar

- `unpaid_break_total_minutes`: hoje e util para custo, mas semantica e mais ampla que "break".
- Acoplamento historico entre `min_break_minutes` do operador e `min_layover_minutes` do veiculo em partes do fluxo.
- Soft/hard de descanso obrigatorio: o relatorio agora esta claro, mas a politica de bloqueio continua configuravel.

## O Que Remover ou Desativar Depois

- Nenhuma remocao automatica foi feita nesta rodada.
- Candidatos a revisao futura:
  - aliases redundantes entre `min_connection_time` e `min_layover_minutes`
  - relatorios que ainda falam apenas em `meal_break` quando a regra real e `mandatory_rest`
  - flags historicas de qualidade operacional que nao distinguem idle de descanso legal

## Ajuste Implementado

- Novo helper: `optimizer/src/services/operational_time_service.py`
- Novo payload por duty:
  - `duty_time_segments`
  - `operational_time_report`
- Novo agregado em resultado final:
  - `operational_time_reports`
- Novos codigos de violacao:
  - `MANDATORY_REST_MISSING`
  - `INVALID_REST_POSITION`
  - `MAX_DRIVING_EXCEEDED`

## Testes

- Unitarios novos:
  - idle simples
  - pausa normal
  - descanso obrigatorio valido
  - soltura/recolhimento nao contam como descanso
  - codigos claros de violacao
- Regressao rodada com sucesso:
  - `optimizer/tests/unit/test_operational_time_semantics.py`
  - `optimizer/tests/unit/test_explainability_and_costs.py`
- Cobertura:
  - nao foi possivel comparar cobertura com baseline porque o ambiente atual nao possui `pytest-cov`
- Payload real local empresa 16:
  - `production`: `15` veiculos, `17` crew, custo `256510.21`, `2` hard issues (`MANDATORY_GROUP_SPLIT`) e `2` soft issues (`MANDATORY_REST_MISSING`)
  - `strict`: bloqueado com `MANDATORY_GROUP_SPLIT` e `MANDATORY_REST_MISSING` em `D102` e `D106`

## Veredito

Nao pronto.

Ressalvas:

- A semantica final e o relatorio agora distinguem idle, pausa normal, descanso obrigatorio, soltura e recolhimento.
- O avaliador de custo ainda usa alguns agregados historicos (`spread - work`) para custo trabalhista.
- A validacao local da empresa 16 expôs problemas reais remanescentes de `MANDATORY_GROUP_SPLIT` e `MANDATORY_REST_MISSING`.
