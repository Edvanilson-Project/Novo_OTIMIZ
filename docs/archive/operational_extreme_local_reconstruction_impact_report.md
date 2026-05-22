# Validação de Impacto - Reconstrução Local de Duties Extremas

Data: 2026-04-29
Carta: empresa 16, 298 viagens reais
Algoritmo: `hybrid_pipeline`
Seed: `20260429`
Método de execução: `OptimizerService.run(...).as_dict()` usando o payload real `ops_validation_production_payload.json`

## Cenários comparados

- `OFF`: `enable_soft_issue_reassignment_postopt=false`
- `ON`: `enable_soft_issue_reassignment_postopt=true`

## Tabela antes/depois

| Métrica | OFF | ON | Delta |
|---|---:|---:|---:|
| Custo total | R$ 249.202,46 | R$ 247.290,87 | - R$ 1.911,59 |
| Veículos | 15 | 15 | 0 |
| Duties | 19 | 19 | 0 |
| Crew | 18 | 17 | -1 |
| Viagens perdidas | 0 | 0 | 0 |
| Viagens duplicadas | 0 | 0 | 0 |
| Hard violations | 2 | 2 | 0 |
| Utilização média | 55,02% | 59,29% | + 4,27 p.p. |
| Idle médio | 294,58 min | 250,68 min | - 43,89 min |
| Overtime total | 179 min | 179 min | 0 |
| Duties < 30% | 3 | 2 | -1 |
| Duties > 12h | 10 | 8 | -2 |
| Spread médio | 600,84 min | 556,95 min | - 43,89 min |

## Duties extremas

Critério usado: `utilization < 25%` e `spread > 720 min`.

### OFF

- duty `102`: `205 min` de trabalho, `830 min` de spread, `24,70%` de utilização, `625 min` de idle
- duty `106`: `155 min` de trabalho, `829 min` de spread, `18,70%` de utilização, `674 min` de idle
- duty `108`: `86 min` de trabalho, `788 min` de spread, `10,91%` de utilização, `702 min` de idle

### ON

- duty `520`: `205 min` de trabalho, `830 min` de spread, `24,70%` de utilização, `625 min` de idle
- duty `524`: `155 min` de trabalho, `839 min` de spread, `18,47%` de utilização, `684 min` de idle

### Leitura

- a duty extrema equivalente à `108` foi eliminada
- a duty extrema equivalente à `102` permaneceu igual
- a duty extrema equivalente à `106` permaneceu, com leve piora local (`829 -> 839 min` de spread, `18,70% -> 18,47%` de utilização)

## Estrutura da reconstrução

Auditoria da rodada `ON`:

- duties reconstruídas: `1`
- tasks realocadas: `7`
- novas duties criadas: `1`
- duties eliminadas: `1`
- movimentos aceitos: `5`
- `improved=true`

Baseline interno da auditoria:

- extreme duties: `3 -> 2`
- low utilization duties: `3 -> 2`
- high spread duties: `10 -> 8`
- fragmented duties: `17 -> 15`
- waiting minutes: `3435 -> 2611`
- unpaid break minutes: `5607 -> 4763`
- vehicle switches: `71 -> 69`
- uncovered blocks: `0 -> 0`
- violations: `0 -> 0`

## Duties afetadas

### 1. Reconstrução local da duty extrema

- fonte: duty `108` no cenário `OFF` e duty `526` na auditoria do cenário `ON`
- trips originais: `[5473, 5479, 5665, 5668, 5681, 5686]`
- resultado:
  - `[5473, 5479]` foi isolado em nova duty `533`
  - `[5665, 5668]` foi anexado à duty `532`
  - `[5681, 5686]` foi anexado à duty `532`
- efeito:
  - eliminou `1` duty extrema
  - criou `1` duty curta nova, mas operacionalmente compacta

### 2. Realocações adicionais aceitas

- `[5644, 5652]` saiu da duty `100` e entrou na duty `531`
- `[5715, 5717]` saiu da duty `112` e entrou na duty `527`
- `[5710, 5712]` saiu da duty curta `114` e entrou na duty `528`
- `[5426, 5429]` saiu da duty `96` e entrou na duty `522`

### 3. Duties cuja composição mudou

No `OFF`, tiveram composição alterada ou foram absorvidas: `96`, `100`, `104`, `108`, `109`, `110`, `112`, `113`, `114`.

No `ON`, surgiram ou ficaram recompostas: `514`, `518`, `522`, `527`, `528`, `530`, `531`, `532`, `533`.

Houve `10` duties que permaneceram com a mesma composição de trips entre os dois cenários.

## Análise operacional

- houve melhoria real nas métricas agregadas e no alvo principal
- a reconstrução reduziu custo, idle, spread médio, duties longas e duties de baixa utilização
- cobertura permaneceu intacta: `0` viagens perdidas, `0` duplicadas
- hard constraints não pioraram: continuaram `2` hard violations, sem novas violações
- o efeito colateral principal foi local:
  - uma das duties extremas remanescentes piorou um pouco
  - o overtime total não melhorou
  - os `2` splits obrigatórios continuaram existindo

## Classificação

`melhora clara`

## Veredito

`manter` a estratégia de reconstrução local.

Justificativa:

- reduziu duties extremas (`3 -> 2`)
- melhorou métricas agregadas relevantes
- não piorou custo; pelo contrário, reduziu `R$ 1.911,59`
- não piorou cobertura
- não aumentou hard violations

Ponto de atenção antes de encerrar o assunto:

- ainda sobra `1` duty extrema muito ruim e `1` duty extrema limítrofe
- vale ajustar a estratégia para atacar a duty remanescente equivalente à `106/524`, que não foi resolvida e até piorou levemente
