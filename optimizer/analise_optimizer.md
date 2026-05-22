# Análise do Optimizer — Estrutura Real

> Auditoria baseada em leitura do código em 2026-05-14. Substitui versão genérica anterior (output Ollama com estrutura inventada).

## Estrutura real (`optimizer/src/`)

```
optimizer/src/
├── algorithms/
│   ├── base/         evaluator.py (avaliação base)
│   ├── csp/          greedy, set_partitioning, set_partitioning_optimized, chunked_orchestrator
│   ├── vsp/          greedy, mcnf, assignment, simulated_annealing, tabu_search, genetic
│   ├── integrated/   joint_solver, vcsp_solver
│   ├── hybrid/       pipeline (orquestrador)
│   ├── evaluator.py  (avaliador 819 linhas)
│   ├── joint_opt.py  (1450 linhas)
│   └── joint_opt_boundary.py
├── api/              FastAPI: routes/, converters.py, schemas.py (685 linhas)
├── core/             celery_app, config, exceptions, logging, rule_engine
├── domain/           interfaces.py, models.py (753 linhas)
├── infrastructure/   routing_client.py
└── services/
    ├── optimizer_service.py            (3669 linhas — orquestrador principal)
    ├── algorithm_dispatcher.py         (215 — Strategy via callables, Sprint I-1)
    ├── parameter_normalization.py      (246 — Sprint I-2)
    ├── trip_group_inference.py         (241 — Sprint I-3)
    ├── operational_time_service.py     (328 — CCT semântica)
    ├── hard_constraint_validator.py    (558)
    ├── solution_validator.py
    ├── maintenance_validator.py
    ├── comprehensive_auditor.py
    ├── operational_quality_helpers.py
    ├── strategy_service.py, strategy_persistence_service.py, strategy_worker_state.py
    ├── ai_service.py
    ├── optimizer_tasks.py              (Celery tasks)
    └── rostering/                      (subpacote)
```

- 67 arquivos `.py`, 25.839 linhas
- 330 testes passam, 2 skipados (CCT semântica, Sprint F)

## Componentes-chave

### `services/optimizer_service.py` (3669 linhas)
Orquestrador. Já passou por 3 splits iterativos nos Sprints I-1..I-3 (de 4287 → 3669, −14%). Continua sendo o maior arquivo do projeto. Mais splits possíveis quando tocar nas próximas seções.

### Algoritmos
- **CSP** (Crew Scheduling): greedy + set_partitioning (versão otimizada existe paralela), chunked_orchestrator para escala.
- **VSP** (Vehicle Scheduling): greedy, mcnf (601), assignment, e meta-heurísticas (SA, tabu, genetic).
- **Integrated**: `vcsp_solver.py` (726) e `joint_solver.py` — abordagem conjunta veículo+motorista.
- **Hybrid**: `pipeline.py` (602) — orquestra VSP→CSP ou variantes.
- **`joint_opt.py`** (1450 linhas) — implementação histórica de otimização conjunta, candidata a revisão para identificar overlap com `integrated/`.

### Domínio
- `domain/models.py` (753) define entidades de trip, vehicle, driver, schedule.
- `domain/interfaces.py` — contratos.

### API
- FastAPI em `api/routes/` + schemas Pydantic (685 linhas em `schemas.py`).
- `core/celery_app.py` para tasks assíncronas.

## Observações reais (não especulativas)

1. **`optimizer_service.py` ainda grande (3669)**. Não é problema em si, mas há mais alvos de extração (parameter validation, result post-processing).
2. **CSP duplicado**: `set_partitioning.py` e `set_partitioning_optimized.py` coexistem. Verificar se a versão antiga ainda é referenciada ou se pode ser removida.
3. **`joint_opt.py` (1450) vs `integrated/joint_solver.py`**: provável sobreposição/legado. Mapear chamadas antes de mexer.
4. **2 testes skipados em CCT semântica** com `reason` explícito (Sprint F) — investigar se ainda fazem sentido ou se viraram cobertura morta.
5. **Logs Celery**: `celery.log` tem 40 MB (untracked). Adicionar ao `.gitignore` se ainda não está, ou rotacionar.

## O que NÃO foi observado (não inventado)

- Não vi código sem validação crítica em loaders (a versão Ollama afirmava isso sem ler).
- Não vi falta de concorrência (Celery já trata).
- Não vi falta de tratamento de exceção sistêmica — `core/exceptions.py` existe e é usado.
- Hardening de auth/tenant já foi feito no Sprint G (backend).

## Próximos passos candidatos (priorizar conforme objetivo)

| # | Item | Esforço | Risco | Valor |
|---|------|---------|-------|-------|
| 1 | Investigar `set_partitioning.py` vs `_optimized.py` — remover legado se sem callers | baixo | baixo | médio |
| 2 | Mapear `joint_opt.py` vs `integrated/` — consolidar ou documentar diferença | médio | médio | alto |
| 3 | Próximo split iterativo de `optimizer_service.py` (mirar < 3000 linhas) | médio | baixo | médio |
| 4 | Adicionar `celery.log` ao `.gitignore` se ausente | trivial | nenhum | baixo |
| 5 | Revisar 2 skips em CCT — limpar ou reabilitar | baixo | baixo | baixo |
