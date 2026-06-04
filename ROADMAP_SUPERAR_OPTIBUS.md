# ROADMAP — Superar o Optibus (handoff para agentes de IA / Antigravity)

> **Propósito:** documento vivo para qualquer agente de IA (Antigravity, Claude, Codex)
> continuar o trabalho de otimização VSP/CSP do OTIMIZ **sem se perder**. Contém: estado
> atual (o que NÃO refazer), invariantes que NÃO podem ser quebrados, e o backlog
> priorizado com **COMO FAZER** (passos, arquivos, comandos, critério de pronto).
>
> **Leia também:** `CLAUDE.md` (§5 = invariantes do otimizador), `AGENTS.md` (protocolo
> operacional), `artifacts/RELATORIO_OTIMIZ_vs_OPTIBUS_2026-06-04.md` (a comparação real).
>
> **Última atualização:** 2026-06-04. **Mantenha esta data e o §1 atualizados a cada PR.**

---

## 0. TL;DR para o agente

- O OTIMIZ **supera o Optibus no hub (Mussurunga 35 vs 36)** e **empata no radial (Mirantes 82 vs 82)** após a execução de T1 (matriz de deadhead real). A suíte tem **684 passed / 0 failed / 5 skipped**.
- O **caminho foi T1 (matriz de deadhead real)**, que removeu a distorção do proxy e liberou os turnarounds de 0 minutos.
  Tudo o mais é refinamento ou paridade de features.
- **NÃO reabra** BUG A/B/C nem a regra de deadhead (já corrigidos — §2). NÃO conflate
  `max_block_span` (1440, veículo) com `max_vehicle_shift` (960, motorista).
- Antes e depois de QUALQUER mudança: rode a suíte (§4) e o harness de comparação (§4).
  **Nunca** rode suíte + sweep ao mesmo tempo (contenção de CPU distorce os números).

---

## 1. ESTADO ATUAL (o que já está feito — NÃO refazer)

Branch: `fix/optimizer-regional-dedup-deadhead-proxy`.

| Commit | O quê |
|---|---|
| `2017089` | BUG A — encadeamento gap=0 no mesmo terminal |
| `ac30744` | BUG B (span de bloco) + BUG C (dedup B&P) + deadhead inferido + testes + relatório |

**Placar (limpo, determinístico):**

| Instância | LB | Optibus | OTIMIZ | Status |
|---|---|---|---|---|
| Mussurunga (hub, 696 viagens) | 35 | 36 / 80 jornadas | **35** (regional) | supera 🏆 |
| Mirantes (radial, 554 viagens) | 73 | 82 / 149 jornadas | **82** (hybrid_pipeline) | empata ✅ |

**Comparação de jornadas (crew): AINDA NÃO FEITA de forma justa** — rodou com
`cct_params={}` (regras default). Ver T2.

---

## 2. INVARIANTES — NÃO QUEBRE (regressão garantida se quebrar)

Cada um destes já foi um bug corrigido nesta base. Há testes que os protegem.

1. **`max_block_span_minutes` (1440 = dia do veículo) ≠ `max_vehicle_shift_minutes`
   (960 = jornada do motorista).** O span do **bloco-veículo** usa `max_block_span`. A
   jornada do motorista é restrição de **CSP**. Um ônibus roda ~21h servido por 2-3
   motoristas (run-cutting). Sites já corrigidos: `optimizer/src/algorithms/utils.py`
   (`extract_connection_params`), `vsp/assignment.py`, `vsp/mcnf.py`,
   `vsp/branch_and_price.py`, `joint_opt_boundary.py`. Testes:
   `test_heavy_real::test_vehicle_shift_respected`,
   `test_vsp_tolerance_and_multiline::test_no_merge_when_shift_exceeded`,
   `test_stress_mcnf::test_mcnf_vs_greedy_stress_reduction`.
2. **gap=0 entre viagens distintas só é viável no MESMO terminal
   (`destination_id == origin_id`) e quando `required = max(min_layover, deadhead) ≤ 0`.**
   Arquivo: `utils.py::_is_connection_feasible_logic`. Testes:
   `test_regulatory_rules::test_vsp_enforces_min_layover_even_same_terminal`,
   `::test_optimizer_avoids_short_layover_in_output_solution`.
