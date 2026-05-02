# FASE 1: Action Plan - MVP+1 Edition
**Objetivo:** De 40-50% para 65-70% (Optibus competitive)  
**Duração:** 6 semanas (4 cores)  
**Resultado:** Dashboard + Multi-depot + Vehicle Types

---

## 📋 O Que Implementar

### Semana 1-2: Foundation (Multi-depot + Vehicle Types)

#### 1.1 Multi-Depot Support
**O que é:** Sistema de garagens/depots múltiplos
**Por que:** 80% dos clientes têm múltiplos depots
**Impacto:** +50% potencial de mercado

**Tarefas:**
```
1.1.1 Database Schema
  [ ] Adicionar tabela 'depots' (id, name, location, city)
  [ ] Adicionar 'depot_id' a vehicles
  [ ] Adicionar 'origin_terminal_id' a trips
  Esforço: 4 horas

1.1.2 Python Backend
  [ ] Modificar solver para respeitar depot_id
  [ ] Calcular deadhead ENTRE depots (distância real)
  [ ] Validar que veículo sempre volta ao seu depot
  [ ] Testar com Company 16 (múltiplos terminals)
  Esforço: 20 horas

1.1.3 API Backend
  [ ] POST /api/v1/depots (CRUD)
  [ ] Modificar blocks para incluir depot_id
  [ ] Validação: trip.origin_depot = vehicle.depot
  Esforço: 10 horas

1.1.4 Testes
  [ ] 5+ testes de multi-depot
  [ ] Teste com dados reais (2+ depots)
  [ ] Performance test (overhead do multi-depot)
  Esforço: 8 horas

Total Semana 1-2.1: ~42 horas = 1 semana (1 dev)
```

#### 1.2 Vehicle Types
**O que é:** Diferentes tipos de veículos (ônibus, van, micro)
**Por que:** Otimiza custos reais (ônibus caro para 10 pessoas)
**Impacto:** +20-30% ROI

**Tarefas:**
```
1.2.1 Database Schema
  [ ] Tabela 'vehicle_types' (id, name, capacity, cost_per_day, accessible)
  [ ] Adicionar 'type_id' a vehicles
  Esforço: 2 horas

1.2.2 Python Backend
  [ ] Modificar cost calculation para usar vehicle_type.cost
  [ ] Validar capacidade: sum(trips) <= vehicle.capacity
  [ ] Priorizar veículos menores quando possível
  Esforço: 16 horas

1.2.3 API Backend
  [ ] POST /api/v1/vehicle-types (CRUD)
  [ ] Modificar vehicle creation para incluir type
  Esforço: 6 horas

1.2.4 Testes
  [ ] 5+ testes de vehicle types
  [ ] Teste de otimização de custos
  Esforço: 6 horas

Total Semana 1-2.2: ~30 horas = 0.75 semana (1 dev)
```

**Semana 1-2 Total: ~70 horas = 1.75 semanas (1 dev) ou 3-4 dias (2 devs em paralelo)**

---

### Semana 3-4: Interface (Dashboard Básico)

#### 2.1 React Dashboard Component
**Stack:** React + Next.js + TailwindCSS + Chart.js

**Tarefas:**
```
2.1.1 Setup
  [ ] npx create-next-app (ou usar existente)
  [ ] Adicionar Tailwind, Chart.js
  [ ] Setup autenticação (reusar backend)
  Esforço: 4 horas

2.1.2 Layout Básico
  [ ] Header com logo OTIMIZ
  [ ] Sidebar com menu
  [ ] Stats box: vehicles, duties, coverage%, errors
  Esforço: 6 horas

2.1.3 Visualization de Blocos
  [ ] Tabela com todos os blocos
  [ ] Cada linha = 1 veículo
  [ ] Mostrar trips em ordem temporal
  [ ] Cores para tipo de veículo
  Esforço: 12 horas

2.1.4 Gráficos & KPIs
  [ ] Gráfico de utilização por veículo
  [ ] Gráfico de cobertura
  [ ] KPI cards: custos, horas, velocidade
  Esforço: 8 horas

2.1.5 Integração com Backend
  [ ] API calls para carregar dados
  [ ] Upload de CSV/arquivo
  [ ] Run optimization button
  [ ] Mostrar resultado em tempo real
  Esforço: 10 horas

2.1.6 Testes
  [ ] Testes de UI (React Testing Library)
  [ ] Testes E2E (Cypress ou Playwright)
  Esforço: 8 horas

Total Semana 3-4: ~48 horas = 1.2 semanas (1 frontend dev)
```

