# Rascunho — Plano de Melhorias (sessão 2026-05-25)
**Status:** PROPOSTA — nada será executado sem seu OK explícito.
**Foco prioritário (pedido do usuário):** solver e algoritmos. Garantia de correção.

---

## Princípios

1. Só faço o que é **melhoria real** (afeta comportamento, custo, correção).
   - Cosmético sem benefício mensurável → fora.
2. Cada fase tem **critério de sucesso verificável** antes de marcar como done.
3. Não invento. Cada item tem `arquivo:linha`.
4. CLAUDE.md `§5` (invariantes do solver) é a fonte da verdade pra Fase 1.

---

## Fase 1 — Auditoria de invariantes do solver  🔴 **PRIORIDADE MÁXIMA**

CLAUDE.md (§5 Domain Knowledge) e memória de sessões enumeram 6 invariantes
críticos. Vou auditar **cada um** com check estático + (se possível) probe runtime:

| # | Invariante | Arquivo alvo (verificar) | Critério de sucesso |
|---|---|---|---|
| 1.1 | `max_vehicle_shift_minutes` (driver) ≠ `max_block_span_minutes` (vehicle) — nunca conflatar | `optimizer/src/algorithms/vsp/{greedy,mcnf,branch_and_price,assignment}.py`; `joint_opt.py` | Cada algoritmo lê os 2 params separadamente; nenhum reaproveita um pelo outro silenciosamente |
| 1.2 | Set Partition `== 1`, não `>= 1` | `optimizer/src/algorithms/csp/set_partitioning.py`; `set_partitioning_optimized.py` | Constraint do MIP é `pulp.LpConstraintEQ`/`==`, não `>=` |
| 1.3 | `pairing_delta` subtraído de `marginal_cost` antes de virar `connection_cost` | `optimizer/src/algorithms/vsp/greedy.py` | grep por `pairing_delta` + leitura: `connection_cost ≥ 0` sempre |
| 1.4 | Cache fingerprint NÃO inclui componente temporal | grep `time.time()` em código de cache | Nenhum cache key tem `// 3600` ou `time.time()` |
| 1.5 | Async FastAPI routes não bloqueiam | `optimizer/src/api/routes/*.py`; `backend/src/modules/operations/*.controller.ts` | `async def` que chama Celery/blocking → usa `asyncio.to_thread` ou equivalente |
| 1.6 | Lower-bound MCNF para Salvador 298 trips = 14 veículos | tests/ou benchmark | Executar instância salvador.json se existir; senão pular com nota |

**Probe runtime opcional** — se eu conseguir ler `INTERNAL_SECURITY_KEY` via
Python sem expor (já tentei e falhou no turno anterior por permissão), rodo
otimização live com 3 algoritmos (mcnf, branch_and_price, vcsp_pulp) e:
- Conto eventos por bloco
- Confirmo zero overlap de trips no mesmo bloco
- Verifico `total_cost > 0`
- Verifico `len(unique_trip_ids_assigned) == len(trips)` (cobertura total)

**Suite de testes** — rodar `pytest -q optimizer/tests` se possível e mostrar
contagem. Tempo estimado: ~3 min se infra OK.

**Tempo total:** ~15 min.
**Risco:** nenhum (audit-only, sem edit).
**Saída:** seção nova em `VALIDACAO_REAL_2026_05_25.md` com verdict ✅/🔴 para cada
invariante + lista de bugs reais se houver.

---

## Fase 2 — Gantt: hardcodes que ignoram CCT do tenant  🔴 **MELHORIA REAL**

**Problema (já documentado em VALIDACAO_REAL §2.3):** o componente decide o
que é "refeição" vs "descanso" usando constantes fixas, ignorando o que o
tenant configurou.

| # | Local | Hardcode | Fix |
|---|---|---|---|
| 2.1 | `TabGantt.tsx:731` | `const BREAK_REST = 30;` | Usar `intervalPolicy.minBreakMinutes` (já existe no escopo) |
| 2.2 | `TabGantt.tsx:659` | `intervalKind = dur >= 60 ? 'refeicao' : 'descanso'` | Usar `intervalPolicy.mealBreakMinutes` |
| 2.3 | `TabGantt.tsx:734` | `const isMeal = dur >= 60;` | Mesma policy |
| 2.4 | `TabGantt.tsx:1058` | `gap >= 30 ? 'normal_break' : 'idle'` | Usar `intervalPolicy.minBreakMinutes` |

**Por que é melhoria real:** se tenant configurou `meal_break_minutes=60` (CLT
art.71 jornada >6h) e `min_break_minutes=60`, hoje o Gantt rotula errado a metade
dos eventos. Coordenador da operação vê "Descanso obrigatório 30min" quando o
solver gerou 60min.

**Risco:** baixo — `buildEventsFromSegments` já recebe `intervalPolicy` indireta-
mente via prop. Preciso passar `intervalPolicy` para as funções que ainda usam
constantes.

