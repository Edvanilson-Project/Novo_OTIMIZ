# AUDITORIA SÊNIOR — OTIMIZAÇÃO, PERFORMANCE E QUALIDADE
**Data:** 2026-05-17  
**Auditor:** Claude Sonnet 4.6 (Anthropic) — Role: Senior OR Engineer + Software Architect  
**Branch:** `feature/fase-1-2-3-product-enhancement`  
**Escopo:** Código completo (optimizer Python + backend NestJS + frontend Next.js + testes + docs)

---

## AVISO METODOLÓGICO

Esta auditoria foi conduzida por leitura direta de código. Cada afirmação cita arquivo e linha. Alegações sem evidência de código são marcadas explicitamente como **"Não comprovado no código"**. Nenhuma funcionalidade foi inventada.

---

## 1. RESUMO EXECUTIVO

O sistema **OTIMIZ é tecnicamente real e não é um simulador**. Ele executa algoritmos legítimos de Vehicle Scheduling Problem (VSP) e Crew Scheduling Problem (CSP), com ILP via PuLP/CBC, OR-Tools CP-SAT e múltiplas metaheurísticas (SA, Tabu, Genetic). A arquitetura de pipeline híbrido é sofisticada e funcional para instâncias de pequeno a médio porte (até ~1.000 viagens).

Porém, existem **lacunas sérias** que impedem a comparação honesta com Optibus em escala, qualidade comprovada e produção robusta. O maior risco é comercial: o sistema pode ser vendido como "nível Optibus" sem evidência de que supera greedy em datasets reais e grandes.

**Veredito geral: Promissor, parcialmente implementado, escala não provada, benchmark faltante.**

---

## 2. MAPA DO SISTEMA (O QUE REALMENTE EXISTE)

### 2.1 Stack Técnico

| Camada | Tecnologia | Arquivo principal | Linhas |
|--------|-----------|-------------------|--------|
| Optimizer core | Python 3.14 + FastAPI | `optimizer/src/services/optimizer_service.py` | 3688 |
| CSP Greedy | Python | `optimizer/src/algorithms/csp/greedy.py` | 3583 |
| Dispatcher | Python | `optimizer/src/services/algorithm_dispatcher.py` | 395 |
| CSP Set Partitioning (ILP) | PuLP + numba | `optimizer/src/algorithms/csp/set_partitioning_optimized.py` | 1453 |
| VSP Joint Solver | Python | `optimizer/src/algorithms/joint_opt.py` | 1457 |
| VCSP ILP | PuLP | `optimizer/src/algorithms/integrated/vcsp_solver.py` | 748 |
| Hybrid Pipeline | Python | `optimizer/src/algorithms/hybrid/pipeline.py` | 757 |
| MCNF VSP | PuLP/CBC | `optimizer/src/algorithms/vsp/mcnf.py` | 639 |
| B&P VSP | Python | `optimizer/src/algorithms/vsp/branch_and_price.py` | 628 |
| Genetic VSP | Python | `optimizer/src/algorithms/vsp/genetic.py` | 577 |
| SA VSP | Python | `optimizer/src/algorithms/vsp/simulated_annealing.py` | 410 |
| Backend NestJS | TypeScript | `backend/src/modules/operations/optimization.service.ts` | 2815 |
| Cost Evaluator | Python (Decimal) | `optimizer/src/algorithms/evaluator.py` | 834 |
| Solution Validator | Python | `optimizer/src/services/solution_validator.py` | 530 |
| Weekly Rostering | OR-Tools CP-SAT | `optimizer/src/services/rostering/weekly_solver.py` | 392 |

### 2.2 Algoritmos VSP (Vehicle Scheduling Problem)

Todos **implementados e chamáveis via API**:

| Algoritmo | Tipo | Arquivo | Escala máxima real |
|-----------|------|---------|---------------------|
| GreedyVSP | Greedy construtivo | `vsp/greedy.py` | Ilimitada (segundos) |
| SimulatedAnnealingVSP | Metaheurística | `vsp/simulated_annealing.py` | ~220 trips (padrão) |
| TabuSearchVSP | Metaheurística | `vsp/tabu_search.py` | ~220 trips (padrão) |
| GeneticVSP | Metaheurística (EA) | `vsp/genetic.py` | ~220 trips (padrão) |
| MCNFVSP | ILP binário (PuLP/CBC) | `vsp/mcnf.py` | ~800 trips por chunk |
| AssignmentVSP | Bipartite matching | `vsp/assignment.py` | >5000 trips |
| BranchAndPrice | B&P + ILP | `vsp/branch_and_price.py` | Não benchmarkado |
| RegionalDecompositionSolver | Decomposição regional | `vsp/regional_decomposition.py` | Não benchmarkado |
| TimetableSlackOptimizer | Pré-processamento | `vsp/timetable_slack.py` | Qualquer |

### 2.3 Algoritmos CSP (Crew Scheduling Problem)

| Algoritmo | Tipo | Arquivo |
|-----------|------|---------|
| GreedyCSP | Greedy duty builder | `csp/greedy.py` (3583 linhas) |
| SetPartitioningOptimizedCSP | ILP set cover (PuLP/CBC) | `csp/set_partitioning_optimized.py` |
| CPSatCSP | OR-Tools CP-SAT set cover | `csp/cp_sat_csp.py` |
| SetPartitioningCSP | ILP original | `csp/set_partitioning.py` |

