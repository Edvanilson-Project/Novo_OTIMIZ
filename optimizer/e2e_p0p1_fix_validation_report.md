# E2E P0/P1 Fix Validation
## Veredito
- `hybrid_pipeline` strict completou E2E para 298, 596 e 1000 viagens.
- `hybrid_pipeline` strict em 2000 viagens falhou de forma estruturada com `MANDATORY_GROUP_SPLIT`.
- `assignment_vsp` 298 strict continua falhando de forma controlada com `ALGORITHM_UNSUPPORTED_STRICT_GROUPS`.
- Não houve `NameError`, `VEHICLE_OVERLAP` em solução OK, nem `failed` sem código de erro nos cenários validados.

## Arquivos alterados
- `optimizer/src/algorithms/vsp/greedy.py`
- `optimizer/src/services/optimizer_service.py`
- `optimizer/tests/unit/test_solver_edge_cases.py`
- `backend/src/modules/operations/optimization.service.ts`
- `backend/src/modules/operations/optimization.service.spec.ts`
- `optimizer/scripts/e2e_benchmark_real_flow.py`

## Testes executados
- `./optimizer/venv/bin/python -m compileall -q optimizer/src`: passed
- `./optimizer/venv/bin/python -m pytest optimizer/tests/unit/test_solver_edge_cases.py optimizer/tests/unit/test_vsp_tolerance_and_multiline.py optimizer/tests/unit/test_settings_parameter_effects.py -q`: 35 passed, 1 warning
- `npm test -- --runInBand backend/src/modules/operations/optimization.service.spec.ts`: 4 passed
- `npm run build`: passed
- `E2E assignment_vsp 298 strict`: failed controlled ALGORITHM_UNSUPPORTED_STRICT_GROUPS
- `E2E hybrid_pipeline 298/596/1000/2000 strict`: 298/596/1000 completed; 2000 failed structured MANDATORY_GROUP_SPLIT

- `GET /api/v1/operations/latest-schedule` com JWT da company 22 após o 2000: `failed`, `error_code=MANDATORY_GROUP_SPLIT`, `error_message`, `hard_constraint_report` e `performance` presentes.

## Tabela final
| algoritmo | volume | direct | e2e | erro | veículos | duties | custo | perdidas | duplicadas | hard | latest_report | latest_perf | backend_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| assignment_vsp | 298 | error | failed | ALGORITHM_UNSUPPORTED_STRICT_GROUPS | 0 | 0 | 0.0 | 298 | 0 | 0 | False | True | 6459.55 |
| hybrid_pipeline | 298 | ok | completed |  | 14 | 21 | 47392.01 | 0 | 0 | 0 | True | True | 6332.0 |
| hybrid_pipeline | 596 | ok | completed |  | 22 | 42 | 94704.61 | 0 | 0 | 0 | True | True | 16717.34 |
| hybrid_pipeline | 1000 | ok | completed |  | 50 | 75 | 178761.92 | 0 | 0 | 0 | True | True | 35217.01 |
| hybrid_pipeline | 2000 | error | failed | MANDATORY_GROUP_SPLIT | 0 | 0 | 0.0 | 2000 | 0 | 0 | True | True | 115676.68 |

## Antes vs depois
| Cenário | Antes | Depois |
| --- | --- | --- |
| hybrid 298 strict | E2E falhava com `VEHICLE_OVERLAP` após repair | `completed`, 0 perdidas, 0 duplicadas, 0 hard violations |
| hybrid 596/1000 strict | Python direto falhava com `NameError: needed`; E2E podia cair em overlap | `completed`, sem NameError e sem hard violations |
| hybrid 2000 strict | `MANDATORY_GROUP_SPLIT` | continua `failed`, mas estruturado, com report/performance no latest |
| assignment 298 strict | esperado falhar controlado | permanece `ALGORITHM_UNSUPPORTED_STRICT_GROUPS` |

## Observação
O cenário 5000 não foi reexecutado nesta rodada. A correção do polling remove o timeout prematuro observado ao alinhar o limite do backend ao limite hard do Celery mais margem, mas esse caso específico ainda precisa de uma nova execução longa para confirmação empírica.
