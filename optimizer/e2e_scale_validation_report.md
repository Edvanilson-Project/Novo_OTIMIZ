# OTIMIZ E2E Scale Validation Report

Data: 2026-04-28  
Fluxo validado: Backend NestJS -> PostgreSQL -> Celery -> Redis -> Optimizer Python -> Persistencia -> latest-schedule.

## Veredito

O E2E de escala ainda nao passou.

- Python direto passou em 2000 e 5000 viagens com decomposicao, fallback local e 0 violacoes hard.
- O fluxo E2E falhou nos dois volumes com erro estruturado `SCALE_CHUNK_FAILED`.
- Nao houve loop de polling, timeout prematuro, estouro de Redis, perda de payload ou kill de memoria do worker.
- A falha principal e divergencia de semantica de dados entre Python direto e Backend/E2E quando `trip_group_id` esta ausente: o Python direto infere mais grupos obrigatorios que o backend antes de enviar o payload.
- O frontend visual nao foi aberto em navegador nesta rodada; foi validado o contrato de API usado pela tela via `latest-schedule`.

## Resultado por volume

| algoritmo | volume | direto Python | E2E | erro E2E | tempo backend s | leitura latest ms | Redis result bytes | Celery RSS antes/depois MB | Celery CPU antes/depois s |
|---|---:|---|---|---|---:|---:|---:|---:|---:|
| hybrid_pipeline | 2000 | ok | failed | SCALE_CHUNK_FAILED | 45.493 | 28.71 | 1572960 | 169.9 / 289.2 | 2.56 / 42.36 |
| hybrid_pipeline | 5000 | ok | failed | SCALE_CHUNK_FAILED | 121.707 | 20.30 | 4194400 | 247.6 / 300.0 | 42.49 / 149.27 |

## Tempos e instrumentacao

| volume | backend total ms | created->updated ms | optimizer solver ms | optimizer elapsed ms | persistencia PostgreSQL isolada | latest read ms |
|---:|---:|---:|---:|---:|---|---:|
| 2000 | 45493.36 | 45260.18 | nao disponivel | nao disponivel | nao instrumentada separadamente | 28.71 |
| 5000 | 121707.49 | 120441.60 | nao disponivel | nao disponivel | nao instrumentada separadamente | 20.30 |

Como o resultado E2E falhou antes de gerar uma solucao final, o payload persistido nao trouxe `optimizer_solver_ms`/`optimizer_total_elapsed_ms`. O tempo de persistencia PostgreSQL tambem nao esta instrumentado como metrica isolada; nesta rodada so foi possivel medir a janela `created->updated` do schedule e a leitura final de `latest-schedule`.

## Comparacao Python direto vs E2E

| volume | direto custo | E2E custo | direto veic. | E2E veic. | direto duties | E2E duties | direto perdidas | E2E perdidas | direto hard | E2E hard |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000 | 259824.13 | 0.00 | 84 | 0 | 112 | 0 | 0 | 2000* | 0 | 0 |
| 5000 | 661999.79 | 0.00 | 204 | 0 | 288 | 0 | 0 | 5000* | 0 | 0 |

`*` No E2E, as viagens aparecem como perdidas porque o schedule terminou `failed` e nenhum bloco final foi persistido. Nao e uma solucao `completed` com perda silenciosa.

## Escala no Python direto

| volume | status escala | chunks | fallback chunks | stitching aceitas | stitching rejeitadas | split_groups | hard violations |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2000 | partially_completed | 4 | 1 | 1 | 63 | 0 | 0 |
| 5000 | partially_completed | 9 | 1 | 19 | 253 | 0 | 0 |

## Escala no E2E

| volume | status | chunks detectados | failed chunks | chunk falho | erro primario | erro fallback |
|---:|---|---:|---:|---:|---|---|
| 2000 | failed | 4 | 1 | 3 | list index out of range | MANDATORY_GROUP_SPLIT `[25043, 25047]`, `[25045, 25054]` |
| 5000 | failed | 9 | 1 | 8 | list index out of range | MANDATORY_GROUP_SPLIT `[30031, 30040]`, `[30037, 30047]` |

## Diagnostico

O problema nao foi infraestrutura. O Celery finalizou e retornou erro de negocio estruturado; o backend persistiu `failed` com `error_code=SCALE_CHUNK_FAILED`; o `latest-schedule` expos `error_code`, `error_message` e `performance`.

A divergencia observada:

| volume | grupos inferidos no Python direto | grupos no E2E/backend | grouped trips E2E |
|---:|---:|---:|---:|
| 2000 | 998 | 984 | 1968 |
| 5000 | 2497 | 2463 | 4926 |