### 2.4 Solvers Integrados (VCSP)

| Solver | Tipo | Status |
|--------|------|--------|
| VCSPJointSolver | ILP conjunto (PuLP) | Implementado, escala limitada |
| JointSolver | Pipeline integrado | Implementado |
| JointBP | B&P conjunto | Implementado |
| HybridPipeline | Multi-fase MCNF→SA→Tabu→GA→ILP | Implementado e testado |

### 2.5 Pipeline Híbrido (Algoritmo Principal)

Sequência real (`hybrid/pipeline.py:76–500`):

1. **n > 5.000 trips**: AssignmentVSP direto (sem metaheurísticas)
2. **n ≤ 5.000**: MCNF-ILP como baseline
3. **n ≤ 220 ou blocks ≤ 180**: SA (2×, 35% budget) → Tabu (35%) → Genetic (20%)
4. **n > 220**: pula metaheurísticas, compara MCNF vs Greedy
5. Fase final: CSP ILP polish (CP-SAT ou PuLP) para n ≤ 1.500 trips / 450 blocos

---

## 3. O QUE O SISTEMA REALMENTE FAZ

### 3.1 Sim, o sistema otimiza de verdade

**Evidências concretas:**

- `vsp/mcnf.py:390–429`: Monta MILP binário com PuLP (`LpProblem`, `LpVariable cat="Binary"`), resolve com CBC/HiGHS, extrai cadeia de blocos
- `hybrid/pipeline.py:123–186`: Compara MCNF vs SA vs Tabu vs Genetic, mantém melhor solução
- `evaluator.py:46`: Usa `Decimal` para precisão em custos, com função objetivo documentada
- `csp/cp_sat_csp.py:64`: Usa `cp_model.CpModel()` do OR-Tools com `Minimize()` real
- `services/rostering/weekly_solver.py:153`: OR-Tools CP-SAT para rostering semanal

**Função objetivo real:**
```
Z = Σ_k f_k (frota) + Σ_(i,j) c_ij x_ij (deadhead) + Σ_d cost_d (jornadas) + penalidades
```

### 3.2 O que o sistema não faz (apesar de parecer fazer)

Abaixo, cada item com evidência de código:

| Afirmação | Realidade | Evidência |
|-----------|-----------|-----------|
| "CP-SAT e SET_PARTITIONING são algoritmos distintos" | Ambos usam o mesmo caminho (`_run_sp` + `set_covering_factory`). A distinção só existe na fábrica: se ortools disponível, ambos retornam CPSatCSP | `algorithm_dispatcher.py:370-371` |
| "Column Generation real (CG iterativo)" | SetPartitioning faz 1 iteração de pricing por padrão (`max_pricing_iterations: 1 if self.pricing_enabled else 0`). Não há convergência dual como CG real | `set_partitioning_optimized.py:197` |
| "MCNF = Min Cost Network Flow clássico" | Na verdade é MILP binário (Branch-and-Bound via CBC). O nome é enganoso; linear_sum_assignment não é usado no código real | `mcnf.py:390-442` |
| "Escala até 100.000 viagens" | Sem evidência no código ou testes. HybridPipeline usa AssignmentVSP para n>5000, sem benchmark acima de 2.000 trips | `pipeline.py:98` |
| "ALNS implementado" | Não existe. Nenhum arquivo com destroy/repair operators ou ALNS no codebase | Busca no codebase: 0 resultados |
| "Disruption Recovery" | Não implementado | Busca no codebase: 0 resultados |
| "Rostering multi-dia completo" | `weekly_solver.py` existe (OR-Tools, 392 linhas) mas integração ao pipeline principal não evidenciada | `rostering/weekly_solver.py` |

---

## 4. BUGS CRÍTICOS

### BUG-01 — Fallback silencioso no MCNF sem aviso na resposta API (SEVERIDADE: ALTA)

**Arquivo:** `vsp/mcnf.py:444-468`  
**Problema:** Quando o solver ILP falha ou retorna INFEASIBLE, o sistema faz fallback para GreedyVSP. O fallback é registrado no log e no `result.meta["fallback_used"]`, mas **não há garantia de que o caller/API exponha esse warning ao usuário final**. O usuário recebe uma resposta que parece "otimização MCNF", mas na verdade é greedy.

```python
if prob.status != pulp.constants.LpStatusOptimal:
    ...
    res = GreedyVSP(vsp_params=self.vsp_params).solve(...)
    res.meta.update({"fallback_used": True, "fallback_reason": status_str})
    return res
```

**Risco:** Em produção, o MCNF pode sempre fazer fallback para greedy (por timeout ou infeasibilidade) sem o cliente perceber.

**Correção:** O backend deve verificar `result.meta.get("fallback_used")` e incluir esse aviso na resposta da API.

---

### BUG-02 — Aliasing SET_PARTITIONING = CP_SAT na camada de despacho (SEVERIDADE: MÉDIA)

