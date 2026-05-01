# Operational Decision Engine Validation Report

## Objetivo
Validar se a nova seleção operacional publica o melhor cenário quando ele melhora pelo menos 2 KPIs, utilizando a carta real da empresa 16.

## Parâmetros da Execução (E2E)
- **Empresa**: 16
- **Algorithm**: `hybrid_pipeline`
- **Seed**: `20260429`
- **Group Infeasibility Mode**: `production`
- **Operational Quality Mode**: `balanced`

## Validação de Logs

A engine validou e comparou o `current_plan` (Plano atual - solver_baseline) com o cenário `plus_one_duty`.

**Trecho extraído diretamente do Celery Worker Log (PostgreSQL/Redis integration)**:
```log
[OP-DECISION]
- current_plan metrics: total_cost=256510.21, duties_lt_25=2, duties_gt_12h=9, idle=169.37, rest_missing=2, overtime=179
- candidate metrics: total_cost=252674.49, duties_lt_25=1, duties_gt_12h=8, idle=130.35, rest_missing=1, overtime=179
- motivos da escolha: blocking=[], improvements=['duties_lt_25', 'duties_gt_12h', 'avg_idle_minutes', 'mandatory_rest_missing'], materially_better=True

[OP-QUALITY] task completed run_id=420 mode=balanced chosen_scenario=plus_one_duty
```

## Comparação: `current_plan` vs Candidate (`plus_one_duty`)

| Métrica | `current_plan` | Candidate (`plus_one_duty`) | Delta | Melhoria? |
| :--- | :--- | :--- | :--- | :--- |
| **Custo Total** | R$ 256.510,21 | R$ 252.674,49 | -R$ 3.835,72 | Sim (não é critério de bloqueio operacional, mas ajudou) |
| **Duties < 25%** | 2 | 1 | -1 | ✅ Sim |
| **Duties > 12h** | 9 | 8 | -1 | ✅ Sim |
| **Idle Médio (min)** | 169.37 | 130.35 | -39.02 min | ✅ Sim |
| **Rest Missing** | 2 | 1 | -1 | ✅ Sim |
| **Overtime** | 179 | 179 | 0 | Inalterado |
| **Blocking Reasons** | N/A | `[]` | - | Não piora hard/coverage |
| **Materially Better**| N/A | `True` | - | >= 2 KPIs atingidos |

## Critérios de Aprovação

- [x] Candidate com melhora >= 2 KPIs for escolhido (`plus_one_duty` melhorou 4 KPIs).
- [x] `chosen_scenario != current_plan` quando houver candidato melhor (O log confirmou `chosen_scenario=plus_one_duty`).
- [x] Cobertura não piorar (`blocking=[]`).
- [x] Hard violations não aumentarem (`blocking=[]`).
- [x] Latest-schedule refletir a decisão (Validado no retorno E2E, a decisão guiou as constraints resultantes).
- [x] DB Persistir a decisão: A engine de Python passou a decisão no atributo `meta` do payload devolvido via Celery -> Redis -> Backend e gravado na task associada.

## Veredito
**APROVADO**.

A camada de decisão operacional explícita provou estar funcional. Ao rodar no modo `balanced`, o sistema corretamente inspecionou o cenário subjacente, constatou a melhoria rigorosa de 4 diferentes KPIs (duties <25%, duties >12h, idle e rest missing) sem violar regras de cobertura, cravou `materially_better=True` e elegeu o cenário substituto ao `current_plan`, validando o sucesso da alteração em `optimizer_service.py`.
