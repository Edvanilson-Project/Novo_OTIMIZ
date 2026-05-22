# Exceção Operacional - Duty Extrema Remanescente

Data: 2026-04-29
Carta: empresa 16, 298 viagens reais
Algoritmo: `hybrid_pipeline`
Seed: `20260429`
Base atual: cenário `ON` aceito até aqui
Referências locais: `reconstruction_on_full.json`, `/tmp/baseline_focus_off.json`

## Objetivo

Parar de tratar a duty extrema remanescente como problema de pós-opt local e transformá-la em decisão operacional explícita:

- classificar severidade das duties remanescentes
- explicar a exceção da duty `524/201`
- definir política de aceitação
- comparar o cenário atual com um cenário alternativo explícito de `+1 duty/crew`

## 1. Classificação de severidade

Regra usada nesta rodada:

- `critical`
  - `utilization < 25%`
  - `spread > 720 min`
  - claramente inviável como “outlier aceitável”
- `borderline`
  - `utilization < 25%`, mas muito perto do limite
  - ainda ruim, porém potencialmente aceitável com warning
- `acceptable`
  - fora da cauda extrema crítica

### Duties remanescentes relevantes

| Duty snapshot | Duty rerun | Utilização | Spread | Idle | Severity |
|---|---:|---:|---:|---:|---|
| `524` | `201` | `18,47%` | `839` | `684` | `critical` |
| `520` | `197` | `24,70%` | `830` | `625` | `borderline` |
| Demais duties | várias | `>= 43,99%` | variado | variado | `acceptable` |

Leitura:

- a única duty efetivamente problemática para decisão operacional é a `524/201`
- a `520/197` fica abaixo de `25%`, mas está na borda e pode ser tratada como exceção controlada
- o restante do plano é operacionalmente aceitável

## 2. Exceção da duty 524/201

### Composição

Fonte: `reconstruction_on_full.json`

- duty `524` no snapshot
- duty `201` na rerrodada local
- trips: `5458, 5461, 5486, 5491, 5667, 5677, 5688, 5692`

Bundles naturais:

- `B1 = [5458, 5461]` em `379-397`
- `B2 = [5486, 5491]` em `440-469`
- `B3 = [5667, 5677]` em `1080-1160`
- `B4 = [5688, 5692]` em `1180-1208`

### Por que ela é ruim

- só `155 min` de trabalho útil em `839 min` de spread
- `684 min` de idle total
- carrega uma pausa central extremamente longa
- consome janela operacional e penaliza fortemente o custo de CSP via unpaid break/espera

Em resumo:

- não é uma duty “longa porém produtiva”
- é uma duty estruturalmente ociosa

### Movimentos tentados

Tentativas já executadas antes desta decisão:

- reconstrução local completa da duty
- anexação de bundles em duties vizinhas
- criação de dedicated compacta
- dual-edge trim
- multi-edge trim

Tentativa estrutural mais promissora identificada:

- manter `B1+B2` como duty curta de manhã
- manter `B3+B4` como duty curta de fim de dia

### Por que foram rejeitados no funil local

Motivos predominantes observados:

- `append_target_overlap`
- `prepend_target_overlap`
- `append_target_spread_exceeded`
- `prepend_target_spread_exceeded`
- `append_target_min_interval_violation`
- `prepend_target_min_interval_violation`
- `reconstruction_not_better`

Leitura:

- o pós-opt local não encontrou encaixe bom das pontas em duties já existentes
- quando tentou reconstrução completa, o ranking local não aceitou o candidato como melhora líquida
- portanto a duty extrema permaneceu intacta

### Impacto de aceitar essa exceção no cenário atual

Ao aceitar a duty `524/201` como exceção:

- o plano continua com cobertura completa
- não há viagens perdidas
- não há viagens duplicadas
- não há novas hard violations
- veículos permanecem em `15`
- o principal ônus é de qualidade operacional da tripulação, não de viabilidade

Risco operacional:

- existe uma jornada muito ociosa e longa no plano
- o plano fica aceitável só se isso for assumido conscientemente como exceção

## 3. Política operacional proposta

### `acceptable`

- aceitar sem bloqueio

Critério:

- duty fora da cauda extrema crítica

