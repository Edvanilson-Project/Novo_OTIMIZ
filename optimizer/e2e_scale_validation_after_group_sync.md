# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 2000 | failed | 51.629 |  | 32.8 | 1572960 | 384.6 |  |  | / | 0.0 | 0 | 0 | 2000 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 5000 | completed | 136.209 | 130.701 | 128.77 | 5242976 | 440.9 | 9 | 1 | 5/363 | 982071.44 | 183 | 421 | 0 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| hybrid_pipeline | 2000 | -259824.13 | -84 | -112 | 2814.97 | 0 |
| hybrid_pipeline | 5000 | 320071.65 | -21 | 133 | 2759.51 | 0 |

## Bugs Encontrados

- Nenhum bug novo detectado nos cenarios executados.

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`