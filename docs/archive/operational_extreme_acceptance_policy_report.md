# Política de Aceitação - Duties Extremas

Data: 2026-04-29
Base principal: cenário `ON` de `operational_extreme_local_reconstruction_impact_report.md`
Referência de cauda anterior: cenário `OFF`
Fonte detalhada: `reconstruction_on_full.json` e `reconstruction_off_full.json`

## Objetivo

Definir uma política operacional para aceitar, rejeitar ou tentar reconstrução adicional quando ainda restarem duties extremas no resultado.

## 1. Distribuição atual das duties

Cenário usado como base: `ON`

Resumo:

- custo total: `R$ 247.290,87`
- veículos: `15`
- duties: `19`
- utilização média: `59,29%`
- spread médio: `556,95 min`
- idle médio: `250,68 min`
- duties `< 25%`: `2`
- duties `< 30%`: `2`
- duties `> 12h`: `8`

### 1.1 Ordenadas por utilização

| Ordem | Duty | Utilização | Spread | Idle | Trabalho |
|---|---:|---:|---:|---:|---:|
| 1 | `524` | `18,47%` | `839` | `684` | `155` |
| 2 | `520` | `24,70%` | `830` | `625` | `205` |
| 3 | `515` | `43,99%` | `823` | `461` | `362` |
| 4 | `527` | `54,26%` | `610` | `279` | `331` |
| 5 | `528` | `54,99%` | `531` | `239` | `292` |
| 6 | `522` | `59,27%` | `572` | `233` | `339` |
| 7 | `519` | `61,45%` | `594` | `229` | `365` |
| 8 | `517` | `62,53%` | `790` | `296` | `494` |
| 9 | `521` | `62,91%` | `790` | `293` | `497` |
| 10 | `523` | `62,92%` | `809` | `300` | `509` |
| 11 | `516` | `63,80%` | `826` | `299` | `527` |
| 12 | `531` | `64,34%` | `488` | `174` | `314` |
| 13 | `518` | `65,96%` | `379` | `129` | `250` |
| 14 | `525` | `66,03%` | `836` | `284` | `552` |
| 15 | `532` | `69,02%` | `184` | `57` | `127` |
| 16 | `514` | `70,18%` | `114` | `34` | `80` |
| 17 | `533` | `73,68%` | `38` | `10` | `28` |
| 18 | `530` | `73,71%` | `175` | `46` | `129` |
| 19 | `529` | `74,29%` | `354` | `91` | `263` |

Leitura:

- a cauda ruim está concentrada em `2` duties
- há um degrau muito claro entre `520` e `515`
- abaixo de `25%` não existe “caso aceitável”; entram só jornadas claramente ruins

### 1.2 Ordenadas por spread

| Ordem | Duty | Spread | Utilização | Idle | Trabalho |
|---|---:|---:|---:|---:|---:|
| 1 | `524` | `839` | `18,47%` | `684` | `155` |
| 2 | `525` | `836` | `66,03%` | `284` | `552` |
| 3 | `520` | `830` | `24,70%` | `625` | `205` |
| 4 | `516` | `826` | `63,80%` | `299` | `527` |
| 5 | `515` | `823` | `43,99%` | `461` | `362` |
| 6 | `523` | `809` | `62,92%` | `300` | `509` |
| 7 | `517` | `790` | `62,53%` | `296` | `494` |
| 8 | `521` | `790` | `62,91%` | `293` | `497` |
| 9 | `527` | `610` | `54,26%` | `279` | `331` |
| 10 | `519` | `594` | `61,45%` | `229` | `365` |
| 11 | `522` | `572` | `59,27%` | `233` | `339` |
| 12 | `528` | `531` | `54,99%` | `239` | `292` |
| 13 | `531` | `488` | `64,34%` | `174` | `314` |
| 14 | `518` | `379` | `65,96%` | `129` | `250` |
| 15 | `529` | `354` | `74,29%` | `91` | `263` |
| 16 | `532` | `184` | `69,02%` | `57` | `127` |
| 17 | `530` | `175` | `73,71%` | `46` | `129` |
| 18 | `514` | `114` | `70,18%` | `34` | `80` |
| 19 | `533` | `38` | `73,68%` | `10` | `28` |

Leitura:

- `8` duties ainda estão acima de `12h`
- isso sozinho não inviabiliza a solução
- o problema operacional real aparece quando spread alto vem junto com utilização baixa

