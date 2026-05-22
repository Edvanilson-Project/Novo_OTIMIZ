# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 2000 | completed | 86.762 | 82.181 | 56.75 | 1835104 | 296.5 | 4 |  | 1/70 | 415330.04 | 74 | 164 | 0 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| hybrid_pipeline | 2000 | 415330.04 | 74 | 164 | 20507.95 | 0 |

## Chunk Diff hybrid_pipeline 2000

| chunk | trips | direct status | e2e status | direct veic. | e2e veic. | delta veic. | direct duties | e2e duties | delta duties |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| 0 | 600 | None | completed | None | 20 | 20 | None | 46 | 46 |
| 1 | 600 | None | completed | None | 20 | 20 | None | 48 | 48 |
| 2 | 600 | None | completed | None | 20 | 20 | None | 49 | 49 |
| 3 | 200 | None | completed | None | 15 | 15 | None | 21 | 21 |

- stitching direct/e2e: accepted `0` / `1`, rejected `0` / `70`, output blocks `0` / `74`.

## Bugs Encontrados

- Nenhum bug novo detectado nos cenarios executados.

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`