---

### Semana 4-5: Integração e Refinamento

#### 3.1 Edição Manual (MVP)
```
3.1.1 Drag & Drop de Trips
  [ ] Permitir arrastar trip entre veículos
  [ ] Atualizar em tempo real no backend
  [ ] Validar se alocação fica válida
  [ ] Mostrar erro se inválido
  Esforço: 16 horas

3.1.2 Reordenação de Trips
  [ ] Dentro mesmo veículo: reorder trips
  [ ] Atualizar cálculo de deadhead
  [ ] Visualizar impacto em custos
  Esforço: 8 horas

Total Semana 4-5: ~24 horas = 0.6 semana (1 frontend dev)
```

#### 3.2 QA & Refinement
```
3.2.1 Testes com Dados Reais
  [ ] Testar com Company 16 (298 trips)
  [ ] Testar com múltiplos depots
  [ ] Testar com múltiplos vehicle types
  Esforço: 12 horas

3.2.2 Performance Optimization
  [ ] Medir tempo de carregamento
  [ ] Otimizar API calls
  [ ] Lazy loading de componentes
  Esforço: 8 horas

3.2.3 UX Refinement
  [ ] Feedback visual
  [ ] Mensagens de erro claras
  [ ] Documentação in-app
  Esforço: 10 horas

Total Semana 4-5: ~30 horas = 0.75 semana (1 dev)
```

---

## 📊 Timeline Visual

```
SEMANA 1-2 (Backend)
├─ Multi-depot Implementation
│  ├─ DB schema [████░░] 2h
│  ├─ Python solver [████████░░] 20h
│  └─ API + tests [████░░] 18h
│
├─ Vehicle Types Implementation  
│  ├─ DB schema [██░░] 2h
│  ├─ Cost calculation [████████░░] 16h
│  └─ API + tests [████░░] 12h
│
└─ TOTAL: ~70h (em paralelo: 3-4 dias com 2 devs)

SEMANA 3-4 (Frontend)
├─ Dashboard Setup [██░░] 4h
├─ Layout & Components [████░░] 18h
├─ Charts & KPIs [██████░░] 16h
├─ Backend Integration [██████░░] 10h
├─ Testing [██████░░] 8h
│
└─ TOTAL: ~56h (1 frontend dev em 1.4 semanas)

SEMANA 5-6 (Integration & QA)
├─ Drag & Drop [████████░░] 16h
├─ Real Data Testing [████░░] 12h
├─ Performance Tuning [████░░] 8h
├─ UX Refinement [████░░] 10h
│
└─ TOTAL: ~46h (1-2 devs em 0.5-1 semana)

═══════════════════════════════════════════
TOTAL FASE 1: ~170 horas
TEMPO REAL: 6 semanas (4 devs core) ou 12 semanas (1 dev)
RECOMENDADO: 6 semanas com 2-3 devs (1 backend, 1 frontend, 1 QA/integração)
```

---

## 🎯 Milestones & Sign-offs

### Semana 1 (End-of-week)
- [ ] Multi-depot database schema pronto
- [ ] First test passing: can create depot
- [ ] Sign-off: Technical lead

### Semana 2 (End-of-week)
- [ ] Multi-depot + Vehicle Types fully implemented
- [ ] 15+ tests passing
- [ ] Real data test: Company 16 loads correctly
- [ ] Sign-off: QA lead

### Semana 3 (End-of-week)
- [ ] Dashboard layout complete
- [ ] Can upload CSV and display results
- [ ] Charts working
- [ ] Sign-off: Product owner

### Semana 4 (End-of-week)
- [ ] Dashboard fully integrated with backend
- [ ] Drag & drop working
- [ ] E2E test passing
- [ ] Sign-off: QA lead

### Semana 5 (End-of-week)
- [ ] QA on real data complete
- [ ] Performance acceptable
- [ ] All tests green
- [ ] Sign-off: Technical lead

### Semana 6 (End-of-week)
- [ ] Customer pilot ready
- [ ] Documentation complete
- [ ] Demo prepared
- [ ] Sign-off: Product owner
- 🎉 **LAUNCH MVP+1**

---

## 👥 Team Required

