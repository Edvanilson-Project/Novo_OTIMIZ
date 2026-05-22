# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 298 | failed | 6.27 |  | 12.5 | 262240 | 338.0 | 0.0 | 0 | 0 | 298 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 596 | failed | 16.554 |  | 19.96 | 524384 | 365.7 | 0.0 | 0 | 0 | 596 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 1000 | failed | 45.363 |  | 17.37 | 917600 | 444.8 | 0.0 | 0 | 0 | 1000 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 2000 | failed | 131.918 |  | 22.78 | 1835104 | 835.5 | 0.0 | 0 | 0 | 2000 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| hybrid_pipeline | 298 | -45587.29 | -17 | -19 | 1840.96 | 0 |
| hybrid_pipeline | 596 | 0.0 | 0 | 0 | 2592.21 | 0 |
| hybrid_pipeline | 1000 | 0.0 | 0 | 0 | -1148.55 | 0 |
| hybrid_pipeline | 2000 | 0.0 | 0 | 0 | -28148.84 | 0 |

## Bugs Encontrados

- Nenhum bug novo detectado nos cenarios executados.

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`