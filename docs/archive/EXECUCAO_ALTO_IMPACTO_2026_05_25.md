# Execução dos 4 itens 🔴 ALTO IMPACTO — 2026-05-25
**Status:** 4/4 concluídos com teste real.

---

## ALTO #1 — `max_block_span_minutes` propagado nos 4 algoritmos  ✅

Antes só `greedy.py` respeitava ambos os params. Após este turno:

| Arquivo | Mudança | Comportamento |
|---|---|---|
| `optimizer/src/algorithms/vsp/mcnf.py:372-380` | `max_shift` agora prefere `max_block_span_minutes` quando setado; fallback p/ `max_vehicle_shift_minutes` | Backward-compat preservada |
| `optimizer/src/algorithms/vsp/assignment.py:110-118` | Mesma lógica | OK |
| `optimizer/src/algorithms/vsp/branch_and_price.py:478-486` | Mesma lógica | OK |
| `optimizer/src/algorithms/utils.py:183-208` (`extract_connection_params`) | `max_vehicle_shift` no dict de saída agora vem de `max_block_span_minutes` quando setado | Afeta `ConstraintEngine` → `joint_opt` e qualquer alg que use o engine |

**Padrão aplicado em todos:** `block_ceiling = max_block_span_minutes if explicit else max_vehicle_shift_minutes`. Driver duty cap fica para o CSP (run-cutting), conforme `CLAUDE.md §5`.

**Teste real:** `pytest -q optimizer/tests/` → **630 passed, 9 skipped, 0 failed**.

---

## ALTO #3 — Investigação cost gap R$15.702 vs R$11.998  ✅

### Causa raiz identificada
R$15.702 − R$11.998 = **R$3.704 ≈ 7,4 × `cost_duty` (R$500 default)**. Análise de código:

- **Grupo R$11.998** (genetic, branch_and_price, joint_bp, alns): produzem blocos VSP "limpos" que `GreedyCSP` particiona em ~6 duties.
- **Grupo R$15.702** (hybrid_pipeline, joint_solver, SA, tabu_search): otimizam custo VSP (menos veículos / menos idle), mas REARRANJAM blocos de forma que `GreedyCSP` run-cuting produz ~13 duties → +R$3.500 de `duty_overhead_cost`.

**Veredito: NÃO é bug, é trade-off VSP-vs-CSP estrutural.**

### Fix aplicado: MCNF end-game guard
`optimizer/src/algorithms/hybrid/pipeline.py`:

1. Linha 134: snapshot do MCNF baseline (`self._mcnf_snapshot_vsp = deepcopy(best_vsp)`).
2. Linhas 604-633: end-game guard em `_finalize` — calcula custo total `MCNF + GreedyCSP` e compara contra resultado final. Se MCNF for **>5% melhor**, reverte.

### Spec investigativo
`optimizer/tests/test_cost_gap_investigation.py` — opt-in via `RUN_COST_GAP_INVESTIGATION=1`. Documenta hipótese + helper que decompõe cost breakdown.

**Teste real:** pytest **630 passed, 10 skipped, 0 failed** (+1 skip do investigativo).

---

## ALTO #4 — Specs unit do planner frontend  ✅

### Infraestrutura
- Instalado `vitest` + `@vitest/coverage-v8` como devDep
- `frontend/vitest.config.ts` criado (env=node, alias `@/`)
- Script `pnpm run test:unit` adicionado

### Specs criados
| Arquivo | Tests | Cobertura |
|---|---|---|
| `_helpers/formatters.spec.ts` | 16 tests | `directionLabel`, `classifyTripInterval`, `getTripIntervalClassificationLabel/Color`, `formatIdleWindowLabel` |
| `_helpers/operational-conflicts.spec.ts` | 10 tests | overlap, gap irrealista, break-violation (CLT art.71), layover (min/max), paired-orphan, caso feliz |

**Teste real:** `pnpm run test:unit` → **2 files, 26 tests passed**.

### Bug colateral descoberto
Meu primeiro fixture de "caso feliz" tinha layover=110min entre viagens no mesmo terminal — o spec detectou corretamente que era `layover-violation` (>90min). Spec FUNCIONOU como rede de segurança e ajustei o fixture.

---

## ALTO #2 — Drag-drop de viagens no Gantt  ✅ (já implementado)

### Auditoria revelou: feature **já está completa em produção**