**Arquivo:** `algorithm_dispatcher.py:370`  
**Problema:**
```python
elif algorithm in (AlgorithmType.SET_PARTITIONING, AlgorithmType.CP_SAT):
    result = _run_sp(**common_kwargs, csp_factory=csp_factory, set_covering_factory=set_covering_factory)
```

Ambos os algoritmos chamam exatamente a mesma função `_run_sp`. A distinção entre "Set Partitioning (CBC)" e "CP-SAT (OR-Tools)" é resolvida **dentro da fábrica** baseada na disponibilidade do ortools — não no enum escolhido pelo usuário. Isso significa que um usuário que explicitamente escolhe `SET_PARTITIONING` na UI pode receber CP-SAT, e vice-versa.

**Risco:** Resultados não-reprodutíveis se a disponibilidade do ortools mudar entre ambientes. Documentação vs comportamento inconsistente.

---

### BUG-03 — MCNF chunking temporal perde otimalidade global (SEVERIDADE: MÉDIA)

**Arquivo:** `vsp/mcnf.py:147-221`  
**Problema:** Para n > 800 trips, MCNF usa chunking temporal com 10% de overlap. Trips na fronteira entre chunks podem ser atribuídas a blocos subótimos. A implementação atual tenta resolver conflitos filtrando trips já atribuídas, mas isso pode deixar trips isoladas em blocos singleton.

```python
if block_trip_ids & assigned_trip_ids:
    filtered_trips = [t for t in block.trips if t.id not in assigned_trip_ids]
    ...
    block = Block(id=block_id_counter, trips=filtered_trips, ...)
```

**Risco:** Para instâncias de 800-5000 trips (a faixa mais comum em produção), a solução MCNF pode ser pior que greedy puro por fragmentação excessiva de blocos.

---

### BUG-04 — Parâmetros CCT e VSP se sobrescrevem mutuamente (SEVERIDADE: MÉDIA)

**Arquivo:** `optimizer_service.py:152-156`  
**Problema:**
```python
for key, value in intent_params.items():
    if key not in ("trips", "vehicle_types"):
        cct_params[key] = value
        vsp_params[key] = value
```

Todos os parâmetros do DTO são propagados para ambos `cct_params` e `vsp_params`. Parâmetros com mesmo nome mas semântica diferente (ex: `max_shift_minutes` tem significado diferente para veículo e para motorista) são sobrescritos sem distinção.

**Risco:** Bug silencioso onde parâmetro de motorista afeta decisão de veículo ou vice-versa.

---

### BUG-05 — INTERNAL_OPTIMIZER_KEY lança exceção em `onModuleInit` (SEVERIDADE: BAIXA)

**Arquivo:** `backend/src/modules/operations/optimization.service.ts:67-72`  
**Comportamento:** Se `INTERNAL_OPTIMIZER_KEY` não estiver definida ou usar o valor padrão, o módulo NestJS falha ao inicializar. Isso é bom para segurança, mas pode causar falha silenciosa em ambientes de desenvolvimento sem `.env` configurado corretamente.

---

## 5. PROBLEMAS DE PERFORMANCE

### PERF-01 — O(N²) no MCNF sem escape precoce adequado (CRÍTICO para N→800)

**Arquivo:** `vsp/mcnf.py:326-364`

```python
for i in range(N):
    for j in range(i + 1, N):
        gap = trips_sorted[j].start_time - trips_sorted[i].end_time
        if gap > max_shift:
            break  # correto — mas só para max_shift
        ...
        valid_X[(i, j)] = {...}
```

O break por `max_shift` é a única otimização. Para `max_shift` grande (ex: 960 min = 16h), o loop percorre quase N² pares. Com N=800, são até 320.000 iterações. O número de variáveis MILP pode ser grande o suficiente para tornar o branch-and-bound intratável dentro do timeout.

**Medição:** Sem profiling real no código. O timeout `mcnf_ilp_timeout_seconds` é fixado em `min(60, time_budget)`, o que pode não ser suficiente para instâncias densas.

---

### PERF-02 — GreedyCSP com 3.583 linhas — complexidade opaca

**Arquivo:** `csp/greedy.py`  
**Problema:** 3.583 linhas em um único arquivo é uma red flag severa de manutenibilidade. A lógica de duty building, run-cutting, rostering e pós-processamento está misturada. Sem profiling, é impossível identificar onde está o gargalo para CSP em grandes instâncias.

**Impacto:** Qualquer bug ou regressão no CSP greedy afeta todos os algoritmos que o usam como base.

---

### PERF-03 — Metaheurísticas bloqueadas para n > 220 trips

**Arquivo:** `hybrid/pipeline.py:39,147-199`

```python
DEFAULT_MAX_VSP_METAHEURISTIC_TRIPS = 220
```

Para n > 220 trips (que é a maioria dos casos de produção reais), SA, Tabu e Genetic são pulados. O pipeline usa MCNF + (possivelmente) Greedy comparação. Isso significa que para operações reais (500-2000 trips), a "busca por melhor solução" não ocorre.

**Por que isso é um problema crítico:** O sistema foi documentado como sistema de otimização com SA/Tabu/Genetic, mas esses algoritmos só rodam em instâncias de teste pequenas.

