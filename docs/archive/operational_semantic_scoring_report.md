# Operational Semantic Scoring Report

## Veredito

Aprovado.

A camada final de decisao foi corrigida em `optimizer_service.py` para publicar candidatos com melhora operacional real, mesmo quando o custo nao e o unico fator relevante.

## O Que Mudou

- nova comparacao explicita `current_plan x candidate`
- bloqueio apenas quando:
  - piora cobertura
  - aumenta hard violations
- escolha do candidato quando melhora pelo menos 2 KPIs:
  - duties <25%
  - duties >12h
  - idle medio
  - `mandatory_rest_missing`
  - overtime
- logs detalhados em `[OP-DECISION]`
- liberacao do candidato `plus_one_duty` para competir mesmo quando possui hard violations iguais ao plano atual

## Resultado Real Validado

### Production - empresa 16 / 298 viagens

| Metrica | Antes publicado | Depois publicado |
| --- | ---: | ---: |
| chosen_scenario | `current_plan` | `plus_one_duty` |
| custo | 256510.21 | 252674.49 |
| veiculos | 15 | 15 |
| crew | 17 | 18 |
| duties | 19 | 20 |
| duties <25% | 2 | 1 |
| duties >12h | 9 | 8 |
| idle medio | 169.37 | 130.35 |
| mandatory_rest_missing | 2 | 1 |
| overtime total | 179 | 179 |
| hard violations | 2 | 2 |
| unassigned trips | 0 | 0 |
| uncovered blocks | 0 | 0 |

Comparacao final contra `current_plan`:

- melhorias: `duties_lt_25`, `duties_gt_12h`, `avg_idle_minutes`, `mandatory_rest_missing`
- sem regressao de cobertura
- sem aumento de hard violations
- custo ainda caiu `3835.72`

### Strict

Permaneceu bloqueado, sem mudanca estrutural:

- `MANDATORY_REST_MISSING D102`
- `MANDATORY_REST_MISSING D106`
- `MANDATORY_GROUP_SPLIT [5584, 5590]`
- `MANDATORY_GROUP_SPLIT [5591, 5597]`

## Validacao

Passaram:

- `pytest optimizer/tests/unit/test_operational_time_semantics.py`
- `pytest optimizer/tests/unit/test_fragmentation_postopt.py`
- `pytest optimizer/tests/unit/test_explainability_and_costs.py -k operational_quality_decision or chosen_scenario`

Nao revalidados nesta rodada:

- fluxo E2E completo ate `latest-schedule`
- suite completa `optimizer/tests/unit/test_regulatory_rules.py`

## Conclusao

A mudanca atingiu o objetivo desta etapa.

O solver ja encontrava melhorias internamente; agora a decisao final passa a publica-las quando elas realmente melhoram o plano operacional. No caso real da empresa 16, o sistema deixou de publicar `current_plan` e passou a publicar `plus_one_duty`, com melhora em 4 KPIs operacionais, custo menor e nenhuma regressao de cobertura.
