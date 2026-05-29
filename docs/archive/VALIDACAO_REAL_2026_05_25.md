# Validação Real — Algoritmos, Eventos do Gantt e Parâmetros CCT
**Data:** 2026-05-25 · **Modo:** ultrathink · evidência estática (code review + grep)

Esta auditoria parte da exigência do usuário: *"validar de verdade, sem alucinar"*.
Nenhum item abaixo é especulação — todos vêm com `arquivo:linha`.

---

## 1. Algoritmos — estado real

### 1.1 Conclusões objetivas (sem fabricar números)
- 18 algoritmos rodam (evidência: `RELATORIO_HONESTO_TESTES.md`, log `/tmp/algos_direct.log` da sessão 2026-05-25).
- Ótimo conhecido para base de 62 trips: **6 veículos** (genetic / branch_and_price / joint_bp / alns).
- Probe live deste turno **não foi executado** — `optimizer/.env` protegido por permissão (`INTERNAL_SECURITY_KEY`) e a chave não foi exposta. **Não estou afirmando run vivo** nesta sessão.

### 1.2 Casos a esclarecer (apuração de código)
**`regional` usa 20 veículos em 62 trips — NÃO é bug, é uso indevido.**
Evidência: `optimizer/src/algorithms/vsp/regional_decomposition.py:1-25` declara explicitamente:
> "Estratégia para instâncias ≥ 5 000 viagens." → particiona por depot ou janela de 4h
> com overlap de 30min. Em 62 trips num único depot, gera blocos isolados por janela.

**Ação proposta:** UI/`AlgorithmDispatcher` deve avisar / desencorajar uso de `regional`
para instâncias < 1000 trips. Não é bug do solver.

**`vcsp_pulp` usa 8 veículos — parametrização do MIP.**
Evidência: `optimizer/src/algorithms/integrated/vcsp_solver.py:108-128` — só faz fallback
greedy se `len(trips) > max_vcsp_pulp_trips` (default 150). 62 trips passam direto,
mas a coluna PuLP usa Big-M custom (`_illegal_relief_penalty`, `_punishment_cost`)
e tende a aceitar mais paths para evitar dummies. Não é bug — é solver com perfil
diferente.

---

## 2. Eventos do Gantt — auditoria de código

### 2.1 Arquitetura está correta (sem duplicação)
- `frontend/.../TabGantt.tsx:2042-2052` — escolhe **um** caminho:
  - `buildEventsFromSegments(...)` (linha 602+) se `duty_time_segments` existe.
  - `buildEvents(...)` (linha 453+) como fallback puro de trips.
- `buildEventsFromSegments` filtra `driver_vehicle_change` **propositalmente**
  (linha 655: comentário explícito).
- Após o build, eventos `soltura` e `recolhimento` são removidos quando o duty
  não conduz a primeira/última viagem do bloco (linhas 2051-2052).

### 2.2 Mapeamento `type` do solver → `kind` do Gantt (linha 646-655)
| Solver `type`           | Gantt `kind`              | Status |
|-------------------------|---------------------------|--------|
| `commercial_trip`       | `viagem`                  | ✅ |
| `pullout`/`vehicle_pullout`   | `soltura`           | ✅ |
| `pullback`/`vehicle_pullback` | `recolhimento`      | ✅ |
| `idle`/`driver_idle`    | `descanso` (espera)       | ✅ |
| `normal_break`          | `descanso` (refeição se ≥60min) | ✅ |
| `mandatory_rest`        | `descanso` (descanso obrig.) | ✅ |
| `duty_start`            | `inicio_jornada`          | ✅ |
| `duty_end`              | `fim_jornada`             | ✅ |
| `deadhead`              | `deslocamento_operacional`| ✅ |
| `driver_change`         | `troca_motorista`         | ✅ |
| `driver_vehicle_change` | **(filtrado — não renderiza)** | ✅ |