3. **Partição: cada viagem em EXATAMENTE 1 bloco/duty (`== 1`, nunca `>= 1` sem dedup).**
   `set_partitioning*.py` usa `== 1`. `branch_and_price` usa covering + dedup na
   reconstrução. Checar sempre: `placed == unique == total`, `dups == 0`.
4. **Deadhead:** sem lat/long, estima-se pelo menor trecho de serviço × `0.6`
   (`deadhead_service_time_factor`). Com lat/long, usa haversine. Pares sem rota = proibido.
   Arquivo: `optimizer_service.py::_ensure_deadhead_coverage`.
5. **Cache fingerprint nunca inclui tempo** (`time.time()//3600`) — quebra TTL.
6. **Rotas async FastAPI:** nunca `.delay()` bloqueante; use `await asyncio.to_thread(...)`.

---

## 3. BACKLOG PRIORIZADO — como SUPERAR o Optibus

> Formato por tarefa: **objetivo · por quê · COMO (passos) · arquivos · validação ·
> pronto quando · risco**. Marque `[x]` ao concluir e atualize o §1.

### [x] T1 — Matriz de deadhead REAL (geo/GTFS)  ⭐ PRIORIDADE MÁXIMA
- **Objetivo:** Mirantes ≤ 82 (superar). É o ÚNICO lever honesto que falta.
- **Por quê:** hoje o deadhead é proxy (trecho de serviço × 0,6). O Optibus usa matriz
  real terminal→terminal. O proxy superestima trajetos longos → +4 veículos no Mirantes.
- **COMO:**
  1. Obter coordenadas reais das paradas. Fontes: GTFS `stops.txt` da OTTrans, ou
     geocoding dos `Origin/Destination Stop Id`. (Pergunte ao usuário se há GTFS.)
  2. Popular `Trip.origin_latitude/longitude` e `destination_latitude/longitude` no
     ingest (backend `operations.service` parser de upload) e no harness
     `scratch/compare_optibus.py` (hoje não seta coords).
  3. `_ensure_deadhead_coverage` JÁ usa haversine (`fallback_deadhead_speed_kmh`, default
     18 km/h) quando há coords — ajuste a velocidade p/ a realidade urbana de Salvador.
  4. ALTERNATIVA superior: ingerir matriz terminal→terminal de um roteador real
     (OSRM/Google/Here) → pré-popular `trip.deadhead_times[origin_id]` (respeitado por
     `_ensure_deadhead_coverage`, que só preenche o que falta).
  5. Validar com a matriz REAL do Optibus (10 pares no arquivo Mirantes) como sanity.
- **Arquivos:** `optimizer/src/services/optimizer_service.py`
  (`_ensure_deadhead_coverage`, `_estimate_deadhead_minutes`, `_haversine_km`);
  `optimizer/src/domain/models.py` (Trip já tem os campos lat/long);
  backend parser de upload (popular coords); `scratch/compare_optibus.py`.
- **Validação:** `./venv/bin/python scratch/compare_optibus.py "<Mirantes>.xlsx"
  --out artifacts/cmp_mir_geo.json --config fair --budget 30` → best ≤ 82.
- **Pronto quando:** Mirantes best ≤ 82 com deadhead derivado de coords/matriz reais E
  suíte verde E sem rota inventada (deadhead ≥ haversine físico).
- **Risco:** depende de dado externo (coords). Sem ele, 86 é o teto honesto.

### [ ] T2 — Calibração CCT e comparação JUSTA de jornadas (crew)
- **Objetivo:** comparar e bater jornadas (Optibus 80 / 149).
- **Por quê:** hoje rodamos `cct_params={}` → OTIMIZ gera ~96-112 / ~185-195 (mais
  jornadas, mais curtas). Não é comparação justa: depende das regras "Nova"/"Regra Antiga".