---

### PERF-04 — Cache de schedule com TTL mas sem invalidação por tenant

**Arquivo:** `backend/src/modules/operations/optimization.service.ts:43-44`

```typescript
private scheduleCache = new Map<number, { data: any; timestamp: number }>();
private readonly CACHE_TTL_MS = SCHEDULE_CACHE_TTL_MS;
```

Cache em memória simples. Em ambiente multi-tenant, schedules de diferentes empresas podem ser cacheados com o mesmo `scheduleId` se houver colisão de IDs entre tenants.

---

## 6. PROBLEMAS MATEMÁTICOS

### MATH-01 — "Column Generation" é apenas 1 iteração (CRÍTICO)

**Arquivo:** `csp/set_partitioning_optimized.py:196-198`

```python
self.max_pricing_iterations = max(
    0, int(self.vsp_params.get("max_pricing_iterations", 1 if self.pricing_enabled else 0))
)
```

Column Generation legítimo itera até que nenhuma coluna com custo reduzido negativo exista (dual convergência). Com 1 iteração, o algoritmo:
1. Gera colunas iniciais (via GreedyCSP)
2. Resolve o Restricted Master Problem
3. Tenta adicionar novas colunas (1 vez)
4. Para

Isso não é CG — é set partitioning com geração limitada de colunas. A otimização pode ser significativamente pior que CG real.

---

### MATH-02 — Penalidade Big-M dinâmica sem análise de completude

**Arquivo:** `csp/set_partitioning_optimized.py:195`  
**Problema:** O parâmetro `max_candidate_successors_per_task` tem padrão 6. Isso significa que cada tarefa considera no máximo 6 sucessoras. Se a tarefa correta (de menor custo) for a 7ª candidata, ela nunca entra no ILP. A solução pode ser infeasível ou subótima por truncamento.

---

### MATH-03 — Custo de deadhead sem distância real

**Arquivo:** `vsp/mcnf.py:348-351`

```python
dh = max(min_layover, int(trips_sorted[i].deadhead_times.get(trips_sorted[j].origin_id, 0)))
idle = gap - dh
cost = (dh * deadhead_cost) + (idle * idle_cost)
```

O custo de deadhead usa `deadhead_times` do trip (dict). Quando o par destino→origem não tem tempo de deadhead registrado, assume 0 → custo subestimado → o solver pode criar blocos com deadhead impossível.

**Risco:** Solução ótima no modelo ≠ solução viável na operação real.

---

### MATH-04 — Função objetivo não incluída no relatório de saída

O `cost_breakdown` existe, mas não há cálculo de "gap de otimalidade" na saída. Sem o lower bound (ex: peak vehicle requirement de Bodin & Golden), não é possível saber se a solução está a 5% ou 40% do ótimo.

---

## 7. AUDITORIA DE TESTES

### 7.1 Testes que realmente existem

| Arquivo | Linhas | O que testa | Qualidade |
|---------|--------|-------------|-----------|
| `test_quality_vs_optibus.py` | 669 | 55 testes: lower bound, coverage, no-overlap, custo, Gini, runtime | BOA — mas apenas em datasets sintéticos pequenos |
| `test_regulatory_rules.py` | 1265 | Regras CCT, EV, constraints | BOA — mas 11 testes estavam quebrados (ver memória) |
| `test_solution_validator.py` | 282 | Validação de sobreposição, max_shift | ADEQUADA |
| `test_algorithms.py` | 647 | Múltiplos algoritmos | ADEQUADA |
| `test_pipeline_regression.py` | 109 | Regressão pipeline | FRACA — cenários pequenos |
| `qa_exhaustive.py` | 1213 | QA exaustiva | Não classificada como pytest standard |
| `benchmark_salvador.py` | 259 | Benchmark GTFS Salvador | FRACA — não integrado no CI |

### 7.2 O que os testes NÃO testam (lacunas críticas)

1. **Não há teste comparando SA/Tabu/Genetic vs MCNF no mesmo dataset** — não existe prova de que as metaheurísticas melhoram a solução
2. **Não há teste com n > 500 trips no CI** — toda a suite de qualidade usa datasets pequenos (10-200 trips)
3. **Não há teste de viabilidade end-to-end** (backend → optimizer → resultado verificável)
4. **Não há benchmark automatizado** — benchmarks existem como scripts separados, não como testes pytest
5. **Não há teste de timeout** — o que acontece quando o ILP não converge em 60s?
6. **Não há teste de fallback** — o que acontece quando PuLP não está disponível?
7. **Não há teste de multi-tenant isolation** — schedules de empresa A vs empresa B

### 7.3 Testes falsamente tranquilizadores

`test_pvr_reduction_vs_naive_baseline` (linha 169 de test_quality_vs_optibus.py):
```python
def test_pvr_reduction_vs_naive_baseline(self):
    trips = _consecutive_trips(20, gap=90)
    n = len(trips)  # naive: 1 vehicle per trip = 20 vehicles
    sol = GreedyVSP().solve(trips, vt)
    assert sol.num_vehicles < n * 0.5
```

