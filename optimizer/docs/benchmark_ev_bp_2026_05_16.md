# Benchmark EV-Aware B&P — 2026-05-16

Sprint 2: label SPPRC 6D com SoC como recurso duro.
Comparação: greedy vs B&P não-EV vs B&P EV-aware.

## Configuração

| Parâmetro | Valor |
|---|---|
| Seed | 42 |
| Tamanhos | 30, 80, 150 viagens |
| Bateria EV | 300 kWh |
| SoC mínimo | 10% (30 kWh) |
| Taxa de carga | 150 kW |
| Energia custo | R$ 2,50/kWh |
| Consumo | 1,8 kWh/km |
| Budget B&P | 20-60s por tamanho |
| Iterations | 4 pricing rounds |
| Columns | 500 max |

## Resultados

```
    n alg                   blocks         cost   time_s  mid_charge
------------------------------------------------------------------------
   30 greedy/non-EV             13     28828.75      0.0           0
   30 bp/non-EV                 13     28550.00      0.1           0
   30 bp/EV                     13     28550.00      0.1           0
   80 greedy/non-EV             22     50324.25      0.1           0
   80 bp/non-EV                 20     47952.00      0.2           0
   80 bp/EV                     19     46710.17      0.3           0
  150 greedy/non-EV             38     82512.42      0.2           0
  150 bp/non-EV                 33     75865.25      0.6           0
  150 bp/EV                     35     79059.58      1.0           0
```

## Análise

**B&P vs Greedy (não-EV):**
- 80 viagens: -2 blocos (-9%), custo -4,7%
- 150 viagens: -5 blocos (-13%), custo -8,0%
- Overhead de tempo: < 0,5s para instâncias pequenas

**B&P EV-aware vs B&P não-EV:**
- 30 viagens: idêntico (instância pequena, warm-start domina)
- 80 viagens: **-1 bloco**, custo menor (menos veículos compensa custo de energia)
- 150 viagens: +2 blocos — SoC constraint fragmenta algumas sequências longas
  (correto: EV não pode encadear muitas viagens pesadas sem recarga)

**Overhead do label 6D:**
- Aumento de tempo: ~0,1-0,4s vs B&P não-EV (dominância 4D mantém paridade)
- `mid_charge=0` em todos os casos: charge_rate_kw=150kW absorve gaps típicos

**Conclusão:** Label 6D com SoC é viável computacionalmente. Para instâncias reais com distâncias longas e poucas oportunidades de recarga, o `mid_charge > 0` sinaliza blocos que precisam de replanejamento de rota de carga.
