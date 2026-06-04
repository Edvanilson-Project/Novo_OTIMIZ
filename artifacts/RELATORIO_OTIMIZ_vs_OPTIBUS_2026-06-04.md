# Relatório técnico — OTIMIZ vs Optibus (comparação real + correções)

**Data:** 2026-06-04
**Instâncias reais (export Optibus `_full_schedule`):**
- `Estação Mussurunga - Sábado - Nova` (hub urbano, viagens curtas, 1 terminal central)
- `Mirantes-Base2-NovasRegrasIntervalo com Regra Antiga` (radiais longas, multi-terminal)

**Postura:** sincero, realista, cirúrgico. Onde o OTIMIZ perde, está escrito que perde,
com o porquê. Onde ganha, está provado com número, método reproduzível e suíte verde.

---

## 1. Resumo executivo

| Instância | Viagens | LB | **Optibus** | OTIMIZ inicial | **OTIMIZ final** | Veredito |
|---|---|---|---|---|---|---|
| Mussurunga | 696 | 35 | **36** | 45 (+25%) | **36** (16/17 algos) | **empata o Optibus** |
| Mirantes | 554 | 73 | **82** | 87 (+6%) | **86** (B&P) / 87 | **+4,9%**, gap real de deadhead |

**Conclusão:** o OTIMIZ não estava pior por incapacidade dos algoritmos — estava pior por
**bugs de modelagem**. Corrigidos, ele **empata o Optibus no hub (Mussurunga, 36)** e fica
a **+4,9% no radial multi-terminal (Mirantes, 86 vs 82)**. O resíduo do Mirantes é
otimização de *deadhead*/reposicionamento com matriz geográfica real — área onde o Optibus
é genuinamente mais maduro e que este export (só com IDs de parada, sem lat/long) não traz.

> Transparência: com o BUG A sozinho + um deadhead plano "afortunado" (flat 20-30 min,
> fisicamente otimista), o OTIMIZ chega a **35 no Mussurunga (supera) e 84-85 no Mirantes**.
> Optei por **deadhead realista** (ver §5.4): não fabrico vitória com reposicionamento
> fisicamente implausível.

---

## 2. Metodologia (por que é justa)

1. **Só viagens extraídas.** `Event Type == service_trip` = timetable (entrada).
   `Vehicle Block Id`/`Duty id` = solução do Optibus (baseline). Segmentos `_1/_2`
   remontados em viagens reais (2218→696; 724→554) — invariante para nº de veículos.
2. **Calibrado pelo próprio Optibus:** `min_layover=0` (encadeia back-to-back),
   `max_block_span=1440` (blocos de até 21h), deadhead inferido da timetable (§5.4).
3. **17 algoritmos** rodados em ambas, com checagem de viabilidade (cobertura `== total`,
   zero sobreposição, zero duplicata). Medições **limpas e determinísticas** (sem carga
   concorrente; confirmado mcnf×3 e regional×3 idênticos).
4. **Reprodutível:** `optimizer/scratch/compare_optibus.py`; saídas
   `artifacts/cmp_{mussurunga,mirantes}_clean.json`.

---

## 3. Baseline Optibus

| Métrica | Mussurunga | Mirantes |
|---|---|---|
| Viagens reais | 696 | 554 |
| Limite inferior (concorrência) | 35 | 73 |
| **Veículos / Jornadas** | **36 / 80** | **82 / 149** |
| Jornadas por veículo | 2,22 | 1,82 |
| km comercial / morto | 9.784 / 0 (0%) | 15.856 / 693 (4,4%) |
| Span do bloco-veículo (máx) | 14,8h (21,2h) | 13,7h (19,6h) |
| Jornada média do motorista | 6,6h | 6,4h |
| Deadhead: eventos / pares / mediana | 0 / 0 / — | 32 / 10 / 43min |

> Jornadas/veículo > 1 confirma **run-cutting** (1 ônibus, vários motoristas/dia):
> span do veículo (≈15h) ≫ jornada do motorista (≈6,5h) — invariante `CLAUDE.md §5`.

---

## 4. Resultado final por algoritmo (limpo, determinístico)