### 1.3 Ordenadas por idle

| Ordem | Duty | Idle | Utilização | Spread | Trabalho |
|---|---:|---:|---:|---:|---:|
| 1 | `524` | `684` | `18,47%` | `839` | `155` |
| 2 | `520` | `625` | `24,70%` | `830` | `205` |
| 3 | `515` | `461` | `43,99%` | `823` | `362` |
| 4 | `523` | `300` | `62,92%` | `809` | `509` |
| 5 | `516` | `299` | `63,80%` | `826` | `527` |
| 6 | `517` | `296` | `62,53%` | `790` | `494` |
| 7 | `521` | `293` | `62,91%` | `790` | `497` |
| 8 | `525` | `284` | `66,03%` | `836` | `552` |
| 9 | `527` | `279` | `54,26%` | `610` | `331` |
| 10 | `528` | `239` | `54,99%` | `531` | `292` |
| 11 | `522` | `233` | `59,27%` | `572` | `339` |
| 12 | `519` | `229` | `61,45%` | `594` | `365` |
| 13 | `531` | `174` | `64,34%` | `488` | `314` |
| 14 | `518` | `129` | `65,96%` | `379` | `250` |
| 15 | `529` | `91` | `74,29%` | `354` | `263` |
| 16 | `532` | `57` | `69,02%` | `184` | `127` |
| 17 | `530` | `46` | `73,71%` | `175` | `129` |
| 18 | `514` | `34` | `70,18%` | `114` | `80` |
| 19 | `533` | `10` | `73,68%` | `38` | `28` |

Leitura:

- a cauda de idle também é altamente concentrada
- há `3` duties acima de `450 min` de idle
- a duty `515` merece monitoramento, mas ainda está muito acima das duas críticas em qualidade global

## 2. Classificação operacional

### 2.1 Críticas

Regra:

- `utilization < 25%` e `spread > 720 min`

No cenário atual:

- `524`: `18,47%`, `839 min`, `684 min` idle
- `520`: `24,70%`, `830 min`, `625 min` idle

Interpretação:

- são jornadas longas demais para pouco trabalho útil
- consomem janela operacional e pioram custo por long unpaid break e espera
- devem ser tratadas como defeito de qualidade, não como simples “outlier”

### 2.2 Aceitáveis

Regra:

- não são críticas
- ainda têm algum desvio local: `utilization` entre `25%` e `55%`, ou `spread > 720 min`, ou `idle > 240 min`

No cenário atual:

- `515`, `516`, `517`, `521`, `523`, `525`, `527`, `528`

Interpretação:

- podem permanecer no resultado final
- exigem monitoramento, mas não justificam rejeição sozinhas
- duties longas com `utilização >= 60%` entram aqui: são extensas, porém produtivas

### 2.3 Boas

Regra:

- `utilization >= 55%`
- `spread <= 600 min`
- `idle <= 240 min`

No cenário atual:

- `522`, `518`, `519`, `514`, `533`, `531`, `529`, `532`, `530`

Interpretação:

- são jornadas compactas ou pelo menos bem proporcionadas
- esse grupo já representa quase metade da solução: `9/19`

## 3. Limites operacionais recomendados

### 3.1 Limites centrais

- máximo de duties `< 25%`: `1`
- máximo de duties `< 30%`: `2`
- máximo de duties `> 12h`: `8`

### 3.2 Leitura dos limites

`< 25%`

- esse é o principal gatilho de rejeição
- `2` ou mais duties abaixo de `25%` indicam cauda ruim demais
- `1` duty abaixo de `25%` só é tolerável se estiver perto da borda, por exemplo `24%` a `25%`, e sem outra distorção grave

`< 30%`

- é um limite de dispersão da cauda
- `2` ainda é operacionalmente administrável
- `3` ou mais já indica fragmentação persistente

`> 12h`

- `8` é alto, mas hoje é o melhor patamar observado sem perda de cobertura
- como várias duties longas ainda são produtivas, esse indicador deve ser secundário
- acima de `8` deve acionar melhoria; sozinho não precisa rejeitar se a solução estiver limpa nas métricas de baixa utilização

## 4. Simulação de cenários

### 4.1 Atual

| Cenário | Custo | Veículos | Duties | Duties `<25%` | Duties `<30%` | Duties `>12h` |
|---|---:|---:|---:|---:|---:|---:|
| Atual (`ON`) | `R$ 247.290,87` | `15` | `19` | `2` | `2` | `8` |

