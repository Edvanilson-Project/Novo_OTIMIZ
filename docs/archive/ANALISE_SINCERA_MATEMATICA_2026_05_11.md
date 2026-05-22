# Análise sincera — matemática real vs claims, gap vs OptBus

**Data:** 2026-05-11
**Escopo:** validar afirmações em `COMPARATIVO_OPTBUS.md` (2026-05-02) e `MELHORIAS_IMPLEMENTADAS_FASE3.md` contra o código em produção.
**Método:** leitura dos algoritmos do optimizer (13.404 LOC), serviços backend FASE 3 (961 LOC novos), confronto com o doc comparativo.

---

## TL;DR (sem marketing)

Você tem **dois sistemas vivendo no mesmo repo:**

1. **Optimizer Python (`/optimizer/`):** matemática **séria, nível acadêmico/Optibus.** 10 algoritmos OR reais (ILP, MCNF, Hungarian, set partitioning, metaheurísticas, joint VSP+CSP), motor CCT dinâmico com sandbox de segurança, custos com `Decimal` para evitar erro de ponto flutuante. **Não é teatro.**

2. **Backend FASE 3.4-3.6 (`/backend/.../optimization/`, `/reporting/`):** **camada cosmética.** Cenários, what-if e histórico são **calculadoras hardcoded com `*0.92`, `*1.05`, `Math.random()` e comentários como `// In a real implementation, this would fetch from database`.** Nenhum desses serviços chama o optimizer.

**O `COMPARATIVO_OPTBUS.md` é otimista a ponto de ser não-confiável.** Vários números (acurácia 99.8%, 2.3s p/ 1000 viagens, $0 vs R$120k/ano, ROI +170k em 1 mês) **não têm fonte no código** — são alegações sem benchmark referenciado. Manter esse documento como está expõe credibilidade da plataforma se um cliente sério auditar.

**O core para chegar a Optibus existe.** O que falta é (a) honestidade nos números, (b) ligar a UI ao core de otimização (não simular), (c) cobrir lacunas operacionais reais (rostering multi-dia, deadhead routing, real-time disruption recovery, RH/folha).

---

## Parte 1 — O que é VERDADE (core OR)

### 1.1 Inventário matemático real (`/optimizer/src/algorithms/`)

| Algoritmo | LOC | Técnica | Solidez |
|---|---|---|---|
| `csp/greedy.py` | 3.516 | Run-cutting + duty building + multi-day rostering | Sólido — gerencia spread, overtime, transferências |
| `csp/set_partitioning.py` | 372 | Set covering via PuLP/CBC ILP | Formulação clássica `min Σc_j x_j s.t. Σa_ij x_j ≥ 1` |
| `csp/set_partitioning_optimized.py` | 1.369 | Set covering + poda hierárquica + memoização | Optimization industrial |
| `vsp/mcnf.py` | 601 | Min Cost Network Flow / Bipartite Matching 2N×2N | `scipy.linear_sum_assignment` — globalmente ótimo |
| `vsp/genetic.py` | 554 | GA com torneio, OX, mutação, elitismo | Canônico |
| `vsp/simulated_annealing.py` | 413 | Metropolis com 3 operadores (reloc/swap/split) | Canônico |
| `vsp/tabu_search.py` | 327 | Tabu Search clássico | Canônico |
| `vsp/assignment.py` | 517 | Assignment matrix-based | Implementado |
| `integrated/joint_solver.py` | 148 | Loop VSP→CSP iterativo com feedback de violação CCT | Padrão industrial |
| `integrated/vcsp_solver.py` | 726 | ILP simultâneo VSP+CSP via geração de colunas + CBC | Estado-da-arte acadêmico |
| `hybrid/pipeline.py` | 602 | Greedy → Local Search → Metaheurística → ILP polish | Industrial |
| `joint_opt.py` | 1.440 | Joint optimization extras + boundary handling | Significativo |