### Option A: Ideal (3 people, 6 weeks)
```
1 Backend Developer
  - Multi-depot implementation
  - Vehicle types integration
  - API endpoints
  - Backend testing
  - Time: Full-time, weeks 1-2.5, then 50% weeks 3-5

1 Frontend Developer
  - Dashboard UI
  - Charts/visualization
  - Drag & drop
  - Integration tests
  - Time: Full-time, weeks 3-5, then 50% week 6

1 QA Engineer
  - Test planning
  - Real data testing
  - Performance testing
  - UAT coordination
  - Time: 50% weeks 1-2, then full-time weeks 3-6
```

### Option B: Lean (2 people, 9-10 weeks)
```
1 Full-stack Developer
  - Everything backend
  - Basic UI setup
  - Integration
  - Time: Full-time

1 Frontend Developer
  - UI implementation
  - Refinements
  - Testing
  - Time: Full-time, weeks 3-6
```

### Option C: Solo (1 person, 12 weeks)
```
1 Developer
  - Backend first 2 weeks
  - Frontend next 2 weeks
  - Integration 1 week
  - Polish 1 week
  - Time: Full-time, 12 weeks (não recomendado)
```

---

## 🔧 Tech Stack Confirmado

### Backend (Existing - keep)
- NestJS (TypeScript)
- PostgreSQL
- Python optimizer (via subprocess)

### Frontend (New for Dashboard)
- Next.js 14+
- React 18+
- TailwindCSS
- Chart.js or Recharts
- React DnD (drag & drop)

### Deployment
- Same as MVP (Docker container)
- Environment: production-ready

---

## 📈 Expected Results

### By End of Phase 1 (6 weeks):

```
Feature Coverage:        50% ➜ 70% (+40%)
Optimization Quality:    80% ➜ 85% (+6%)
UX/Interface:            10% ➜ 60% (+600%)
Performance:             70% ➜ 75% (+7%)
Intelligence:             0% ➜  0% (deferred)
───────────────────────────────────────
TOTAL:                  40% ➜ 70% (+75%)

vs Optibus:             40% ➜ 70%
```

### Market Impact:

```
Before MVP+1:
  - Vendável apenas para: Startups, pilotos
  - Max clientes: ~20
  - TAM (Total Addressable Market): 10%

After MVP+1:
  - Vendável para: PMEs + alguns grandes
  - Max clientes: ~150
  - TAM: 60%
```

---

## 💰 Business Case

### Investment: 6 weeks × 3 devs × $4000/week = ~$72,000

### Return:
- MVP clients already paying (pipeline)
- MVP+1: +3-5x pricing possible
- ROI breakeven: 2-3 months

---

## ⚠️ Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Backend changes break existing | Medium | High | Comprehensive test suite |
| Frontend takes longer | Medium | High | Use component library |
| Real data integration issues | Low | High | Start week 1 with test data |
| Performance degradation | Low | Medium | Profile early and often |
| Scope creep | High | High | Strict scope lock for MVP+1 |

---

## 🚀 Getting Started (Today)

### Step 1: Approve Plan
- [ ] Product owner reviews
- [ ] Technical lead confirms feasibility
- [ ] Team available for weeks 1-6

### Step 2: Setup
- [ ] Create GitHub project with milestones
- [ ] Setup CI/CD pipeline if not done
- [ ] Brief team on plan

### Step 3: Day 1 (Monday Week 1)
- [ ] Backend dev: Start multi-depot schema
- [ ] Frontend dev: Setup Next.js + Tailwind
- [ ] QA: Test plan + data preparation

---

## 📞 Weekly Sync

Every Monday:
- What was completed
- What's blocked
- Updated timeline
- Decisions needed

---

## Success = This

**Week 6 Demo:**
```
[Opens dashboard]
"Aqui está o OTIMIZ MVP+1. Vamos otimizar?"

[Uploads CSV com Company 16 data]
[Sistema rodar otimização]
[Dashboard mostra:
  - 17 veículos necessários
  - R$8,872 custo/dia
  - 98% cobertura
  - Zero erros críticos
]

[Arrasta uma trip para outro veículo]
[Custos atualizam em tempo real]

"E aqui você pode editar manualmente.
Pronto para competir com Optibus? ✅"
```

---

**Timeline:** 6 semanas  
**Team:** 2-3 pessoas  
**Investment:** ~$70K  
**Return:** 3-5x em pricing, +60% TAM  

**Vamos começar segunda-feira? 🚀**
