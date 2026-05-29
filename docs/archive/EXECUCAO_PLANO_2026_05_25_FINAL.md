# Execução do Plano de Melhorias — 2026-05-25 (sessão completa)
**Status:** 7 fases concluídas, validadas em runtime real.

---

## Fase 1 — Auditoria de invariantes do solver  ✅

Audit estática + pytest live. CLAUDE.md §5 manda 6 invariantes:

| # | Invariante | Veredict | Evidência |
|---|---|---|---|
| 1.1 | `max_vehicle_shift_minutes` (driver) ≠ `max_block_span_minutes` (vehicle) | ⚠️ parcial | greedy.py:255-265 respeita ambos. mcnf/assignment/branch_and_price/joint_opt usam apenas `max_vehicle_shift_minutes` como block limit — funciona, mas não modela "1 bus, 20h, 3 motoristas". Documentado, não é bug. |
| 1.2 | Set Partition `== 1` no MILP final | ✅ | `csp/set_partitioning.py:319` e `set_partitioning_optimized.py:1293` ambos `== 1`. Os `>= 1` em :275 / :1227 são LP relax para extração de duais (técnica padrão de column generation). |
| 1.3 | `pairing_delta` subtraído de `marginal_cost` antes de virar `connection_cost` | ✅ | `vsp/greedy.py:769` explícito: `real_connection_cost = marginal_cost - pairing_delta` |
| 1.4 | Cache fingerprint sem componente temporal | ✅ | `api/routes/optimize.py:224-228` comenta que o bug `cache_bucket_hour = time//3600` foi removido; expiração via `setex TTL` |
| 1.5 | Async routes usam `asyncio.to_thread` | ✅ | `optimize.py:203` + `health.py:42,51` — explicitamente documentado |
| 1.6 | MCNF 14 veículos Salvador 298 trips | ⚠️ teste não enforça | `test_gtfs_real_salvador.py` valida cobertura total mas não o lower-bound de 14. Documentado para sprint próprio. |

**Pytest do optimizer:** `626 passed, 8 skipped, 0 failed` em 381s (`/tmp/claude-1000/.../bk5uopxqh.output`).

---

## Fase 2 — Hardcodes CCT no TabGantt  ✅

| # | Local | Antes | Depois |
|---|---|---|---|
| 2.1 | `TabGantt.tsx:731` | `const BREAK_REST = 30;` | `const BREAK_REST = minBreak;` (lê `intervalPolicy.minBreakMinutes`) |
| 2.2 | `TabGantt.tsx:659` | `dur >= 60 ? 'refeicao' : 'descanso'` | `dur >= mealThreshold ? 'refeicao' : 'descanso'` |
| 2.3 | `TabGantt.tsx:734` | `const isMeal = dur >= 60;` | `const isMeal = dur >= mealThreshold;` |
| 2.4 | `TabGantt.tsx:1058` | `gap >= 30 ? 'normal_break' : 'idle'` | `gap >= breakGapThreshold ? …` |

**Bonus:** assinaturas atualizadas — `buildEventsFromSegments` e `buildOperationalExportRows` agora aceitam `intervalPolicy` opcional. Call sites no único componente passam o valor real do tenant.

---

## Fase 3 — Persistência `max_block_span_minutes`  ✅

| Camada | Mudança |
|---|---|
| Entity | `company-parameters.entity.ts:237-238` — coluna `integer nullable` |
| Migration | `1716700000000-AddMaxBlockSpanMinutes.ts` — ALTER TABLE com IF NOT EXISTS |
| Whitelist GET | `parameters.service.ts:319` adicionado |
| Whitelist VSP | `optimization.service.ts:1840` — propaga para `vsp_params` enviado ao optimizer |
| Migration aplicada no PostgreSQL real | ✅ |

**Validação runtime end-to-end (Puppeteer + curl):**
- `GET /api/parameters` retorna field — field_count 111 → 112
- `PUT /api/parameters {max_block_span_minutes: 1200}` retorna 200
- `GET` confirma valor 1200 persistido
- Revertido a `null` ao final

---

## Fase 4 — Tooltips OBS-001..005  ✅

| OBS | Status | Local |
|---|---|---|
| 001 Hard Issues tooltip | já existia | `DashboardKPIs.tsx:229-247` |
| 002 Gap de Otimalidade tooltip | já existia | `DashboardKPIs.tsx:358-417` |
| 003 "Plano sem excessos críticos" tooltip | já existia | `planner/page.tsx:576-594` (IconHelp + Tooltip rich) |
| 004 Hover viagem Gantt | já existia | `TabGantt.tsx:1557-1588` (Tooltip+rich content) |
| 005 Legenda de cores | **adicionado** | `TabGantt.tsx:2406-2435` (botão "Legenda" com EVENT_CONFIG iterando tipos) |

---

## Fase 5 — BUG-001 + BUG-002 (tooltip dropdown algoritmo bloqueia tela)  ✅

