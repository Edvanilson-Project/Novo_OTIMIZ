# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| assignment_vsp | 298 | failed | 6.246 |  | 10.77 | 262240 | 279.2 | 0.0 | 0 | 0 | 298 | 0 | 0 | 0 | False/True |
| hybrid_pipeline | 298 | failed | 6.247 |  | 10.05 | 262240 | 279.2 | 0.0 | 0 | 0 | 298 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| assignment_vsp | 298 | 0.0 | 0 | 0 | 6207.29 | 0 |
| hybrid_pipeline | 298 | 0.0 | 0 | 0 | 1819.69 | 0 |

## Bugs Encontrados

- assignment_vsp 298: P0: viagens perdidas no resultado persistido
- assignment_vsp 298: P0: status final nao completou (failed)
- hybrid_pipeline 298: P0: viagens perdidas no resultado persistido
- hybrid_pipeline 298: P0: status final nao completou (failed)

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`