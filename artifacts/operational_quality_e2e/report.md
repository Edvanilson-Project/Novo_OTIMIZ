# Operational Quality E2E

Gerado em: 2026-04-30T13:33:06.862Z
Seed fixa usada: 42

Veredito: **nao pronto**

## Ambiente

- Coluna `operational_quality_mode` em `company_parameters`: ausente

## strict

| Item | Run 1 | Run 2 |
| --- | --- | --- |
| execucao completa | passou | passou |
| status correto | passou | passou |
| sem polling infinito | passou | passou |
| chosen_scenario persistido | falhou | falhou |
| rejected_scenarios persistido | falhou | falhou |
| justification presente | falhou | falhou |
| trade_offs presente | falhou | falhou |
| API operational_quality_decision | falhou | falhou |
| API consistente | falhou | falhou |
| UI modo selecionado | passou | passou |
| UI cenario exibido | falhou | falhou |
| UI label esperada | falhou | falhou |
| payload Redis capturado | passou | passou |
| latest-schedule mudou | passou | passou |
| latest-schedule < 5s | passou | passou |

Consistencia com mesma seed: **idêntica**

Principais logs:

- run 1: schedule 409, chosen=null, elapsed=120.207s, latestScheduleGet=33ms, redisPayload=327776B, workerMaxRss=252924KB
- run 2: schedule 410, chosen=null, elapsed=125.144s, latestScheduleGet=6ms, redisPayload=327776B, workerMaxRss=256484KB

## balanced

| Item | Run 1 | Run 2 |
| --- | --- | --- |
| execucao completa | passou | passou |
| status correto | passou | passou |
| sem polling infinito | passou | passou |
| chosen_scenario persistido | falhou | falhou |
| rejected_scenarios persistido | falhou | falhou |
| justification presente | falhou | falhou |
| trade_offs presente | falhou | falhou |
| API operational_quality_decision | falhou | falhou |
| API consistente | falhou | falhou |
| UI modo selecionado | passou | passou |
| UI cenario exibido | falhou | falhou |
| UI label esperada | falhou | falhou |
| payload Redis capturado | passou | passou |
| latest-schedule mudou | passou | passou |
| latest-schedule < 5s | passou | passou |

Consistencia com mesma seed: **idêntica**

Principais logs:

- run 1: schedule 411, chosen=null, elapsed=125.136s, latestScheduleGet=7ms, redisPayload=327776B, workerMaxRss=260208KB
- run 2: schedule 412, chosen=null, elapsed=125.133s, latestScheduleGet=8ms, redisPayload=327776B, workerMaxRss=264448KB

## optimized

| Item | Run 1 | Run 2 |
| --- | --- | --- |
| execucao completa | passou | passou |
| status correto | passou | passou |
| sem polling infinito | passou | passou |
| chosen_scenario persistido | falhou | falhou |
| rejected_scenarios persistido | falhou | falhou |
| justification presente | falhou | falhou |
| trade_offs presente | falhou | falhou |
| API operational_quality_decision | falhou | falhou |
| API consistente | falhou | falhou |
| UI modo selecionado | passou | passou |
| UI cenario exibido | falhou | falhou |
| UI label esperada | falhou | falhou |
| payload Redis capturado | passou | passou |
| latest-schedule mudou | passou | passou |
| latest-schedule < 5s | passou | passou |

Consistencia com mesma seed: **idêntica**

Principais logs:

- run 1: schedule 413, chosen=null, elapsed=125.143s, latestScheduleGet=7ms, redisPayload=327776B, workerMaxRss=267408KB
- run 2: schedule 414, chosen=null, elapsed=130.149s, latestScheduleGet=13ms, redisPayload=327776B, workerMaxRss=268444KB
