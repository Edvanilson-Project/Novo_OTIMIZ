# Análise de Pastas/Arquivos - Fluxo Real vs Não Utilizados

## Com base na execução real (Schedule 377, Company 16, 298 viagens, hybrid_pipeline)

### PASTAS/ARQUIVOS ESSENCIAIS (exercitados na execução)

#### Backend (NestJS)
1. **backend/src/modules/operations/optimization.service.ts** - CORE: dispara otimização, constrói payload
2. **backend/src/modules/operations/optimization.gateway.ts** - WebSocket para updates (não confirmado uso)
3. **backend/src/modules/database/entities/*.entity.ts** - Entidades: Trip, Schedule, CompanyParameters, DutyAssignment, BlockAssignment
4. **backend/src/modules/database/repositories/*.repository.ts** - Acesso a dados
5. **backend/src/modules/parameters/parameters.service.ts** - Provável uso na construção de params (não confirmado diretamente)

#### Optimizer (FastAPI)
1. **optimizer/main.py** - Entry point, endpoints /optimize, /health
2. **optimizer/src/core/celery_app.py** - Configuração Celery
3. **optimizer/src/services/optimizer_tasks.py** - Task Celery que executa otimização
4. **optimizer/src/services/optimizer_service.py** - Serviço principal do solver
5. **optimizer/src/api/routes/optimize.py** - Rotas de otimização (não confirmado, mas implícito)
6. **optimizer/src/domain/models.py** - Modelos Trip, VehicleType, etc.

#### Infraestrutura
1. **docker-compose.yml** - Orquestração postgres, redis, backend
2. **backend/Dockerfile** - Build do backend
3. **optimizer/Dockerfile** - Build do optimizer
4. **optimizer/start.sh** - Startup script (Celery + uvicorn)

### PASTAS/ARQUIVOS NÃO EXERCITADOS (nesta execução)

#### Backend
1. **backend/src/modules/operations/optimization.service.spec.ts** - Testes unitários (não em execução real)
2. **backend/src/modules/auth/** - Autenticação usada, mas não testada a fundo nesta execução
3. **backend/src/modules/reports/** - Não usado na execução
4. **backend/src/modules/audit/** - Audit interceptor presente, mas não confirmado logging nesta execução
5. **backend/src/modules/users/, /companies, /lines, /terminals** - Não exercitados diretamente nesta chamada

#### Optimizer
1. **optimizer/tests/** - Toda pasta de testes (unit, integration, stress) - NÃO USADA
2. **optimizer/src/api/routes/strategy.py, whatif.py, rostering.py** - Rotas não acionadas
3. **optimizer/src/algorithms/** - Algoritmos alternativos (greedy, genetic, etc.) não usados (apenas hybrid_pipeline)
4. **optimizer/src/services/strategy_*.py** - Serviços de estratégia não confirmados nesta execução
5. **optimizer/exhaustive_operational_test.py, exhaustive_parameter_test.py** - Scripts de teste não usados
6. **optimizer/fallback_verification.py** - Não usado

#### Scripts e Outros
1. **scripts/** - Scripts auxiliares não usados
2. **frontend/** - Não exercitado (apenas backend/optimizer)
3. **.aider.*.md** - Histórico de chat, não código
4. **project_audit.md** - Documentação, não código executável
5. **test_params.py, traceback_*.log** - Arquivos de teste/debug não usados

### FUNCIONALIDADES EXISTENTES MAS NÃO EXERCITADAS

1. **Algoritmos alternativos**: greedy, genetic, simulated_annealing, tabu_search, set_partitioning, joint_solver (apenas hybrid_pipeline usado)
2. **What-if analysis**: Endpoint /whatif não acionado
3. **Rostering**: Endpoint /rostering não usado
4. **Strategy service**: Serviço de estratégia não confirmado se usado
5. **Column Generation**: Enable mencionado nos params, mas não confirmado se efetivamente usado
6. **Multi-line blocks**: allow_multi_line_block=true mas apenas 1 linha na empresa 16
7. **Relief points**: allow_relief_points=false nos params
8. **Electric vehicles**: Nenhum vehicle_type elétrico usado

### PONTOS DE MAIOR RISCO DE CÓDIGO MORTO OU REDUNDANTE

1. **Pasta optimizer/tests/**: Grande volume de testes (unit, integration, stress) que podem estar desatualizados
2. **Múltiplos algoritmos**: 6 algoritmos implementados, mas apenas 1 usado na execução
3. **Rotas não usadas**: strategy, whatif, rostering podem ser código morto ou funcionalidades futuras
4. **fallback_verification.py**: Script específico que pode ser código temporário
5. **test_celery_rules.py, test_mega_qa.py**: Scripts de teste na raiz do optimizer
6. **Backend audit module**: Interceptor presente, mas não confirmado se ativo
7. **operator_change_terminals_only, reduced_weekly_rest**: Parâmetros não exercitados

### OBSERVAÇÕES DE TENANCY
- **Problema identificado**: CompanyId solicitado (22) ≠ processado (16)
- **Causa provável**: JWT token tinha companyId=16, sistema usou TenantContext implícito
- **Risco**: Execuções podem não ser na empresa correta se houver confusão de contexto

### RECOMENDAÇÃO DE LIMPEZA (apenas diagnóstico, não executar agora)

1. **Validar Tenancy**: Garantir que companyId vem do parâmetro, não do token quando especificado
2. **Remover ou atualizar testes desatualizados**: Se não passam, estão gerando confusão
3. **Verificar rotas não usadas**: Se não são usadas no frontend ou via API, podem ser removidas
4. **Simplificar algoritmos**: Se apenas hybrid_pipeline é usado em produção, considerar modularização
5. **Audit se todos os parâmetros são necessários**: Muitos parâmetros no company_parameters não foram exercitados
