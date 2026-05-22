# OTIMIZ Trip Group Unification Validation

Data: 2026-04-28  
Decisao arquitetural: **Opcao A**.

- O backend nao infere mais `trip_group_id`.
- O backend envia `trip_group_id` bruto do banco, inclusive `NULL`.
- O optimizer virou a unica fonte de verdade para inferencia/materializacao de grupos obrigatorios.

## Arquivos alterados

- `backend/src/modules/operations/optimization.service.ts`
- `backend/src/modules/operations/optimization.service.spec.ts`
- `optimizer/src/api/schemas.py`
- `optimizer/src/api/routes/optimize.py`
- `optimizer/src/services/optimizer_tasks.py`
- `optimizer/src/services/optimizer_service.py`
- `optimizer/tests/unit/test_solver_edge_cases.py`

## O que mudou

Antes:

- Backend inferia grupos sinteticos ao montar o payload.
- Optimizer tambem inferia grupos quando `trip_group_id = NULL`.
- Resultado: o mesmo dataset gerava problemas diferentes entre Python direto e E2E.

Depois:

- Backend envia `trip_group_id` cru e anexa apenas metadados de auditoria:
  - `trip_group_inference_mode=optimizer_only`
  - `backend_trip_group_stats`
- Optimizer valida que o payload recebido bate com os metadados do backend.
- Optimizer registra tres contagens:
  - `backend_trip_group_stats`
  - `optimizer_input_stats`
  - `optimizer_effective_stats`
- Em `SCALE_CHUNK_FAILED`, o erro agora inclui `group_inference_report` e `hard_constraint_report` com `failed_chunks` e grupos problematicos.

## Antes vs depois

| volume | antes backend/E2E | antes Python direto | depois backend payload | depois optimizer efetivo | situacao |
|---:|---:|---:|---:|---:|---|
| 2000 | 984 grupos | 998 grupos | 0 grupos explicitos | 998 grupos inferidos | divergencia removida |
| 5000 | 2463 grupos | 2497 grupos | 0 grupos explicitos | 2497 grupos inferidos | divergencia removida |

Logs antes:

- 2000: `[SCALE] Decomposed hybrid_pipeline: trips=2000 groups=984 chunks=4`.
- 5000: `[SCALE] Decomposed hybrid_pipeline: trips=5000 groups=2463 chunks=9`.

Logs depois:

- Backend: `trip_groups=0, grouped_trips=0`.
- Optimizer 2000: `[GROUPS] mode=optimizer_only backend=0/0 input=0/0 effective=998/1996 inferred=True`.
- Optimizer 5000: `[GROUPS] mode=optimizer_only backend=0/0 input=0/0 effective=2497/4994 inferred=True`.

## Validacao executada

- `./optimizer/venv/bin/python -m compileall -q optimizer/src`: passed
- `./optimizer/venv/bin/python -m pytest optimizer/tests/unit/test_solver_edge_cases.py -q`: 10 passed
- `npm test -- --runInBand backend/src/modules/operations/optimization.service.spec.ts`: 4 passed
- `npm run build` no backend: passed
- E2E:
  - `hybrid_pipeline 2000 strict`
  - `hybrid_pipeline 5000 strict`

## Resultado E2E

| volume | Python direto | E2E | erro | backend total ms | optimizer ms | Redis payload bytes | Celery RSS antes/depois MB | hard report no latest |
|---:|---|---|---|---:|---:|---:|---:|---|
| 2000 | ok | failed | `SCALE_CHUNK_FAILED` | 51629.23 | n/d | 1572960 | 264.6 / 384.6 | sim |
| 5000 | ok | completed |  | 136209.30 | 130700.52 | 5242976 | 384.6 / 440.9 | sim |

## Comparacao Python direto vs E2E

| volume | direto custo | E2E custo | direto veic. | E2E veic. | direto duties | E2E duties | perdidas E2E | hard E2E |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000 | 259824.13 | 0.00 | 84 | 0 | 112 | 0 | 2000* | 0 |
| 5000 | 661999.79 | 982071.44 | 204 | 183 | 288 | 421 | 0 | 0 |

`*` Em 2000 o schedule terminou `failed`, entao nao houve blocos persistidos finais.

## Leitura tecnica sincera

O problema de dupla inferencia foi resolvido. Essa parte agora tem evidencia:

- o backend nao materializa grupos;
- o optimizer recebeu o payload cru;
- a inferencia efetiva do optimizer passou a reproduzir exatamente a cardinalidade do Python direto.

Mas o efeito no E2E foi parcial:

- `5000` melhorou de `failed` para `completed`, com 0 viagens perdidas, 0 duplicadas, 0 hard violations e `split_groups=0`;
- `2000` continuou falhando em um chunk pequeno com `list index out of range` no primario e `MANDATORY_GROUP_SPLIT` no fallback.

Portanto, a divergencia de grupos era uma causa raiz real, mas nao era a unica causa do `SCALE_CHUNK_FAILED`.

## Evidencia de erro estruturado em 2000

- `error_code=SCALE_CHUNK_FAILED`
- `group_inference_report` presente em `error_details`
- `hard_constraint_report` presente no `latest-schedule`
- `failed_chunks[0]`:
  - `chunk_index=3`
  - `trip_count=200`
  - `primary_error=list index out of range`
  - `fallback error=MANDATORY_GROUP_SPLIT [32039, 32048]; [32051, 32060]; [32056, 32059]; [32062, 32065]`

## Veredito final

- A decisao A foi implementada corretamente.
- A dupla inferencia de `trip_group_id` deixou de existir.
- A consistencia backend -> optimizer para grupos ficou validada.
- `5000 strict` agora passa no E2E.
- `2000 strict` ainda nao passa no E2E.

Conclusao: a causa raiz pedida nesta rodada foi resolvida, mas o sistema ainda nao pode ser considerado validado em escala strict para 2000+ de forma geral, porque resta pelo menos um segundo problema independente no caminho de chunk pequeno.