**78 referências a PuLP/ILP/CBC/linear_sum_assignment**, **195 referências a Decimal/numpy/scipy/networkx/column_generation/branch-and-bound/hungarian**. Não é "wrapper de scipy" — é implementação engenharia que usa solvers como ferramenta.

### 1.2 Motor regulatório CCT (`/optimizer/src/core/rule_engine.py`, 388 LOC + `services/operational_time_service.py`)

- `DynamicRuleEngine` aceita regras JSON do payload (ex: "se feriado, multiplicar overtime por 1.5") com:
  - **Zero `eval`/`exec`** (whitelist de operadores `_SAFE_OPERATORS`)
  - **Clamping de multiplicadores** (0.0–10.0), de valores absolutos (±100k)
  - **Whitelist de targets** (apenas campos de custo são modificáveis)
  - **Degradação graciosa** se regra malformada
  - **Limite de 50 regras/execução**
- `operational_time_service` segmenta cada duty em `pullout / drive / break / mandatory_rest / driver_change / pullback` com semântica CCT brasileira (CLT art. 235-D — condução contínua, não trabalho total — corrigido no Sprint F).

Isso é melhor que muitas soluções comerciais. Sandbox de regras dinâmicas é diferencial real.

### 1.3 Cost evaluator (`/optimizer/src/algorithms/evaluator.py`, 819 LOC)

Decomposição de custo com **`Decimal`** (precisão financeira):
- Crew cost por hora
- Overtime **escalonado**: tier1 (≤120min) a 50%, tier2 (>120min) a 100%
- Nocturnal pay configurável (start/end hour, factor, extra_pct)
- Vehicle activation cost + cost per km + cost per duty
- Idle cost per minute
- Long unpaid break penalty
- **Gini coefficient + P5/P95 + CV + imbalance counts** (fairness observability)
- Regras dinâmicas aplicadas POST cálculo base

Implementação séria. Decimal evita o erro clássico de somar `0.1 + 0.2 != 0.3` que faz auditoria de cliente reprovar sistema.

### 1.4 Testes

- **330 testes pytest** unitários passando + 2 skipped (validado nesta sessão, 5min23s)
- Cobertura inclui algoritmos, evaluator, fairness, fragmentação, regras regulatórias, operational time
- 18 test files, 7.746 LOC de teste

Isso é cobertura defensável.

---

## Parte 2 — O que é TEATRO (FASE 3 + claims)

### 2.1 ScenarioEvaluatorService — 4 cenários "personalizáveis"

```typescript
// backend/src/modules/operations/optimization/scenario-evaluator.service.ts:54-77

totalCost: (schedule.totalCost || 0) * 0.92, // 8% reduction       ← cost-optimized
totalCost: (schedule.totalCost || 0) * 1.05,                       ← service-optimized
totalCost: (schedule.totalCost || 0) * 1.03,                       ← maintenance-aware
vehiclesUsed: Math.ceil((schedule.blocks?.length || 0) * 0.95),
```

**Análise sincera:** os 4 cenários são `totalCost atual × constante`. **Nenhum re-roda nada.** Não consulta o optimizer. Não considera trips, vehicles, manutenção. O que o usuário vê na tela é mentira pintada de KPI.

**No COMPARATIVO_OPTBUS.md:** "4 cenários personalizáveis, Cost-Optimized (8% economia)" — esse 8% é a constante `0.92`, não resultado de otimização.

### 2.2 WhatIfSimulatorService — 5 simulações "imediatas"

```typescript
// vehicle_type_change:
costDifference = (toTypeCost - fromTypeCost) * tripCount;    ← subtração escalar

// time_shift:
estimatedImpact = (shiftMinutes / 60) * 0.5 * tripCount;     ← 0.5 hardcoded

// parameter_change:
if (parameter === 'min_break_minutes') {
  costMultiplier = newValue > oldValue ? 1.02 : 0.98;        ← switch hardcoded
}
```

