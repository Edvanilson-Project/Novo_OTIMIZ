# Checklist de Conformidade — Optbus / Goal Systems

Referência: formatos de intercâmbio Optbus (HASTUS-style) e Goal Systems (*Vehicle Duty*/*Crew Duty*).

## Legenda
- ✅ conforme
- ⚠ parcial / ajuste recomendado
- ❌ divergência bloqueante para integração

## A. Modelo de dados de entrada (`schemas.py`)

| Campo Optbus/Goal | Atual (`TripInput`) | Status | Observação |
|---|---|---|---|
| `trip_number` (int) | `id: int` | ✅ | Mapeável 1:1. |
| `line_code` (str 6 chars) | `line_id: int` | ⚠ | Optbus exige código alfanumérico; adicionar `line_code: str` opcional. |
| `place_from` / `place_to` (code) | `origin_id` / `destination_id` (int) | ⚠ | Necessita mapping para códigos de ponto (stop_code). |
| `time_from` / `time_to` (HH:MM:SS) | `start_time`/`end_time` (minutos desde meia-noite, `int`) | ❌ | Converter para ISO 8601 na fronteira de saída. Internamente `int` é ok (performance). |
| `vehicle_type` (str) | `VehicleTypeInput.id: int` + `name: str` | ⚠ | Expor `name` como código primário no output. |
| `service_day` (YYYY-MM-DD) | `service_day: Optional[int]` | ❌ | Inteiro não interpreta data; adotar `date` ISO. |

## B. Restrições de jornada (CCT / Optbus `duty_rules`)

| Regra | Implementação | Status |
|---|---|---|
| `max_shift_minutes` (spread) | `VCSPJointSolver.max_shift_minutes` (default 720) | ✅ |
| `max_work_minutes` | `VCSPJointSolver.max_work_minutes` (default 480) | ✅ |
| `meal_break` janela configurável | `meal_break_minutes` (default 60), sem janela obrigatória entre 3h–5h | ⚠ Adicionar `meal_break_window_start/end` conforme Goal. |
| `min_inter_shift_rest` | `min_inter_shift_rest_minutes` (660) | ✅ |
| `relief only at terminal` | Aplicado via `terminal_location_ids` (vcsp_solver.py:586) | ✅ |
| `max_continuous_driving` | `GreedyCSP.max_driving` (270) | ✅ |
| `overtime_multiplier` | `Decimal('1.5')` default | ✅ |
| `weekly_driving_limit` | `weekly_driving_limit_minutes` (3360) | ✅ |
| `fortnight_driving_limit` | `fortnight_driving_limit_minutes` (5400) | ✅ |
| `nocturnal window` | `nocturnal_start/end_hour` + `_nocturnal_overlap` | ✅ |

## C. Saídas (Vehicle Block / Crew Duty)

| Campo Optbus/Goal | Atual | Status |
|---|---|---|
| `block_id` | `Block.id: int` | ✅ |
| `pull_out_place`, `pull_out_time` | `block.meta["start_depot_id"]` | ⚠ Falta `pull_out_time` ISO. |
| `pull_in_place`, `pull_in_time` | `block.meta["end_depot_id"]` | ⚠ Idem. |
| `deadhead_minutes` | `block.meta["deadhead_minutes"]` | ✅ |
| `idle_minutes` | `block.meta["idle_minutes"]` | ✅ |
| `activation_cost` | `block.meta["activation_cost"]` | ✅ |
| `duty_id` | `Duty.id` | ✅ |
| `duty_segments` (com `piece_type`, `from_time`, `to_time`) | `DutySegment` (via `duty.add_task`) | ⚠ Validar emissão explícita de `piece_type` (sign-on/drive/sign-off/break). |
| `overtime_minutes` | `duty.overtime_minutes` | ✅ |
| `illegal_relief` flag | `duty.meta["illegal_relief"]` | ✅ (Goal compatível como warning) |

## D. Fluxo e custos (MCNF / Bipartite Matching)

| Item | Observação |
|---|---|
| Modelagem 2N×2N com `linear_sum_assignment` | Docstring menciona, porém implementação real é MILP via PuLP/CBC (`mcnf.py:313`). Atualizar docstring para refletir Set-Partitioning real. |
| Penalidade de conexão inter-linha | `cost -= fixed_cost * 0.05` quando `origin==destination` (mcnf.py:286). Não-padrão Optbus; documentar. |
| Depot capacity constraint | Modelada como restrição linear (mcnf.py:352). ✅ |
| Pull-out + fixed activation | `pullout_costs[(did,i)] = fixed_cost + (dh*deadhead_cost)` ✅ |
| Big-M para viagens não atribuídas | Dinâmico (vcsp_solver.py:307–336). ✅ Porém usa `0.5 R$/min` hardcoded — não reflete parâmetro de custo real. ⚠ |

## E. Itens bloqueantes para integração externa

1. ❌ Converter `start_time`/`end_time` em ISO ao serializar para sistemas Optbus.
2. ❌ Expor `service_day` como `YYYY-MM-DD`.
3. ⚠ Adicionar `line_code`/`vehicle_code` como strings na fronteira de saída (camada `api/converters.py`).
4. ⚠ Adicionar `pull_out_time` / `pull_in_time` no `block.meta`.
5. ⚠ Padronizar sentinela de deadhead ausente (MCNF usa 0, VCSP usa 999_999).

## F. Resumo

- **Regras de jornada:** 95% compatível (apenas janela de refeição e `piece_type` pendentes).
- **Modelo de custo:** núcleo correto; magic numbers a parametrizar.
- **Formato de dados:** internamente eficiente (int minutes), mas **não pronto** para export direto Optbus/Goal — requer camada conversora ISO na `api/converters.py`.
- **Robustez:** um bug bloqueante corrigido (`Ellipsis`), dois riscos de concorrência identificados, um risco de inconsistência de sentinela.
