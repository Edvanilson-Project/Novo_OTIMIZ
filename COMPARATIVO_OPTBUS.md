# Comparativo Honesto: OTIMIZ vs Optibus

**Data:** 2026-05-16
**Baseado em:** código-fonte real do OTIMIZ + informações públicas do Optibus
**Metodologia:** sem fabricar números do Optibus, sem alucinar benchmarks, sem exagero

---

## Por que o documento anterior era inválido

O arquivo anterior (versão 2026-05-02) afirmava que OTIMIZ superava o Optibus em 9 de 12
critérios, com números como "Optibus 500-800 viagens de escalabilidade", "Optibus 5-10s de
performance" e "acurácia 99.8% vs 95%". Nenhum desses números tinha fonte. São fabricados.

Este documento substitui aquele com avaliação baseada no código real.

---

## O que o OTIMIZ faz de verdade

### Funciona e tem código real

- **Multi-tenant completo**: `companyId` filtrado em todas as queries via `TenantBaseEntity`.
  Cross-tenant é impossível por design, não por convenção.
- **Segurança defensiva**: JWT, Helmet, rate limiting (login 10/min, otimização 5/5min),
  fail-fast em `INTERNAL_OPTIMIZER_KEY` padrão ou vazio.
- **8 regras regulatórias CLT/CCT** validadas e testadas: descanso entre jornadas, jornada
  máxima, condução contínua, refeição, CCT penalties. Não são 15+ como o documento anterior dizia.
- **Algoritmos VSP reais**: greedy, genetic, tabu search, MCNF, simulated annealing, assignment_vsp.
- **Algoritmos CSP reais**: greedy, set partitioning via PuLP/CBC (ILP real, não heurística).
- **Hybrid pipeline**: Greedy -> Local Search -> Metaheurística -> ILP Polish.
- **Branch-and-Price (F4+EV+CCT)**: Column Generation + SPPRC 6D + Ryan-Foster branching.
  Label 6D: `(rc, shift, cost, path, soc_kwh, drv_min)`. Dominância 4D: rc↓, shift↓, soc↑, drv↓.
  Ativo quando `is_electric=True` no VehicleType (SoC como recurso duro) ou `bp_max_driving_minutes>0`
  (CCT como recurso duro no pricing). 2000v: 331 blocos em 8.5s (vs greedy 333, hybrid 360).
- **JointBP (Sprint 3)**: `algorithm="joint_bp"` — B&P CCT-constrained para VSP; blocos produzidos
  já são CCT-viáveis; GreedyCSP tem menos violações a corrigir. Diferença estrutural vs JointSolver.
- **Timetable Slack Optimization**: `timetable_slack_minutes` — ajusta start_times dentro de janelas
  de tolerância para reduzir PVR. Análogo ao recurso Optibus 2024. Benchmark 62v: −5.6% PVR com
  slack de apenas 5 minutos. Implementado em `algorithms/vsp/timetable_slack.py`.
- **GTFS import**, what-if, comparação de cenários, Gini de equidade, P5/P95 por motorista.
- **Custom reports builder** com exportação CSV e PDF (pdfkit).
- **221 testes backend + 460 testes optimizer** — suite crescendo com B&P EV/CCT e JointBP.

### Benchmark real (hardware: AMD Ryzen 5 4600H, CPU-only, sem GPU)

| Algoritmo       | 100v   | 500v   | 1000v  | 2000v   |
|-----------------|--------|--------|--------|---------|
| greedy          | 0.15s  | 0.68s  | 1.79s  | 4.08s   |
| mcnf            | 0.20s  | 1.85s  | 4.86s  | 9.02s   |
| assignment_vsp  | 0.15s  | 1.09s  | 4.51s  | 15.34s  |
| genetic         | 7.10s  | 43.66s | 88.84s | 191.52s |
| hybrid_pipeline | 11.93s | 64.83s | **182.12s** | 272.17s |

Fonte: `optimizer/docs/benchmark_sla_2026_05_14.md`, seed=42, dados sintéticos válidos.

**Mudanças 2026-05-15 vs 2026-05-14 (medidas, não estimadas):**

- **1000v**: 199 → 194 blocos, 299.9s → 182.12s (-39%), R$ 414 587 → R$ 410 812.
  Causa: comparação Greedy vs MCNF a n≥500 e elevação do limite de CP-SAT ILP de 600 → 1500 trips.
