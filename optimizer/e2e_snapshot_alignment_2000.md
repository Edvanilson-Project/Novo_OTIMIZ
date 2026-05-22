# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `2298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 2000 | completed | 167.169 | 161.987 | 68.69 | 1835104 | 275.2 | 4 |  | 55/1348 | 411358.99 | 138 | 196 | 0 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta | params/hash/seed/groups |
|---|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 2000 | 0.0 | 0 | 0 | 7775.45 | 0 | True/True/True/True |

## Chunk Diff hybrid_pipeline 2000

| chunk | trips | direct status | e2e status | direct veic. | e2e veic. | delta veic. | direct duties | e2e duties | delta duties |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| 0 | 600 | completed | completed | 72 | 72 | 0 | 72 | 72 | 0 |
| 1 | 600 | completed | completed | 48 | 48 | 0 | 48 | 48 | 0 |
| 2 | 600 | completed | completed | 60 | 60 | 0 | 60 | 60 | 0 |
| 3 | 200 | completed | completed | 13 | 13 | 0 | 16 | 16 | 0 |

- stitching direct/e2e: accepted `55` / `55`, rejected `1348` / `1348`, output blocks `138` / `138`.
- replay snapshot: `optimizer/replays/e2e_hybrid_pipeline_2000_schedule_375.json`

## Bugs Encontrados

- Nenhum bug novo detectado nos cenarios executados.

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`