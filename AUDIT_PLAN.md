# Plano de Auditoria: Backend + Frontend
## Análise Completa de Funcionalidades, Parâmetros e CRUDs

---

## 🎯 OBJETIVO
Verificar se todas as funcionalidades estão corretas, sem dados mockados, 
com parâmetros corretos e CRUDs bem implementados.

---

## 📋 ESTRUTURA DE ANÁLISE

### MÓDULO 1: AUTENTICAÇÃO & TENANCY
**Backend Controllers:**
- AuthController (login, logout, register)
- TenantContext (company_id isolation)

**O que verificar:**
- [ ] Login retorna token válido
- [ ] Logout invalida session
- [ ] Company ID é verificado em todos endpoints
- [ ] Sem acesso cross-company
- [ ] Passwords são hashed (bcrypt)

**Frontend:**
- [ ] Login form funciona
- [ ] Token é armazenado (localStorage/sessionStorage)
- [ ] Token é enviado em headers
- [ ] Logout limpa o token
- [ ] Redirect após login

---

### MÓDULO 2: OPERAÇÕES (Optimization)
**Backend Controllers/Services:**
- OptimizationService.runOptimization()
- OptimizationService.pollOptimizerTask()
- OptimizationService.persistResults()
- OptimizationService.getLatestSchedule()

**Funcionalidades:**
1. Iniciar Otimização
   - [ ] Recebe companyId, parâmetros
   - [ ] Valida trips (mínimo X viagens)
   - [ ] Envia para optimizer
   - [ ] Retorna schedule_id
   - [ ] Não mockado

2. Monitorar Progresso
   - [ ] Polling status do Celery
   - [ ] Atualiza status em DB
   - [ ] WebSocket notificações
   - [ ] Timeout handling

3. Persistir Resultados
   - [ ] Salva blocks (veículos)
   - [ ] Salva duties (motoristas)
   - [ ] Salva assignments
   - [ ] Metadados completos
   - [ ] Cost calculado corretamente

4. Obter Latest Schedule
   - [ ] Retorna dados do DB
   - [ ] Não mockado
   - [ ] Todas propriedades presentes
   - [ ] Duties com segments

**Parâmetros críticos:**
- [ ] algorithm_preference (hybrid, csp, vsp)
- [ ] operational_quality_mode
- [ ] min_break_minutes
- [ ] meal_break_minutes
- [ ] max_shift_minutes
- [ ] pullout_minutes / pullback_minutes
- [ ] allow_vehicle_swap
- [ ] allow_multi_line_block

---

### MÓDULO 3: PARÂMETROS
**Backend Controller:**
- ParametersController (CRUD de parâmetros)

**CRUDs:**
1. CREATE
   - [ ] POST /api/v1/parameters (new company)
   - [ ] Default values preenchidos
   - [ ] Validação de ranges
   - [ ] Persiste em BD

2. READ
   - [ ] GET /api/v1/parameters (by company)
   - [ ] Retorna último salvo
   - [ ] Não mockado

3. UPDATE
   - [ ] PUT /api/v1/parameters
   - [ ] Valida cada parametro
   - [ ] Não permite valores inválidos
   - [ ] Audit log atualizado

4. DELETE
   - [ ] Não deveria ser permido (soft delete)
   - [ ] Reset to defaults (opção)

---

### MÓDULO 4: USUÁRIOS
**Backend Controller:**
- UsersController (CRUD users)

**CRUDs:**
1. CREATE
   - [ ] POST /api/v1/users
   - [ ] Email único (validação)
   - [ ] Password hashed
   - [ ] Company ID associado

2. READ
   - [ ] GET /api/v1/users (list)
   - [ ] GET /api/v1/users/:id
   - [ ] Filter by company

3. UPDATE
   - [ ] PUT /api/v1/users/:id
   - [ ] Password change se necessário
   - [ ] Email change validation

4. DELETE
   - [ ] DELETE /api/v1/users/:id
   - [ ] Soft delete (is_active = false)
   - [ ] Schedules não deletados

---

### MÓDULO 5: EMPRESAS
**Backend Controller:**
- CompaniesController (CRUD companies)

**CRUDs:**
1. CREATE
   - [ ] POST /api/v1/companies
   - [ ] Gera ID único
   - [ ] Cria parâmetros padrão
   - [ ] Cria usuário admin

2. READ
   - [ ] GET /api/v1/companies/:id
   - [ ] Retorna com parâmetros

3. UPDATE
   - [ ] PUT /api/v1/companies/:id
   - [ ] Valida mudanças

4. DELETE
   - [ ] Soft delete

---

### MÓDULO 6: VIAGENS
**Backend Controller:**
- TripsController (CRUD trips)

**CRUDs:**
1. CREATE
   - [ ] POST /api/v1/trips (import CSV)
   - [ ] Valida campos obrigatórios
   - [ ] Pareia ida/volta (trip_group_id)
   - [ ] Calcula distância se necessário

2. READ
   - [ ] GET /api/v1/trips (list)
   - [ ] GET /api/v1/trips/:id
   - [ ] Filter by company
   - [ ] Não mockado

3. UPDATE
   - [ ] PUT /api/v1/trips/:id
   - [ ] Valida mudanças

4. DELETE
   - [ ] DELETE /api/v1/trips/:id

---

### MÓDULO 7: SCHEDULES (Resultados)
**Backend Controller:**
- SchedulesController

**CRUDs:**
1. CREATE
   - [ ] Automático ao rodar optimization
   - [ ] Status: PROCESSING

2. READ
   - [ ] GET /api/v1/schedules (list)
   - [ ] GET /api/v1/operations/latest-schedule
   - [ ] Retorna duties com segments
   - [ ] Metadados completos

