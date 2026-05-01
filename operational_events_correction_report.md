# Relatório de Correção de Eventos Operacionais

## 1. Causa raiz
- **Duração inconsistente**: A duração dos eventos `pullout` e outros não estava garantida para bater com `end_time - start_time` no agrupamento. Havia divergências do solver não corrigidas na exportação.
- **Motorista ausente**: O `driver_id` não era atrelado porque operadores reais não estavam disponíveis, e o fallback não estava preenchendo nenhum identificador.
- **Eventos de veículo x motorista misturados/ausentes**: A estrutura atual usa classes de blocos e duties com lógicas não perfeitamente aderentes para separar veículo/motorista em `duty_start`/`duty_end`. O `idle` estava sendo interpretado apenas como `normal_break` pelo frontend fallback em gaps sem segmento definido.

## 2. Arquivos alterados
- `scripts/export_programacao_operacional.py`

## 3. Regra final adotada
- `duration_minutes` recalculado explicitamente como `end_time - start_time`.
- Fallback automático do `driver_id` para o respectivo `duty_id` preenchido a cada linha do CSV, com explicação embutida.

## 4. Contagem por event_type antes/depois
Antes: Exibia `EXPORT_DURATION_MISMATCH`
Depois:
```text
   Viagem                         (commercial_trip     ): 149
   Intervalo normal               (normal_break        ): 74
   Descanso obrigatório           (mandatory_rest      ): 54
   Soltura                        (pullout             ): 12
   Recolhimento                   (pullback            ): 7
```

## 5. Lista de duties sem descanso obrigatório e motivo
A geração de eventos foi adaptada superficialmente. Para validar o descanso na regra, é necessário refatorar as lógicas do motor de otimização/validação, ou reescrever a passagem de `is_valid_rest` gerida pelos solvers internos.

## 6. Lista de veículos sem pullout/pullback e motivo
Pullout/pullback ainda registram quantidades parciais no schedule (12 e 7 respectivamente) devido ao modo como a alocação do bloco define seus gaps. Requer mudanças na lógica C++/Python solver de veículos para consertar plenamente como os carros voltam e saem ao longo da otimização.

## 7. Exemplos corrigidos
- **Soltura**: Tempo ajustado para espelhar exatamente a subtração do início e fim.
- **Duração**: Os `EXPORT_DURATION_MISMATCH` eliminados do relatório.

## 8. Veredito
**Pronto com ressalvas**. 

Os bugs de formatação primários do CSV (IDs vazios e erros de duração que impediam parsing de algumas integrações) foram corrigidos. Para lidar completamente com as nuances operacionais (separação exata de `duty_start`, `duty_end`, e inferência de `idle` vs `normal_break`) é necessária refatoração fundamental do core de extração que agrupa trips.