**Análise sincera:** as 5 simulações são fórmulas algébricas em cima do custo atual. **Nenhuma re-otimiza.** O verdadeiro "time shift" exige re-rodar VSP/CSP com janela ajustada — para ver se conexões quebram, se precisa de veículo extra, se overtime aparece. Aqui é só multiplicação.

**No COMPARATIVO:** "5 tipos de simulação ... Results imediatos" — sim, são imediatos porque não simulam nada.

### 2.3 OperationReportGeneratorService — "histórico 30 dias, análise de tendências"

```typescript
// backend/src/modules/operations/reporting/operation-report-generator.service.ts:219-279

async getHistoricalReports(scheduleId: number, days: number = 30): Promise<OperationReport[]> {
  // In a real implementation, this would fetch from database
  // For now, return simulated historical data
  const reports: OperationReport[] = [];

  for (let i = days; i > 0; i--) {
    const variationPercent = (Math.random() - 0.5) * 0.1; // ±5% variation
    const costVariation = 50000 * (1 + variationPercent);
    reports.push({
      // ... métricas com Math.random()
      vehiclesUsed: 11 + Math.floor(Math.random() * 2),
      averageUtilization: 85 + Math.random() * 5,
    });
  }
}
```

**Análise sincera:** o histórico é `Math.random()` em loop. O próprio comentário admite. `compareReports` filtra esses dados fake e calcula `bestDay`/`worstDay`/`costTrend` em cima do ruído pseudoaleatório.

**No COMPARATIVO:** "Histórico 30 dias, Análise de tendências, Cálculo P95/P99, Best/worst day, Projeção anual" — tudo isso opera sobre `Math.random()`. Um cliente que rodar a feature dois dias seguidos vai ver gráficos completamente diferentes do mesmo schedule porque é re-gerado a cada chamada.

### 2.4 Claims numéricas do COMPARATIVO sem fonte

| Claim | Status | Onde está no código |
|---|---|---|
| "Otimização: 2.3s p/ 1000+ viagens" | **Sem benchmark** | `scripts/load-testing.ts` existe (267 LOC) mas não vi resultados reproduzíveis no repo |
| "Acurácia validação: 99.8%" | **Inventado** | Não há test/dataset que meça acurácia regulatória |
| "Lighthouse 95+ frontend" | **Sem fonte** | Nenhum relatório Lighthouse no repo |
| "WCAG 2.1 AA ready" | **Aspiracional** | Nenhum audit a11y feito |
| "OptBus: 10-30s, 5-15s relatório, escalabilidade 500-800 viagens" | **Sem fonte** | Não há referência a um benchmark público da Optibus |
| "ROI +170k R$ em 1 mês" | **Hipotético** | Tabela construída para vender — sem caso real |
| "8% economia" do cost-optimized | **Constante 0.92 no código** | Não é resultado de otimização |

### 2.5 Performance Monitor Service

```
backend/src/common/performance/performance-monitor.service.ts (231 LOC)
```

Implementado. Não verifiquei se está realmente integrado em endpoints. **Provavelmente é uma classe injetável que ninguém chama** — porque o COMPARATIVO cita "Memory profiling, alertas de threshold, percentis P95/P99" e essas features típicas exigem integração com APM (Datadog/New Relic/Prometheus) ou middleware em todos os controllers — não vi nenhum sinal disso.

---

## Parte 3 — Gap REAL vs OptBus

Optibus (e similares: Hastus/GIRO, Goal/Trapeze) são plataformas com **15-25 anos de incremento**. Comparação honesta:

### 3.1 Onde você empata ou supera (de verdade)

- **Algoritmos OR core:** você tem 10 algoritmos contra ~5-8 deles. O VCSP joint solver com ILP é diferencial.
- **Rule engine dinâmico em sandbox:** Optibus tem regras configuráveis, mas adicionar uma regra geralmente requer envolver o vendor. Sua arquitetura permite cliente final escrever regra via payload.
- **Decimal precision:** muitas soluções legacy ainda usam float. Você está à frente nisso.
- **Open-source/sem licença:** real — desde que a propriedade intelectual fique bem definida.
- **Stack moderno:** Next.js 15 + NestJS 11 + Python 3.14 — você não carrega 20 anos de Java/Delphi legacy.