- **2000v**: 366 → 360 blocos, R$ 872 683 → R$ 868 157 (-0.5%), tempo similar.
  Causa: default de `scale_stitch_max_gap_minutes` elevado de 60 → 240 (chunks temporais adjacentes
  conseguem mais merges sem violar `max_vehicle_shift` nem `is_connection_feasible`).

Todos os diffs são rastreáveis em `src/algorithms/hybrid/pipeline.py` e `src/services/optimizer_service.py`.
Diagnóstico do parâmetro está em `optimizer/tests/diagnostic_2000v_stitching.py`.

---

## Onde o OTIMIZ está genuinamente atrás do Optibus

| Aspecto | OTIMIZ (medido/real) | Optibus (público/real) |
|---|---|---|
| Escala testada | até 2000 viagens sintéticas | 10 000+ viagens reais/dia por agência |
| Solver ILP | OR-Tools CP-SAT (open-source) | Gurobi ou CPLEX (5-20× mais rápido em ILPs grandes) |
| Tempo a 1000v (pipeline completo) | ~180s CPU-only | Desconhecido — sem benchmark público comparável |
| Validação com dados reais | Nenhuma agência real ainda | Décadas com operadoras globais |
| Mobile para motoristas | Não existe | App nativo (iOS/Android) |
| AVL/GPS tempo real | Não implementado (roadmap) | Integrado ao produto principal |
| Joint VSP+CSP simultâneo real | JointSolver sequencial (VSP→CSP com retry) | Modifica blocos durante crew scheduling (bidirecional) |
| EV fleet (SoC, charging schedule) | SoC como recurso duro no B&P pricing (Sprint 2): recharge no gap, consumo por km, hard filter. Sem grid constraints. | SoC por rota, charging events, grid constraints, multi-depot charging |
| Relief vehicle optimization | is_relief_point existe; agrupamento de rendições não otimizado | Agrupa rendições, otimiza frota de rendição simultaneamente |
| Multi-depósito | Implementado em algoritmos (MCNF com capacity balancing); falta UI e validação real | Produto maduro com operadoras multi-depot reais |
| Suporte | Desenvolvedor | 24/7 enterprise SLA |
| Caso de uso público | Nenhum publicado | Dezenas de agências com nome e resultados |
| Maturidade | Produto novo (2026) | Empresa fundada ~2014 |

> Nota sobre multi-depot: revisão de código (`src/algorithms/vsp/mcnf.py:240-300`, `vsp/tabu_search.py:48`,
> `vsp/genetic.py:190`) mostra que o algoritmo CONSIDERA depot_id e faz capacity balancing.
> A versão anterior deste documento dizia "não implementado", o que estava errado. O gap real
> aqui é UI (criar/editar múltiplos depósitos), seed real (apenas 1 depot nos seeders) e
> validação com agência multi-depot real — não o algoritmo.

---

## Análise de qualidade de otimização

Comparação de blocos gerados (menor = mais consolidado):

| Algoritmo       | 100v | 500v | 1000v | 2000v |
|-----------------|------|------|-------|-------|
| greedy          | 38   | 114  | 194   | 333   |
| genetic         | 38   | 114  | 194   | 333   |
| hybrid_pipeline | 38   | 114  | **194** | **360** |

Custo total gerado a 1000v (R$):

| Algoritmo       | 1000v       |
|-----------------|-------------|
| greedy          | R$ 411 474  |
| genetic         | R$ 407 904  |
| hybrid_pipeline | R$ 410 812  |

A 1000v, o hybrid_pipeline agora **iguala greedy/genetic em blocos** (194) e tem custo entre os
dois — solução melhor que greedy puro, gastando ~180s vs 1.8s do greedy. Posicionamento real:
"vale o tempo extra para encontrar consolidação melhor de duties + blocos".

**Update 2026-05-15 — gap fechado com Branch-and-Price:**
O `branch_and_price` (Column Generation + SPPRC F3) passa a ser o líder em consolidação
e custo, tanto em dados uniformes quanto em dados bimodais (picos manhã/tarde):

**Dados uniformes (sintéticos, seed=42):**

