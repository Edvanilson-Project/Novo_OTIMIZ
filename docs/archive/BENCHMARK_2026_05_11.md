# Benchmark inicial do optimizer — 2026-05-11

Primeiro benchmark reproduzível com dataset sintético. Mediu o motor em diferentes tamanhos e algoritmos. Reproduzível via `scripts/benchmark_optimizer.py`.

## Ambiente

- Otimizador Python rodando em `http://localhost:8000` (uvicorn + Celery worker)
- Trips sintéticas: 4 terminais, 3 linhas, durações 30–80min, distribuição uniforme em 24h
- 2 tipos de veículo (micro + convencional)
- `random_seed=42` (reprodutível)
- `time_budget_s=120` por run

## Resultados — matriz pequena (smoke)

| N | Algo | Status | Solve ms | Custo R$ | Veículos | Duties | Trips→ | Órfãs | Violações CCT | Hard issues | Gini | CV |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | mcnf | completed | **3035** | 54.127,70 | 21 | 24 | 100 | 0 | 0 | 0 | 0,32 | 0,55 |
| 100 | hybrid_pipeline | completed | 51.069 | 54.127,70 | 21 | 24 | 100 | 0 | 0 | 0 | 0,32 | 0,55 |
| 500 | mcnf | completed | **3071** | 198.880,82 | 81 | 97 | 500 | 0 | 0 | 0 | 0,28 | 0,49 |
| 500 | hybrid_pipeline | completed | 24.091 | 198.880,82 | 81 | 97 | 500 | 0 | 0 | 0 | 0,28 | 0,49 |

## Observações honestas

- **MCNF é dominante em latência** para esse perfil de dataset: ~3s independente do tamanho, contra 24–51s do hybrid_pipeline. Empate em qualidade (mesmo custo, mesma frota, mesmo Gini).
- **Hybrid não vence aqui** porque o problema (deadhead 0, conexões fáceis) é praticamente um VSP puro — MCNF (Hungarian) já acha o ótimo. Hybrid se justifica quando há acoplamento VSP+CSP com violações CCT, o que esses dados sintéticos não introduzem.
- **Gini 0,28–0,32** indica distribuição razoavelmente equilibrada de jornadas entre motoristas. Reduz com mais duties (efeito de média).
- **CV 0,49–0,55** confirma dispersão moderada — não há outliers extremos.
- **0 violações CCT** — esperado: trips de duração 30–80min com gaps grandes não geram violação de condução contínua.

## Anti-claims importantes

- O número **"2,3s para 1000+ viagens"** do `COMPARATIVO_OPTBUS.md` **não é reproduzível** nesse setup. MCNF chegou a 3,1s para N=500, mas isso é VSP puro (sem CSP/CCT). Hybrid (que faz VSP+CSP) leva 24s+ para 500 trips. N=1000 ainda precisa de medição (não rodada para preservar tempo de bench).
- Não foi testada qualidade vs benchmark conhecido (não há baseline pública para comparação). O que se mede aqui é apenas qualidade RELATIVA entre os algoritmos do próprio sistema.

## Próximas medições (não feitas neste smoke)

| Tarefa | Por quê |
|---|---|
| N=1000, 2000 trips | Validar claim de escalabilidade linear ou identificar onde quebra |
| Dataset com violações CCT plantadas | Verificar quando hybrid começa a vencer mcnf |
| Comparar VCSP_PULP (ILP exato) com hybrid | Medir gap ótimo vs heurística |
| Variar seeds (5 corridas / config) | Calcular desvio padrão da latência |
| Dataset com deadhead real (terminais distantes) | Estressar MCNF com matriz custo não-trivial |

## Como reproduzir

```bash
python3 scripts/benchmark_optimizer.py --sizes 100,500,1000 --algo mcnf,hybrid_pipeline
```

Saída: tabela markdown no stdout + JSON em `/tmp/benchmark_YYYYMMDD_HHMMSS.json`.

Variáveis de ambiente respeitadas:
- `OPTIMIZER_URL` (default `http://localhost:8000`)
- `INTERNAL_OPTIMIZER_KEY` (default `internal-key-123456`)