3. UPDATE
   - [ ] Automático durante persistência
   - [ ] Status: COMPLETED/FAILED

4. DELETE
   - [ ] Soft delete (manter histórico)

---

### MÓDULO 8: RELATÓRIOS
**Backend Controller:**
- ReportsController

**Funcionalidades:**
1. KPIs Report
   - [ ] GET /api/v1/reports/kpis
   - [ ] Retorna métricas calculadas
   - [ ] Não mockado

2. Comparison Report
   - [ ] GET /api/v1/reports/compare
   - [ ] Compara dois schedules
   - [ ] Diferenças de custo, duties, etc

3. History Report
   - [ ] GET /api/v1/reports/history
   - [ ] Lista otimizações anteriores

---

## 🎨 FRONTEND ANALYSIS

### PÁGINA 1: Login
**Componentes:**
- LoginForm
- AuthGuard

**Funcionalidades:**
- [ ] Form validation (email, password)
- [ ] Submit chama /auth/login
- [ ] Token armazenado
- [ ] Redirect para /operations/planner

---

### PÁGINA 2: Operations Planner
**Componentes:**
- TabGantt (Gantt chart)
- TabList (Lista de viagens)
- AiCostDrawer (Copilot IA)

**Funcionalidades:**
1. Listar Viagens
   - [ ] Busca de /api/v1/operations/latest-schedule
   - [ ] Não mockado
   - [ ] Mostra todas viagens

2. Gantt Chart
   - [ ] Timeline visual
   - [ ] Agrupado por duty/vehicle
   - [ ] Cores por linha

3. Copilot IA
   - [ ] Chat com IA
   - [ ] Sugestões de otimização

4. Exportar CSV
   - [ ] Download programacao_operacional.csv
   - [ ] Download viagens_detalhadas.csv
   - [ ] Download motoristas.csv

---

### PÁGINA 3: Settings - Parameters
**Componentes:**
- ParameterForm

**Funcionalidades:**
1. Listar Parâmetros
   - [ ] GET /api/v1/parameters
   - [ ] Mostra valores atuais

2. Editar Parâmetros
   - [ ] Form com validation
   - [ ] PUT /api/v1/parameters
   - [ ] Salva no BD

3. Parâmetros Mostrados
   - [ ] algorithm_preference
   - [ ] operational_quality_mode
   - [ ] min_break_minutes
   - [ ] meal_break_minutes
   - [ ] max_shift_minutes
   - [ ] pullout_minutes
   - [ ] pullback_minutes
   - [ ] allow_vehicle_swap
   - [ ] allow_multi_line_block

---

## 🔍 VERIFICAÇÕES CRÍTICAS

### 1. Fluxo de Parâmetros
```
Frontend Form 
  → PUT /api/v1/parameters
  → ParametersService.updateParameters()
  → DB salva
  → Próxima otimização usa novos valores
```
- [ ] Verificar se está tudo conectado

### 2. Fluxo de Otimização
```
Frontend clica "Optimize"
  → POST /api/v1/operations/optimize
  → OptimizationService.runOptimization()
  → Envia para Optimizer (FastAPI)
  → Celery processa
  → persistResults() salva em BD
  → getLatestSchedule() retorna ao frontend
```
- [ ] Verificar cada passo

### 3. Fluxo de Dados (Sem Mock)
- [ ] Viagens vêm do BD (não hardcoded)
- [ ] Parâmetros vêm do BD (não hardcoded)
- [ ] Results vêm do Optimizer (não fake)
- [ ] Schedules vêm do BD (não mock)

### 4. Validações
- [ ] Email validation em backend
- [ ] Company ID validation em todos endpoints
- [ ] Parameter ranges validation
- [ ] Trip data validation
- [ ] Input sanitization

---

## 🐛 BUGS A PROCURAR

### Categoria 1: Null/Undefined
- [ ] duty_time_segments null quando não deveria
- [ ] operational_time_report missing
- [ ] quality_metrics undefined
- [ ] metadata vazio

### Categoria 2: Type Mismatch
- [ ] String vs Number em timestamps
- [ ] Boolean vs String em flags
- [ ] Array vs Object em results

### Categoria 3: State Inconsistency
- [ ] Schedule status PROCESSING mas resultado já existe
- [ ] Duties sem assignments
- [ ] Blocks sem trips

### Categoria 4: Cross-Company Data Leak
- [ ] User de company A vê data de company B
- [ ] Schedules shared entre companies
- [ ] Parameters overwritten entre companies

### Categoria 5: Missing Data
- [ ] CSV exporta menos viagens que input
- [ ] Duties sem motoristas
- [ ] Blocos sem custos

---

## 📊 MÉTODO DE ANÁLISE

### Fase 1: Code Review (4h)
- Ler controllers
- Ler services
- Ler models
- Identificar riscos

### Fase 2: Test Execution (2h)
- Rodar E2E tests
- Rodar unit tests
- Verificar coverage

### Fase 3: Manual Testing (4h)
- Fazer login
- Rodar otimização
- Editar parâmetros
- Exportar CSVs
- Verificar dados

### Fase 4: Static Analysis (2h)
- ESLint/Pylint
- Type checking
- Security scan

### Fase 5: Report (2h)
- Compilar findings
- Priorizar bugs
- Recomendar fixes

---

## 🎯 SAÍDA ESPERADA

**Relatório com:**
1. Status de cada CRUD
2. Lista de funcionalidades verificadas
3. Bugs encontrados (com severidade)
4. Dados mockados (se houver)
5. Parâmetros mal configurados
6. Inconsistências
7. Recomendações

