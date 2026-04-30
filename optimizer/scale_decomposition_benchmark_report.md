# OTIMIZ Benchmark Report

- algoritmo: `hybrid_pipeline`
- viagens reais lidas: `298`
- company_id: `16`
- fail_on_hard_violations: `True`

| volume | status | tempo s | CPU s | RSS delta MB | custo | veiculos | duties | perdidas | duplicadas | hard violations |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000 | ok | 50.792 | 45.554 | 286.4 | 259824.13 | 84 | 112 | 0 | 0 | 0 |
| 5000 | ok | 143.773 | 129.868 | 32.0 | 661999.79 | 204 | 288 | 0 | 0 | 0 |

## Estratégia de escala

- Threshold direto: ate 1000 viagens.
- Faixa intermediaria: 1000 a 1999 viagens com strict atual e fallback controlado.
- Decomposição obrigatória: 2000+ viagens.
- Chunk alvo: 600 viagens; chunk máximo: 800 viagens.
- Particionamento: unidade indivisível por `trip_group_id`/grupo obrigatório, ordenada por linha, região e janela temporal.
- Stitching: só aceita conexão entre blocos quando `is_connection_feasible` passa; conexão rejeitada mantém blocos separados.

## Decomposição por volume

| volume | status escala | chunks | fallback chunks | chunk budget s | stitching accepted | stitching rejected | split_groups | hard_issues |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2000 | partially_completed | 4 | 1 | 30.0 | 1 | 63 | 0 | 0 |
| 5000 | partially_completed | 9 | 1 | 30.0 | 19 | 253 | 0 | 0 |

## Logs principais

- 2000: `[SCALE] Decomposed hybrid_pipeline: trips=2000 groups=998 chunks=4 target=600 max=800`.
- 2000: `chunk[3] primary hybrid failed: list index out of range`; fallback local concluiu; resultado final `partially_completed` sem hard violations.
- 5000: `[SCALE] Decomposed hybrid_pipeline: trips=5000 groups=2497 chunks=9 target=600 max=800`.
- 5000: `chunk[8] primary hybrid failed: list index out of range`; fallback local concluiu; resultado final `partially_completed` sem hard violations.

## Comparação com antes

| volume | antes | depois |
|---:|---|---|
| 2000 | strict global falhava com `MANDATORY_GROUP_SPLIT` | decomposição OK, 0 perdidas, 0 duplicadas, 0 hard violations |
| 5000 | não havia validação concluída nesta rodada; risco de timeout/instância global | decomposição OK no Python direto, 0 perdidas, 0 duplicadas, 0 hard violations |

## Limite da validação

Esta rodada validou o optimizer Python direto com dados reais/sintéticos do banco. O fluxo E2E completo Backend/Celery/Redis/Tela não foi reexecutado para 2000/5000 depois desta implementação.
