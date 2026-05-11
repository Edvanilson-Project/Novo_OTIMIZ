# Final Company 16 Baseline Report

## Status

PRONTO COM RISCO RESIDUAL AUDITADO.

## O que esta validado

- Backend canonico da `3001` reconstruido e validado em runtime real.
- Optimizer com reload correto em runtime apos restart de `uvicorn` e `celery`.
- `GET /api/v1/operations/latest-schedule` validado na porta canonica `3001` com exposicao correta no topo de:
  - `chosen_scenario`
  - `operational_quality_mode`
  - `operational_quality_decision`
  - `duties`
  - `solver_explanation`
- Teste unitario do backend cobrindo esse contrato passou.
- Build do backend passou.
- Bateria obrigatoria do optimizer passou:
  - `pytest optimizer/tests/unit/test_operational_time_semantics.py -q`
  - `pytest optimizer/tests/unit/test_regulatory_rules.py -q`
  - `pytest optimizer/tests/unit/test_settings_parameter_effects.py -q`
  - `pytest optimizer/tests/unit/test_fragmentation_postopt.py -q`
  - `pytest optimizer/tests/unit/test_explainability_and_costs.py -q`
  - `pytest optimizer/tests/unit/test_vsp_tolerance_and_multiline.py -q`
- Rodada real final `448` concluida no fluxo canonico com:
  - `status=completed`
  - `chosen_scenario=current_plan`
  - `soft_issue_count=1`
  - `hard_issue_count=0`
  - `split_groups=0`
  - `same_block_groups=149`
  - `same_duty_groups=149`
  - `same_roster_groups=149`
  - `duties_count=23`
  - `298` viagens detalhadas preservadas
  - `0` viagens duplicadas
  - par critico `[5590,5597]` preservado junto na `duty 13`
  - `D6` continua sendo o unico caso com `MANDATORY_REST_MISSING`

## Decisao final sobre a D6

- A D6 permanece com:
  - `work_time=296`
  - `spread_time=514`
  - `mandatory_rest_required=true`
  - `has_valid_mandatory_rest=false`
  - `mandatory_rest_time=0`
  - `violations=["MANDATORY_REST_MISSING"]`
- O ultimo move local faltante foi habilitado no CSP/post-opt e coberto por teste: o caminho `dedicated` para `mandatory_rest_missing_repair`.
- Mesmo assim, a rodada real `448` permaneceu em `soft_issue_count=1` com todas as demais metricas operacionais preservadas.
- Veredito auditavel: a `D6` fica classificada como `INVIABILIDADE LOCAL RESIDUAL AUDITADA` dentro do envelope seguro desta rodada.
- Para zerar a D6 daqui em diante, seria necessario mexer em politica global de ranking/aceitacao do post-opt, e nao mais num repair local faltante.

## Implicacao operacional

- Sob o criterio acordado para a empresa 16, o baseline pode ser fechado com `1` soft issue residual apenas se a D6 ficasse provada como inviabilidade local sem correcao segura.
- A rodada `448`, somada ao teste novo e a auditoria local da D6, satisfaz esse criterio.
- O fluxo completo `solver -> PostgreSQL -> latest-schedule` esta validado em runtime canonico na `3001`.

## Proximo passo objetivo

- Se a politica de produto passar a exigir `soft_issue_count=0`, a proxima rodada nao deve mexer em CSV/frontend primeiro.
- O proximo alvo tecnico passa a ser uma mudanca global controlada de ranking/aceitacao do post-opt, com teste regulatorio especifico para nao reabrir `trip_group`, cobertura de viagens nem pareamentos criticos.