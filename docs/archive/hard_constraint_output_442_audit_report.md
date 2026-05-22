# HARD_CONSTRAINT_OUTPUT 442 - Auditoria Auditavel

## Escopo

- Empresa: 16
- Execucao original auditada: 442
- Restricoes do trabalho:
  - nao mexer em frontend, CSV ou UI;
  - nao relaxar regra hard para passar;
  - nao esconder violacao em production;
  - corrigir ou explicar de forma auditavel o HARD_CONSTRAINT_OUTPUT.

## Conclusao executiva

O HARD_CONSTRAINT_OUTPUT da execucao 442 nao era uma inviabilidade operacional provada do par [5590, 5597]. Era um bug de selecao de solucao no optimizer.

O grupo [5590, 5597] foi materializado como grupo obrigatorio pelo backend/optimizer, mas candidatos VSP e candidatos de pos-otimizacao ainda podiam ser escolhidos mesmo quebrando esse grupo, porque o pipeline nao tratava essa quebra como hard regression na comparacao local.

Em paralelo, parte das violacoes MANDATORY_REST_MISSING continha um falso positivo: janela longa sem trabalho produtivo suficiente estava marcando mandatory rest required apenas por spread alto.

## Evidencia da 442

### Sintoma observado

- A 442 terminou com HARD_CONSTRAINT_OUTPUT.
- O hard report continha MANDATORY_GROUP_SPLIT [5590, 5597].
- A auditoria de grupos mostrava um unico split_group.

### Fato operacional do par auditado

- Trip 5590:
  - janela 805 -> 847;
  - origem 2;
  - destino 1;
  - direction IDA.
- Trip 5597:
  - janela 847 -> 874;
  - origem 1;
  - destino 2;
  - direction VOLTA.

As duas viagens eram contiguas no tempo e formavam um encadeamento natural de ida/volta.

### Fato de dados

- No input cru do banco, as viagens nao tinham tripGroupId real util para esse par.
- O optimizer materializou um trip_group_id sintetico para obrigar o grupo no solve.
- Portanto, se o resultado final separa [5590, 5597], a separacao foi introduzida pelo solver/pipeline, nao pelo dado de entrada.

## Causa raiz

### Causa raiz 1: selecao VSP e pos-opt aceitavam regressao de grupo obrigatorio

O fluxo materializava grupos obrigatorios via _inject_trip_group_constraints, inclusive ativando:

- hard_pairing_vehicle_level = true;
- hard_pairing_penalty.

Mas havia dois pontos de perda de garantia:

1. MCNFVSP originalmente nao internalizava hard_pairing_vehicle_level como custo suficientemente duro.
2. Mesmo depois desse ajuste, a selecao posterior ainda podia aceitar um candidato que reabria o split, porque:
   - o HybridPipeline contava hard issues VSP sem incluir split de trip_group obrigatorio;
   - o joint post-opt comparava candidatos pelo score global e podia aceitar uma solucao com menos crew mesmo piorando trip_group_split_groups.

Ou seja: o contrato de grupo obrigatorio existia na injecao da restricao, mas ainda nao era preservado como criterio hard em toda a cadeia de selecao.

### Causa raiz 2: mandatory rest required estava sensivel a spread alto sem trabalho suficiente

No operational_time_service, mandatory_rest_required podia ser acionado por spread_time alto mesmo quando a duty nao ultrapassava o limiar de trabalho produtivo exigido pela regra.

Isso gerava falso positivo em jornadas com janela longa, mas com pouco trabalho efetivo.

## Correcoes aplicadas

### Correcao A: endurecimento do pairing obrigatorio no MCNF

Arquivo alterado:

- optimizer/src/algorithms/vsp/mcnf.py

Resumo:

- quando hard_pairing_vehicle_level esta ativo, o MCNF passa a usar hard_pairing_penalty na quebra do par obrigatorio;
- o mesmo endurecimento foi aplicado ao custo de pull-in que encerrava bloco antes do par obrigatorio.

Efeito esperado:

- o baseline VSP deixa de tratar esse agrupamento como mera preferencia suave.

### Correcao B: mandatory rest so quando ha trabalho que dispara a regra

Arquivo alterado:

- optimizer/src/services/operational_time_service.py

Resumo:

- mandatory_rest_required deixou de ser acionado por spread_time isolado;
- a exigencia passou a depender de trabalho produtivo e drive continuo compatíveis com a regra.

Efeito esperado:

- jornadas com janela longa, mas com trabalho abaixo do limiar, nao geram falso mandatory rest missing.

### Correcao C: tratar split de trip_group obrigatorio como regressao hard na selecao

Arquivos alterados:

- optimizer/src/algorithms/hybrid/pipeline.py
- optimizer/src/algorithms/joint_opt.py

Resumo:

- o HybridPipeline agora conta split de trip_group em mais de um bloco como hard issue quando hard_pairing_vehicle_level esta ativo;
- o post-opt agora rejeita candidato que piora trip_group_split_groups quando a integridade do grupo esta marcada como hard;
- a comparacao principal do post-opt deixou de aceitar regressao de grupo obrigatorio apenas porque o score global melhorou.

Efeito esperado:

- uma solucao mais barata ou com menos crew nao pode vencer se ela reintroduzir o split obrigatorio.

## Testes adicionados e executados

### Testes adicionados

- optimizer/tests/unit/test_vsp_tolerance_and_multiline.py
  - test_hard_pairing_vehicle_level_forces_pair_when_soft_mode_splits
  - test_hard_pairing_split_counts_as_vsp_hard_issue
- optimizer/tests/unit/test_operational_time_semantics.py
  - test_long_spread_with_low_work_does_not_require_mandatory_rest
- optimizer/tests/unit/test_fragmentation_postopt.py
  - test_post_opt_comparator_rejects_trip_group_split_regression_when_integrity_is_hard

### Validacao executavel

- Suite focada VSP + post-opt:
  - 31 testes passaram.
- Suite obrigatoria do optimizer mais slice tocado:
  - 131 testes passaram;
  - 1 warning conhecido de Pydantic.

## Evidencia runtime

### Execucao 443

- Objetivo: validar a primeira correcao de split apos reinicio do runtime.
- Resultado observado:
  - split_groups = 0;
  - 5590 e 5597 ficaram no mesmo bloco e na mesma duty;
  - soft issues cairam para 4, mas ainda com worker antigo para a regra de mandatory rest.

Conclusao:

- confirmou que o primeiro bug tinha sido atacado no baseline e no fluxo real;
- ainda nao validava a segunda correcao, porque o worker precisava ser reiniciado.

### Execucao 444

- Objetivo: validar a regra nova de mandatory rest no runtime.
- Resultado observado:
  - cct_violations = 3;
  - os soft issues cairam de 4 para 3;
  - porem o split [5590, 5597] reapareceu no resultado final;
  - a persistencia final foi HARD_CONSTRAINT_OUTPUT.

Diagnostico da 444:

- a melhoria de soft issues estava correta;
- o split obrigatorio reapareceu no resultado final porque o post-opt ainda podia aceitar regressao de grupo obrigatorio.

### Execucao 445

- Objetivo: validar o runtime apos a correcao final da selecao VSP/post-opt.
- Resultado observado:
  - schedule 445 persisted como completed;
  - error_code = null;
  - hardConstraintReport.output.ok = true;
  - hard_issues = 0;
  - soft_issues = 3;
  - soft issues remanescentes: D6, D10, D12;
  - trip_group_audit:
    - groups_total = 149;
    - split_groups = 0;
    - same_block_groups = 149;
    - same_duty_groups = 149;
    - same_roster_groups = 149;
  - latest-schedule retornou completed com hardIssueCount = 0 e softIssueCount = 3.

Prova do par auditado:

- block_assignments da 445:
  - block 13 contem {5590,5597};
- duty_assignments da 445:
  - duty 13 contem {5590,5597};
  - mandatory_rest_required = false;
  - sem violacoes nessa duty.

Conclusao da 445:

- a reintroducao do split obrigatorio foi eliminada no runtime;
- a queda de 4 para 3 soft issues foi preservada;
- o latest-schedule e a persistencia do banco ficaram coerentes com o resultado validado.

## Classificacao final da 442

- Classificacao: BUG
- Nao classificar como inviavel.

Justificativa:

1. o par [5590, 5597] e temporalmente contiguo e operacionalmente encadeavel;
2. o proprio sistema o materializou como grupo obrigatorio;
3. a quebra ocorreu por selecao indevida de candidato, nao por prova de impossibilidade operacional;
4. houve reproducao runtime que mostrou o split desaparecer e depois reaparecer por outro ponto de selecao, confirmando problema de software e nao inviabilidade fisica.

## Estado atual

### Pronto

- mandatory rest falso-positivo por spread alto foi corrigido e testado;
- regressao de split obrigatorio agora foi tratada tambem na selecao do pipeline e do post-opt;
- testes unitarios focados e suite obrigatoria passaram.

### Ainda depende de evidencia runtime final

- nada pendente para a classificacao do caso 442.

## Fechamento

Com a 445 concluida, o caso fica auditavelmente fechado assim:

1. a 442 falhou por bug de software, nao por inviabilidade operacional provada;
2. a regra de mandatory rest foi ajustada para remover o falso positivo por spread alto;
3. a selecao VSP/post-opt foi corrigida para impedir regressao de trip_group obrigatorio;
4. a reproducao real final 445 confirmou:
  - nenhum hard issue;
  - [5590, 5597] preservado no mesmo bloco, duty e roster;
  - 3 soft issues remanescentes, todos de mandatory rest, sem esconder violacao.
