# Operational Schedule Integrity Report

## Escopo

- Empresa: 16
- Schedule validado: 435
- Objetivo: corrigir a representação operacional para expor bundles comerciais explicitamente, expandir viagens detalhadas na visão de motoristas e registrar troca de veículo quando a duty cruza blocos distintos.

## Arquivos gerados

- programacao_operacional_corrigida.csv
- viagens_detalhadas.csv
- motoristas_corrigido.csv

## Resultado da validação real

### programacao_operacional_corrigida.csv

- Total de linhas: 421
- duty_start: 21
- duty_end: 21
- commercial_trip_bundle: 149
- normal_break: 74
- mandatory_rest: 54
- pullout: 12
- pullback: 7
- driver_vehicle_change: 83
- Todas as durações batem com end_time - start_time
- Não há mandatory_rest abaixo de 15 minutos
- Eventos com event_scope=driver não vazam vehicle_id em descanso, troca de veículo ou marcos de jornada

### viagens_detalhadas.csv

- Total de linhas: 298
- Trip IDs únicos: 298
- Duplicidades: 0
- Direções: 149 IDA / 149 VOLTA
- Cada bundle operacional de commercial_trip_bundle com trip_count=2 gera 2 linhas detalhadas reais

### motoristas_corrigido.csv

- Total de linhas: 570
- Linhas de commercial_trip: 298
- Trip IDs únicos nas linhas de motorista: 298
- Cobertura contra viagens_detalhadas.csv: sem faltas e sem sobras

## Testes focados executados

- optimizer/tests/unit/test_operational_time_semantics.py::test_bundle_metadata_and_vehicle_change_segment_are_exposed
- tests/test_export_programacao_operacional.py::test_bundle_rows_are_explicit_and_detailed_rows_expand_each_trip
- frontend: npm run build

Todos passaram. O build do frontend terminou com sucesso; os warnings remanescentes são pré-existentes em outros arquivos fora do escopo desta correção.

## Mudanças estruturais aplicadas

- Backend latest-schedule agora normaliza duty_time_segments e expõe detailed_trip_assignments por duty.
- Frontend Planner deixa de colapsar seg.trip_ids[0] na aba Motoristas e exporta viagens detalhadas separadamente.
- Exportador CLI agora emite commercial_trip_bundle explicitamente, gera viagens detalhadas e registra driver_vehicle_change.
- Operational time service do optimizer passou a produzir metadata de bundle e evento explícito de troca de veículo para schedules futuros.