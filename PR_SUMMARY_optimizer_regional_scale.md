# PR: Optimizer — regional dedup, deadhead-aware objective & scale robustness

**Branch:** `fix/optimizer-regional-dedup-deadhead-proxy` → `main`
**Commits:** 9
**Tipo:** fix / feat / test / docs / chore (optimizer)

---

## Resumo

Sequência de correções e melhorias no otimizador VSP focadas em **três frentes**:

1. **Correção do invariante set-partition (`== 1`)** na decomposição regional — cobertura duplicada eliminada.
2. **Objetivo deadhead-aware** em SA/Tabu/genetic/ALNS — heurísticas deixam de encadear conexões cross-terminal "baratas" mas espacialmente caras.
3. **Robustez e otimalidade em escala** — todos os algoritmos passam a alcançar o ótimo de frota até 3000 trips; fallback monolítico gracioso quando a decomposição falha; mcnf resolve um único fluxo ótimo em escala.

Validado contra o card real de Salvador (SUNT GTFS, 674–6740 trips, deadhead Haversine real). Resultado-chave no card real de 2696–2832 trips: **frota 320 → 184–192 veículos (−40%)**, custo **−38 a −39%**, cobertura total, 0 overlaps.

---

## Commits (ordem cronológica)

| # | Hash | Mensagem |
|---|------|----------|
| 1 | `2cb7e75` | fix: regional duplicate-coverage + deadhead-aware SA/Tabu objective |
| 2 | `587ec15` | feat: regional vehicle-reuse stitch + deadhead consistency + real-card bench |
| 3 | `57ace24` | fix: graceful monolithic fallback when scale decomposition fails |
| 4 | `c184e89` | fix: mcnf reaches single-flow optimum at scale (was fragmenting to regional) |
| 5 | `365effa` | fix: raise auto_regional_threshold 1000→3000 so all algorithms reach the optimum at scale |
| 6 | `d8ea501` | fix: regional serializes deadhead_times to ProcessPool workers |
| 7 | `d743874` | docs: robustness audit verdicts (pair-stress and EV charger are design, not bugs) |
| 8 | `17a4010` | test: EV charger-conflict scenario must enable strict_hard_validation |
| 9 | `1e10b23` | chore: remove orphan manual-inspection scripts from src/ |

---

## Detalhe das mudanças

### 1. Cobertura duplicada na regional (`2cb7e75`)
- `_group_by_time_window` sobrepunha janelas em 30 min e o merge concatenava blocos sem dedup → trip de fronteira coberta 2× (41/40). Fix: dedup por `trip.id` no merge (mantém 1ª cobertura) + `unassigned` como complemento real do conjunto coberto.
- Proxy `quick_cost_from_trips` de SA/Tabu era deadhead-blind → encadeavam conexões cross-terminal caras. Adicionado termo deadhead (default `1.0`). No-op quando `deadhead_times` vazio.

### 2. Stitch de reuso de veículo + consistência deadhead (`587ec15`)
- `_stitch_blocks`: passa greedy que reusa veículo entre janelas/regiões. 160 trips: 78 → 26 veículos (gap 290% → 30%), cobertura/overlaps preservados.
- genetic e ALNS passam `deadhead_cost_per_minute` ao proxy. `Trip.__post_init__` coage chaves `deadhead_times` para int.
- `scratch/bench_real_gtfs_deadhead.py`: roda todos algoritmos no card real (674 trips, 20 terminais, deadhead Haversine de stops.txt).

### 3. Fallback monolítico gracioso (`57ace24`)
- `hybrid_pipeline` abortava com `SCALE_CHUNK_FAILED` (SPREAD_EXCEEDED) em card real com deadhead. Fix: `OptimizerService.run` faz 1 retry monolítico (`disable_scale_decomposition=True`) e registra `meta.performance.scale_decomposition_fallback`. `MANDATORY_GROUP_SPLIT` segue exposto.