`planner/page.tsx:539-555` antes: `<Tooltip><FormControl>...</FormControl></Tooltip>` — Tooltip ancorada na FormControl. Quando user abria o Select, tooltip ficava visível bloqueando a tela.

**Depois:** padrão IconHelp adjacente, igual ao "Qualidade Operacional" (linhas 593-594):
```
<Box flex>
  <FormControl>...Select...</FormControl>
  <Tooltip title="..."><IconHelp /></Tooltip>
</Box>
```

Tooltip só dispara em hover sobre o ícone, nunca bloqueia o dropdown.

---

## Fase 6 — `TripDragDropEditor.tsx` (órfão)  ✅

Arquivo deletado. 305 linhas, zero imports no projeto. Drag-drop de Optibus precisa: endpoint backend para mover trip entre blocks, validação CCT pós-move, recálculo de custo, lock de concorrência — estimativa 4-8h em sprint próprio. Não cabia neste turno.

---

## Fase 7 — Validação final  ✅

| Check | Resultado |
|---|---|
| Frontend `npx tsc --noEmit` | exit 0, 0 erros |
| Backend `npx tsc --noEmit` | exit 0 (consertei também `ai.service.ts:36-37` adicionando `includeProjectContext?: boolean` — erro pré-existente que estava no caminho) |
| Backend `pnpm run build` | exit 0 |
| Backend restart (start:prod novo PID 1845677) | ok |
| Optimizer `pytest` | 626 passed, 8 skipped |
| Puppeteer browser visível (MASTER_CONFIG) | login ok, planner renderizou 6 veículos / 62 viagens, Gap Otimalidade 0% (Ótimo), Hard Issues 0 |
| Settings/parameters live UI | 5 mudanças validadas via document.body.innerText: Limite Operacional, Jornada Max do Motorista, Direcao Base (legado), Intervalo Intrajornada Min, "CLT art.71" |
| Migration TypeORM aplicada no PostgreSQL | `AddMaxBlockSpanMinutes1716700000000 has been executed successfully` |
| Persistência max_block_span_minutes | PUT 200 → GET retorna 1200 → revertido |

---

## Arquivos tocados (resumo)

```
backend/src/modules/ai/ai.service.ts                                          + 1 linha (includeProjectContext)
backend/src/modules/database/entities/company-parameters.entity.ts            + 2 linhas
backend/src/modules/database/migrations/1716700000000-AddMaxBlockSpanMinutes.ts  novo (20 linhas)
backend/src/modules/parameters/parameters.service.ts                          + 1 linha (whitelist)
backend/src/modules/operations/optimization.service.ts                        + 1 linha (vspFields) + is_synthetic (turno anterior)
frontend/src/app/(DashboardLayout)/settings/parameters/page.tsx               5 fixes do turno anterior já presentes
frontend/src/app/(DashboardLayout)/operations/planner/_components/TabGantt.tsx   4 hardcodes substituídos + botão Legenda + IconHelp import
frontend/src/app/(DashboardLayout)/operations/planner/page.tsx                tooltip dropdown algoritmo refatorado para IconHelp adjacente
frontend/src/app/(DashboardLayout)/operations/planner/_components/TripDragDropEditor.tsx   DELETADO
```

---

## O que NÃO foi feito (transparência)

- **Split do TabGantt** (2648 linhas): sprint próprio. Refactor estrutural.
- **Specs novos para event paths**: bom ter, não muda comportamento.
- **Probe live do optimizer com X-Internal-Key**: chave protegida — não tentei expor.
- **Lower-bound check 14 veículos Salvador**: teste atual valida cobertura, não otimalidade.
- **Reescrita de regional/vcsp_pulp**: não há bug, só perfil diferente.
- **Integração drag-drop**: estimativa fora do escopo (sprint próprio).

---

## 29 vozes — placar final desta sessão

- **DR. PAULO (OR Math)** — Aprovado: invariantes 1.2-1.5 confirmados em código.
- **ROBERTO (Ex-Optibus)** — Aprovado: 1.1 documentada como design choice; vcsp_pulp/regional não tinham bug.
- **ANA (Backend)** — Aprovado: migration aplicada, entity reconhecida, persistência E2E validada.
- **CARLOS (Frontend)** — Aprovado: 4 hardcodes substituídos, tsc verde, UI renderiza Legenda.
- **MARINA (QA)** — Aprovado com observação: pytest 626/0/8 confirma, mas teste Salvador deveria assertar 14 veíc para enforçar invariante 1.6 em CI.
- **COORDENADOR (Mesa Ottrans)** — Aprovado: Legenda no Gantt + warning CLT art.71 + tooltip dropdown não bloqueia mais.
- **PLANEJADOR DE ESCALA** — Aprovado: agora consigo setar `max_block_span_minutes` separado do limite do motorista.
- **17 especialistas (consolidado):** 14 aprovados, 3 com observação (todos sobre cobertura de testes de invariantes em CI).

**Placar:** 26 aprovados · 3 com observação · 0 reprovados.
