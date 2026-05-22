# Follow-up Focalizado - Duty Crítica 524

Data: 2026-04-29
Carta: empresa 16, 298 viagens reais
Algoritmo: `hybrid_pipeline`
Seed: `20260429`
Base operacional: cenário `ON` de `operational_extreme_local_reconstruction_impact_report.md`
Reprodução local desta tentativa: payload `ops_validation_production_payload.json`

## Objetivo

Fazer uma tentativa cirúrgica para eliminar ou compactar a duty crítica `524`, sem alterar:

- arquitetura global
- solver VSP/global
- chunking
- thresholds globais
- hard rules

Critério de aceitação desta rodada:

- eliminar a duty extrema equivalente à `524`
- ou subir sua utilização para `>= 24%`
- ou reduzir duties `< 25%` de `2` para `1`
- sem perda de cobertura, sem duplicação, sem nova hard violation e sem aumento de veículos

## 1. Composição original da duty 524

Fonte: `reconstruction_on_full.json`

Resumo:

- duty `524`
- `start_time=379`
- `end_time=1208`
- `work=155 min`
- `spread=839 min`
- `idle=684 min`
- `utilization=18,47%`
- `trip_ids=[5458, 5461, 5486, 5491, 5667, 5677, 5688, 5692]`

Decomposição por bundle natural:

| Bundle | Trips | Faixa | Trabalho | Observação |
|---|---|---:|---:|---|
| B1 | `5458, 5461` | `379-397` | `18 min` | ponta inicial distante |
| B2 | `5486, 5491` | `440-469` | `29 min` | ponta inicial distante |
| B3 | `5667, 5677` | `1080-1160` | `80 min` | miolo tardio |
| B4 | `5688, 5692` | `1180-1208` | `28 min` | ponta final tardia |

Leitura operacional:

- o spread ruim não vem de um bloco central fragmentado
- ele é causado por duas pontas curtas de manhã e duas pontas curtas no fim do dia
- o melhor candidato estrutural seria preservar um miolo compacto (`B3+B4`) e absorver as pontas da manhã em outra duty curta compatível

## 2. Duty equivalente na rerrodada local

Na reprodução direta pelo payload real, a duty equivalente à `524` apareceu como:

- duty `201`
- mesma composição: `5458, 5461, 5486, 5491, 5667, 5677, 5688, 5692`
- mesmas métricas: `155/839`, `18,47%`

Ou seja:

- `524` no snapshot detalhado corresponde a `201` no rerun local

## 3. Movimentos testados

### 3.1 Remoção da duty inteira com reconstrução focalizada

Foi habilitado um modo opt-in no pós-opt local via `soft_issue_reconstruction_focus_duty_ids=[201]` para testar a duty alvo sem afetar o restante da carta.

O fluxo testado foi:

- remover a duty inteira
- quebrar a duty em bundles finos
- tentar anexar bundles em outras duties viáveis
- criar dedicated compacta apenas para bundles que não coubessem

Resultado:

- nenhum movimento com `source_duty_id=201` foi aceito
- o auditor registrou `reconstruction_not_better=7`

### 3.2 Dual-edge trim e multi-edge trim apenas na duty alvo

Foi implementado um passo focalizado adicional no pós-opt local para a duty alvo:

- trim coordenado de múltiplas bordas
- preservando o miolo reconstruído na própria duty
- realocando apenas bundles removidos

Planos avaliados no código:

- trims de prefixo/sufixo com `>= 2` bundles
- dual-edge trim
- multi-edge trim

Plano operacional mais promissor:

- mover `B1=[5458,5461]`
- mover `B2=[5486,5491]`
- preservar `B3+B4=[5667,5677,5688,5692]` como duty compacta

Esse plano teria a seguinte lógica:

- manhã seria absorvida por uma duty curta compatível
- tarde/noite permaneceria compacta
- a duty extrema `524/201` deixaria de existir como cauda longa

Resultado real da rerrodada:

- nenhum `accepted_move` com `source_duty_id=201`
- nenhum `accepted_move` com `mode=edge_trim_reconstruction`
- o cenário final ficou idêntico ao baseline

## 4. Movimentos aceitos e rejeitados

### Aceitos

Nesta tentativa focalizada, não houve movimento aceito envolvendo a duty `524/201`.

Os movimentos aceitos pelo pós-opt continuaram sendo os mesmos já conhecidos do cenário base e não tocaram a duty alvo.

### Rejeitados

Principais rejeições observadas para a duty `201`:

- `append_target_overlap`
- `prepend_target_overlap`
- `append_target_spread_exceeded`
- `prepend_target_spread_exceeded`
- `append_target_min_interval_violation`
- `prepend_target_min_interval_violation`
- `reconstruction_not_better`

Leitura prática:

- movimentos unitários de borda continuam falhando por overlap ou por qualidade da duty destino
- mesmo com trim coordenado, o candidato completo para a duty `201` não entrou como melhora líquida no ranking do pós-opt
- na prática, o solver local continuou preferindo manter a composição original da duty extrema

## 5. Validação de segurança

Comparação baseline `ON` vs tentativa focalizada:

- `0` viagens perdidas
- `0` viagens duplicadas
- `0` novas hard violations
- `0` aumento de veículos
- mesmos `2` relaxed groups

## 6. Tabela antes/depois

Baseline usado: `/tmp/baseline_focus_off.json`
Tentativa focalizada: `/tmp/focused_201_trim.json`

| Métrica | Antes | Depois | Delta |
|---|---:|---:|---:|
| Custo total | `R$ 247.290,87` | `R$ 247.290,87` | `0,00` |
| Veículos | `15` | `15` | `0` |
| Duties | `19` | `19` | `0` |
| Crew | `17` | `17` | `0` |
| Utilização média | `59,29%` | `59,29%` | `0,00 p.p.` |
| Duties `<25%` | `2` | `2` | `0` |
| Duties `<30%` | `2` | `2` | `0` |
| Duties `>12h` | `8` | `8` | `0` |
| Idle médio | `250,68 min` | `250,68 min` | `0,00` |
| Overtime | `179 min` | `179 min` | `0` |
| Relaxed groups | `2` | `2` | `0` |

## 7. Veredito

`manter cenário anterior`

Justificativa:

- a duty `524/201` continuou existindo como extrema
- a utilização dela não subiu para `>= 24%`
- duties `<25%` permaneceram em `2`
- não houve melhora de custo, veículos, crew, duties ou cauda operacional
- a tentativa foi segura, mas sem ganho real

## 8. Conclusão objetiva

Esta rodada mostrou que:

- a leitura estrutural da duty `524` está correta
- o padrão dela pede poda coordenada de múltiplas bordas
- porém, mesmo com reconstrução focalizada e trim coordenado opt-in, o pós-opt atual não conseguiu transformar isso em melhora aceita

Portanto, para esta carta e com as restrições impostas, a mudança deve ser:

- `rejeitada` como melhoria operacional
- e o cenário anterior deve ser `mantido`