### 4.2 Com eliminação de mais 1 duty extrema

Hipótese usada:

- alvo principal: duty `524`
- sem nova rerrodada
- simulação operacional conservadora
- assume absorção/compactação da duty crítica sem criar novo veículo

Base da estimativa:

- a duty `524` custa hoje `R$ 2.114,28`
- duties compactas de porte parecido no cenário atual custam aproximadamente `R$ 620` a `R$ 900`
- logo, eliminar ou compactar essa duty tende a capturar a maior parte da penalidade hoje embutida nela

Estimativa:

| Cenário | Custo | Veículos | Duties | Observação |
|---|---:|---:|---:|---|
| Atual | `R$ 247.290,87` | `15` | `19` | 2 críticas |
| Eliminar `+1` extrema | `R$ 245,8 mil` a `R$ 246,0 mil` | `15` | `18` | ganho estimado de `R$ 1,3 mil` a `R$ 1,5 mil` |

Impacto operacional esperado:

- custo: melhora material
- veículos: tendência de permanecer em `15`
- duties: queda de `19 -> 18`
- duties `< 25%`: `2 -> 1`
- duties `< 30%`: `2 -> 1`
- spread médio e idle médio: melhora relevante

Risco do cenário:

- a redução de custo projetada é plausível, mas não garantida sem rerrodada
- se a absorção da duty `524` estourar outra jornada, o ganho pode migrar de custo para overtime

## 5. Trade-offs claros

### 5.1 O que vale aceitar

- spread alto com boa produtividade
- duty longa mas com `utilização >= 60%`
- pequena sobra de cauda desde que localizada em `1` duty limítrofe

### 5.2 O que não vale aceitar

- duas ou mais duties claramente extremas
- duty com `utilização < 20%`
- duty com `idle > 600 min` sem contrapartida operacional forte

### 5.3 O que justifica nova reconstrução

- problema concentrado em poucas duties
- cobertura intacta
- sem novas hard violations
- potencial claro de reduzir penalidade local sem trocar veículos

Esse é exatamente o caso atual: a solução já está boa no agregado, mas a cauda ruim ainda está pequena o bastante para merecer mais uma tentativa focalizada.

## 6. Política final de aceitação

### 6.1 Aceitar solução

Aceitar quando todos os itens abaixo forem verdadeiros:

- `0` viagens perdidas
- `0` viagens duplicadas
- nenhuma nova hard violation
- duties `< 25%` <= `1`
- duties `< 30%` <= `2`
- duties `> 12h` <= `8`
- se existir a única duty `< 25%`, ela deve ser limítrofe, não crítica severa

Definição prática de “limítrofe”:

- `utilização >= 24%`
- `idle < 650 min`
- sem outra duty na mesma faixa crítica

### 6.2 Rejeitar solução

Rejeitar quando qualquer item abaixo ocorrer:

- duties `< 25%` >= `2`
- alguma duty com `utilização < 20%`
- duties `< 30%` >= `3`
- duties `> 12h` > `8` junto com piora de custo ou cobertura
- surgimento de nova hard violation, viagem perdida ou duplicada

### 6.3 Tentar reconstrução adicional

Tentar reconstrução adicional quando:

- a solução falha apenas pela cauda de duties extremas
- cobertura e hard constraints seguem estáveis
- o problema está concentrado em `1` ou `2` duties
- há expectativa razoável de eliminar `1` duty extrema sem aumentar veículos

## 7. Decisão final

Regra recomendada:

`aceitar` apenas soluções com no máximo `1` duty abaixo de `25%`, no máximo `2` duties abaixo de `30%`, no máximo `8` duties acima de `12h`, e sem perda de cobertura nem nova violação hard.

Aplicação no cenário atual:

- o cenário atual `ON` ainda **não passa** na régua final porque tem `2` duties `< 25%`
- ele deve ser classificado como **quase aceitável, mas ainda pendente de reconstrução adicional**
- o alvo prioritário é a duty `524`

Conclusão executiva:

- os limites recomendados são realistas para esta carta
- o principal critério de qualidade deve ser a cauda de baixa utilização, não apenas o número bruto de duties longas
- a política final deve rejeitar soluções com `2` duties extremas e pedir mais uma tentativa focalizada quando a cobertura continuar intacta
