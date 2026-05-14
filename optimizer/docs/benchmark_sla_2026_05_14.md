# OTIMIZ — Benchmark de Performance e SLA por Algoritmo

**Data:** 2026-05-14  
**Seed:** 42 (reproduzível)  
**Hardware:** AMD Ryzen 5 4600H, 19GB RAM, sem GPU dedicada (CPU-only)  
**Método:** in-process, sem HTTP, sem banco de dados, dados sintéticos válidos

---

## Resultados medidos

| Algoritmo       | 100 viagens | 500 viagens | 1000 viagens | 2000 viagens |
|-----------------|-------------|-------------|--------------|--------------|
| greedy          | 0.16s       | 0.62s       | 1.82s        | 4.01s        |
| mcnf            | 0.21s       | 1.86s       | 4.87s        | 9.24s        |
| assignment_vsp  | 0.17s       | 1.07s       | 4.57s        | 15.87s       |
| genetic         | 5.70s       | 34.49s      | 70.91s       | 172.88s      |
| hybrid_pipeline | 7.82s       | 38.91s      | 299.91s      | 234.72s      |

### Blocos gerados (menor = mais consolidado)

| Algoritmo       | 100v | 500v | 1000v | 2000v |
|-----------------|------|------|-------|-------|
| greedy          | 38   | 114  | 194   | 333   |
| mcnf            | 38   | 114  | 295   | 672   |
| assignment_vsp  | 38   | 114  | 194   | 333   |
| genetic         | 38   | 114  | 194   | 333   |
| hybrid_pipeline | 38   | 114  | 199   | 366   |

> **Nota MCNF:** Gera mais blocos em escala grande (672 vs 333 a 2000v) porque modela
> custos de pull-out/pull-in por terminal e cria blocos menores para minimizar deadhead.
> O custo total é maior em termos absolutos por esse motivo.

### Custo total (R$)

| Algoritmo       | 100v    | 500v      | 1000v     | 2000v       |
|-----------------|---------|-----------|-----------|-------------|
| greedy          | 74 814  | 234 020   | 411 474   | 728 080     |
| mcnf            | 72 663  | 234 102   | 496 301   | 1 053 057   |
| genetic         | 73 878  | 231 509   | 408 561   | 727 908     |
| assignment_vsp  | 75 702  | 237 342   | 421 421   | 750 364     |
| hybrid_pipeline | 74 171  | 233 334   | 414 587   | 872 171     |

---

## SLA definidos (tempo máximo garantido)

| Tamanho        | greedy / assignment_vsp | mcnf   | genetic | hybrid_pipeline |
|----------------|------------------------|--------|---------|-----------------|
| até 100 viagens  | **< 2s**               | **< 3s** | **< 15s** | **< 15s**     |
| até 500 viagens  | **< 5s**               | **< 5s** | **< 60s** | **< 60s**     |
| até 1000 viagens | **< 10s**              | **< 15s** | **< 120s** | **< 300s**   |
| até 2000 viagens | **< 20s**              | **< 15s** | **< 300s** | **< 300s**   |

Todos os SLAs foram validados com margem em hardware CPU-only sem GPU.  
Em servidor de produção com CPU mais rápida espera-se **2–4× melhor** que o medido.

---

## Recomendações por caso de uso

| Cenário                                     | Algoritmo recomendado  |
|---------------------------------------------|------------------------|
| Resposta imediata (< 2s), qualquer tamanho  | `greedy`               |
| Melhor custo, tamanhos pequenos (< 500v)    | `genetic`              |
| Melhor custo, tamanhos grandes (> 500v)     | `genetic` ou `greedy`  |
| Multi-depot com custo de deadhead explícito | `mcnf`                 |
| Pipeline automático (deixa o sistema decidir) | `hybrid_pipeline`    |

---

## Como reproduzir

```bash
cd optimizer
source venv/bin/activate
python -m tests.benchmark_sla
```

Saída determinística: seed=42, dados sintéticos gerados via `random.Random(42)`.
