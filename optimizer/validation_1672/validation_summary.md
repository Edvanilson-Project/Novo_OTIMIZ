# Validação Linha 1672 — 92 viagens

BaseURL: http://127.0.0.1:8000

| Algoritmo | OK | Veic | Crew | CCT | Unassigned | Custo | Tempo(s) | Obs |
|---|---|---|---|---|---|---|---|---|
| greedy | ✓ | 33 | 24 | 0 | 0 | 41237.25 | 0.11 |  |
| mcnf | ✓ | 11 | 22 | 0 | 0 | 25646.4 | 0.31 |  |
| genetic | ✗ | 13 | 25 | 1 | 0 | 28271.48 | 9.67 | status=200 err=None |
| simulated_annealing | ✓ | 33 | 24 | 0 | 0 | 41003.75 | 40.02 |  |
| tabu_search | ✗ | 12 | 26 | 1 | 0 | 24980.87 | 40.02 | status=200 err=None |
| set_partitioning | ✓ | 33 | 23 | 0 | 0 | 41346.93 | 0.14 |  |
| joint_solver | ✓ | 11 | 24 | 0 | 0 | 23171.6 | 12.02 |  |
| hybrid_pipeline | ✓ | 11 | 22 | 0 | 0 | 25645.57 | 52.58 |  |
| vcsp_pulp | ✓ | 23 | 23 | 0 | 0 | 32600.35 | 3.05 |  |
