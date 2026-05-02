# D6 Mandatory Rest Final Audit

## Escopo

- Empresa: 16.
- Schedule final auditada: 448.
- Runtime validado no fluxo canonico:
  - backend NestJS na porta 3001;
  - optimizer FastAPI na porta 8000;
  - Celery com Redis em `localhost:6388/0`.
- Objetivo: decidir de forma auditavel se a `D6` ainda exige nova mudanca segura no neighborhood local do CSP/post-opt ou se permanece como inviabilidade residual local.

## Mudanca local validada antes da rodada 448

- Arquivo alterado: `optimizer/src/algorithms/csp/greedy.py`.
- Ajuste aplicado: o caminho `dedicated` do `_soft_issue_reassignment_postopt` deixou de ficar bloqueado por `continue` quando o motivo era apenas `mandatory_rest_missing_repair`.
- Efeito do ajuste: o neighborhood local passou a poder avaliar uma duty dedicada para corrigir descanso obrigatorio faltante sem depender de `extreme_low_utilization_spread`.

## Prova local reproduzivel

- A duty `D6` da empresa 16 continuou com o mesmo conjunto de viagens reais na rodada final:
  - `5437, 5441, 5462, 5474, 5485, 5488, 5498, 5502, 5546, 5555, 5563, 5564, 5573, 5575, 5583, 5587`.
- Na auditoria local sobre a propria D6, com o codigo ja corrigido, dois bundles internos permaneceram `repairable`:
  - `[5462, 5474]`;
  - `[5546, 5555]`.
- Em isolamento, a extracao de qualquer um desses bundles para uma duty dedicada:
  - remove `mandatory_rest_missing` da duty de origem;
  - nao cria `uncovered_blocks`;
  - preserva cobertura de viagens.
- O teste novo que fixa esse comportamento passou:
  - `pytest optimizer/tests/unit/test_fragmentation_postopt.py -q -k dedicated_duty_to_fix_mandatory_rest_missing`

## Evidencia runtime da rodada 448

- A rodada 448 foi disparada apos restart de `uvicorn` e `celery` com o patch carregado em memoria.
- Resultado final observado no optimizer e no backend canonico:
  - `schedule_id=448`;
  - `status=completed`;
  - `chosen_scenario=current_plan`;
  - `operational_quality_mode=balanced`;
  - `soft_issue_count=1`;
  - `hard_issue_count=0`;
  - `cctViolations=1`;
  - `split_groups=0`;
  - `same_block_groups=149`;
  - `same_duty_groups=149`;
  - `same_roster_groups=149`.
- Preservacao de viagens e pareamentos criticos:
  - `298` linhas em `detailed_trip_assignments`;
  - `298` `trip_ids` unicos;
  - `0` viagens duplicadas;
  - par critico `[5590, 5597]` permaneceu junto na `duty 13`.

## Estado final da D6 na 448

- A `D6` continuou presente no `latest-schedule` final com:
  - `work_time=296`;
  - `spread_time=514`;
  - `mandatory_rest_required=true`;
  - `has_valid_mandatory_rest=false`;
  - `mandatory_rest_time=0`;
  - `violations=["MANDATORY_REST_MISSING"]`.
- O `latest-schedule` canonico da `3001` e o PostgreSQL convergiram para o mesmo resultado operacional.

## Limite da correcao segura atual

- O movimento local que faltava foi de fato habilitado e coberto por teste.
- Mesmo assim, a rodada real `448` nao mudou o resultado final da D6.
- Isso significa que o bloqueio restante nao e mais ausencia de implementacao do move local `dedicated`.
- Para forcar a D6 a sair do estado atual, a proxima mudanca precisaria mexer em pelo menos um destes pontos globais:
  - criterio de ranking/aceitacao entre candidatos de soft issue;
  - politica de melhor-candidato-por-passe;
  - limite de passes/candidate budget;
  - custo de aumento de `crew` e proliferacao de duties curtas no ranking global.
- Esses pontos deixam de ser um `repair controlado local` e passam a alterar a politica global de selecao do CSP/post-opt.

## Veredito

- Sob o envelope de mudanca permitido nesta rodada, a `D6` fica classificada como `INVIABILIDADE LOCAL RESIDUAL AUDITADA`.
- O estado final aceito pela evidencia da `448` e:
  - `soft_issue_count=1`;
  - `hard_issue_count=0`;
  - sem perda de viagens;
  - sem duplicacao de viagens;
  - sem regressao de `trip_group`.
- Qualquer tentativa adicional de zerar a D6 exigira mudanca global de selecao heuristica, nao mais um ajuste local seguro do move faltante.