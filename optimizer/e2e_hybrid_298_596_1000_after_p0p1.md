# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 298 | completed | 6.353 | 3.614 | 43.82 | 327776 | 241.7 | 47392.01 | 14 | 21 | 298 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 596 | completed | 16.736 | 12.109 | 66.71 | 655456 | 267.8 | 94704.61 | 22 | 42 | 596 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 1000 | completed | 35.205 | 34.084 | 58.09 | 917600 | 322.1 | 178761.92 | 50 | 75 | 1000 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| hybrid_pipeline | 298 | 1804.72 | -3 | 2 | -1156.51 | 0 |
| hybrid_pipeline | 596 | 9587.19 | -4 | 8 | -676.09 | 0 |
| hybrid_pipeline | 1000 | 21646.5 | -6 | 17 | -18633.25 | 0 |

## Bugs Encontrados

- hybrid_pipeline 298: P0: viagens perdidas no resultado persistido
- hybrid_pipeline 596: P0: viagens perdidas no resultado persistido
- hybrid_pipeline 1000: P0: viagens perdidas no resultado persistido

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`