### Mussurunga — Optibus 36 | LB 35
16/17 algoritmos = **36** (greedy, mcnf, assignment, hybrid, B&P, joint_bp, joint_solver,
SA, tabu, alns, set_part., vcsp, lagrangean, bundle, genetic, joint_timetable).
`regional` = 41 (algoritmo fraco aqui — nunca é o melhor). **Melhor = 36 = Optibus.**

### Mirantes — Optibus 82 | LB 73
`branch_and_price` = **86** (melhor); maioria = **87**; `regional` = 98.
**Melhor = 86 (+4,9%).** Todos 17/17 viáveis, 554/554 cobertos, 0 duplicatas.

---

## 5. Bugs encontrados e CORRIGIDOS

### 5.1 BUG A — gap=0 entre viagens distintas era proibido ✅ (commit `2017089`)
`utils.py::_is_connection_feasible_logic` rejeitava todo `gap==0` entre viagens distintas
(só permitia mesmo `trip_group_id`). **Prova:** o OTIMIZ rejeitaria **51% (Mussurunga) /
55% (Mirantes)** das conexões do próprio Optibus (encadeamentos gap=0 no mesmo terminal).
**Fix:** gap=0 viável com turnaround instantâneo no mesmo terminal
(`destination_id==origin_id`) E `required=max(min_layover,deadhead) ≤ 0`. `min_layover>0`
preserva o turnaround técnico. Efeito: Mussurunga 45→36, Mirantes 87→86. Beneficia os 15
algoritmos de VSP.

### 5.2 BUG B — span do bloco limitado pela jornada do motorista ✅
O span do **bloco-veículo** era limitado por `max_vehicle_shift_minutes` (960=motorista) em
vez de `max_block_span_minutes` (1440=dia do veículo). Violava `CLAUDE.md §5`. Causava a
falha **pré-existente** `test_stress_mcnf` ([MCNF-SPLIT] em 960).
**Fix em 6 arquivos** (`utils.extract_connection_params`, `vsp/assignment`, `vsp/mcnf`,
`vsp/branch_and_price`, `joint_opt`, `joint_opt_boundary`): o span do bloco usa
`max_block_span_minutes` (1440); a jornada do motorista é restrição de CSP. **2 testes que
fixavam a semântica errada foram atualizados** para o parâmetro correto (`max_block_span_minutes`).
`test_stress_mcnf` agora **passa**.

### 5.3 BUG C — sobre-cobertura (viagem duplicada) ✅
`branch_and_price` colocava 26 viagens em 2 blocos (covered 580/554) — o master usa
covering (`>=1`) e colunas selecionadas se sobrepunham (`CLAUDE.md §5`: deveria ser `==1`).
**Fix:** dedup na reconstrução — cada viagem entra em exatamente UM bloco. Resultado: B&P
554/554, **0 duplicatas**, em ambas as instâncias. (`joint_bp` já ficou correto após A/B.)

### 5.4 Modelagem de deadhead/reposicionamento ✅ (melhoria)
Antes: sem lat/long, pares entre terminais distintos = `999999` (proibido) → o OTIMIZ não
reposicionava (regional Mussurunga = **50**). **Fix** (`_ensure_deadhead_coverage`): infere
o deadhead terminal→terminal pelo **menor tempo de serviço observado entre os terminais**,
escalado por `deadhead_service_time_factor` (default **0,6**, pois o trecho vazio é mais
rápido que o trecho com paradas). Calibração validada contra o Optibus: deadhead real
mediano 43min / trecho de serviço ~67min → fator ≈ 0,64 ≈ 0,6.
Efeito: habilita reposicionamento realista; regional Mussurunga 50→**41**; Mirantes viável
em todos os 17. Pares sem rota de serviço continuam proibidos (correto).

---

## 6. Suíte de testes (gate de regressão)

| Estado | passed | failed | skipped |
|---|---|---|---|
| Original (antes de tudo) | 683 | 1 (`test_stress_mcnf`, pré-existente) | 5 |
| **Final (A+B+C+deadhead)** | **684** | **0** | **5** |

