# Relatório de Riscos — Pipeline VCSP/MCNF

Escopo: `optimizer/src/algorithms/vsp/mcnf.py`, `optimizer/src/algorithms/integrated/vcsp_solver.py`, `optimizer/src/algorithms/csp/greedy.py`, `optimizer/src/api/schemas.py`.
Princípio aplicado: *Não Causar Dano* — abaixo apenas indicações; nenhuma alteração lógica foi propagada exceto uma correção óbvia sinalizada em "Correções aplicadas".

## 1. Bugs determinísticos (alta severidade)

### 1.1 `validate_solution_quality` — argumento `Ellipsis`
`vcsp_solver.py:493` chama `self.evaluator.total_cost_breakdown(result, ...)`. O `...` (objeto `Ellipsis`) é literal Python, não um "a preencher". Qualquer chamada ao método quebra em `TypeError`. **Corrigido** — veja patch.

### 1.2 Mistura Decimal × float no `_evaluate_path`
`vcsp_solver.py:574, 597, 598` executam `work_time/60` onde `work_time` é `Decimal`. A divisão `Decimal/int` funciona, mas o resultado é então multiplicado por `self.evaluator.crew_cost_per_hour`. Se `crew_cost_per_hour` estiver como `float` no `CostEvaluator` (verificar), o produto lança `decimal.InvalidOperation`. **Ação:** confirmar tipo em `CostEvaluator.crew_cost_per_hour` antes de patch.

### 1.3 Inconsistência de default de deadhead
- `mcnf.py:275` usa `deadhead_times.get(..., 0)` (otimista — conexão viável mesmo sem dado).
- `vcsp_solver.py:285, 293` usa `999_999` (Big-M — conexão inviável).

Duas execuções do mesmo input geram soluções distintas conforme o solver. **Ação:** padronizar sentinela (`999_999`) em ambos ou propagar dado real do OSRM.

## 2. Precisão numérica

### 2.1 Magic number `cost -= fixed_cost * 0.05` (mcnf.py:286)
Desconto arbitrário de 5% do custo fixo quando `destination_id == origin_id`. Não mapeia a nenhuma regra Optbus. Pode tornar o custo negativo (clamp em 0 L289 mascara). Documentar ou parametrizar.

### 2.2 Big-M heurístico (vcsp_solver.py:321)
`avg_cost = sum(t.duration)/len(trips) * 0.5` — o `0.5` é R$/min hardcoded; não reflete `driver_cost_per_minute` do DTO. Risco: Big-M sub-dimensionado permite soluções que "compram" inviabilidade barata.

### 2.3 `_ev_relax` — consumo energético (mcnf.py:494)
`base_e = distance_km * 1.25` kWh/km. Valor plausível para ônibus midi, mas não parametrizado por `VehicleType`. Adicionar `kwh_per_km` ao schema.

### 2.4 `_ev_relax` — recarga em qualquer gap com depot (mcnf.py:498-502)
Assume que toda parada com `t.depot_id != None` admite recarga, ignorando `max_simultaneous_chargers`. Em frotas grandes isto sobrestima SoC.

## 3. Tratamento de casos de borda

| Função | Borda | Risco |
|---|---|---|
| `MCNFVSP.solve` | `trips=[]` | Retorna `VSPSolution` vazio (ok). |
| `MCNFVSP._solve_subproblem` | `vehicle_types=[]` | `vehicle=None` → cai em `settings.default_vehicle_fixed_cost` (ok). |
| `VCSPJointSolver._evaluate_path` | `len(path)==0` | `path[0]` / `path[-1]` lançam `IndexError`. Atualmente o caller garante `len>=1`, mas sem guarda explícita. |
| `VCSPJointSolver._generate_paths` | Viagem sem `deadhead_times` | `.get(..., 0)` retorna 0 → conexão viável fictícia. |
| `_temporal_clustering` | `chunk_size < overlap` | `start = end - overlap_size` pode recuar indefinidamente (loop infinito). Constantes atuais (`800/0.10=80`) são seguras, mas a função não valida. |
| `_calculate_safe_big_m` | `trips=[]` | Retorno hardcoded 1M/10M (ok). |
| `validate_solution_quality` | `result.total_cost == 0` | L498: divisão por zero no `optimality_gap`. |

## 4. Race conditions / Concorrência

- `VCSPJointSolver` é stateful (`self._illegal_relief_penalty`, `self._punishment_cost`). Se duas chamadas `solve()` sobre a mesma instância concorrerem (Celery worker reciclando), sobrescrevem mutuamente os Big-Ms. **Ação:** mover para variáveis locais passadas por parâmetro, ou usar `threading.local`.
- `trip.deadhead_times` é mutado in-place em `_precalculate_deadheads`. Se o mesmo `Trip` for compartilhado entre jobs (cache), há corrida. **Ação:** clonar `Trip` ou usar dicionário externo.

## 5. Performance

- `_generate_paths` DFS com `MAX_PATHS=20_000` e guarda de cobertura pós-hoc: para N≈500 trips, a enumeração pode levar >10s antes do orçamento CBC. Mover poda por janela (`time_window_end = 480 min`) para dentro do loop `sorted_trips` via `bisect_right` eliminaria a iteração linear.
- `mcnf._solve_subproblem`: pré-filtro de conexões é `O(N²)`. Para N=1000 isto já é 1M comparações — aceitável, mas o `deadhead_times.get()` é dict lookup dentro do loop. Considerar matriz NumPy densa.

## 6. Correções aplicadas neste relatório

1. **`vcsp_solver.py:493`** — substituído argumento `...` por lista vazia `[]` em `total_cost_breakdown`. Restaura chamabilidade do método; semântica preservada (breakdown sem contexto adicional).

Nenhuma outra alteração foi feita: todas as demais recomendações ficam como **propostas** para revisão do arquiteto.