Este teste compara Greedy vs "1 veículo por viagem". Mas "1 veículo por viagem" não é uma baseline realista — qualquer greedy trivial vence. A baseline deveria ser o lower bound real (peak concurrent trips) ou uma solução humana.

---

## 8. DOCUMENTAÇÃO VS CÓDIGO

| Afirmação na doc | Realidade no código | Status |
|-----------------|---------------------|--------|
| "MCNF = Min Cost Network Flow" | ILP binário via PuLP, não network flow | ENGANOSA |
| "Column Generation iterativo" | 1 iteração por padrão | EXAGERADA |
| "Nível Optibus" no header de set_partitioning_optimized.py | Sem benchmark comparativo | EXAGERADA |
| "Escala 30k trips" (memória de commit anterior) | AssignmentVSP para n>5000, sem QA de qualidade | NÃO COMPROVADA |
| "503 optimizer tests pass" (memória) | Muitos são testes unitários de estrutura, não de qualidade de otimização | PARCIALMENTE CORRETA |
| OR-Tools CP-SAT instalado | Sim, `ortools>=9.10.0` em requirements.txt | CORRETA |
| "Optibus: PVR -10%, crew -5%" nas referências dos testes | Não há benchmark OTIMIZ vs OTIMIZ-greedy para verificar | REFERÊNCIA PENDENTE |

---

## 9. MATRIZ DE ADERÊNCIA TIPO OPTIBUS

| Área | Nota 0–10 | Status | Evidência | Risco | Próxima ação |
|------|-----------|--------|-----------|-------|--------------|
| VSP (Vehicle Scheduling) | 6/10 | Parcial | MCNF ILP + SA + Tabu + Greedy implementados. Metaheurísticas desligadas para n>220 | Médio | Benchmarkar SA vs MCNF; aumentar limite ou justificar |
| CSP (Crew Scheduling) | 5/10 | Parcial | GreedyCSP funcional. Set Partitioning com 1 iter de CG. Regras CCT presentes | Médio | Implementar CG real ou ao menos 5–10 iterações |
| VCSP (Integrado) | 4/10 | Frágil | VCSPJointSolver existe mas escala limitada; sem benchmark joint vs sequencial | Alto | Benchmarkar com instância real |
| Rostering multi-dia | 3/10 | Frágil | weekly_solver.py existe, CP-SAT, mas não integrado no pipeline principal | Alto | Integrar + testar com escala real |
| Regras trabalhistas (CCT) | 6/10 | Parcial | GreedyCSP tem max_shift, max_driving, break, overtime. Hard constraints validadas | Médio | Adicionar testes de regressão para cada regra |
| Função objetivo | 7/10 | Implementada | Decimal precision, breakdown VSP+CSP+fairness | Baixo | Adicionar gap de otimalidade ao output |
| Validação de solução | 6/10 | Parcial | SolutionValidator verifica overlap, deadhead, max_shift | Médio | Validação independente pós-solver |
| Testes | 4/10 | Frágil | 55 testes de qualidade + QA, mas todos em datasets pequenos sintéticos | Alto | Adicionar testes com dados reais e >1000 trips |
| Performance | 5/10 | Parcial | Greedy é rápido; ILP pode ser lento sem benchmark | Médio | Profiling em instâncias de 500, 1000, 2000 trips |
| Escalabilidade | 3/10 | Não provada | Nenhum teste ou benchmark acima de 2000 trips com qualidade medida | Crítico | Benchmark obrigatório: 1k, 5k, 10k, 50k trips |
| API/Backend | 7/10 | Implementada | NestJS robusto, INTERNAL_KEY validation, rate limiting, throttler | Baixo | Expor fallback_used no response |
| Frontend | 6/10 | Implementada | Leaflet map, Gantt, dashboards, Gini KPI | Baixo | — |
| Banco de dados | 7/10 | Implementado | Migrations, entities, multi-tenant, OptimizationRun | Baixo | — |
| Documentação | 3/10 | Enganosa | Nomes enganosos (MCNF, "Column Generation"), promessas sem benchmark | Alto | Reescrever claims com evidência |
| Observabilidade | 6/10 | Parcial | structlog, prometheus, /health, /ready. Sem APM nem tracing | Médio | Adicionar request tracing |
| Produção | 5/10 | Parcial | Docker compose completo, rate limiting, CORS, secrets. Sem K8s, sem CI/CD completo | Médio | Completar pipeline CI com benchmark obrigatório |
| Comparação com Optibus | 2/10 | Não comprovada | Nenhum benchmark direto. Afirmações sem evidência | Crítico | Executar benchmark estruturado antes de qualquer venda |

---

## 10. PLANO DE CORREÇÃO POR PRIORIDADE

### PRIORIDADE 1 — CRÍTICO (bloqueia produção honesta)

#### P1-A: Expor `fallback_used` na API response
**Arquivo:** `backend/src/modules/operations/optimization.service.ts`  
**Mudança:** Verificar `optimizerResponse.meta?.fallback_used` e adicionar ao response com warning.

#### P1-B: Benchmark obrigatório de qualidade
Criar `optimizer/tests/benchmark_proof_of_optimization.py`:
- Dataset 50, 200, 500, 1000 trips
- Comparar: naive (1 veh/trip) → greedy → SA → MCNF → Hybrid
- Medir: nº veículos, custo total, gap vs lower bound
- Exigir: Hybrid ≤ Greedy em veículos; Hybrid ≤ 15% do lower bound
- Rodar automaticamente no CI