Os dados sinteticos enviados ao banco tinham `trip_group_id = NULL`. No Python direto, o optimizer infere pares obrigatorios internamente. No E2E, o backend tambem infere/atribui grupos antes de montar o payload, mas chega a uma cardinalidade diferente. Essa diferenca muda o perfil dos chunks e faz o ultimo chunk pequeno falhar no fallback por `MANDATORY_GROUP_SPLIT`.

## Validacoes de estabilidade

| item | resultado |
|---|---|
| Backend nao marcou failed antes do Celery terminar | passou |
| Polling nao entrou em loop infinito | passou |
| Celery nao foi morto por memoria | passou |
| Redis nao perdeu payload | passou |
| PostgreSQL persistiu status final | passou |
| latest-schedule retornou erro estruturado | passou |
| latest-schedule retornou performance | passou |
| latest-schedule retornou hard_constraint_report | nao disponivel nesta falha |
| Frontend render visual em navegador | nao testado |

## Logs principais

- 2000: `[SCALE] Decomposed hybrid_pipeline: trips=2000 groups=984 chunks=4 target=600 max=800`.
- 2000: `chunk[3] primary hybrid failed: list index out of range`.
- 2000: fallback local falhou com `MANDATORY_GROUP_SPLIT [25043, 25047]; MANDATORY_GROUP_SPLIT [25045, 25054]`.
- 2000: optimizer retornou `SCALE_CHUNK_FAILED`, backend persistiu `schedule_id=361`.
- 5000: `[SCALE] Decomposed hybrid_pipeline: trips=5000 groups=2463 chunks=9 target=600 max=800`.
- 5000: `chunk[8] primary hybrid failed: list index out of range`.
- 5000: fallback local falhou com `MANDATORY_GROUP_SPLIT [30031, 30040]; MANDATORY_GROUP_SPLIT [30037, 30047]`.
- 5000: optimizer retornou `SCALE_CHUNK_FAILED`, backend persistiu `schedule_id=362`.
- FastAPI status: `optimization_task_failed ... type=business code=SCALE_CHUNK_FAILED`.

## Bugs e gaps encontrados

| prioridade | item | evidencia | impacto |
|---|---|---|---|
| P0 | E2E 2000 strict nao completa | `SCALE_CHUNK_FAILED`, failed chunk 3/4 | Criterio de aceite de 2000 nao atendido |
| P0 | E2E 5000 strict nao completa/partially_completed | `SCALE_CHUNK_FAILED`, failed chunk 8/9 | Criterio de aceite de 5000 nao atendido |
| P1 | Divergencia de inferencia de `trip_group_id` entre Python direto e backend | 2000: 998 vs 984 grupos; 5000: 2497 vs 2463 grupos | Resultados Python direto e E2E nao sao comparaveis |
| P1 | `hard_constraint_report` ausente no latest para falha de chunk | `latest_has_hard_constraint_report=False` com failed chunks em `error_details` | Tela perde diagnostico operacional detalhado |
| P2 | Ultimo chunk pequeno ainda dispara `list index out of range` no caminho primario | chunk 3/4 e 8/9 | Fallback fica obrigatorio nesses cenarios |

## 10000 viagens

Nao executei 10000 viagens. Motivo: 2000 e 5000 falharam no E2E em criterio obrigatorio. Rodar 10000 agora seria baixo sinal e consumiria tempo/memoria em cima da mesma divergencia ja comprovada.

## Plano P0/P1 recomendado

P0:

- Padronizar uma unica fonte de verdade para inferencia de grupos obrigatorios quando `trip_group_id` vier nulo: ou backend nao infere e deixa o optimizer inferir, ou ambos usam exatamente a mesma funcao/regra.
- Reexecutar E2E 2000 strict apos a padronizacao e exigir `completed`/`partially_completed` com 0 hard violations, 0 split_groups e 0 viagens perdidas em solucao OK.
- Reexecutar E2E 5000 strict apos 2000 passar.

P1:

- Incluir `failed_chunks` e issues hard em `hard_constraint_report` quando o erro for `SCALE_CHUNK_FAILED`.
- Investigar o `list index out of range` do caminho primario em chunk pequeno, sem alterar threshold/chunking enquanto nao houver evidencia isolada.
- Validar render visual da tela com o ultimo schedule failed e, depois, com schedule completed/partially_completed.

## Artefatos

- JSON bruto do harness: `optimizer/e2e_scale_validation_report.json`
- JSON resumo final: `optimizer/e2e_scale_validation_summary.json`
- Benchmark Python direto anterior: `optimizer/scale_decomposition_benchmark_report.md`