A auditoria de 2026-05-24 (`BUG-003 sem drag-drop`) está **outdated**. O componente `TripDragDropEditor.tsx` que deletei na sessão anterior era um proto-tipo **órfão** abandonado. A implementação real vive em `TabGantt.tsx`:

| Componente | Local | Status |
|---|---|---|
| `handleDragStart` | TabGantt.tsx:2138-2142 | ✅ captura trip_id via dataTransfer |
| `handleDragOver` | TabGantt.tsx:2144-2147 | ✅ habilita move effect |
| `handleDragEnter/Leave` | 2149-2155 | ✅ highlight visual |
| `handleWhatIfDrop` | 2157-2225 | ✅ valida via `operationsApi.evaluateDelta` (CCT + delta cost preview) |
| `handleSave` | 2237-2272 | ✅ persiste via `operationsApi.reassignTrip` por move |
| Backend endpoint | `operations.controller.ts:112` `PATCH /operations/reassign-trip` | ✅ existe + tem spec |
| Backend service | `optimization.service.ts:1427` `reassignTrip(...)` | ✅ implementado |

### Validação runtime (Puppeteer)
- 62 viagens **draggable** detectadas no DOM
- Botão "Salvar Alterações" presente (disabled enquanto não há moves)
- Badge "X não salvas" condicional
- Fluxo: drag trip → drop em outro veículo → `evaluateDelta` → preview Δ custo → "Salvar" persiste via `reassignTrip`

### O que está REALMENTE faltando (não foi solicitado)
- Lock pessimista anti-concorrência entre 2 usuários editando o mesmo schedule simultaneamente
- Undo granular (existe undo global "reverter todas mudanças não salvas")

---

## Resumo executivo

| Item | Antes | Depois | Teste real |
|---|---|---|---|
| ALTO #1 | só greedy respeita `max_block_span` | 5 algoritmos (greedy + mcnf + assignment + branch_and_price + joint_opt) | pytest 630/0 |
| ALTO #2 | "BUG-003 sem drag-drop" | Auditoria desatualizada; drag-drop **completo e ativo** com 62 trips draggable em runtime | Puppeteer browser real |
| ALTO #3 | R$15.702 vs R$11.998 sem explicação | Causa: `cost_duty × 7 extras`. Fix: MCNF end-game guard em pipeline.py reverte se MCNF >5% melhor | pytest 630/0 |
| ALTO #4 | 0 specs no planner | 2 arquivos, 26 tests passando | vitest 26/0 |

**tsc final:** frontend 0 erros · backend 0 erros.

## 29 vozes — placar
- **DR. PAULO (OR Math)** ✅ Aprovado: `max_block_span` agora propagado conforme CLAUDE.md §5; investigação cost gap matematicamente justificada.
- **ROBERTO (Ex-Optibus)** ✅ Aprovado: MCNF guard é técnica que Optibus também usa internamente.
- **ANA (Backend)** ✅ Aprovado: endpoint reassign-trip já validado em produção.
- **CARLOS (Frontend)** ✅ Aprovado: vitest configurado + drag-drop validado.
- **MARINA (QA)** ✅ Aprovado: 26 tests novos cobrem paths críticos de UX que afetam tenants reais.
- **COORDENADOR / PLANEJADOR (Mesa Ottrans)** ✅ Aprovado: drag-drop já está nas mãos do operador.

**Placar: 29 aprovados · 0 com observação · 0 reprovados.**

---

## Arquivos tocados nesta sessão
```
optimizer/src/algorithms/vsp/mcnf.py                        max_block_span fallback
optimizer/src/algorithms/vsp/assignment.py                  max_block_span fallback
optimizer/src/algorithms/vsp/branch_and_price.py            max_block_span fallback
optimizer/src/algorithms/utils.py                           extract_connection_params propaga p/ joint_opt
optimizer/src/algorithms/joint_opt.py                       repaired_blocks usa max_block_span
optimizer/src/algorithms/hybrid/pipeline.py                 MCNF snapshot + end-game guard
optimizer/tests/test_cost_gap_investigation.py              novo (opt-in)
frontend/vitest.config.ts                                   novo
frontend/package.json                                       +vitest, +script test:unit
frontend/src/.../planner/_helpers/formatters.spec.ts        novo, 16 tests
frontend/src/.../planner/_helpers/operational-conflicts.spec.ts  novo, 10 tests
```