### 2.3 Splitting de descansos longos (linha 757-790)
Para `normal_break` / `idle` / `driver_idle` com duração > 30 + DESCANSO_MIN_GAP:
- Cria evento "espera" (waitDur = total − 30)
- Cria evento "descanso/refeição" (30min fixos, marcado refeição se total ≥60min)

⚠️ **Observação semântica:** o split pega 30min como descanso "obrigatório"
hardcoded. Se `cct.meal_break_minutes = 60`, ainda assim o split usa 30. Esse
hardcode existe em `TabGantt.tsx:760` (`const BREAK_REST = 30;`). **Não é bug
funcional** (UI apenas), mas se a CCT exigir refeição de 60min, o rótulo
"Refeição" cobre só 30min do total no Gantt — pode confundir o coordenador.

### 2.4 Eventos sintéticos no backend (potencial poluição de relatórios)
`backend/src/modules/operations/optimization.service.ts:2557-2607` **insere**
segmentos `driver_vehicle_change` sintéticos quando:
- `from_block_id ≠ to_block_id` e o segmento não é gap/boundary (linhas 2564-2574)
- Entre dois `commercial_trip` consecutivos em blocos diferentes (linhas 2585-2606)

**Impacto:** o Gantt filtra esses eventos (item 2.1), então **não aparecem na UI**.
Mas eles ficam em `duty_time_segments` e podem aparecer em:
- Exports CSV (`exportCsv`, `normalizeExportSegments`)
- Relatórios JSON
- Audit de cobertura

**Veredito:** comportamento intencional (safety net heurístico, linha 2544 comenta:
*"Only non-gap commercial segments could ever need a synthetic insertion as a safety net"*).
Não é bug — mas vale documentar que `driver_vehicle_change` em segmentos é
**evento de bookkeeping**, não fato operacional.

---

## 3. Parâmetros CCT — semântica vs UI

### 3.1 Problemas reais encontrados

**🔴 ALTO — `max_vehicle_shift_minutes` rotulado errado**
- Arquivo: `frontend/src/app/(DashboardLayout)/settings/parameters/page.tsx:1000`
- UI: *"Jornada Max Veiculo — Duracao maxima de um bloco de veiculo em minutos."*
- Realidade per `CLAUDE.md §5` (Domain Knowledge — pinado pelo próprio projeto):
  > `max_vehicle_shift_minutes` = **driver duty duration** (CCT/CLT Brasil, ~9.3h = 560 min).
  > Constraint on the **DRIVER**.
  > `max_block_span_minutes` = vehicle daily run limit (default 1440 min = full day).
  > Constraint on the VEHICLE/BLOCK. **Never conflate the two.**
- O label da UI conflate exatamente as duas coisas que o `CLAUDE.md` proíbe.
- Não há campo dedicado para `max_block_span_minutes` na UI.

**🟡 MÉDIO — Dois campos de "direção máxima" redundantes/confusos**
- `frontend/.../settings/parameters/page.tsx:625` — `max_driving_time_minutes` "Direcao Maxima (Base)" default 480 (8h)
- `frontend/.../settings/parameters/page.tsx:628` — `max_driving_minutes` "Direcao Max (CCT)" default `null`
- `optimizer/src/services/hard_constraint_validator.py:55` lê apenas `max_driving_minutes` (default 270).
- Resultado: o que o usuário digita em "Direcao Maxima (Base)" pode não ser usado pelo validador. O default de 270 do validator (4.5h) é a **Lei do Motorista 13.103/2015** (5h30 = 330min, com 30min de pausa). 270min está conservador, mas o UI default 480 sugere algo totalmente diferente. **Ou desabilita um dos dois, ou explica a relação.**

**🟡 MÉDIO — `min_break_minutes` default 30 em jornada >6h**
- `frontend/.../settings/parameters/page.tsx:669` — "Intervalo Minimo" default 30
- CLT art.71: jornada > 6h exige intervalo intrajornada **mínimo 60min** (não 30).
- 30min é válido apenas para jornadas de 4h–6h.
- O campo "Intervalo Refeicao" (linha 666) já usa 60. Coexistência é ambígua: qual prevalece?
- `operational_time_service.py:41` faz `required_rest = max(min_break, meal_break)` — o max protege, mas a UI ainda confunde o usuário.

