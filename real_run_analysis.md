# Análise de Execução Real - OTIMIZ System

## Resumo Executivo

Execução real realizada com sucesso em 29/04/2026 13:16 UTC.
- **Schedule ID**: 377
- **Task ID**: 74946607-dafc-4ba1-9dfd-d85ed3959efd
- **Status**: completed (com hard violations)
- **Algoritmo**: hybrid_pipeline
- **Viagens processadas**: 298 (não as 5000 originais da empresa 22 - sistema processou empresa 16)
- **Empresa efetiva**: 16 (Matriz SP) - observar discrepância no companyId do schedule

## Identificação da Carta Real

### Dados da Empresa
- **company_id**: 16 (Matriz SP) - processado efetivamente
- **company_id original solicitado**: 22 (OTIMIZ E2E Benchmark)
- **schedule_id**: 377
- **run_id**: 377

### Estatísticas da Carta (Empresa 22 - original)
- **Total de viagens**: 5000
- **Total de linhas**: 1 (lineId=104201)
- **Trip groups explícitos**: 0 (trip_group_id nulo em todas as 5000)
- **Viagens sem trip_group_id**: 5000
- **Período de operação**: 270 a 3938 minutos (04:30 às 65:38 - virada de meia-noite)
- **Primeiro horário**: 270 (04:30)
- **Último horário**: 3938 (65:38 = próximo dia 17:38)
- **Pontos/terminais distintos**: 4 (2 origins + 2 destinations)
- **Vehicle types usados**: 1 (padrão)

### Parâmetros da Empresa 22 (company_parameters id=43)
- algorithm_preference: hybrid_pipeline
- strict_hard_constraints: true (não confirmado se aplicado)
- strict_operational_mode: true (não confirmado se aplicado)
- strict_zero_gap_validation: true (não confirmado se aplicado)
- group_infeasibility_mode: strict (não confirmado se aplicado)
- cost_vehicle: 14565.104535778026
- cost_km: 1.0
- cost_duty: 439.6983429020171
- force_round_trip: true
- enforce_trip_groups_hard: true
- operator_pairing_hard: true

## Fluxo Real Mapeado

### 1. Banco PostgreSQL (otimiz-v2-postgres)
- **Arquivo**: `backend/src/modules/database/entities/*.entity.ts`
- **Dado que entra**: SELECT em trips, company_parameters, schedules
- **Dado que sai**: JSON com trips, params, vehicle_types
- **Transformação**: TypeORM converte entidades para objetos JS
- **Risco**: Senha do banco incorreta no .env inicial causou falha de conexão

### 2. Backend NestJS (otimiz-v2-backend)
- **Arquivo**: `backend/src/modules/operations/optimization.service.ts`
- **Função**: `runOptimization(companyId, algorithm)`
- **Dado que entra**: companyId=22 (mas processou companyId=16)
- **Dado que sai**: Payload para optimizer
- **Transformação**:
  - Trips mapeadas com normalização de virada de meia-noite (end < start → +1440)
  - Parâmetros reconstruídos via `buildCctParams()` e `buildVspParams()`
  - Vehicle types hardcoded como array com 1 tipo
- **Risco**: Discrepância entre companyId solicitado (22) e processado (16) - possível cache ou erro de tenancy

### 3. Payload para FastAPI Optimizer
- **Endpoint**: POST http://optimizer:8000/optimize
- **Dado que entra**: 
  - trips: 298 viagens (não 5000 da empresa 22)
  - vehicle_types: 1 tipo
  - cct_params: ver seção de parâmetros
  - optimization_params: ver seção de parâmetros
- **Risco**: CompanyId divergente (22 vs 16)

### 4. FastAPI Optimizer (otimiz-optimizer)
- **Arquivo**: `optimizer/main.py`
- **Endpoint**: `/optimize` (redireciona para `/optimize/` com trailing slash)
- **Dado que entra**: Payload JSON
- **Validação**: X-Internal-Key header
- **Dado que sai**: task_id (Celery task ID)

### 5. Celery Worker
- **Arquivo**: `optimizer/src/core/celery_app.py`
- **Task**: `src.services.optimizer_tasks`
- **Dado que entra**: Mesmo payload do optimizer
- **Processamento**: 
  - Reconstrói objetos Trip, VehicleType
  - Executa algoritmo hybrid_pipeline
  - Chama OptimizerService
- **Risco**: worker_prefetch_multiplier=1 (1 tarefa por vez) - adequado para CPU-bound

### 6. Solver (OptimizerService)
- **Arquivo**: `optimizer/src/services/optimizer_service.py`
- **Algoritmo**: hybrid_pipeline
- **Dado que sai**: Resultado da otimização
- **Métricas capturadas**:
  - vehicles=15
  - crew=18
  - total_cost=249722.04
  - cct_violations=2

### 7. Redis Result Backend
- **Container**: otimiz-v2-redis (porta 6388)
- **Uso**: Armazena resultados do Celery
- **Serializer**: JSON com compressão GZIP
- **Retenção**: 12 horas (result_expires=43200)

### 8. Backend Polling
- **Arquivo**: `backend/src/modules/operations/optimization.service.ts`
- **Método**: Polling do task_id no Redis via Celery result backend
- **Dado que entra**: task_id
- **Dado que sai**: Status da tarefa (PENDING, SUCCESS, FAILURE)