- **COMO:**
  1. Levantar com o usuário/OTTrans os parâmetros exatos das regras "Nova" e "Regra
     Antiga" (jornada máx, intervalo mín, pausa após X de condução, DSR, etc.).
  2. Mapear para `cct_params`: `max_shift_minutes`, `min_break_minutes`,
     `mandatory_break_after_minutes`, `max_driving_minutes`, `weekly_rest_minutes`,
     `pullout_minutes`/`pullback_minutes`, `allow_relief_points`.
  3. Passar no harness e medir `len(res.csp.duties)` e `res.csp.cct_violations`.
  4. Há um scratch exploratório `test_mcnf_plus_csp.py` (raiz, não rastreado): "36V fixos
     → quantos motoristas o CSP acha". Reaproveitar/expandir.
- **Arquivos:** `optimizer/src/algorithms/csp/greedy.py` (parâmetros CCT),
  `operational_time_service`, `scratch/compare_optibus.py` (passar cct_params reais).
- **Pronto quando:** com regras equivalentes às do Optibus, duties ≤ 80/149 e
  `cct_violations == 0`. Atualizar §7 do relatório.
- **Risco:** sem as regras exatas, comparação fica indicativa.

### [ ] T3 — `regional` fraco/regressão
- **Objetivo:** `regional` deixar de ser o pior (hoje 41 Muss / 98 Mir).
- **COMO:** revisar `vsp/regional_decomposition.py` (decomposição por região degrada em
  multi-terminal radial); OU no dispatcher, escolher por custo entre `regional` e
  `mcnf/assignment` (fallback automático). Conferir se BUG B/deadhead regrediram (era 35).
- **Arquivos:** `vsp/regional_decomposition.py`, dispatcher em `optimizer_service.py`.
- **Pronto quando:** `regional` ≤ melhor-2 nas duas instâncias, ou fallback ativo.

### [ ] T4 — B&P com set-partitioning (`==1`) de verdade
- **Objetivo:** otimalidade comprovada (hoje é covering `>=1` + dedup heurístico).
- **COMO:** no master de `vsp/branch_and_price.py` (linhas ~110/138/221), avaliar trocar
  `>= 1` por `== 1`, garantindo colunas-singleton no pool para viabilidade. Comparar
  contagem de veículos antes/depois; manter o dedup como rede de segurança.
- **Pronto quando:** B&P ≤ contagem atual, 0 duplicatas, suíte verde.

### [ ] T5 — `deadhead_service_time_factor` por operador / auto-tune
- Expor por empresa; 0,6 é default calibrado (Optibus 43min real / 67min serviço ≈ 0,64).

---

## 4. PLAYBOOK DE VALIDAÇÃO (sempre antes/depois)

```bash
cd "/home/edvanilson/Área de trabalho/Novo_OTIMIZ/optimizer"

# 1) Suíte completa (baseline = 684 passed / 0 failed / 5 skipped). ~12 min.
./venv/bin/python -m pytest tests/ -q -p no:cacheprovider

# 2) Comparação real OTIMIZ vs Optibus (17 algoritmos). ~10 min por instância.
./venv/bin/python scratch/compare_optibus.py \
  "../Estação Mussurunga - Sábado - Nova_full_schedule.xlsx" \
  --out ../artifacts/cmp_mussurunga_clean.json --config fair --budget 30
./venv/bin/python scratch/compare_optibus.py \
  "../Mirantes-Base2-NovasRegrasIntervalo com Regra Antiga_full_schedule.xlsx" \
  --out ../artifacts/cmp_mirantes_clean.json --config fair --budget 30

# 3) Bench sintético dos 17 algoritmos (invariantes de qualidade).
./venv/bin/python scratch/bench_all_algorithms.py --lines 2 --scale 2.1 --budget 60 \
  --out ../artifacts/bench.json --repeat 2   # --repeat 2 = checa determinismo
```

**Critérios de aceite de QUALQUER mudança no VSP/CSP:**
- Suíte: 684 passed / 0 failed (ou mais; nunca menos sem justificativa escrita).
- Comparação: cobertura `== total`, `overlaps == 0`, `dups == 0` em todos os algos.
- Determinismo: rode 2-3× o algoritmo alterado; `(veículos, custo)` idênticos.
- Não pioran o melhor-por-instância (Muss 36, Mir 86) sem justificativa.

