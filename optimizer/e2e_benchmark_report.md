# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| assignment_vsp | 298 | failed | 61.918 |  | 8.52 | 262240 | 556.6 | 0.0 | 0 | 0 | 298 | 0 | 0 | 0 | False/False |
| hybrid_pipeline | 298 | failed | 61.911 |  | 7.78 | 262240 | 556.8 | 0.0 | 0 | 0 | 298 | 0 | 0 | 0 | False/False |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| assignment_vsp | 298 | -62556.58 | -14 | -20 | 61658.43 | 0 |
| hybrid_pipeline | 298 | 0.0 | 0 | 0 | 57615.3 | 0 |

## Bugs Encontrados

- assignment_vsp 298: P0: viagens nao persistidas/cobertas no resultado final
- assignment_vsp 298: P0: status final nao completou (failed)
- hybrid_pipeline 298: P0: viagens nao persistidas/cobertas no resultado final
- hybrid_pipeline 298: P0: status final nao completou (failed)

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`