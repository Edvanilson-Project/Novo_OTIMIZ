# Relatório Operacional - Carta Real Empresa 16

Data: 2026-04-29
Cenário analisado: empresa 16 (Matriz SP), 298 viagens reais, algoritmo `hybrid_pipeline`

## Como a validação foi feita

A análise foi feita olhando a carta e o resultado como operação real, sem inspecionar algoritmo ou código-fonte.

Foram executados dois cenários com a mesma carta real:
- `production`: `strict_hard_validation=false`, `group_infeasibility_mode=production`
- `strict`: `strict_hard_validation=true`, `group_infeasibility_mode=strict`

Para manter comparação justa, as duas rodadas usaram a mesma seed explícita (`20260429`).

Observação operacional importante:
- a base real de viagens da empresa 16 traz `lineId` nulo no banco; para atender ao schema da API do optimizer, foi gerado um mapeamento determinístico por `lineCode` (`1042=1`, `104201=2`, `1048=3`, `1067=4`).
- isso não altera horários, terminais, duração, pairing, sequência nem continuidade física das viagens.

## Resultado objetivo dos dois modos

### 1. Production

Status: `completed`

Resumo:
- 298 de 298 viagens cobertas
- 15 veículos
- 18 tripulações reportadas no topo do resultado
- 19 duties efetivamente retornadas
- custo total: R$ 249.068,25
- violações CCT: 0
- viagens não atribuídas: 0
- blocos descobertos: 0

Leitura operacional:
- a solução fecha a operação inteira sem buracos aparentes
- não foram encontrados conflitos físicos de sequência nas cadeias analisadas
- não houve gap negativo em blocos ou duties
- não houve conexão impossível por terminal nas sequências analisadas

### 2. Strict

Status: `failed`

Motivo real da falha:
- `MANDATORY_GROUP_SPLIT [5584, 5590]`
- `MANDATORY_GROUP_SPLIT [5591, 5597]`

Leitura operacional:
- no modo estrito, a carta não fecha mantendo certos pares obrigatórios na mesma jornada/bloco
- em `production`, esses pares são separados para a solução caber
- portanto, `production` entrega uma solução operacionalmente executável, mas com relaxamento real de pairing obrigatório

## O que está bom

- Cobertura total da carta: 298/298 viagens.
- Frota retornada não é absurda: o pico simultâneo mínimo calculado pela própria carta é 10 veículos, e a solução usou 15.
- Não apareceram sobreposições temporais dentro de blocos ou duties.
- Não apareceram conexões fisicamente impossíveis entre terminal de chegada e terminal de saída seguintes.
- O custo ficou muito próximo da execução real já persistida, mas ligeiramente melhor:
  - execução persistida: R$ 249.722,04 com hard violation
  - nova execução production: R$ 249.068,25 sem violação CCT

## O que está ruim

### 1. Jornadas com spread muito alto e pouco trabalho útil

Há duties claramente ruins do ponto de vista operacional:
- duty 85: 127 min de trabalho em 838 min de spread, utilização 15,2%, custo R$ 2.199,28
- duty 87: 155 min de trabalho em 839 min de spread, utilização 18,5%, custo R$ 2.114,28
- duty 78: 190 min de trabalho em 831 min de spread, utilização 22,9%, custo R$ 1.988,87

Impacto real:
- motorista fica “preso” quase o dia inteiro para produzir pouco
- escala fica difícil de sustentar em operação real
- percepção de ociosidade e improdutividade é alta
- qualquer atraso tende a degradar ainda mais essas jornadas longas e frágeis

### 2. Ociosidade estrutural alta nas jornadas

Média de tempo ocioso dentro do spread das duties: 294,8 minutos.

Casos extremos de ociosidade dentro do spread:
- duty 85: 711 min de spread não produtivo
- duty 87: 684 min de spread não produtivo
- duty 78: 641 min de spread não produtivo

Impacto real:
- equipe fica subutilizada
- custo indireto da escala aumenta
- aumenta risco de rejeição operacional mesmo com cobertura matematicamente completa

### 3. Muitas jornadas esticadas no limite alto do dia

Duties com spread acima de 13 horas:
- 78, 79, 80, 81, 84, 85, 86, 87, 88, 89

Duties com overtime:
- 79: 26 min
- 80: 44 min
- 84: 44 min
- 88: 8 min
- 90: 2 min

Impacto real:
- operação fica mais sensível a atraso
- mais dificuldade para gestão de equipe e cobertura de contingência
- desenho parece “fechado”, mas não robusto

### 4. Turnarounds muito curtos aparecem com frequência

Todas as 19 duties têm ao menos uma transição abaixo de 15 minutos.

Leitura operacional:
- não apareceu conexão impossível, mas vários encaixes são apertados
- para carta pendular e terminal simples, parte disso pode ser aceitável
- mesmo assim, isso reduz folga operacional e capacidade de absorver atraso

### 5. Inconsistência de leitura para usuário final

No resultado production:
- topo do resultado reporta 18 tripulações
- o retorno contém 19 duties

Na execução persistida anterior, já existia inconsistência semelhante.

Impacto real:
- o usuário final perde confiança na leitura gerencial
- pode haver erro de interpretação na tomada de decisão de frota/equipe

## O que precisa ajuste antes de confiar plenamente no resultado como operação real

- Rever o tratamento de pairing obrigatório para os grupos que quebram no modo estrito.
- Revisar o desenho de duties com spread muito alto e trabalho muito baixo.
- Avaliar se os turnarounds sub-15 min são aceitáveis para a operação real da linha/terminal.
- Revisar a métrica exibida de `crew` versus quantidade real de duties retornadas.

## Conclusão executiva

A carta real da empresa 16 fecha em `production` e não fecha em `strict`.

Isso significa:
- o sistema consegue montar uma operação completa e fisicamente coerente
- porém a solução aceita em `production` relaxa pairing obrigatório que o modo estrito rejeita
- além disso, várias jornadas são operacionalmente fracas por excesso de spread e pouca produção útil

Conclusão prática:
- como prova de cobertura de carta, o resultado `production` faz sentido
- como escala operacional “boa” para rodar no mundo real sem ressalvas, ainda não está bom
- o principal problema real não é falta de cobertura, e sim qualidade operacional das jornadas e dependência de relaxamento de pairing obrigatório
