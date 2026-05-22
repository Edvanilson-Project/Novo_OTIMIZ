# Melhoria de Qualidade Operacional das Duties

Data: 2026-04-29
Carta rerrodada: empresa 16, 298 viagens reais, `hybrid_pipeline`
Seed preservada: `20260429`

## Métricas definidas

As métricas operacionais de duty agora são calculadas explicitamente no CSP:

- `utilization = work_time / spread_time`
- `max_idle_time = maior gap interno entre tasks`
- `total_idle_time = spread_time - work_time`
- `max_spread = spread_time`
- `min_work_time = work_time`
- `break_count = número de gaps internos entre tasks`
- `fragment_count = break_count`
- `short_connection_count = gaps > 0 e < 15 min`

Thresholds suaves aplicados:

- utilização alvo: `30%`
- spread suave máximo: `12h` (`720 min`)
- idle suave máximo: `180 min`
- trabalho mínimo suave: `180 min` (ou `min_work_minutes` quando maior)
- fragmentação suave: até `2` quebras
- conexão curta: abaixo de `15 min`

## Onde as métricas foram aplicadas

- `CSP / duty building`
  - score de extensão de duty agora inclui penalização por baixa utilização, spread alto, idle alto, trabalho baixo, fragmentação e conexões curtas
  - arquivo: [optimizer/src/algorithms/csp/greedy.py](/home/edvanilson/Área%20de%20trabalho/Novo_OTIMIZ/optimizer/src/algorithms/csp/greedy.py)

- `CSP / postopt soft issues`
  - o `soft_issue_reassignment_postopt` passou a tratar `low_utilization`, `high_spread` e `fragmentation` como problemas operacionais válidos para mover tasks entre duties
  - arquivo: [optimizer/src/algorithms/csp/greedy.py](/home/edvanilson/Área%20de%20trabalho/Novo_OTIMIZ/optimizer/src/algorithms/csp/greedy.py)

- `Fallback selection`
  - o ranking de fallback do `OptimizerService` agora usa também `quality_summary` do CSP quando empate de group audit permite
  - arquivo: [optimizer/src/services/optimizer_service.py](/home/edvanilson/Área%20de%20trabalho/Novo_OTIMIZ/optimizer/src/services/optimizer_service.py)

- `Stitching`
  - o stitching de blocos em escala decomposta deixou de pegar o primeiro candidato viável e passou a preferir emendas com menor gap e menor span projetado
  - arquivo: [optimizer/src/services/optimizer_service.py](/home/edvanilson/Área%20de%20trabalho/Novo_OTIMIZ/optimizer/src/services/optimizer_service.py)

- `Joint post-opt`
  - o comparador global de candidatos passou a considerar qualidade operacional agregada além de frota, crew, violações e pares preferenciais
  - arquivo: [optimizer/src/algorithms/joint_opt.py](/home/edvanilson/Área%20de%20trabalho/Novo_OTIMIZ/optimizer/src/algorithms/joint_opt.py)

## Código ajustado

- duty score suave e `quality_summary` no resultado CSP
- `quality_metrics` por duty expostos no payload final
- pós-otimização guiada por baixa utilização/spread/fragmentação
- fallback e stitching com critério mais operacional
- testes unitários atualizados e verdes

## Validação executada

Testes locais:

- `pytest optimizer/tests/unit/test_fragmentation_postopt.py -q`
- `pytest optimizer/tests/unit/test_settings_parameter_effects.py -q`

Resultado:

- `31` testes passaram

## Comparação antes/depois

Base anterior (`production`, snapshot salvo):

- custo total: `R$ 249.068,25`
- veículos: `15`
- crew reportado: `18`
- duties: `19`
- violações CCT: `0`
- utilização média: `56,43%`
- idle médio por duty: `294,84 min`
- duties com utilização < `30%`: `3`
- duties com spread > `12h`: `10`
- trip groups relaxados em production: `2`

Nova execução após ajuste:

- custo total: `R$ 247.343,12`
- veículos: `15`
- crew reportado: `18`
- duties: `19`
- violações CCT: `0`
- utilização média: `58,15%`
- idle médio por duty: `255,26 min`
- duties com utilização < `30%`: `2`
- duties com spread > `12h`: `8`
- trip groups relaxados em production: `2`

Delta:

- custo: `- R$ 1.725,13`
- veículos: `0`
- crew: `0`
- duties: `0`
- utilização média: `+ 1,72 p.p.`
- idle médio: `- 39,58 min`
- low-util duties: `- 1`
- high-spread duties: `- 2`

## Checagem strict

A rerodada `strict` em 2026-04-29 continuou falhando exatamente pelos mesmos grupos já conhecidos:

- `MANDATORY_GROUP_SPLIT [5584, 5590]`
- `MANDATORY_GROUP_SPLIT [5591, 5597]`

Leitura:

- não houve regressão nova de inviabilidade dura
- o relaxamento de pairing em `production` continua o mesmo, sem piorar

## Impacto operacional real

Melhorias reais:

- a carta continua fechando integralmente
- o custo caiu sem aumentar frota nem crew
- a utilização média das jornadas subiu
- caiu o número de jornadas muito esticadas
- caiu o número de jornadas com utilização abaixo de `30%`

Resíduo que ainda preocupa:

- ainda existe uma duty muito ruim (`duty 203`: `86 min` de trabalho em `788 min` de spread, `10,91%` de utilização)
- ainda há `8` duties acima de `12h`
- a fragmentação ainda é alta em várias duties
- o relaxamento dos dois grupos obrigatórios continua necessário em `production`

## Conclusão prática

O ajuste melhorou a qualidade operacional sem quebrar a solução:

- a carta continua fechando
- não voltou nenhuma falha nova de `MANDATORY_GROUP_SPLIT`
- a qualidade das duties melhorou de forma mensurável
- ainda não está “bom o suficiente” para dizer que o problema operacional foi resolvido por completo

Próximo passo recomendado:

- atacar especificamente duties extremas de baixa utilização no pós-opt, priorizando remoção de tasks de borda que criam spreads longos com baixa produção
