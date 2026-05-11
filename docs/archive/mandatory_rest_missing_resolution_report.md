# Mandatory Rest Missing Resolution Report

## Escopo

- Empresa: 16.
- Algoritmo: `hybrid_pipeline`.
- Modo operacional: `balanced`.
- Parametros criticos mantidos: `mandatory_break_after_minutes=240`, `meal_break_minutes=30`, `min_break_minutes=10`, `allow_vehicle_swap=true`, `enforce_trip_groups_hard=true`, `operator_pairing_hard=true`.
- Objetivo desta rodada: resolver ou explicar de forma auditavel as 3 soft issues de `MANDATORY_REST_MISSING` remanescentes sem reabrir hard issues nem `split_groups`.

## Mudanca implementada no optimizer

- Arquivo alterado: `optimizer/src/algorithms/csp/greedy.py`.
- Foi adicionada a deteccao local `_mandatory_rest_repairable_task_indexes(duty)`.
- A heuristica passou a marcar `candidate sources` com `reason="mandatory_rest_missing_repair"` quando a extracao de uma task interna:
  - elimina `MANDATORY_REST_MISSING` na duty de origem;
  - nao cria novo `MANDATORY_REST_MISSING` na task isolada;
  - permanece dentro do mesmo neighborhood local do CSP/post-opt.
- O `_soft_issue_reassignment_postopt` passou a aceitar esse motivo na via `dedicated`, antes restrita a `extreme_low_utilization_spread`.

## Validacao do optimizer

- Teste novo: `optimizer/tests/unit/test_fragmentation_postopt.py::test_soft_issue_postopt_can_move_internal_task_to_fix_mandatory_rest_missing`.
- Validacoes executadas com sucesso:
  - `pytest optimizer/tests/unit/test_operational_time_semantics.py -q`
  - `pytest optimizer/tests/unit/test_regulatory_rules.py -q`
  - `pytest optimizer/tests/unit/test_settings_parameter_effects.py -q`
  - `pytest optimizer/tests/unit/test_fragmentation_postopt.py -q`
  - `pytest optimizer/tests/unit/test_explainability_and_costs.py -q`
  - `pytest optimizer/tests/unit/test_vsp_tolerance_and_multiline.py -q`

## Evidencia runtime

### Rodada 446

- Resultado observado: `hard_issue_count=0`, `soft_issue_count=3`, `split_groups=0`.
- Interpretacao correta: falso negativo de validacao do patch.
- Causa: a rodada 446 foi disparada antes de reiniciar `uvicorn` e `celery`, portanto executou o codigo Python antigo do optimizer.

### Rodada 447

- Antes da reexecucao, foram reiniciados `uvicorn` e `celery` e o cache `optimizer:cache:*` foi limpo no Redis.
- Resultado bruto do worker e persistencia no PostgreSQL convergiram para:
  - `schedule_id=447`
  - `status=completed`
  - `hard_issue_count=0`
  - `soft_issue_count=1`
  - `split_groups=0`
  - `chosen_scenario=current_plan`

### Rodada 448

- Antes da reexecucao, o optimizer recebeu uma segunda mudanca local segura no mesmo slice de `greedy.py`:
  - o caminho `dedicated` de `_soft_issue_reassignment_postopt` deixou de ficar bloqueado quando o motivo era apenas `mandatory_rest_missing_repair`.
- O novo comportamento ficou coberto por teste dedicado:
  - `pytest optimizer/tests/unit/test_fragmentation_postopt.py -q -k dedicated_duty_to_fix_mandatory_rest_missing`
- Depois do patch, `uvicorn` e `celery` foram reiniciados e a empresa 16 foi reexecutada no fluxo canonico completo.
- Resultado bruto do worker, backend `3001` e PostgreSQL convergiram para:
  - `schedule_id=448`
  - `status=completed`
  - `hard_issue_count=0`
  - `soft_issue_count=1`
  - `split_groups=0`
  - `same_block_groups=149`
  - `same_duty_groups=149`
  - `same_roster_groups=149`
  - `chosen_scenario=current_plan`
  - `298` viagens preservadas sem perda ou duplicacao

## Resultado por duty

### Duty 6

- Estado na 448: continua com `MANDATORY_REST_MISSING`.
- Evidencia operacional:
  - `duty_start=315`
  - `duty_end=829`
  - `work_time=296`
  - `window_time=514`
  - `normal_break_time=218`
  - `mandatory_rest_time=0`
  - `has_valid_mandatory_rest=false`
- Classificacao: `C`.
- Interpretacao atualizada:
  - a D6 segue sendo um caso real de `MANDATORY_REST_MISSING`;
  - o move local `dedicated` para `mandatory_rest_missing_repair` foi efetivamente habilitado e validado por teste;
  - mesmo assim, a rodada real `448` nao alterou o resultado final da D6;
  - portanto, o bloqueio remanescente nao e mais ausencia de move local implementado, e sim limite da politica global de selecao/ranking do post-opt.
- Classificacao final: `INVIABILIDADE LOCAL RESIDUAL AUDITADA` dentro do envelope seguro desta rodada.

### Duty 10

- Estado na 447: resolvida.
- Evidencia operacional:
  - `duty_start=369`
  - `duty_end=908`
  - `work_time=358`
  - `mandatory_rest_time=54`
  - `has_valid_mandatory_rest=true`
  - `violations=[]`
- Classificacao final: `RESOLVIDA`.
- Interpretacao: a familia de repair local introduzida no CSP/post-opt passou a produzir descanso obrigatorio valido neste caso real.

### Duty 12

- Estado na 447: resolvida.
- Evidencia operacional:
  - `duty_start=395`
  - `duty_end=952`
  - `work_time=332`
  - `mandatory_rest_time=66`
  - `has_valid_mandatory_rest=true`
  - `violations=[]`
- Classificacao final: `RESOLVIDA`.
- Interpretacao: a mesma via de repair local passou a produzir descanso obrigatorio valido tambem para esta duty.

## Conclusao tecnica

- As 3 soft issues da configuracao original nao permaneceram apos a rodada correta com reload do optimizer.
- A mudanca local no CSP/post-opt reduziu o caso real de `3 -> 1` soft issues sem reintroduzir hard issues e sem reabrir `split_groups`.
- O remanescente `D6` nao e bug cosmetico de classificacao; e uma violacao real sob a semantica final de descanso obrigatorio.
- A rodada `448` demonstrou que, apos habilitar o ultimo move local faltante (`dedicated` para `mandatory_rest_missing_repair`), o resultado real continua em `soft_issue_count=1` com `hard_issue_count=0` e `298` viagens preservadas.
- Isso encerra a fronteira de mudanca segura desta rodada: qualquer tentativa adicional de zerar a D6 passa a exigir alteracao global de ranking/aceitacao do CSP-postopt, e nao mais um repair local faltante.
- O estado atual desta frente e:
  - `D10`: resolvida.
  - `D12`: resolvida.
  - `D6`: explicada de forma auditavel e reclassificada como inviabilidade local residual dentro do envelope seguro atual.