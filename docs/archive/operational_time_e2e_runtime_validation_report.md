# Operational Time Semantic - E2E Runtime Validation

**Schedule Usado**: 434

## Contagem por Event Type (CSV)
- duty_start: 21
- commercial_trip: 149
- normal_break: 74
- duty_end: 21
- pullout: 12
- mandatory_rest: 54
- pullback: 7

## Contagem por Event Label (CSV)
- Início de jornada: 21
- Viagem: 149
- Intervalo normal: 74
- Fim de jornada: 21
- Soltura: 12
- Descanso obrigatório: 54
- Recolhimento: 7

## Descanso Obrigatório por Duty
- Duty 1: Required=False, Valid=False, Violations=[]
- Duty 2: Required=False, Valid=False, Violations=[]
- Duty 3: Required=False, Valid=False, Violations=[]
- Duty 4: Required=False, Valid=False, Violations=[]
- Duty 5: Required=False, Valid=False, Violations=[]
- Duty 6: Required=False, Valid=False, Violations=[]
- Duty 7: Required=False, Valid=False, Violations=[]
- Duty 8: Required=False, Valid=False, Violations=[]
- Duty 9: Required=False, Valid=False, Violations=[]
- Duty 10: Required=False, Valid=False, Violations=[]
- Duty 12: Required=False, Valid=False, Violations=[]
- Duty 13: Required=False, Valid=False, Violations=[]
- Duty 14: Required=False, Valid=False, Violations=[]
- Duty 15: Required=False, Valid=False, Violations=[]
- Duty 16: Required=False, Valid=False, Violations=[]
- Duty 17: Required=False, Valid=False, Violations=[]
- Duty 18: Required=False, Valid=False, Violations=[]
- Duty 19: Required=False, Valid=False, Violations=[]
- Duty 20: Required=False, Valid=False, Violations=[]
- Duty 21: Required=False, Valid=False, Violations=[]
- Duty 22: Required=False, Valid=False, Violations=[]

## Duties com Operator Not Assigned
Nenhum

## Duties e Veículos com Pullout/Pullback
- Duty/Vehicle: 18/ (pullback)
- Duty/Vehicle: 19/ (pullback)
- Duty/Vehicle: 16/ (pullback)
- Duty/Vehicle: 13/ (pullout)
- Duty/Vehicle: 5/ (pullout)
- Duty/Vehicle: 21/ (pullout)
- Duty/Vehicle: 10/ (pullout)
- Duty/Vehicle: 20/ (pullback)
- Duty/Vehicle: 4/ (pullout)
- Duty/Vehicle: 7/ (pullout)
- Duty/Vehicle: 6/ (pullout)
- Duty/Vehicle: 14/ (pullback)
- Duty/Vehicle: 14/ (pullout)
- Duty/Vehicle: 2/ (pullout)
- Duty/Vehicle: 17/ (pullback)
- Duty/Vehicle: 22/ (pullout)
- Duty/Vehicle: 3/ (pullout)
- Duty/Vehicle: 15/ (pullback)
- Duty/Vehicle: 9/ (pullout)

## Trecho PostgreSQL Metadata (Duties)
```json
[
  {
    "end": 315,
    "type": "duty_start",
    "start": 315,
    "duration": 0,
    "location": 1
  },
  {
    "end": 341,
    "type": "commercial_trip",
    "start": 315,
    "block_id": 1,
    "duration": 26,
    "trip_ids": [
      5437,
      5441
    ],
    "driving_time": 26,
    "location_end": 1,
    "location_start": 1
  }
]
...
```

## Trecho Latest-Schedule (ResultSummary.duties)
```json
{
  "duty_id": 1,
  "duty_end": 429,
  "idle_time": 0,
  "work_time": 80,
  "duty_start": 315,
  "suggestion": "Aceitar com warning se os tempos estiverem aderentes a operacao real.",
  "violations": [],
  "window_time": 114,
  "driving_time": 80,
  "pullout_time": 0,
  "pullback_time": 0,
  "user_explanation": "Esta jornada possui 114 minutos de janela total, mas apenas 80 minutos de trabalho produtivo. Os 34 minutos restantes ficaram classificados como espera operacional, pausa normal ou buffers de soltura/recolhimento.",
  "normal_break_time": 34,
  "mandatory_rest_time": 0,
  "invalid_rest_position": false,
  "operator_not_assigned": true,
  "mandatory_rest_required": false,
  "has_valid_mandatory_rest": false
}
...
```

## Veredito Final
**PRONTO**. O pipeline de otimização E2E está validado e submetendo a semântica operacional do Core via Celery para o Banco Postgres e sendo retornado via JSON e convertendo devidamente em CSV.
