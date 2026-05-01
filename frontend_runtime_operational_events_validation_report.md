# Frontend Runtime Operational Events Validation Report

Data: 2026-05-01
Ambiente validado: http://localhost:3000/operations/planner

## 1. Escopo

Validação runtime do frontend sem alterar core, solver, optimizer, backend ou decision engine.

Objetivos cobertos:

- abrir o Planner real no navegador;
- validar o card decisório operacional em tela;
- exportar o CSV operacional pela própria UI;
- comparar o CSV da UI com o CSV do CLI gerado por `scripts/export_programacao_operacional.py --company-id 16`;
- verificar consistência de contagens, durações e labels operacionais.

## 2. Ajuste frontend necessário para fechar a validação

Foi identificada uma divergência local no exportador da UI em [frontend/src/app/(DashboardLayout)/operations/planner/_components/TabGantt.tsx](frontend/src/app/(DashboardLayout)/operations/planner/_components/TabGantt.tsx):

- `driver_id` era exportado vazio em todas as linhas;
- `driver_idle` não estava mapeado explicitamente para `Ociosa` no CSV;
- a explicação do fallback de motorista não acompanhava o contrato do CLI.

O ajuste foi feito somente no frontend, no builder `buildOperationalExportRows`, alinhando o CSV da UI ao contrato já usado no CLI.

## 3. Evidência visual real no Planner

Validação feita via Playwright em http://localhost:3000/operations/planner.

### 3.1 Card decisório operacional visível

Elementos confirmados em tela:

- card de decisão operacional visível;
- `chosen_scenario`: `Plano +1 duty`;
- `operational_quality_mode`: `balanced`;
- `justification` visível com explicação do critério balanced;
- `trade_offs` visíveis com bullets do cenário escolhido.

Trechos confirmados pelo navegador:

- `Cenário escolhido: Plano +1 duty`
- `Modo: balanced`
- `Modo operacional selecionado: balanced.`
- `Trade-offs do cenário escolhido:`

### 3.2 Labels operacionais confirmados visualmente

Na aba `Motoristas`, expandindo jornadas reais:

- `Motorista 4`: aparecem visualmente `Início de jornada`, `Soltura`, `Viagem`, `Intervalo normal`, `Descanso obrigatório` e `Fim de jornada`.
- `Motorista 15`: aparecem visualmente `Início de jornada`, `Viagem`, `Intervalo normal`, `Recolhimento` e `Fim de jornada`.

Status dos labels pedidos:

- `Início de jornada`: confirmado visualmente.
- `Fim de jornada`: confirmado visualmente.
- `Viagem`: confirmado visualmente.
- `Intervalo normal`: confirmado visualmente.
- `Descanso obrigatório`: confirmado visualmente.
- `Soltura`: confirmado visualmente.
- `Recolhimento`: confirmado visualmente.
- `Ociosa`: não apareceu visualmente neste cenário porque o dataset atual exportado pela UI e pelo CLI contém `0` eventos `idle/driver_idle`.

## 4. Exportação real do CSV pela UI

O botão `Programação Operacional` foi acionado na aba `Viagens` do Planner.

O arquivo gerado pela UI foi validado a partir do blob produzido pelo navegador no clique real do botão, com os seguintes resultados:

- total de linhas: `338`
- nenhuma duração inválida: `0`
- nenhuma ocorrência de `Refeição` genérica: `0`
- linhas com `driver_id` vazio: `0`
- total de `trip_ids` comerciais: `298`

Header confirmado no CSV da UI:

- `schedule_id, block_id, duty_id, driver_id, vehicle_id, sequence, event_type, event_label, start_time, end_time, duration_minutes, origin_id, destination_id, trip_ids, is_work_time, is_driving_time, is_idle_time, is_normal_break, is_mandatory_rest, is_pullout, is_pullback, rest_valid, rule_code, violation_code, explanation`

## 5. Comparação UI x CLI

CSV do CLI validado com:

- `scripts/export_programacao_operacional.py --company-id 16`

Resultado da comparação:

- total de linhas UI = `338`
- total de linhas CLI = `338`
- mesma contagem por `event_type`: `sim`
- nenhuma duração inválida na UI: `0`
- nenhuma duração inválida no CLI: `0`
- nenhuma `Refeição` genérica na UI: `0`
- nenhuma `Refeição` genérica no CLI: `0`
- `driver_id` vazio na UI: `0`
- `driver_id` vazio no CLI: `0`
- total de `trip_ids` comerciais na UI: `298`
- total de `trip_ids` comerciais no CLI: `298`

### 5.1 Contagem por event_type

Mesma contagem na UI e no CLI:

- `commercial_trip`: `149`
- `duty_start`: `21`
- `duty_end`: `21`
- `idle`: `0`
- `driver_idle`: `0`
- `normal_break`: `74`
- `mandatory_rest`: `54`
- `pullout`: `12`
- `pullback`: `7`
- `deadhead`: `0`

## 6. Por que agora são 338 linhas

Decomposição das `338` linhas exportadas:

- `42` linhas de abertura/fechamento de jornada:
  - `21` `duty_start`
  - `21` `duty_end`
- `149` linhas de `commercial_trip`
- `128` linhas de intervalos:
  - `74` `normal_break`
  - `54` `mandatory_rest`
  - `0` `idle/driver_idle`
- `19` linhas operacionais de garagem:
  - `12` `pullout`
  - `7` `pullback`

Soma:

- `42 + 149 + 128 + 19 = 338`

## 7. Regras de validação pedidas

### 7.1 Nenhuma `Refeição` genérica

Resultado: `ok`

- UI: `0` ocorrências
- CLI: `0` ocorrências

### 7.2 `duration_minutes = end_time - start_time`

Resultado: `ok`

- UI: `0` divergências
- CLI: `0` divergências

### 7.3 `driver_id` vazio somente se `operator_not_assigned=true`

Resultado observável no CSV exportado: `ok, sem linhas com driver_id vazio`

Observação:

- o CSV exportado não carrega a coluna `operator_not_assigned`;
- após o ajuste do frontend, o export da UI passou a preencher `driver_id` com o identificador da duty, em linha com o CLI;
- portanto não restaram linhas vazias em `driver_id` nem na UI nem no CLI.

### 7.4 Total de `trip_ids` comerciais = `298`

Resultado: `ok`

- UI: `298`
- CLI: `298`

### 7.5 CSV da UI e CLI com mesma contagem por `event_type`

Resultado: `ok`

- todas as contagens por `event_type` coincidem entre UI e CLI.

## 8. Veredito

**UI pronta**

Motivo:

- houve evidência real no navegador do Planner via Playwright;
- o card decisório operacional apareceu com cenário, modo, justificativas e trade-offs;
- o CSV foi exportado pela própria UI;
- o CSV da UI fechou com `338` linhas, `298` trip_ids comerciais, `0` `driver_id` vazios e `0` durações inválidas;
- a contagem por `event_type` da UI ficou idêntica à do CLI.