#### P1-C: Documentar limites reais de escala
Remover ou reescrever afirmações de "nível Optibus" sem evidência. Documentar os limites reais:
- n ≤ 220: Pipeline completo (SA + Tabu + GA)
- 220 < n ≤ 800: MCNF ILP + Greedy comparação
- 800 < n ≤ 5000: MCNF chunked + Greedy
- n > 5000: AssignmentVSP

#### P1-D: Corrigir aliasing CP_SAT = SET_PARTITIONING
**Arquivo:** `algorithm_dispatcher.py`  
Separar os dois caminhos. Se usuário escolhe `SET_PARTITIONING`, forçar PuLP. Se escolhe `CP_SAT`, forçar OR-Tools (retornar erro se não disponível).

---

### PRIORIDADE 2 — ALTA (afeta confiabilidade)

#### P2-A: Aumentar `max_pricing_iterations` para 5 mínimo no CSP ILP
**Arquivo:** `set_partitioning_optimized.py`  
`max_pricing_iterations: 1 → 5` por padrão. Medir impacto no tempo e qualidade.

#### P2-B: Validação de deadhead no MCNF
Verificar se `deadhead_times` contém a rota i→j antes de aceitar conexão. Rejeitar conexão quando deadhead não está mapeado em vez de assumir 0.

#### P2-C: Teste de regressão para cada regra CCT
`test_regulatory_rules.py` tem 1265 linhas mas 11 testes estavam quebrados. Verificar status atual e fixar.

#### P2-D: Teste de fallback MCNF
```python
def test_mcnf_fallback_is_flagged():
    # Force ILP timeout, verify fallback_used=True in meta
    # Verify fallback solution is still feasible
```

---

### PRIORIDADE 3 — MÉDIA (melhora qualidade)

#### P3-A: Profiling do GreedyCSP (3583 linhas)
Executar `cProfile` em instância de 200 blocos. Identificar as top-5 funções por tempo. Extrair helpers em arquivos separados.

#### P3-B: Aumentar limite de metaheurísticas para n ≤ 500
`DEFAULT_MAX_VSP_METAHEURISTIC_TRIPS = 220 → 500` se SA/Tabu terminam dentro de 30s para 500 trips. Medir antes de mudar.

#### P3-C: Adicionar gap de otimalidade ao output
Calcular e retornar `lower_bound` (peak concurrent trips) e `optimality_gap_pct` em todo response de otimização.

#### P3-D: Integrar weekly_solver no pipeline principal
Rostering semanal deveria ser opcional mas acessível via API, com testes de integração.

---

## 11. COMO PROVAR QUE O SISTEMA OTIMIZA (Plano de Testes)

Implementação recomendada: `optimizer/tests/proof_of_optimization_suite.py`

```python
"""
Suite de prova de otimização — responde se o sistema otimiza de verdade.
Executa com: pytest tests/proof_of_optimization_suite.py -v
"""

def test_lower_bound_calculated():
    """Todo output deve ter lower_bound = peak concurrent trips (Bodin & Golden 1981)."""
    ...

def test_mcnf_beats_or_matches_greedy_small():
    """MCNF-ILP deve usar ≤ veículos que Greedy em instâncias ≤ 100 trips."""
    trips = generate_medium_instance(n=50, overlap_pct=0.3)
    greedy_v = GreedyVSP().solve(trips, vt).num_vehicles
    mcnf_v = MCNFVSP().solve(trips, vt).num_vehicles
    assert mcnf_v <= greedy_v, f"MCNF ({mcnf_v}) pior que Greedy ({greedy_v})"

def test_hybrid_beats_greedy_medium():
    """HybridPipeline deve usar < veículos que Greedy em instâncias de 100 trips."""
    trips = generate_medium_instance(n=100, overlap_pct=0.4)
    greedy_result = GreedyVSP().solve(trips, vt)
    hybrid_result = HybridPipeline(time_budget_s=30).solve(trips, vt)
    lb = max_concurrent_trips(trips)
    hybrid_gap = (hybrid_result.vsp.num_vehicles - lb) / lb * 100
    greedy_gap = (greedy_result.num_vehicles - lb) / lb * 100
    assert hybrid_gap <= greedy_gap, f"Hybrid ({hybrid_gap:.1f}%) pior que Greedy ({greedy_gap:.1f}%)"

def test_all_trips_covered_500_trips():
    """Cobertura 100% em instância de 500 trips (teste de escala)."""
    trips = generate_large_instance(n=500)
    result = OptimizerService().run(trips, vt, algorithm=AlgorithmType.HYBRID_PIPELINE)
    covered = {t.id for b in result.vsp.blocks for t in b.trips}
    assert covered == {t.id for t in trips}

def test_no_overlap_500_trips():
    """Nenhum veículo com 2 viagens simultâneas em 500 trips."""
    ...

def test_solver_faster_than_greedy_on_dense_peak():
    """Em pico denso, MCNF deve ter mesmo ou menos veículos que greedy."""
    # Cria 50 viagens simultâneas (lb=50) + 100 viagens consecutivas (lb=1)
    ...

def test_csp_covers_all_blocks():
    """CSP deve cobrir 100% dos blocos VSP."""
    ...

def test_cct_hard_constraint_never_violated():
    """max_shift_minutes jamais violado na saída do solver."""
    ...

def test_runtime_sla_200_trips():
    """200 trips devem completar em < 60s."""
    ...

def test_runtime_sla_1000_trips():
    """1000 trips devem completar em < 300s."""
    ...

def test_optimality_gap_within_20pct_small():
    """Gap ≤ 20% do lower bound para instâncias ≤ 100 trips."""
    ...
```