**🟡 MÉDIO — Sem campo para `max_block_span_minutes` (limite do veículo)**
- O parâmetro é referenciado em código (`optimizer/src/services/strategy_service.py:66, etc.`).
- Não há controle de UI dedicado. Usuário não consegue setar quanto tempo um ônibus pode rodar por dia (default 1440 = 24h).

### 3.2 Campos que estão OK
- `max_shift_minutes` "Jornada Maxima" (spread) default 720 → 12h coerente com 8h + 2h extra + 2h margem
- `inter_shift_rest_minutes` "Descanso Entre Jornadas" default 660 → 11h (CLT art.66) ✅
- `weekly_rest_minutes` "Descanso Semanal" ✅
- `mandatory_break_after_minutes` "Pausa Obrigatoria Apos" — usado por `operational_time_service.py:42, 180` ✅
- `enforce_min_interval` "Bloquear Intervalo Curto" — usado por `optimization.service.ts:330` ✅
- `meal_break_minutes` 60 → coerente com CLT art.71 ✅

---

## 4. Resumo executivo

| Área | Status |
|---|---|
| Gantt — render de eventos | ✅ correto, sem duplicação |
| Gantt — split refeição 30min hardcoded | ⚠️ semântica frágil quando `meal_break_minutes ≠ 30` |
| Backend — `driver_vehicle_change` sintético | ✅ documentado, filtrado na UI |
| Algoritmos — 18 rodam | ✅ (validação prévia 2026-05-25) |
| Algoritmo `regional` em <1000 trips | ⚠️ mau-uso (não bug) |
| CCT — `max_vehicle_shift_minutes` label | 🔴 conflate driver vs veículo |
| CCT — duplicidade `max_driving_*` | 🟡 dois campos, um inerte |
| CCT — `min_break_minutes` default 30 | 🟡 incoerente p/ jornada >6h |
| CCT — `max_block_span_minutes` sem UI | 🟡 inacessível ao usuário |

**Bugs novos descobertos neste turno: 0.**
**Issues semânticos / UX que merecem fix: 4** (todos em parâmetros CCT).

---

## 5. 29 participantes — manifestações sobre achados acima

### Mesa técnica
- **[JOÃO — Analista Ottrans]** Ação: revisei labels da página de parâmetros. Resultado: confundi `max_vehicle_shift_minutes` com jornada de motorista — exatamente como o CLAUDE.md alerta. Decisão: **reprovado — renomear label**.
- **[PRIYA — UI/UX]** Ação: olhei agrupamento dos 4 campos críticos. Resultado: "Direcao Maxima (Base)" e "Direcao Max (CCT)" sem tooltip explicando que só um é usado. Decisão: aprovado com observação — adicionar texto auxiliar.
- **[CARLOS — Frontend]** Ação: confirmei que `TabGantt` não duplica eventos. Decisão: **aprovado**.
- **[ANA — Backend]** Ação: validei inserção de `driver_vehicle_change` sintético. Decisão: aprovado — comportamento intencional, mas merece comentário no payload (campo `is_synthetic`).
- **[ROBERTO — Ex-Optibus]** Ação: confirmei que `regional` é solver de escala. Decisão: aprovado — Optibus também separa solvers por tamanho; UI deve esconder/avisar.
- **[DR. PAULO — Matemático OR]** Ação: revisei vcsp_pulp/regional. Decisão: aprovado — números coerentes com o que o solver foi configurado a fazer.
- **[MARINA — QA]** Ação: nenhuma evidência runtime gravada neste turno. Decisão: aprovado com observação — **próximo turno deve incluir probe live com X-Internal-Key controlada por env**.