### 4. mcnf em escala (`c184e89`)
- `_CLUSTER_SIZE_LIMIT` 800 → 3000 (configurável via `vsp_params["mcnf_cluster_size_limit"]`). Fluxo min-cost único até 3000 trips.
- dispatcher pula o redirect regional para mcnf enquanto cabe num fluxo único.

### 5. `auto_regional_threshold` 1000 → 3000 (`365effa`)
- Dispatcher redirecionava toda heurística para regional ≥1000 trips → fragmentava em 320 veículos no card de 2696. Threshold elevado para 3000 (alinhado a `mcnf_cluster_size_limit`), configurável. Ótimo de frota agora alcançável por TODOS os algoritmos até 3000 trips.

### 6. Serialização de deadhead para workers (`d8ea501`)
- `_trip_to_dict` omitia `deadhead_times` → nos processos filhos `deadhead` virava `{}`, gerando blocos espacialmente inviáveis (bus "teletransporta"). Fix: incluir `deadhead_times`. Repro: 1 → 2 blocos.

### 7–8. Auditoria de robustez (`d743874`, `17a4010`)
- Veredictos documentados: pair-stress e EV charger são design, não bugs.
- `scenario_hard_ev_conflict_rejection` agora seta `strict_hard_validation=True` (era bug de config do teste, não do otimizador). Suite 6/8 → 7/8.

### 9. Limpeza (`1e10b23`)
- Removidos 3 scripts dev-only de `src/` (shipavam na imagem de produção, 0 referências): `exhaustive_parameter_test.py`, `exhaustive_operational_test.py`, `fallback_verification.py`. Superados pelas suites em `tests/`.

---

## Validação

- Regressão ampla (proof + unit + regional + gtfs + round_trip + overnight): **505 passed, 2 skipped, 1 warning** (greedy-gap advisory esperado).
- `pytest --collect-only` = 689 tests (inalterado após limpeza).
- Card real Salvador (674 trips, deadhead Haversine): 15/15 algoritmos feasible, 14/15 atingem 46 veículos (LB concorrência 40, gap deadhead estrutural ~15%); schedule mais barato R$153.096 (mcnf/hybrid, default de produção).
- Card real 2696–2832 trips: 320 → 184–192 veículos (−40%), custo −38/−39%, cobertura total, 0 overlaps, sem OOM.

## Arquivos alterados (20)

```
CLAUDE_OPERATIONAL_STATUS.md                         +226
optimizer/scratch/bench_all_algorithms.py            +109  (novo)
optimizer/scratch/bench_real_gtfs_deadhead.py        +122  (novo)
optimizer/scratch/exp_deadhead_proxy.py              +72   (novo)
optimizer/scratch/exp_mcnf_stitch.py                 +67   (novo)
optimizer/scratch/repro_hybrid_scale.py              +62   (novo)
optimizer/src/algorithms/utils.py                    +14/-…
optimizer/src/algorithms/vsp/alns.py                 +1
optimizer/src/algorithms/vsp/genetic.py              +7
optimizer/src/algorithms/vsp/mcnf.py                 +19
optimizer/src/algorithms/vsp/regional_decomposition.py +95
optimizer/src/algorithms/vsp/simulated_annealing.py  +4
optimizer/src/algorithms/vsp/tabu_search.py          +4
optimizer/src/domain/models.py                       +12
optimizer/src/exhaustive_operational_test.py         -237  (removido)
optimizer/src/exhaustive_parameter_test.py           -187  (removido)
optimizer/src/fallback_verification.py               -104  (removido)
optimizer/src/services/algorithm_dispatcher.py       +26
optimizer/src/services/optimizer_service.py          +35
optimizer/tests/qa_operational_extreme_2026.py       +3
```

## Riscos remanescentes / follow-ups

- Acima de 3000 trips, mcnf ainda roteia para regional (clustering próprio fragmenta mais que o stitch da regional). Documentado, não é regressão.
- mcnf aparenta perder otimalidade em 6740 trips (hybrid 656 < mcnf 780) — flag para follow-up.
- Figuras antigas de regional-at-scale eram otimistas/inviáveis; corrigidas, mas mcnf/hybrid permanecem o caminho recomendado.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