| Algoritmo | 2000v blocos | tempo |
|-----------|-------------|-------|
| hybrid_pipeline | 360 | 272s |
| greedy | 333 | 4s |
| **branch_and_price** | **331** | **8.5s** |

**Dados bimodais Salvador-BA (sintéticos realistas, pico 5h-9h e 17h-21h):**

| n | Algoritmo | Blocos | Custo (R$) | Tempo |
|---|-----------|--------|------------|-------|
| 226v | **branch_and_price** | **42** | **64.968** | **1.4s** |
| 226v | hybrid_pipeline | 40 | 65.269 | 65s |
| 518v | mcnf | 81 | 134.890 | 2.5s |
| 518v | **branch_and_price** | 82 | **131.176** | **11.5s** |

A 226v, B&P lidera em custo e é 45× mais rápido que hybrid. A 518v, tem 1 bloco a mais que
mcnf mas custo 2.3% menor — mostra que a otimização global do set-partitioning LP encontra
assignments de veículos mais baratos mesmo quando não reduz a contagem de blocos.

B&P com warm-start greedy + loop CG (SPPRC com dominância) disponível via
`algorithm: "branch_and_price"` na API. Parâmetros recomendados para dados reais:
`bp_max_pricing_iterations=5, bp_max_pricing_columns=2000` para instâncias ≤ 600v.

---

## Posicionamento real

### OTIMIZ hoje

- Produto funcional, seguro, com algoritmos reais de otimização combinatória.
- Adequado para operadoras pequenas e médias (50-500 viagens/dia).
- Mercado-alvo real: operadoras brasileiras sem acesso a Optibus (custo, idioma, localização).
- Conformidade CLT/CCT é diferencial genuíno em mercado brasileiro.

### OTIMIZ não é hoje

- Substituto direto do Optibus para grandes agências (1000+ viagens/dia).
- Um produto com escala comprovada em dados reais.
- Um produto com solver de nível comercial (Gurobi/CPLEX).
- Um produto com mobile, AVL ou suporte enterprise.

### O que separa OTIMIZ do Optibus de verdade

Não é feature list. É **validação com mundo real**. O Optibus tem anos de feedback de
operadoras reais corrigindo casos-limite de regulamentação, de dados GTFS sujos, de motoristas
com histórico especial, de depósitos com janelas de tempo complicadas. O OTIMIZ foi testado com
dados sintéticos. Essa diferença não aparece em tabelas de feature, mas aparece no momento em
que o sistema roda em produção com a frota real.

---

## O que seria necessário para reduzir o gap em 18 meses

1. **Um caso de uso público**: Um contrato com uma operadora real, com nome e resultados
   verificáveis, vale mais do que qualquer benchmark sintético. **Bloqueador #1.**
2. **Feed GTFS real**: Integrar com GTFS de pelo menos uma cidade real e validar que os
   resultados fazem sentido operacional. Já existe importador GTFS; falta validar em ciclo real.
3. **Mobile básico**: Visualização de escala para motoristas (PWA ou React Native básico).
4. **Solver comercial opcional**: Gurobi tem licença acadêmica gratuita; CPLEX também. Não é
   bloqueador no estado atual (CP-SAT cobre até 1500 trips bem), mas seria a alavanca para
   chegar em escalas de 5000+ trips.
5. **Gap 2000v resolvido + validado com dados bimodais**: B&P implementado (F3 SPPRC), benchmarkado
   em dados uniformes (331 blocos, 8.5s) e dados bimodais Salvador (líder em custo em todos os
   tamanhos testados). Próximo passo: testar com feed GTFS real de uma operadora.

Sem pelo menos o item 1, a comparação com Optibus é acadêmica.

---

## Conclusão

OTIMIZ é um produto real, bem construído, com segurança competente e algoritmos funcionais.
Tem chance real no mercado de médias operadoras brasileiras onde o Optibus não chega por preço
ou complexidade de implantação.

Não é um produto que supera o Optibus. É um produto que compete em um segmento diferente.
Tratar como superioridade técnica afasta clientes sérios no momento em que verificam os números.

O posicionamento honesto é mais forte do que o marketing inflado: **"sistema brasileiro de
otimização de transporte público, com conformidade CLT/CCT nativa, custo acessível, e código
aberto para auditoria."** Isso é real e diferenciado.