---

## 5. TUDO QUE FALTA (gaps vs Optibus, além de T1-T5)

**Otimização (núcleo):**
- Matriz de deadhead real (T1) — o gap concreto.
- Comparação de jornadas calibrada (T2).

**Paridade de plataforma (features que o Optibus tem e o OTIMIZ não):**
- **Rostering multi-dia + preferências de motorista** (Optibus "Preference Designer"/GenAI).
- **Controle em tempo real / operação ao vivo** (Optibus real-time control).
- **Informação ao passageiro** (Optibus passenger info).
- Maturidade/escala provada (Optibus: 1M+ otimizações). OTIMIZ tem diferenciais que o
  Optibus não documenta: **replay reproduzível (fingerprint/seed)** e **equidade (Gini)**.

**Higiene/produção (de auditorias anteriores — ver MEMORY do projeto):**
- JWT refresh, Body DTOs, backup PG, Redis auth (pendentes P1 da auditoria 2026-05-20).

**Limpeza:**
- `test_mcnf_plus_csp.py` na raiz é scratch não rastreado (exploração crew) — mover para
  `optimizer/scratch/` ou remover.

---

## 6. PITFALLS desta base (lições — economize tempo)

- **Docker é o runtime real**, não o nativo. Fix no optimizer só chega no browser com
  **rebuild da imagem** (optimizer+celery) E **flush do redis db2** (cache por fingerprint
  mascara com hit ~140ms). Frontend `.tsx` também é imagem buildada.
- **Sweeps são block-buffered:** o JSON só aparece ao FIM de cada instância; logs `*.log`
  mostram ruído de `[PARAMS-AUDIT]` no meio. Não confie em "parou" pelo log.
- **Contenção de CPU distorce algoritmos com time-budget** (SA/tabu/alns/genetic e até o
  pós-processamento). Rode sweep e suíte **sequencialmente**, nunca juntos.
- **O `svc.run()` faz o pipeline inteiro** (VSP + CSP + stitch + reconciliação); o número
  de veículos é `len(res.vsp.blocks)` APÓS pós-processamento, não só o VSP puro.
- **Segmentos `_1/_2` do Optibus** são timepoints de uma mesma viagem → remontar por
  ID-base (já feito em `compare_optibus.load_optibus`).
- **Login/runtime:** admin@otimiz.com / Otimiz@123; backend :3001; optimize rate-limit
  5/5min (429). Ver MEMORY `optimizer_fix_deploy_gotcha`.

---

## 7. ARQUIVOS-CHAVE

| Papel | Caminho |
|---|---|
| Harness de comparação Optibus | `optimizer/scratch/compare_optibus.py` |
| Bench dos 17 algoritmos | `optimizer/scratch/bench_all_algorithms.py` |
| Viabilidade de conexão VSP (gap/deadhead/span) | `optimizer/src/algorithms/utils.py` |
| Pipeline/serviço + deadhead coverage | `optimizer/src/services/optimizer_service.py` |
| Modelos (Trip, Block, VehicleType…) | `optimizer/src/domain/models.py` |
| CSP/jornadas (CCT) | `optimizer/src/algorithms/csp/greedy.py` |
| Relatório da comparação | `artifacts/RELATORIO_OTIMIZ_vs_OPTIBUS_2026-06-04.md` |
| Dados Optibus (entrada) | `*.xlsx` na raiz (Mussurunga, Mirantes) |
| Saídas da comparação | `artifacts/cmp_*_{fair,clean}.json` |

---

## 8. COMO MANTER ESTE DOC ATUALIZADO (para não se perder)

A cada PR que mexa em VSP/CSP/comparação:
1. Atualize o **§1 (placar + commits)** e a **data** do topo.
2. Marque `[x]` as tarefas concluídas do §3 e mova o aprendizado para §2/§6 se virar invariante.
3. Rode o §4 e cole os números no relatório `artifacts/RELATORIO_OTIMIZ_vs_OPTIBUS_*.md`.
4. Se descobrir um novo invariante, **adicione um teste** que o proteja e cite em §2.