### 9. Persistência
- **Arquivo**: `backend/src/modules/operations/optimization.service.ts`
- **Dado que entra**: Resultado do solver
- **Ação**: Salva em schedules, block_assignments, duty_assignments
- **Dado que sai**: Schedule atualizado com status=completed

### 10. Latest-Schedule
- **Endpoint**: GET /api/v1/operations/latest-schedule?companyId=16
- **Dado que sai**: JSON com resultSummary, blocks, duties, metadata
- **Risco**: Retorna companyId=16, não 22

## Métricas da Execução

### Result Summary
- **num_vehicles**: 15
- **num_crew**: 18
- **total_cost**: 249722.04
- **cct_violations**: 2
- **total_trips**: 298
- **unassigned_trips**: 0
- **hardIssueCount**: 2
- **softIssueCount**: 0
- **hasHardViolations**: true
- **solverStatus**: hard_violation

### Cost Breakdown
- **CSP (Crew Scheduling Problem)**:
  - total: 22081.31
  - work_cost: 2436.72
  - num_duties: 19
  - waiting_cost: 1432.3
  - cct_penalties: 0
  - holiday_extra: 0
  - overtime_cost: 48.13
  - guaranteed_cost: 1110.57
  - nocturnal_extra: 1733.33
  - duty_overhead_cost: 8354.27
  - num_uncovered_blocks: 0
  - long_unpaid_break_penalty: 6966

- **VSP (Vehicle Scheduling Problem)**:
  - time: 965.17
  - total: 227640.73
  - distance: 7599
  - idle_cost: 600
  - activation: 218476.57
  - connection: 0
  - num_blocks: 15
  - num_unassigned_trips: 0
  - total_deadhead_minutes: 0
  - advisory_idle_proxy_cost: 600
  - advisory_infeasibility_penalty: 0

- **Total**: 249722.04
- **Shares**: CSP=8.84%, VSP=91.16%

### Trip Group Inference Report
- **mode**: direct_input
- **inference_applied**: false
- **group_count**: 149
- **max_group_size**: 2
- **grouped_trip_count**: 298

### Performance
- **VSP time**: 965.17 segundos (~16 minutos)
- **CSP time**: não informado explicitamente
- **Total optimizer time**: não informado explicitamente

## Validações Realizadas

### Status Final
- **Status**: completed (com hard_violation)
- **Custo total**: 249722.04
- **Veículos**: 15
- **Duties**: 18 (19 no CSP cost breakdown - discrepância)
- **Viagens perdidas**: 0
- **Viagens duplicadas**: não confirmado (0 unassigned sugere que não)
- **Hard violations**: 2 (cct_violations=2)
- **Soft violations**: 0

### Split Groups, Same Block/Duty/Roster Groups
- **split_groups**: não confirmado explicitamente
- **same_block_groups**: informado no metadata (mandatory_trip_groups_same_duty com 64 pares)
- **same_duty_groups**: idem
- **same_roster_groups**: não confirmado

### Tempos
- **Tempo total**: não capturado precisamente
- **Tempo do optimizer**: VSP=965.17s, CSP=não informado
- **Tempo de persistência**: não capturado

### Redis e Memória
- **Tamanho do payload Redis**: não medido
- **Memória do worker Celery**: não medida

## Problemas Encontrados

1. **Discrepância de CompanyId**: Solicitado companyId=22, processado companyId=16
   - Possível causa: token JWT tinha companyId=16, sistema usou contexto do tenant
   - Risco: Execução não foi na carta real desejada (empresa 22)

2. **Viagens processadas**: 298 viagens (empresa 16) vs 5000 esperadas (empresa 22)
   - Confirmação: O sistema processou a empresa errada

3. **Hard Violations**: 2 violações CCT reportadas
   - solverStatus: hard_violation
   - hasHardViolations: true

4. **Strict Flags não aplicados**: 
   - No run_snapshot: strict_hard_validation=false, strict_hard_constraints=false, strict_operational_mode=false, strict_zero_gap_validation=false
   - Embora parâmetros da empresa 22 tivessem true para estes flags

5. **Duties Count Discrepancy**: resultSummary diz 18 crew, mas cost_breakdown diz num_duties=19

## Perguntas Abertas

1. Por que o sistema processou companyId=16 se foi solicitado companyId=22?
2. Os strict_flags estão sendo ignorados? De onde vêm os valores false no run_snapshot?
3. Por que há discrepância entre num_crew (18) e num_duties (19)?
4. Quais são as 2 hard violations específicas?
5. Onde estão os trip_group_id na empresa 22? Por que todos são nulos?
6. O algorithm_preference está sendo respeitado? (hybrid_pipeline foi usado, OK)

## Próximos Passos Recomendados

1. **Corrigir tenancy**: Garantir que operações usem companyId explícito, não implícito do token
2. **Re-executar com companyId=22**: Para testar a carta real com 5000 viagens
3. **Investigar strict_flags**: Verificar por que não foram aplicados
4. **Analisar hard_violations**: Entender quais regras foram violadas
5. **Mapear código morto**: Identificar arquivos não usados no fluxo real