**Tempo:** ~15 min.
**Critério de sucesso:** `tsc --noEmit` = 0 erros + grep pelas 4 constantes não
encontra mais hardcode.

---

## Fase 3 — Persistência `max_block_span_minutes`  🟡 **DECISÃO PENDENTE**

UI já manda o campo (turno anterior), mas backend não persiste — perde-se
no reload.

Mudanças:
- `backend/.../entities/company-parameters.entity.ts` — adicionar coluna
- `backend/.../migrations/` — nova migration TypeORM
- `backend/.../parameters.service.ts` — ranges + defaults
- `backend/.../optimization.service.ts` — propagar para `vsp_params`

**Risco:** migration é write em produção. Reversível por `down()`.

**Tempo:** ~20 min.
**Critério:** `tsc` ok + tenant consegue setar e o valor reaparece após F5.

---

## Fase 4 — Tooltips e legenda (OBS-001..005 da auditoria 2026-05-24)  🟢 **MELHORIA UX REAL**

Itens documentados, não corrigidos. Tudo low/medium severity mas afeta usuários
operacionais ("Coordenador" e "Planejador de Escala" da Mesa Ottrans).

| # | Item | Local |
|---|---|---|
| 4.1 | Tooltip "Gap Optimalidade" | KPI bar |
| 4.2 | Tooltip "Hard Issues" | KPI bar |
| 4.3 | Tooltip "Plano sem excessos críticos" | KPI bar |
| 4.4 | Tooltip ao hover em viagem do Gantt | Trip row |
| 4.5 | Legenda de cores dos veículos | Header do Gantt |

**Tempo:** ~25 min.

---

## Fase 5 — BUG-001 + BUG-002: tooltip persiste após seleção  🟢 **BAIXO**

Tooltip do dropdown de algoritmos não fecha ao selecionar. Provavelmente é
prop `enterTouchDelay` / `leaveTouchDelay` ou falta de `disableInteractive`.

**Tempo:** ~10 min.

---

## Fase 6 — Drag-drop: integrar ou deletar `TripDragDropEditor.tsx`  🟡 **DECISÃO**

Componente existe (305 linhas), ninguém importa. Duas opções:

**A) Deletar** — assumir que drag-drop não é prioridade agora. 5 min.
**B) Integrar** — precisa: backend endpoint para mover trip entre blocks, validação CCT pós-move, recálculo de custo. **Estimativa real: 4-8 horas.**

Vou recomendar **A** para esta sessão.

---

## Fora de escopo (proposta de pular)

- Split do `TabGantt.tsx` (2648 linhas) — refactor estrutural, sprint próprio.
- Specs novos para event paths — bom ter, mas não é "melhoria real" no sentido
  pedido (não muda comportamento). Sugiro adiar.
- Reescrever `regional_decomposition` ou `vcsp_pulp` — não há bug, só perfil
  diferente para escala.

---

## Vozes (preview — somente Fase 1 e 2, que são as substanciais)

**Fase 1 — Auditoria solver:**
- **[DR. PAULO — Matemático OR]** apoia: invariantes do CLAUDE.md são o
  contrato matemático. Audit estático é necessário antes de qualquer afirmação
  "está otimizando". Decisão: aprovado.
- **[ROBERTO — Ex-Optibus]** apoia, com observação: probe runtime deveria
  incluir comparação com Optibus benchmark salvar como CSV. Decisão: aprovado.
- **[ANA — Backend]** apoia: sem audit a gente está fazendo cargo cult. Decisão: aprovado.
- **[MARINA — QA]** apoia, exige: cada `✅` precisa de `arquivo:linha` ou número
  de teste citado. Decisão: aprovado.

**Fase 2 — Gantt CCT hardcodes:**
- **[COORDENADOR DE OPERAÇÕES — Mesa Ottrans]** apoia forte: rotulagem errada
  do intervalo é o que mais me dá retrabalho. Decisão: aprovado.
- **[PLANEJADOR DE ESCALA — Mesa Ottrans]** apoia: se a CCT do meu tenant fala
  60min, o sistema mostrar 30 é mentira. Decisão: aprovado.
- **[CARLOS — Frontend]** apoia: edits cirúrgicos, tsc protege. Decisão: aprovado.

---

## Pergunta para você

Escolha qual conjunto executar:

- **Conjunto MÍNIMO:** Fase 1 + Fase 2  (≈30 min, zero risco persistente)
- **Conjunto MÉDIO:** Fase 1 + 2 + 3 + 4 + 5  (≈90 min, inclui migration)
- **Conjunto COMPLETO:** todas + decidir Fase 6  (≈100 min)
- **Personalizado:** diga quais fases (ex: "1, 2 e 4 apenas")

Diga qual e eu executo passo a passo, mostrando voice + evidência a cada fase.