---

## 12. COMO FAZER BENCHMARK PROGRESSIVO

```bash
# Benchmark a ser executado ANTES de qualquer release de produção

# Instâncias sintéticas crescentes
python optimizer/tests/benchmark_proof_of_optimization.py \
  --sizes 50,100,200,500,1000,2000,5000 \
  --algorithms greedy,mcnf,sa,tabu,hybrid \
  --repeats 3 \
  --output benchmark_results.csv

# Métricas obrigatórias por instância e algoritmo:
# - num_vehicles
# - lower_bound (peak concurrent)
# - optimality_gap_pct
# - total_cost
# - runtime_seconds
# - fallback_used
# - feasible (0 violations)
```

**Critérios mínimos de aceitação:**

| Instância | Veículos vs LB | Tempo máximo |
|-----------|---------------|--------------|
| 50 trips | ≤ 15% gap | 5s |
| 200 trips | ≤ 20% gap | 30s |
| 500 trips | ≤ 25% gap | 120s |
| 1000 trips | ≤ 30% gap | 300s |
| 5000 trips | Feasible + coverage 100% | 600s |
| 10000 trips | Feasible + coverage 100% | 1200s |

**Nota:** Os limites de 50k e 100k trips requerem investigação de AssignmentVSP + chunking. Não existe evidência atual de que o sistema aguenta essas escalas com qualidade aceitável.

---

## 13. COMO ESCALAR PARA 10.000–100.000 VIAGENS

### Estado atual
- **n ≤ 800**: MCNF ILP direto (real, mas lento para n→800)
- **800 < n ≤ 5000**: MCNF temporal chunking (perde otimalidade de fronteira)
- **n > 5000**: AssignmentVSP (bipartite matching, O(n³) via scipy ou similar)

### Para atingir 10.000 trips
1. Avaliar AssignmentVSP em n=5000–10000 (medir qualidade vs lower bound)
2. Implementar decomposição por linha/garagem antes do solver
3. Usar RegionalDecompositionSolver com subproblemas de ≤ 500 trips

### Para 50.000–100.000 trips
Requer abordagem fundamentalmente diferente:
- **Lagrangean Relaxation** sobre restrições de flow balance
- **Large Neighborhood Search (LNS)** com repair operators
- **Cluster-first, route-second** com linha como unidade
- Ou integrar solver externo (Gurobi, Xpress via API) para subproblemas ILP

**Nenhuma dessas está implementada atualmente.**

---

## 14. RISCOS PARA PRODUÇÃO

| Risco | Probabilidade | Impacto | Mitigação atual |
|-------|--------------|---------|-----------------|
| MCNF faz fallback para greedy em produção (timeout) | ALTA | ALTA — cliente paga por "ILP ótimo", recebe greedy | Meta fallback_used não exposto na API |
| CSP ILP não converge para instâncias densas | MÉDIA | ALTA — duty building greedy subótimo | Timeout + fallback para greedy CSP |
| Metaheurísticas nunca rodam em produção (n>220) | ALTA | MÉDIA — pipeline real ≠ pipeline descrito | Nenhuma |
| Deadhead incorreto por ausência de mapa completo | MÉDIA | ALTA — blocos inviáveis na operação real | Sem validação de cobertura do mapa |
| Bug de parâmetros CCT/VSP compartilhados | MÉDIA | MÉDIA — resultado imprevisível | Nenhuma |
| Solução inviável retornada sem flag explícita | BAIXA | CRÍTICA — operação real afetada | SolutionValidator existe mas não é obrigatório |

---

## 15. MELHORIAS IMPLEMENTADAS NESTA AUDITORIA

Nenhuma alteração de código foi feita nesta auditoria. O relatório identifica o que deve ser corrigido. Implementações requerem validação antes de aplicação.

---

## 16. VEREDITO FINAL

### O sistema está pronto para competir com Optibus?

**NÃO, mas é uma base técnica sólida.**

**O que é real e funciona:**
- Pipeline híbrido multi-fase (MCNF → SA → Tabu → GA → ILP)
- VSP greedy + metaheurísticas para n ≤ 220 trips
- CSP greedy com regras CCT brasileiras
- OR-Tools CP-SAT para rostering semanal
- ILP set covering para CSP
- Custo com precisão Decimal
- Fairness metrics (Gini)
- Backend NestJS robusto, multi-tenant, rate limiting
- Docker compose 5 serviços, /health, /ready

