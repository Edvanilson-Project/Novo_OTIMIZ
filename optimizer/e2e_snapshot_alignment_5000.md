# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `2298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 5000 | failed | 661.208 |  | 36.11 | 4194400 | 297.3 |  |  | / | 0.0 | 0 | 0 | 5000 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta | params/hash/seed/groups |
|---|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 5000 | 0.0 | 0 | 0 | 193279.29 | 0 | False/False/False/False |

## Bugs Encontrados

- hybrid_pipeline 5000: P0: replay direto nao recebeu o mesmo pacote final de parametros
- hybrid_pipeline 5000: P0: replay direto nao recebeu o mesmo hash de trips do E2E
- hybrid_pipeline 5000: P1: seed divergiu entre E2E e replay direto
- hybrid_pipeline 5000: P1: grupos efetivos divergiram entre E2E e replay direto

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`