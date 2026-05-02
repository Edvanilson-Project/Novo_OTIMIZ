# Company 16 Frontend/CSV Baseline 448 Report

## 1. Schedule usada

- Empresa validada: 16.
- Baseline final usada nesta fase: schedule_id 448.
- Status operacional consolidado: completed.
- Cenário escolhido persistido e exibido: current_plan.
- Modo operacional persistido e exibido: balanced.

## 2. latest-schedule validado

O contrato canônico do latest-schedule na porta 3001 foi validado nesta sessão depois da correção do backend e do rebuild do serviço. A schedule 448 ficou exposta com os campos exigidos para a representação operacional do Planner.

Campos validados no fluxo final:

- schedule_id = 448
- status = completed
- hardIssueCount = 0
- softIssueCount = 1
- chosen_scenario = current_plan
- operational_quality_decision presente
- trip_group_audit.split_groups = 0
- duties presentes no topo
- duties[].duty_time_segments presentes
- duties[].operational_time_report presentes

Conclusão desta etapa: o problema remanescente não estava mais no latest-schedule, e sim na paridade de exportação/representação entre UI e CLI.

## 3. Contagem final por CSV

Após o último patch de paridade, a UI exportou exatamente o mesmo conteúdo do CLI para a schedule 448.

- programacao_operacional.csv: 532 linhas
- viagens_detalhadas.csv: 298 linhas
- motoristas.csv: 681 linhas

Comparação final UI vs CLI:

- programacao_operacional.csv: headers_equal = True, exact_match = True
- viagens_detalhadas.csv: headers_equal = True, exact_match = True
- motoristas.csv: headers_equal = True, exact_match = True

Observação operacional: o ajuste final necessário foi alinhar a serialização de horários após meia-noite na UI para o formato do CLI, preservando 24:xx nos CSVs em vez de 00:xx +1.

## 4. Evidência de 298 viagens detalhadas

O CSV viagens_detalhadas.csv fechou com 298 linhas operacionais individuais e 298 source_trip_id únicos.

Isso confirma que, para a empresa 16, a visão detalhada preserva a cardinalidade real de viagens individuais e não colapsa ida/volta em uma única linha.

Também foi mantido o drill-down honesto da programação agrupada:

- programacao_operacional.csv pode representar bundles operacionais
- viagens_detalhadas.csv preserva 1 linha por viagem real

## 5. Evidência de ida/volta preservadas

A contagem final por direção no CSV detalhado ficou:

- 149 IDA
- 149 VOLTA

Conclusão: a baseline 448 preserva ida e volta separadamente na exportação detalhada, sem perda de direção e sem colapso indevido da operação.

## 6. Evidência de D6 como soft issue auditada

A D6 permaneceu como a única ressalva operacional residual da baseline final.

Evidência validada no fluxo final:

- hard_issue_count = 0
- soft_issue_count = 1
- soft issue residual = MANDATORY_REST_MISSING
- duty afetada = D6
- representação de operador ausente preservada com operator_not_assigned = True

No motoristas.csv final, a D6 aparece explicitamente com:

- duty_id = 6
- driver_display_name = Operador não atribuído (D6)
- issue_severity = soft
- issue_codes = MANDATORY_REST_MISSING
- suggestion/explanation auditável para revisão operacional

Conclusão: a D6 não foi escondida, nem mascarada como motorista real, nem tratada como hard violation indevida. Ela foi exposta como ressalva auditável, que era o objetivo correto desta fase.

## 7. Evidência visual/textual da UI

O Planner em produção local no frontend atualizado exibiu corretamente a baseline 448 já alinhada ao backend canônico.

Elementos visuais validados nesta sessão:

- KPI de Frota = 13
- KPI de Viagens = 298
- KPI de Hard Issues = 0
- KPI de Soft Issues = 1
- KPI de Trip Groups Split = 0
- card de decisão operacional presente
- alerta visual de restrição crítica mostrando MANDATORY_REST_MISSING D6
- aba Motoristas mostrando Jornada D6
- rótulo Operador não atribuído (D6)
- indicação visual do soft issue e explicação associada

Conclusão: a UI passou a representar jornada, operador ausente, D6 residual e KPIs operacionais sem inventar motorista e sem esconder a exceção residual.

## 8. Testes e validações executados

Validações executadas nesta frente:

- backend: npm test -- optimization.service.spec.ts
- backend: npm run build
- frontend: npx tsc --noEmit
- frontend: npm run build
- geração CLI oficial da baseline 448 via scripts/export_programacao_operacional.py
- comparação automatizada UI vs CLI dos três CSVs exportados

Resultado da comparação final:

- 0 diferenças em programacao_operacional.csv
- 0 diferenças em viagens_detalhadas.csv
- 0 diferenças em motoristas.csv

## 9. Pendências restantes

Pendência operacional remanescente:

- D6 continua com soft issue MANDATORY_REST_MISSING, já auditada e conhecida desde o fechamento do baseline 448

Pendências de frontend/CSV desta fase:

- nenhuma divergência residual entre UI e CLI

Itens não bloqueantes observados durante o build do frontend:

- warnings de lint já existentes e não relacionados à lógica de exportação/representação validada aqui

## 10. Veredito

Veredito final desta fase:

PRONTO PARA PILOTO CONTROLADO COM RESSALVA D6.

Justificativa objetiva:

- latest-schedule canônico validado para a schedule 448
- Planner visual validado com KPIs e D6 corretos
- programacao_operacional.csv validado
- viagens_detalhadas.csv validado com 298 viagens individuais
- ida/volta preservadas
- motoristas.csv validado com D6 auditável e operador ausente explícito
- UI e CLI em paridade exata nos três CSVs finais

Portanto, o baseline final 448 está representado corretamente no backend, no frontend e nas exportações CSV, sem divergência residual de representação. A única ressalva remanescente continua sendo a D6 já auditada como soft issue operacional, não um defeito novo de persistência, frontend ou exportação.