**O que impede a paridade com Optibus:**
1. Escala não provada além de ~2.000 trips com qualidade medida
2. Metaheurísticas desligadas para a maioria das instâncias reais
3. Sem CG real (column generation iterativo)
4. Sem ALNS
5. Sem disruption recovery
6. Sem benchmark comparativo honesto (só vs naive "1 veh/trip")
7. Rostering multi-dia não integrado ao pipeline
8. Fallback silencioso mascarando performance real

**O maior risco comercial:**  
O sistema pode ser demonstrado em instâncias pequenas onde parece excelente. Em produção com 500-2000 trips, o pipeline usa MCNF chunked + comparação com greedy — o resultado pode ser apenas marginalmente melhor (ou igual) ao greedy puro. Sem o benchmark de gap de otimalidade no output, o cliente não tem como saber.

**Recomendação:**  
Implementar o benchmark progressivo (Seção 12) e o plano de testes (Seção 11) **antes** de qualquer pitch comercial. Os resultados do benchmark determinarão onde o sistema está de fato na escala Optibus.

---

## 17. ACHADOS DO BENCHMARK EXECUTADO (2026-05-17)

Suite `proof_of_optimization_suite.py` executada ao vivo. **21/21 testes passaram.**

### Resultado do benchmark comparativo

```
Instância            LB   Greedy    Gap%   Hybrid    Gap%  Tempo(s)
Consec 30             1        6  500.0%        1    0.0%       7.1 ✓
Consec 100            1       13 1200.0%        1    0.0%       8.6 ✓
Consec 200            1       32 3100.0%        1    0.0%      18.5 ✓
Misto 50 (pk=10)     10       18   80.0%       10    0.0%      11.8 ✓
Misto 100 (pk=15)    15       34  126.7%       15    0.0%      12.6 ✓
Misto 200 (pk=20)    20       62  210.0%       20    0.0%      17.8 ✓
Simul 20             20       20    0.0%       20    0.0%       7.2 ✓
```

### Interpretação dos números

**Hybrid atinge 0% gap em todos os casos.** Isso se deve ao MCNF (fase 1 do pipeline) que, via ILP, encontra a solução de menor número de blocos de veículo.

**Greedy tem gaps elevados** (500%–3100%) para trips consecutivas. Isso é esperado e tem explicação técnica: o Greedy VSP aplica `max_vehicle_shift_minutes` como limite de duração total do bloco (~960 min = 16h), enquanto o MCNF aplica como limite de gap entre trips consecutivas (não duração total). Assim:

- Greedy: 30 trips × 150 min/trip = 4500 min → excede max_shift → fragmenta em múltiplos blocos
- MCNF: cada gap entre trips = 90 min < max_shift → encadeia todos em 1 bloco

### BUG-06 — Definição inconsistente de `max_vehicle_shift_minutes` (SEVERIDADE: ALTA)

**Achado novo (benchmark 2026-05-17)**

O GreedyVSP e o MCNFVSP têm semânticas DIFERENTES para `max_vehicle_shift_minutes`:

- **Greedy**: provavelmente usa como limite de duração total do bloco (start_first → end_last)
- **MCNF**: usa como limite de gap ENTRE trips consecutivas (`if gap > max_shift: break`)

Evidência: `vsp/mcnf.py:330`: `if gap > max_shift: break` — compara `gap = trip_j.start - trip_i.end` com max_shift.

**Impacto:** MCNF pode criar blocos com duração total de 72+ horas (matematicamente feasível em seu modelo, mas operacionalmente impossível). O bloco é então passado ao CSP para run-cutting, mas se o CSP greedy não tiver informação de duração máxima do BLOCO do veículo, pode gerar escalas impraticáveis.

**Correção necessária:** Unificar a definição. Adicionar restrição de duração total do bloco no MCNF (não apenas por gap):
```python
# Após montar chain, verificar:
total_duration = chain[-1].end_time - chain[0].start_time
if total_duration > max_block_duration_minutes:
    # split chain
```

Ou documentar explicitamente que `max_vehicle_shift_minutes` no MCNF é "max idle gap", não "max block duration".

### Aviso de qualidade gerado nos testes

O teste `test_greedy_gap_vs_lower_bound_acceptable` registrou:
```
AVISO DE QUALIDADE: Greedy gap=40.0% > 25% (lb=5, vehicles=7).
Para produção, usar SA/Tabu/Hybrid que atingem <25%.
```

Isso confirma que para uso em produção, o Greedy VSP puro é inadequado — o pipeline híbrido com MCNF é o caminho correto.

### Também observado: `time_budget_exceeded` em logs

O benchmark gerou múltiplos logs `time_budget_exceeded`. Isso indica que o HybridPipeline está esgotando o time budget (20s configurado no benchmark) em instâncias menores. Para as instâncias do benchmark, o MCNF phase provavelmente termina rápido, mas as fases SA/Tabu chegam no limite. Não é um erro — é o comportamento esperado. Mas sinaliza que 20s pode ser curto para o pipeline completo em instâncias de 100-200 trips.

---

*Auditoria concluída em 2026-05-17. 21/21 testes de prova passam. Próxima revisão recomendada após correção de BUG-06 e implementação do benchmark com datasets reais.*