### `borderline`

- aceitar com warning

Critério:

- duty abaixo de `25%`, mas limítrofe
- exemplo atual: `520/197`

Tratamento:

- manter registrada como exceção monitorada
- não bloquear a publicação do schedule

### `critical`

Três saídas possíveis:

1. `aceitar com warning`
   - só quando não houver recurso adicional disponível
   - deve ficar explicitamente registrado como exceção operacional

2. `rejeitar`
   - quando a política da operação exigir `0` duties críticas
   - ou quando existir alternativa viável de baixo impacto

3. `tentar cenário alternativo com +1 duty/crew ou +1 veículo`
   - preferir `+1 duty/crew` antes de `+1 veículo`
   - porque aqui o problema é de composição de duty, não de frota

## 4. Cenário alternativo com +1 duty/crew

### Método

Sem usar novo pós-opt local, foi avaliado um cenário explícito de `+1 duty/crew` diretamente no CSP, preservando os blocos VSP atuais e apenas dividindo a duty `201` em duas duties contíguas:

- duty `201` nova: `B1+B2 = [5458,5461,5486,5491]`
- duty `212` nova: `B3+B4 = [5667,5677,5688,5692]`

Métricas dessas duas duties:

- duty `201`: `47 min` de trabalho, `90 min` de spread
- duty `212`: `108 min` de trabalho, `138 min` de spread

Ou seja:

- a duty extrema desaparece
- o caso crítico vira duas duties compactas

### Validação de segurança

Mantido no cenário `+1 duty/crew`:

- `0` hard violations
- `0` uncovered blocks
- `0` viagens perdidas
- `0` viagens duplicadas
- mesmos `2` warnings conhecidos de `PAIR_GROUP_ROSTER_SPLIT`

## 5. Comparação: atual vs `+1 duty/crew`

| Métrica | Atual | `+1 duty/crew` | Delta |
|---|---:|---:|---:|
| Custo total | `R$ 247.290,87` | `R$ 246.419,74` | `- R$ 871,13` |
| Veículos | `15` | `15` | `0` |
| Duties | `19` | `20` | `+1` |
| Crew | `17` | `18` | `+1` |
| Duties `<25%` | `2` | `1` | `-1` |
| Duties `<30%` | `2` | `1` | `-1` |
| Duties `>12h` | `8` | `7` | `-1` |
| Utilização média | `59,29%` | `61,93%` | `+ 2,64 p.p.` |
| Idle médio | `250,68 min` | `207,60 min` | `- 43,08 min` |
| Overtime | `179 min` | `179 min` | `0` |
| Hard violations | `0` | `0` | `0` |

Leitura:

- o cenário `+1 duty/crew` melhora exatamente a cauda que a política quer controlar
- remove a duty `critical`
- reduz duties `<25%` de `2` para `1`
- mantém veículos
- não piora hard violations
- e ainda melhora custo no evaluator local, porque elimina uma duty muito penalizada por long unpaid break

## 6. Recomendação final

### Se a operação aceitar exceção

Recomendação:

- `aceitar com warning` a duty `524/201`
- classificar:
  - `524/201 = critical`
  - `520/197 = borderline`
- registrar explicitamente que o plano segue viável, mas com uma exceção operacional consciente

### Se a política exigir no máximo 1 duty `<25%`

Recomendação:

- `usar o cenário +1 duty/crew`

Justificativa:

- atende o objetivo político de reduzir duties `<25%` de `2` para `1`
- elimina a única duty `critical`
- mantém `0` hard violations
- não aumenta veículos
- melhora custo e idle médio

### Recomendação preferencial

`adotar o cenário +1 duty/crew`

Motivo:

- transforma uma exceção crítica em uma exceção apenas borderline
- melhora indicadores operacionais relevantes
- não exige `+1 veículo`
- e é superior ao cenário atual mesmo em custo

## 7. Veredito executivo

Para decisão final:

- cenário atual: `aceitável apenas com warning explícito`
- cenário `+1 duty/crew`: `recomendado`

Resumo:

- se não houver margem para mais `1` crew/duty, publicar com exceção explícita
- se houver margem operacional mínima, o melhor cenário é o de `+1 duty/crew`
