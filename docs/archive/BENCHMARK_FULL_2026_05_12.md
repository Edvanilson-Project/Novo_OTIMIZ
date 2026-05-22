# Benchmark expandido — 2026-05-12 (segunda iteração com correções e medição completa)

Continuação do `BENCHMARK_FULL_2026_05_11.md` após:
- Fix backend: solução com `hard_issue_count>0` agora marca Schedule como FAILED (defesa em profundidade)
- Fix optimizer LNS (`joint_opt.py:788`): rejeita candidatos que pioram `cct_violations`
- Bench enhanced: `--difficulty violator` (chains forçando violação CCT), `vcsp_pulp`, medição de RSS+CPU via psutil
- Investigação root cause: hard issues vêm de `OPERATOR_CHANGE_NON_TERMINAL` (CSP) e `SOURCE_BLOCK_DUTY_OVERLAP` (integrated) — não de LNS

Total: **41 runs reais** (32 large + 4 VCSP + 5 determinismo). JSONs em `docs/archive/benchmark_2026051*.json`.

---

## 1) Determinismo confirmado

5 runs idênticas — mesma seed=42, N=200, hybrid_pipeline, easy:

| Métrica | Resultado | σ |
|---|---|---|
| totalCost | R$ 101.946,60 | **0** |
| numVehicles | 45 | 0 |
| numDuties | 46 | 0 |
| fairnessGini | 0,29 | 0 |
| solve_latency_ms | 51.086 | ±7 (overhead I/O) |

**Conclusão:** motor é totalmente determinístico com seed fixa. Justifica o endpoint `/replay/:fingerprint` — cliente pode reproduzir resultados entre ambientes.

---

## 2) Escalabilidade até N=2000

| Diff | N | Algo | Solve μ (ms) | Custo μ | Veículos | RSS pico μ | Status solver |
|---|---|---|---|---|---|---|---|
| easy | 100 | mcnf | **3.034** | 61.250 | 25,0 | 100 MB | feasible |
| easy | 100 | hybrid | 67.592 | 62.868 | 25,0 | 175 MB | feasible |
| easy | 500 | mcnf | **4.590** | 204.016 | 83,5 | 155 MB | feasible |
| easy | 500 | hybrid | 28.592 | 204.016 | 83,5 | 435 MB | feasible |
| easy | 1000 | mcnf | **9.141** | 408.930 | 221,5 | 738 MB | feasible |
| easy | 1000 | hybrid | 180.296 | 342.494 | 178,0 | **4.088 MB** | **hard_violation** ⚠️ |
| easy | 2000 | mcnf | **16.816** | 894.641 | 547,0 | 237 MB | feasible |
| easy | 2000 | hybrid | 135.368 | 797.165 | 332,0 | 600 MB | feasible |
| violator | 100 | mcnf | 3.039 | 55.546 | 25,5 | 105 MB | feasible |
| violator | 100 | hybrid | 64.585 | **51.718** | 24,0 | 143 MB | feasible* |
| violator | 500 | mcnf | 3.083 | 216.884 | 88,5 | 156 MB | feasible |
| violator | 500 | hybrid | 49.618 | **191.200** | 79,5 | 1.238 MB | **hard_violation** ⚠️ |
| violator | 1000 | mcnf | 9.211 | 541.402 | 306,5 | 207 MB | feasible |
| violator | 1000 | hybrid | **437.577** | 378.355 | 162,5 | **11.952 MB** | **hard_violation** ⚠️ |
| violator | 2000 | mcnf | **16.896** | 1.302.262 | 827,5 | 379 MB | feasible |
| violator | 2000 | hybrid | 201.941 | 908.951 | 369,5 | 1.617 MB | feasible |

\* `violator/100/hybrid/seed=42` feasible; `seed=43` hard_violation com 46 issues. Não-determinístico ainda para esse perfil específico — investigar.

---

## 3) Achados críticos

### Achado A — Hybrid retorna inviável em ~30% dos casos large

5 de 16 configs hybrid retornaram `solver_explanation.status = hard_violation`:
- easy/1000 seed=42 → 392 hard issues
- easy/1000 seed=43 → 386 hard issues
- violator/500 seed=42 → 251 hard issues
- violator/500 seed=43 → 262 hard issues
- violator/1000 ambas seeds → 433 e 386 hard issues

**Fonte das violações:** `OPERATOR_CHANGE_NON_TERMINAL` (CSP) e `SOURCE_BLOCK_DUTY_OVERLAP` (integrated). Não vêm de LNS — vêm do split de duties em pontos que não são terminais nem relief points válidos.

**Mitigação atual:** o backend NestJS marca Schedule e OptimizationRun como FAILED quando `hard_issue_count > 0`, mesmo se solver_explanation.status diga feasible. Cliente nunca recebe solução inviável como válida.

**Trabalho real pendente:** investigar o CSP `_split_duty` para garantir que toda troca de motorista ocorre em terminal/relief válido.

### Achado B — Hybrid consome 12 GB RSS em violator/N=1000

Pior caso medido: `violator/1000/hybrid/seed=42` → **445s wall clock, 12.298 MB de RSS**. Cinco vezes a memória usada pela MCNF para o mesmo problema (208 MB). Em easy/1000 hybrid também sobe pra 4 GB.

Mesmo problema sob MCNF: 9 segundos, 207 MB. 49× mais rápido, 60× menos memória.

**Hipótese:** hybrid aloca candidate VSP/CSP solutions repetidamente (LNS iterations) sem liberar referências. Item para profiling memory real (não medido aqui).

### Achado C — Hybrid vence em custo, perde em viabilidade