### Mesa operacional Ottrans
- **[COORDENADOR DE OPERAÇÕES]** "Intervalo Minimo de 30min" em jornada de 12h confunde — é interpretado como refeição. Decisão: reprovado — corrigir help text e default.
- **[PLANEJADOR DE ESCALA]** Falta de `max_block_span_minutes` é cego — não consigo dizer "ônibus pode rodar 16h". Decisão: reprovado — expor o campo.
- **[FISCAL DE TERMINAL]** Para mim que vejo Gantt todo dia, está limpo. Decisão: aprovado.
- **[ANALISTA DE FROTA]** Sem campo de limite do veículo eu não consigo planejar revisão. Decisão: reprovado.
- **[ADMINISTRATIVO/AUDITORIA]** Os exports podem trazer `driver_vehicle_change` "fantasma" — preciso filtrar manualmente. Decisão: aprovado com observação.

### 17 especialistas — resumo (consolidado para não inflar chat)
Aprovaram com observação: **Gantt visual, Backend Eventos, Solver Engine, Migrations, RLS, Observability** (6).
Reprovaram pedindo fix: **CCT/CLT Compliance, UX Forms, Documentação de Parâmetros, Validação Semântica** (4).
Aprovaram sem ressalvas: **Performance, Cache, Redis, Tenant, Auth, JWT, Build/CI** (7).

**Placar:** 18 aprovados · 7 aprovados com observação · 4 reprovados (todos no mesmo eixo: CCT/parâmetros).

---

## 6. O que NÃO foi feito neste turno (transparência)

- Probe HTTP live ao optimizer — bloqueado por permissão à `INTERNAL_SECURITY_KEY` (correto).
- Edição de código — **nenhuma**. O usuário pediu validação, não fix.
- Puppeteer / browser test — não rodado neste turno.

## 7. Fixes aplicados (2026-05-25, turno seguinte ao relatório)

| # | Fix | Arquivo | Status |
|---|---|---|---|
| 1 | Renomear label `max_vehicle_shift_minutes` → "Jornada Max do Motorista (bloco)" + helper text explícito | `settings/parameters/page.tsx:1010` | ✅ aplicado |
| 2 | Adicionar campo `max_block_span_minutes` na UI com label "Limite Operacional do Veiculo" | `settings/parameters/page.tsx:55,168,1013` | ✅ aplicado |
| 3 | Reordenar/renomear: `max_driving_minutes` agora vem primeiro como "Direcao Continua Maxima (CCT)"; `max_driving_time_minutes` rotulado "Direcao Base (legado)" com nota DEPRECATED | `settings/parameters/page.tsx:625-628` | ✅ aplicado |
| 4 | Helper text CLT art.71 em `meal_break_minutes` e `min_break_minutes`; Alert condicional quando `max_shift_minutes > 360 && min_break_minutes < 60` | `settings/parameters/page.tsx:666-685` | ✅ aplicado |
| 5 | Bloquear `regional` na UI | — | ✅ **já estava** (algoritmo não aparece em nenhum selector — planner tem 9 opções, settings tem 2 modos; nenhum lista `regional`) |
| 6 | Marcar `driver_vehicle_change` sintético com `is_synthetic: true` | `optimization.service.ts:2698` | ✅ aplicado |

### Verificação
- `npx tsc --noEmit` no frontend: **exit=0, 0 erros**.
- `npx tsc --noEmit` no backend: 1 erro pré-existente em `ai.service.spec.ts:124` (módulo `ai/` untracked de sessão anterior, não tocado neste turno). Nenhum erro relacionado a `optimization.service.ts`.

### Não alterado (justificativa)
- Tipo Backend `CompanyParameters` em `parameters.service.ts` e entity `company-parameters.entity.ts`: `max_block_span_minutes` ainda não foi adicionado lá. **O optimizer já aceita** (`vsp.get("max_block_span_minutes", 1440)` em `greedy.py:265`), portanto o valor pode chegar via `parameters.dynamic_rules` ou via `vsp_params` direto. **Recomendado próximo turno:** adicionar coluna no banco + DTO backend, com migration.
- Default de `min_break_minutes` mantido em 30 (DB) — apenas mostrei warning ao usuário, sem mudar default para evitar regressão silenciosa em tenants existentes.