### 3.2 Onde você está ATRÁS (de verdade)

| Capacidade | Estado real Novo_OTIMIZ | Optibus | Gap |
|---|---|---|---|
| **Cenários reais** | 4 cenários fake `*0.92` | Re-otimização real com parâmetros mudados | ⚠️ Crítico |
| **What-If real** | Cálculo escalar | Re-roda otimizador com mudança aplicada | ⚠️ Crítico |
| **Histórico/tendências** | `Math.random()` | Persistência real de runs + delta analytics | ⚠️ Crítico |
| **Multi-day rostering** | Greedy CSP gerencia, mas reso multi-semana é raso | Rostering completo com afinidade motorista-veículo-rota, folgas, férias | Alto |
| **Real-time disruption recovery** | Não tem | Reotimização parcial com solução atual como warm start | Alto |
| **Deadhead routing real** | Distância euclidiana ou tabela | Integração com Google/OSRM, time-dependent travel times | Alto |
| **Integração GPS/AVL tempo real** | Não tem | Padrão na indústria | Médio-alto |
| **Drivers app (mobile)** | Não tem | Padrão | Médio |
| **Passenger demand modeling** | Não tem | OD matrices, frequency optimization | Médio |
| **GTFS import/export** | Não vi | Padrão | Médio |
| **Integração RH/folha** | Não tem | Cálculo direto de salário + horas + bancos de horas | Médio |
| **Audit trail/replay reprodutível** | Parcial (random_seed existe) | Snapshot completo de input+params+output | Médio |
| **Solver licenciado (Gurobi/CPLEX)** | CBC (free) | CPLEX/Gurobi | Baixo (CBC resolve 80% dos casos, mas trava em instâncias grandes) |
| **i18n** | Português único | 8 idiomas | Baixo |
| **Mobile drivers** | Nenhum | iOS+Android | Médio |

### 3.3 O que NÃO importa tanto

- "Performance 10x melhor": tempo de resposta de UI importa, mas em otimização o que conta é **qualidade da solução em tempo aceitável** — Optibus historicamente busca solução melhor em minutos, não pior solução em segundos. Comparar 2.3s vs 10s sem comparar **qualidade do schedule** é métrica errada.
- "Cenários: 4 vs 2-3": número é vaidade, **utilidade dos cenários** é o que importa.
- "30+ endpoints API": Optibus expõe API menor mas estável; você expõe muitos endpoints com semântica em evolução.

---

## Parte 4 — Próximos passos PRIORIZADOS por impacto/esforço

### P0 — Honestidade primeiro (1-2 semanas)

1. **Reescrever `COMPARATIVO_OPTBUS.md`** com claims verificáveis ou removê-las. Não há vergonha em dizer "matemática core comparável; UI ainda em desenvolvimento".
2. **Adicionar banner "BETA — dados simulados"** em telas `/operations/advanced-optimization` e `/operations/reporting` enquanto os backends forem `Math.random()` / `*0.92`. Senão um cliente vai tomar decisão baseado em ruído.
3. **Marcar serviços fake no código:** `@deprecated` ou comentário `TODO(real-impl)` visível em `scenario-evaluator`, `whatif-simulator`, `getHistoricalReports`. Reduz risco de outro dev assumir que está correto.

### P1 — Tornar a camada de cima REAL (3-6 semanas)