Confirmado: suíte completa **684 passed, 0 failed, 5 skipped** (703s). Mudanças de teste:
apenas 2 testes que codificavam a semântica errada de BUG B foram ajustados ao parâmetro
correto (`max_block_span_minutes`), preservando a intenção.

---

## 7. Jornadas (crew) — comparação ainda não calibrada

| | Optibus | OTIMIZ (CCT default) |
|---|---|---|
| Mussurunga | **80** | ~96–112 |
| Mirantes | **149** | ~185–195 |

**Ressalva honesta:** rodei com `cct_params={}` (regras default). A contagem de jornadas
depende fortemente das regras "Nova"/"Regra Antiga" que o Optibus aplicou e que este export
não traz. **A comparação de jornadas NÃO é conclusiva** — é lacuna de calibração de CCT, não
necessariamente de qualidade. O motor de jornadas do OTIMIZ (DSR 2100min, limites
quinzenais, run-cutting com relief, pausas CTB Art. 67-C) é detalhado para o Brasil.

---

## 8. OTIMIZ vs Optibus — todos os aspectos

| Aspecto | OTIMIZ | Optibus | Avaliação |
|---|---|---|---|
| **Nº de veículos (VSP)** | 36 / 86 | 36 / 82 | **Empata** no hub; **+4,9%** no radial |
| Algoritmos expostos | **17** | motor proprietário | OTIMIZ mais variedade |
| **Deadhead / reposicionamento** | inferência da timetable (proxy) | **matriz geográfica real** | **Optibus melhor** (gap do Mirantes) |
| Conformidade trabalhista | **CLT/CTB/CCT BR nativo** | genérica configurável | OTIMIZ mais específico p/ BR |
| EV (SoC/recarga) | sim (B&P 6D) | sim | par |
| Run-cutting / relief mid-trip | sim | sim | par |
| Recuperação de disrupção | sim | sim + tempo-real | Optibus mais maduro |
| Reprodutibilidade / replay | **sim (fingerprint/seed)** | n/d | OTIMIZ diferencial |
| Equidade (Gini) observável | **sim** | parcial | OTIMIZ diferencial |
| Rostering multi-dia / preferências | limitado | **forte (GenAI)** | **Optibus melhor** |
| Tempo real / passageiro | não | **sim** | **Optibus melhor** |
| Maturidade / escala provada | em construção | **1M+ otimizações** | **Optibus melhor** |
| Velocidade | 1–9s (instâncias reais) | "segundos a minutos" | par |

---

## 9. O que falta / próximos passos (priorizado)

1. **[ALTA] Matriz de deadhead real** (GTFS/geo) — fecha o gap do Mirantes; o proxy da
   timetable é aproximação. É o único caminho honesto para igualar/superar o Optibus no radial.
2. **[ALTA] Calibrar CCT** ("Nova"/"Regra Antiga") para tornar a comparação de **jornadas**
   justa (hoje inconclusiva — §7).
3. **[MÉDIA] `regional`** está fraco (41/98) e possivelmente regrediu — revisar a
   decomposição multi-terminal; ou fallback automático no dispatcher por custo.
4. **[MÉDIA] B&P set-partitioning** — avaliar `==1` no master (hoje covering+dedup) para
   otimalidade, com colunas-singleton garantindo viabilidade.
5. **[BAIXA] `deadhead_service_time_factor`** — expor por operador; 0,6 é default calibrado.

---

## 10. Reprodução

```bash
cd optimizer
./venv/bin/python scratch/compare_optibus.py \
  "../Estação Mussurunga - Sábado - Nova_full_schedule.xlsx" \
  --out ../artifacts/cmp_mussurunga_clean.json --config fair --budget 30
```

Artefatos: `artifacts/cmp_*_fair.json` (inicial) e `cmp_*_clean.json` (final, limpo).
Fixes: `optimizer/src/algorithms/utils.py`, `src/services/optimizer_service.py`,
`src/algorithms/vsp/{assignment,mcnf,branch_and_price}.py`,
`src/algorithms/{joint_opt,joint_opt_boundary}.py`.
