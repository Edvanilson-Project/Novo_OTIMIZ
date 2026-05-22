# OTIMIZ E2E Validation Report

Versao validada: codigo atual em disco, backend recompilado, FastAPI e Celery reiniciados.

## Tabela por volume

| algoritmo | volume | status E2E | backend/schedule ms | celery ms | optimizer ms | read ms | Redis bytes | Celery RSS MB | custo | veic | duties | perdidas | duplicadas | hard | erro | tela report/perf |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| assignment_vsp | 298 | failed | 5100.8 | 5100.8 | None | 11.24 | 262240 | 267.6 | 0.0 | 0 | 0 | 298 | 0 | 0 | ALGORITHM_UNSUPPORTED_STRICT_GROUPS | False/True |
| hybrid_pipeline | 298 | failed | 5072.99 | 5072.99 | None | 12.5 | 262240 | 338.0 | 0.0 | 0 | 0 | 298 | 0 | 0 | HARD_CONSTRAINT_VIOLATION | True/True |
| hybrid_pipeline | 596 | failed | 15096.76 | 15096.76 | None | 19.96 | 524384 | 365.7 | 0.0 | 0 | 0 | 596 | 0 | 0 | HARD_CONSTRAINT_VIOLATION | True/True |
| hybrid_pipeline | 1000 | failed | 45140.03 | 45140.03 | None | 17.37 | 917600 | 444.8 | 0.0 | 0 | 0 | 1000 | 0 | 0 | HARD_CONSTRAINT_VIOLATION | True/True |
| hybrid_pipeline | 2000 | failed | 130282.95 | 130282.95 | None | 22.78 | 1835104 | 835.5 | 0.0 | 0 | 0 | 2000 | 0 | 0 | MANDATORY_GROUP_SPLIT | True/True |
| hybrid_pipeline | 5000 | failed | 595918.48 | 637293.02 | None | 70.79 | 4194400 | 2043.1 | 0.0 | 0 | 0 | 5000 | 0 | None | MANDATORY_GROUP_SPLIT | False/False |

## Python direto vs E2E

| algoritmo | volume | direto Python | E2E | delta custo | delta veic | delta duties | observacao |
|---|---:|---|---|---:|---:|---:|---|
| assignment_vsp | 298 | error | failed | 0.0 | 0 | 0 | OptimizerError: Algorithm 'assignment_vsp' is not allowed with strict_hard_constraints=true when trip_group_id is presen |
| hybrid_pipeline | 298 | ok | failed | -45587.29 | -17 | -19 | Direto OK, E2E falhou. |
| hybrid_pipeline | 596 | error | failed | 0.0 | 0 | 0 | NameError: name 'needed' is not defined |
| hybrid_pipeline | 1000 | error | failed | 0.0 | 0 | 0 | NameError: name 'needed' is not defined |
| hybrid_pipeline | 2000 | error | failed | 0.0 | 0 | 0 | HardConstraintViolationError: Hard constraints violated: MANDATORY_GROUP_SPLIT [2002273, 2002274]; MANDATORY_GROUP_SPLIT |
| hybrid_pipeline | 5000 | not_completed_in_harness | failed | None | None | None | O harness demorou tempo excessivo no caso 5000; foi interrompido. A tarefa E2E já havia sido submetida e foi recuperada  |

## Bugs encontrados

- P0 hybrid_pipeline 298: Python direto passa, mas E2E falha com HARD_CONSTRAINT_VIOLATION/VEHICLE_OVERLAP após repair/fallback.
- P1 hybrid_pipeline 298: Repair de grupo elimina split mas cria blocos com VEHICLE_OVERLAP no E2E.
- P1 hybrid_pipeline 596: Repair de grupo elimina split mas cria blocos com VEHICLE_OVERLAP no E2E.
- P0 hybrid_pipeline 596: Execucao Python direta falha com NameError: needed não definido.
- P1 hybrid_pipeline 1000: Repair de grupo elimina split mas cria blocos com VEHICLE_OVERLAP no E2E.
- P0 hybrid_pipeline 1000: Execucao Python direta falha com NameError: needed não definido.
- P1 hybrid_pipeline 2000: Strict mode ainda quebra trip_group_id em volume maior.
- P0 hybrid_pipeline 5000: P0: backend/UI marcaram failed sem error_code/error_message enquanto o Celery ainda executava
- P0 hybrid_pipeline 5000: P0: latest-schedule do caso 5000 nao expôs hard_constraint_report/performance/erro estruturado
- P2 hybrid_pipeline 5000: P2: worker Celery chegou a ~2.0 GB RSS no caso 5000

## Logs principais

- Celery: assignment_vsp retornou business error `ALGORITHM_UNSUPPORTED_STRICT_GROUPS` sem crash.
- Celery: hybrid 298/596/1000 falhou em `VEHICLE_OVERLAP` após repair de grupos.
- Celery: hybrid 2000/5000 falhou em `MANDATORY_GROUP_SPLIT` em strict mode.
- Backend: enviou parâmetros strict e `enforce_min_interval=false, min_break=15` em todos os casos.
- Frontend: `npm run build` passou; browser E2E real não foi executado.

## Plano P0/P1/P2

- P0: alinhar timeout backend com Celery; no 5000 o backend marcou failed antes do Celery terminar e perdeu erro estruturado.
- P0: investigar `NameError: needed` no caminho direto Python em 596/1000.
- P1: corrigir repair de grupos para não criar `VEHICLE_OVERLAP` nos blocos dedicados/segmentados.
- P1: ampliar preservação de `trip_group_id` para volumes 2000+ sem depender de sample repair limitado.
- P2: reduzir memória do worker ou garantir reciclagem real; Celery chegou a ~2 GB RSS no 5000.
- P2: criar teste browser E2E real para confirmar renderização da tela, além do contrato `latest-schedule`.