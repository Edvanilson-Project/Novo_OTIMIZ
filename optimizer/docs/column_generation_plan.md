# Plano: Column Generation para VSP (Branch-and-Price)

**Data:** 2026-05-15
**Status:** Scaffolding / projeto multi-fase
**Motivação:** Fechar o gap estrutural 2000v hybrid (360 blocos) vs greedy direto (333 blocos)

---

## 1. Por que CG / B&P agora

Benchmark 2026-05-15 (`docs/benchmark_sla_2026_05_14.md`):

| Algoritmo       | 2000v blocos | tempo |
|-----------------|-------------|-------|
| greedy          | 333         | 4.1s  |
| hybrid_pipeline | 360         | 272s  |

Gap: 27 blocos / 8%. Diagnóstico (`tests/diagnostic_2000v_stitching.py`):
**94% dos stitches são rejeitados por `max_vehicle_shift` ou conexão inviável** —
o problema NÃO é o `scale_stitch_max_gap_minutes`. É a decomposição em chunks que produz
veículos cuja união excede `max_vehicle_shift`.

Reduzir mais exige decomposição diferente ou solver global.
**Column Generation (Branch-and-Price)** é a abordagem padrão na literatura para VSP em larga escala
(Desrochers/Soumis, Borndörfer/Löbel/Weider). Permite tratar 2000–100000 viagens com
qualidade próxima do ótimo, sem decomposição lossy.

## 2. Diferença vs CG existente

O codebase **já tem column generation para CSP** (`csp/set_partitioning.py`),
gerando colunas que são **jornadas de motorista** sobre tarefas pré-cortadas.

Este plano é para **VSP**: colunas serão **blocos de veículo** (sequências
de viagens cobertas por um veículo, respeitando deadhead/conexão/`max_vehicle_shift`).
Os dois CGs são **independentes** — VSP roda antes; CSP roda depois sobre os blocos.

## 3. Formulação

```
Variáveis:   x_p ∈ {0,1}  para cada bloco p ∈ P
Constantes:  a_{ip} = 1 se trip i pertence ao bloco p

Master (set partitioning):
    min  Σ_p c_p x_p
    s.a. Σ_p a_{ip} x_p = 1     ∀ trip i           (cover, duais π_i)
                  x_p ∈ {0,1}

Pricing (shortest path com recursos):
    Para cada par (depot, vehicle_type), achar caminho no grafo de viagens com
    custo reduzido c_p − Σ_{i ∈ p} π_i mínimo. Recursos: shift_minutes,
    layover acumulado, deadhead. Restrições: connection_feasible(i, j),
    max_vehicle_shift, energia (frota elétrica).
```

Geração inicial de colunas: reaproveitar saída do `greedy` ou `mcnf` como
warm start (já fornece ~333 colunas viáveis em 4s para 2000v).

## 4. Arquitetura proposta

```
algorithms/vsp/branch_and_price.py
    ├── MasterProblemLP        # LP relaxado; mantém pool de colunas; expõe duais
    ├── PricingSubproblem      # shortest path com resource constraints (SPPRC)
    └── BranchAndPrice         # loop: master → duais → pricing → repeat → branch
```

Integração:
- `domain/interfaces.py` — IVSPAlgorithm já existe; B&P implementa essa interface.
- `services/algorithm_dispatcher.py` — registrar como `"branch_and_price"` em fase futura.
- `services/optimizer_service.py` — opção em `algorithm` da request (não default).

## 5. Plano em fases

| Fase | Escopo | Critério de aceite | Status |
|------|--------|--------------------|--------|
| **F0** | Scaffolding: stubs, sem solver, sem registro. | Tests 401/401 inalterados. | ✅ DONE |
| **F1** | Master LP (PuLP CBC) + warm-start greedy + MIP final. | 100v: B&P == greedy blocos. 18 testes novos. | ✅ DONE |
| **F2** | _(pulado — fundido em F3)_ | — | ✅ DONE |
| **F3** | SPPRC com dominância (label A domina B se rc≤ AND shift≤). Registro no dispatcher. Mem otimizada (del pós-prop, lazy init, cap=30 succ, auto-scale labels). | 1000v: B&P ≤ greedy. 18 testes passam em 2.3s. `algorithm="branch_and_price"` disponível na API. | ✅ DONE |
| **F4** | Branching Ryan-Foster (branch on fractional pair i,j: subprob must/cannot co-occur). Necessário para instâncias onde LP fracionário não arredonda limpo. | 2000v: ≤ greedy blocos (alvo: ≤333); tempo ≤ 600s. | 🔜 Próximo |
| **F5** | Estabilização + acceleration (proximal, dual bounding, parallel pricing). | 100k+ viagens em ≤30 min. | 🔜 Futuro |

## 6. Riscos

- **PuLP/CBC LP relaxation pode ser lento** para 2000v com 10k+ colunas — pode ser
  necessário trocar p/ HiGHS via API direta ou Gurobi com licença acadêmica.
- **Pricing por labeling** é o coração técnico; bugs aqui produzem colunas inviáveis
  silenciosamente. Validação por replay obrigatório.
- **Integração com `enable_column_generation` do CSP** — flag tem mesmo nome mas
  comportamento diferente. Renomear ou prefixar (`vsp_branch_and_price_enabled`).
- **Scope creep**: B&P puxa cargo de SPPRC, branching, estabilização. Manter
  fases isoladas com critério de aceite mensurável por fase.

## 7. Não-objetivos permanentes

- Não alterar comportamento default — `hybrid_pipeline` continua o caminho recomendado.
- Não tocar a infra CG do CSP (`csp/set_partitioning.py`) — problema diferente.
- B&P não suporta multi-depot com otimização cross-depot — use `mcnf` para isso.

## 8. Uso (F3+)

```json
{
  "algorithm": "branch_and_price",
  "vsp_params": {
    "bp_max_pricing_iterations": 5,
    "bp_max_pricing_columns": 2000,
    "bp_max_labels_per_node": 0
  }
}
```

`bp_max_labels_per_node=0` → auto-escala (recomendado). Para debug: valores explícitos.

## 9. Notas de implementação F3

- `PricingSubproblem._build_successors` cap em 30 succ/nó — instâncias com >30 conexões
  por viagem são raras e os 30 melhores (por start_time) são suficientes para pricing.
- Labels liberados imediatamente após propagação (`labels_at.pop`) — pico de memória
  proporcional ao fan-out, não ao n total.
- MIP final via CBC (PuLP) sobre pool completo — CBC faz branching internamente.
  Ryan-Foster explícito (F4) melhorará a qualidade dos duais no loop CG.
