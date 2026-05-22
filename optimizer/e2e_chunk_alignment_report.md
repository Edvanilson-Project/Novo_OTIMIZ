# OTIMIZ E2E Benchmark

- backend_url: `http://localhost:3001/api/v1`
- company_id: `22`
- source_real_trips: `298`

| algoritmo | volume | status | backend s | optimizer s | read ms | Redis result bytes | Celery RSS MB | chunks | fallback | stitch ok/rej | custo | veic. | duties | perdidas | duplicadas | hard | soft | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| hybrid_pipeline | 2000 | completed | 51.726 | 47.544 | 91.31 | 1835104 | 273.6 | 4 |  | 3/140 | 1756810.28 | 96 | 164 | 0 | 0 | 0 | 0 | True/True |
| hybrid_pipeline | 5000 | completed | 86.904 | 82.059 | 125.33 | 5242976 | 290.4 | 9 |  | 22/576 | 4908512.81 | 281 | 421 | 0 | 0 | 0 | 0 | True/True |

## Comparacao Direto Python vs E2E

| algoritmo | volume | custo delta | veic. delta | duties delta | tempo delta ms | hard delta |
|---|---:|---:|---:|---:|---:|---:|
| hybrid_pipeline | 2000 | 575024.3 | 35 | 53 | 16298.3 | 0 |
| hybrid_pipeline | 5000 | 1707609.16 | 110 | 134 | 30576.89 | 0 |

## Chunk Diff hybrid_pipeline 2000

| chunk | trips | direct status | e2e status | direct veic. | e2e veic. | delta veic. | direct duties | e2e duties | delta duties |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| 0 | 600 | completed | completed | 16 | 48 | 32 | 32 | 46 | 14 |
| 1 | 600 | completed | completed | 16 | 18 | 2 | 32 | 48 | 16 |
| 2 | 600 | completed | completed | 16 | 18 | 2 | 34 | 49 | 15 |
| 3 | 200 | completed | completed | 13 | 15 | 2 | 13 | 21 | 8 |

- stitching direct/e2e: accepted `0` / `3`, rejected `69` / `140`, output blocks `61` / `96`.

## Chunk Diff hybrid_pipeline 5000

| chunk | trips | direct status | e2e status | direct veic. | e2e veic. | delta veic. | direct duties | e2e duties | delta duties |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| 0 | 600 | completed | completed | 16 | 48 | 32 | 32 | 46 | 14 |
| 1 | 600 | completed | completed | 16 | 18 | 2 | 32 | 48 | 16 |
| 2 | 600 | completed | completed | 16 | 18 | 2 | 34 | 49 | 15 |
| 3 | 600 | completed | completed | 16 | 18 | 2 | 34 | 50 | 16 |
| 4 | 600 | completed | completed | 16 | 18 | 2 | 35 | 51 | 16 |
| 5 | 600 | completed | completed | 16 | 54 | 38 | 36 | 52 | 16 |
| 6 | 600 | completed | completed | 36 | 54 | 18 | 36 | 52 | 16 |
| 7 | 600 | completed | completed | 36 | 54 | 18 | 36 | 52 | 16 |
| 8 | 200 | completed | completed | 12 | 21 | 9 | 12 | 21 | 9 |

- stitching direct/e2e: accepted `9` / `22`, rejected `345` / `576`, output blocks `171` / `281`.

## Bugs Encontrados

- Nenhum bug novo detectado nos cenarios executados.

## Logs Principais

- `/tmp/otimiz-e2e-celery.log`
- `backend stdout session`
- `optimizer uvicorn stdout session`