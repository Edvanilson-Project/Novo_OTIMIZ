# OTIMIZ Snapshot/Reproducibility Validation

Data: 2026-04-29
Escopo: `hybrid_pipeline` em strict mode, comparando E2E vs replay direto a partir do `OptimizationRunSnapshot` exportado.

## Veredito executivo

- `2000 strict`: sucesso reprodutivel. E2E e replay direto bateram exatamente em hashes, parametros resolvidos, grupos efetivos, chunks, stitching e resultado final.
- `5000 strict`: falha reprodutivel. E2E e replay direto bateram exatamente em hashes, parametros resolvidos, grupos efetivos e nos mesmos `failed_chunks` com `GROUP_INFEASIBLE`.
- Isso prova que o snapshot/replay agora reproduz o mesmo problema de verdade nos dois volumes.
- Isso nao prova que `5000 strict` esteja pronto para piloto com expectativa de sucesso; prova apenas que a falha atual e deterministica, estruturada e auditavel.

## Tabela 2000 vs 5000

| volume | classificacao | E2E | replay direto | params/hash/seed/groups | chunks/stitch | resultado/falha |
|---:|---|---|---|---|---|---|
| 2000 | success_reproducible | `completed` | `ok` | `True/True/True/True` | `True/True` | resultado final identico |
| 5000 | failure_reproducible | `failed` `SCALE_CHUNK_FAILED` | `failed` `SCALE_CHUNK_FAILED` | `True/True/True/True` + submitted/request `True/True` | `8 chunks` identicos | mesmos 3 chunks inviaveis |

## Caso 2000 strict

- Snapshot: `optimizer/replays/e2e_hybrid_pipeline_2000_schedule_375.json`
- `trips_hash`: `89f2ba414d3d`
- `vehicle_types_hash`: `e66bc502922a`
- `seed`: `42`
- Custo E2E/replay: `411358.99` / `411358.99`
- Veiculos E2E/replay: `138` / `138`
- Duties E2E/replay: `196` / `196`
- Perdidas: `0 / 0`
- Hard violations: `0 / 0`
- Chunks: `4` em ambos
- Stitching aceitas/rejeitadas: `55/1348` em ambos

## Caso 5000 strict

- Snapshot: `optimizer/replays/e2e_hybrid_pipeline_5000_schedule_376.json`
- `trips_hash`: `fb4098176d21`
- `vehicle_types_hash`: `e66bc502922a`
- `seed`: `42`
- E2E: `failed` / `SCALE_CHUNK_FAILED`
- Replay direto: `failed` / `SCALE_CHUNK_FAILED`
- `chunk_count`: `8` em ambos
- Falha top-level identica: `SCALE_CHUNK_FAILED`

### Failed chunks identicos

| chunk | error_code | trip_ids | reason_code |
|---:|---|---|---|
| 5 | `GROUP_INFEASIBLE` | `[71810, 71909]` | `GROUP_CONNECTION_INFEASIBLE` |
| 6 | `GROUP_INFEASIBLE` | `[71885, 71923]` | `GROUP_CONNECTION_INFEASIBLE` |
| 7 | `GROUP_INFEASIBLE` | `[72604, 72614]` | `GROUP_CONNECTION_INFEASIBLE` |

### Leitura tecnica

O relatorio automatico antigo de `5000` ficou enganoso porque o helper de replay resumia qualquer erro para um `status=error` sem preservar o `run_snapshot` e os `failed_chunks`. O replay manual a partir do snapshot exportado mostrou que isso nao era divergencia real de problema. Era divergencia de instrumentacao do relatorio.

No estado atual:

- `resolved_params`: identicos entre E2E e replay.
- `submitted_params`: identicos entre E2E e replay.
- `request_metadata`: identico entre E2E e replay.
- `trip_group_inference_report`: identico entre E2E e replay.
- `failed_chunks`: identicos entre E2E e replay.

## Veredito sobre piloto de producao

Veredito: **condicional**.

- Para `2000 strict`, temos reproducibilidade forte de sucesso. Isso e um sinal bom para piloto controlado.
- Para `5000 strict`, temos reproducibilidade forte da falha. Isso e melhor do que um comportamento opaco, mas ainda nao e o mesmo que demonstrar sucesso operacional nesse volume.
- Portanto, eu nao chamaria isso de “pronto para piloto irrestrito”. Eu chamaria de “pronto para piloto controlado” apenas se a equipe aceitar que certos cenarios strict de `5000` podem terminar em `SCALE_CHUNK_FAILED` por `GROUP_INFEASIBLE`, com diagnostico claro e auditavel.