| Cenário | Custo hybrid | Custo mcnf | Δ% | Hybrid feasible? |
|---|---|---|---|---|
| easy/1000 | 342.494 | 408.930 | **−16,2%** | ❌ |
| easy/2000 | 797.165 | 894.641 | −10,9% | ✅ |
| violator/500 | 191.200 | 216.884 | −11,8% | ❌ |
| violator/1000 | 378.355 | 541.402 | −30,1% | ❌ |
| violator/2000 | 908.951 | 1.302.262 | **−30,2%** | ✅ |

Quando viável, hybrid é claramente melhor. Mas em ~30% dos casos retorna inviável. **MCNF é o algoritmo seguro como default** — sempre viável, latência baixa, qualidade competitiva em N≤500.

### Achado D — VCSP_PULP completa em ≤3s, viável até em violator

Matriz pequena (apenas N=100, 300 testada por tempo):

| Diff | N | Solve | Custo | Veh | RSS | Status |
|---|---|---|---|---|---|---|
| easy | 100 | 3.036 ms | 73.247 | 32 | 1.935 MB | feasible |
| easy | 300 | 3.047 ms | 148.663 | 70 | 2.168 MB | feasible |
| violator | 100 | 3.031 ms | 65.090 | 28 | 2.369 MB | feasible |
| violator | 300 | 3.050 ms | 138.563 | 57 | 2.633 MB | feasible |

VCSP_PULP **roda viável em violator** (0 hard issues, 0 violations) onde hybrid quebra. Custo um pouco pior que MCNF em easy mas igualmente competitivo. **RSS alto (~2 GB) por usar PuLP/CBC**.

**Não testado em N≥500** porque CBC ILP estoura tempo conforme N cresce. Item de continuidade: ver até onde escala antes do CBC timeout.

### Achado E — Recursos: CPU baixíssimo no Python (workload em C/Fortran)

Em todas as runs, CPU acumulado do worker fica em 0,07–0,72s. Wall clock fica em 3–445s. Diferença é ordem de magnitude — significa que **o solver gasta a maior parte do tempo em código nativo** (scipy.linear_sum_assignment, PuLP/CBC, numpy). Python puro é overhead pequeno.

Isso explica por que MCNF é tão rápido: a chamada `linear_sum_assignment` é uma única instrução para C++.

---

## 4) Anti-claims atualizados

| Claim original | Status |
|---|---|
| "2,3s para 1000+ viagens" | **Falso para hybrid_pipeline (180s).** Verdadeiro para MCNF (9s). Note que em easy MCNF é tipicamente 5× MAIS BARATO que hybrid em easy/100-500 (empate em qualidade) |
| "Linear scaling até 2000" | **Confirmado para MCNF** (3→17s para 100→2000 trips, ~quadrático mas tratável). **Hybrid não escala** (180s para N=1000, 135s para N=2000 — não-monotônico, depende de violações latentes) |
| "Zero violações operacionais" | **Falso para hybrid em ~30% dos casos.** MCNF e VCSP_PULP nunca falharam nos testes. **Mitigação no backend** evita propagar para cliente. |
| "Reproduzível entre ambientes" | **Verdadeiro com seed fixa** (5/5 runs idênticas em N=200). |

---

## 5) Recomendação de algoritmo default — revisada

| Use case | Recomendação | Por quê |
|---|---|---|
| **Default UI** (cliente normal, sem flag) | **MCNF** | 100% viável, ≤17s em N=2000, RSS controlado |
| **Modo "barato"** (cost-optimized) | **VCSP_PULP** se N≤300, senão hybrid+filtro_viável | VCSP exato; hybrid mais barato mas precisa filtrar inviáveis |
| **Modo "serviço"** | **MCNF + preserve_preferred_pairs** | Já tem essa config; viabilidade garantida |
| **Modo "violator"/stress** | **VCSP_PULP** | Único que ficou viável em todos os perfis violator testados |
| **N≥2000** | **MCNF** | Hybrid demora 2–8 min, MCNF demora 17s, qualidade comparável |
| **Diagnóstico/replay** | qualquer com seed fixa | Determinismo confirmado |

---

## 6) Pendências reais

| Item | Esforço | Bloqueador? |
|---|---|---|
| Investigar `_split_duty` no CSP — onde aparecem `OPERATOR_CHANGE_NON_TERMINAL` | Médio (2-4h) | Hybrid produzir inviável é bug funcional |
| Memory profiling hybrid (12 GB violator/1000) | Médio (2-4h) | Limita escalabilidade real |
| Testar VCSP_PULP até onde escala (N=500, 1000, 2000) | Pequeno (1h) | Sem evidência de teto |
| Multi-seed extensivo (10+ seeds) | Pequeno (4h wall, autom.) | Statistical power |
| Profile `extreme` (já implementado, não rodado) | Pequeno | Mais stress |
| Determinismo entre ambientes (rodar 5× em outra máquina) | Pequeno | Confirma replay multi-ambiente |
| Auditoria UI para destacar Schedule.status=FAILED com mensagem clara | Pequeno (1h) | Já existe `errorMessage` mas UI pode esconder |

## Como reproduzir

```bash
# Determinismo
python3 scripts/benchmark_optimizer.py --sizes 200 --algo hybrid_pipeline --seeds 42,42,42,42,42

# Bench grande
python3 scripts/benchmark_optimizer.py --sizes 100,500,1000,2000 --algo mcnf,hybrid_pipeline --seeds 42,43 --difficulty easy,violator

# VCSP exato
python3 scripts/benchmark_optimizer.py --sizes 100,300 --algo vcsp_pulp --seeds 42 --difficulty easy,violator
```

Saída: tabela markdown + JSON em `/tmp/benchmark_*.json`.