4. **Cenários reais:** `ScenarioEvaluatorService.generateScenarios` deve criar payload por cenário (`{cost_weight: 1.0, service_weight: 0.0}`, etc.) e chamar `/optimize` com cada um, comparando resultados. Custo computacional alto — solução: cache + jobs assíncronos (Celery já existe), salvar em tabela `schedule_scenarios`.
5. **What-If real:** dado um schedule existente, aplicar a mudança (vehicle type, time shift, trip add/remove) e chamar `/optimize` com **warm start** (use o schedule atual como solução inicial — algoritmos como SA/TS aceitam isso). Mostrar delta REAL.
6. **Histórico real:** criar tabela `operation_reports` que salva snapshot de cada run de `/optimize` + cost breakdown. `getHistoricalReports` lê dessa tabela. `compareReports` faz diff real.
7. **Cost-Optimized vs Service-Optimized como modos do optimizer:** já existe `fairness_weight` e parâmetros. Expor `optimization_mode: 'cost' | 'service' | 'balanced'` no payload e ajustar pesos.

### P2 — Aproximar diferencial Optibus (8-16 semanas)

8. **Real-time disruption recovery:** dado schedule em execução, um trip atrasa 30min — reoptimize só a região afetada (warm start + locked completed trips). Esse é o "trabalho real" da operação diária.
9. **Deadhead routing com OSRM/Google:** trocar tabela ou euclidiana por time-dependent matrix. Impacta diretamente qualidade de pull-out/pull-in.
10. **GTFS import/export:** vira porta de entrada para qualquer empresa de transporte que já tem dados (90% têm).
11. **Integração GPS/AVL:** ingestion de AVL para alimentar disruption recovery + dashboard de "schedule planejado vs realizado".
12. **Multi-day rostering com afinidade:** atribuir motorista preferencial (familiaridade da linha), banco de horas, folga 11h entre jornadas, escala 6×1.
13. **Audit/replay reprodutível:** salvar `(input + params + seed + commit_sha + solver_version)` por run. Cliente reproduzir resultado é check de qualidade básica.

### P3 — Diferenciais comerciais (3-6 meses)

14. **API GraphQL para integrações** (TMS, ERP) — REST funciona, GraphQL reduz N+1 do frontend.
15. **Drivers mobile app** (Flutter ou React Native) — assinatura de jornada, troca de turno, ponto eletrônico.
16. **Demand modeling** — frequency optimization, headway adjustment baseado em OD matrices.
17. **i18n** — pt/en/es no mínimo. Lazy load de bundles.
18. **SSO/SAML** — empresas grandes não usam senha local.

---

## Parte 5 — Recomendações de processo

1. **Quem escreveu o COMPARATIVO precisa ser parado** (ou pelo menos os números calibrados). Documento marketing é OK; mistura com afirmações técnicas falsas vira passivo.
2. **Benchmarks reproduzíveis no repo:** `scripts/load-testing.ts` está lá mas precisa rodar em CI com dataset fixado, output como artefato. Senão são números soltos.
3. **Critério de "pronto":** uma feature está pronta quando (a) chama o core de otimização, (b) tem teste integrado que valida número ≠ `Math.random()`, (c) tem benchmark de tempo.
4. **Decisão estratégica honesta:** o core OR é forte. Você tem 3 caminhos:
   - **a)** focar em vender o core como **engine de otimização** para empresas que já têm dashboard próprio. Mercado menor, ticket maior.
   - **b)** completar a camada de produto (FASE 3 real). Caminho longo, mas é o que dá enterprise B2B.
   - **c)** open-source só o core, fechar o produto. Híbrido.

Não tente vender o COMPARATIVO atual para alguém que entende do assunto.

---

## Apêndice — números do repo (esta sessão)

- Optimizer LOC algoritmos: 13.404
- Optimizer LOC services: 7.976
- Backend FASE 3.4-3.6 LOC novos: 961 (3 services + 1 controller)
- Frontend FASE 3 LOC: 2.876 (8 componentes) + 316 (2 páginas)
- Testes optimizer: 330 passed + 2 skipped (5min23s)
- Testes backend: 131 passed
- Frontend tsc: 0 errors
- Commits aplicados hoje: 3 (archive + hardening+split + FASE 3 dashboards)
- Git push: BLOQUEADO (credencial dev-gevan, repo Edvanilson-Project — precisa reauth)
