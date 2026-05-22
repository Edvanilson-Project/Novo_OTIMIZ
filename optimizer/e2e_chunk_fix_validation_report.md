# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 2000 | completed | 72.264 | 67.363 | 88.53 | 1835104 | 274.8 | 4 |  | 1/70 | 415330.04 | 74 | 164 | 0 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 5000 | completed | 156.899 | 154.08 | 135.44 | 5242976 | 290.4 | 9 |  | 5/363 | 982071.44 | 183 | 421 | 0 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| hybrid_pipeline | 2000 | 155505.91 | -10 | 52 | 6919.35 | 0 |
| hybrid_pipeline | 5000 | 310232.65 | -21 | 133 | 8750.29 | 0 |

## Bugs Encontrados

- Nenhum bug novo detectado nos cenarios executados.

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`