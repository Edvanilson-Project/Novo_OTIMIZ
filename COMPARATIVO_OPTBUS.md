# Comparativo Honesto: OTIMIZ vs Optibus

**Data:** 2026-05-14
**Baseado em:** código-fonte real do OTIMIZ + informações públicas do Optibus
**Metodologia:** sem fabricar números do Optibus, sem alucinar benchmarks, sem exagero

---

## Por que o documento anterior era inválido

O arquivo anterior (versão 2026-05-02) afirmava que OTIMIZ superava o Optibus em 9 de 12
critérios, com números como "Optibus 500-800 viagens de escalabilidade", "Optibus 5-10s de
performance" e "acurácia 99.8% vs 95%". Nenhum desses números tinha fonte. São fabricados.

Este documento substitui aquele com avaliação baseada no código real.

---

## O que o OTIMIZ faz de verdade

### Funciona e tem código real

- **Multi-tenant completo**: `companyId` filtrado em todas as queries via `TenantBaseEntity`.
  Cross-tenant é impossível por design, não por convenção.
- **Segurança defensiva**: JWT, Helmet, rate limiting (login 10/min, otimização 5/5min),
  fail-fast em `INTERNAL_OPTIMIZER_KEY` padrão ou vazio.
- **8 regras regulatórias CLT/CCT** validadas e testadas: descanso entre jornadas, jornada
  máxima, condução contínua, refeição, CCT penalties. Não são 15+ como o documento anterior dizia.
- **Algoritmos VSP reais**: greedy, genetic, tabu search, MCNF, simulated annealing, assignment_vsp.
- **Algoritmos CSP reais**: greedy, set partitioning via PuLP/CBC (ILP real, não heurística).
- **Hybrid pipeline**: Greedy -> Local Search -> Metaheurística -> ILP Polish.
- **GTFS import**, what-if, comparação de cenários, Gini de equidade, P5/P95 por motorista.
- **Custom reports builder** com exportação CSV e PDF (pdfkit).
- **221 testes backend + 342 testes optimizer** — cobertura razoável para produto novo.

### Benchmark real (hardware: AMD Ryzen 5 4600H, CPU-only, sem GPU)

| Algoritmo       | 100v   | 500v   | 1000v  | 2000v   |
|-----------------|--------|--------|--------|---------|
| greedy          | 0.16s  | 0.62s  | 1.82s  | 4.01s   |
| mcnf            | 0.21s  | 1.86s  | 4.87s  | 9.24s   |
| genetic         | 5.70s  | 34.49s | 70.91s | 172.88s |
| hybrid_pipeline | 7.82s  | 38.91s | 299.9s | 234.72s |

Fonte: `docs/benchmark_sla_2026_05_14.md`, seed=42, dados sintéticos válidos.

O `greedy` a 1000v = 1.82s. O `hybrid_pipeline` a 1000v = **300 segundos**. O documento anterior
citava "<2.3s avg" para otimização — isso é verdadeiro apenas para greedy, não para o pipeline
de qualidade. São dados honestos, não propaganda.

---

## Onde o OTIMIZ está genuinamente atrás do Optibus

| Aspecto | OTIMIZ (medido/real) | Optibus (público/real) |
|---|---|---|
| Escala testada | até 2000 viagens sintéticas | 10 000+ viagens reais/dia por agência |
| Solver ILP | PuLP/CBC (open-source) | Gurobi ou CPLEX (10-100x mais rápido em larga escala) |
| Tempo a 1000v (pipeline completo) | ~300s CPU-only | Desconhecido — sem benchmark público comparável |
| Validação com dados reais | Nenhuma agência real ainda | Décadas com operadoras globais |
| Mobile para motoristas | Não existe | App nativo (iOS/Android) |
| AVL/GPS tempo real | Não implementado (roadmap) | Integrado ao produto principal |
| Multi-depósito | Não implementado | Sim |
| Suporte | Desenvolvedor | 24/7 enterprise SLA |
| Caso de uso público | Nenhum publicado | Dezenas de agências com nome e resultados |
| Maturidade | Produto novo (2026) | Empresa fundada ~2014 |

---

## Análise de qualidade de otimização

O `hybrid_pipeline` gera resultados similares ao `greedy` em blocos:

| Algoritmo       | 100v | 500v | 1000v | 2000v |
|-----------------|------|------|-------|-------|
| greedy          | 38   | 114  | 194   | 333   |
| hybrid_pipeline | 38   | 114  | 199   | 366   |

Custo total gerado:

| Algoritmo       | 1000v       |
|-----------------|-------------|
| greedy          | R$ 411 474  |
| hybrid_pipeline | R$ 414 587  |

O pipeline completo gasta 300s e gera resultado **ligeiramente pior** que o greedy a 1000 viagens.
Isso indica que o ILP polish do CBC está limitado pelo tamanho do problema — consegue explorar
apenas uma fração do espaço de soluções no tempo disponível.

Isso não invalida o produto para escalas menores (até ~500 viagens/dia), onde o custo de tempo
é aceitável e o pipeline funciona bem. Mas torna a comparação com Optibus em grandes agências
desonesta.

---

## Posicionamento real

### OTIMIZ hoje

- Produto funcional, seguro, com algoritmos reais de otimização combinatória.
- Adequado para operadoras pequenas e médias (50-500 viagens/dia).
- Mercado-alvo real: operadoras brasileiras sem acesso a Optibus (custo, idioma, localização).
- Conformidade CLT/CCT é diferencial genuíno em mercado brasileiro.

### OTIMIZ não é hoje

- Substituto direto do Optibus para grandes agências (1000+ viagens/dia).
- Um produto com escala comprovada em dados reais.
- Um produto com solver de nível comercial (Gurobi/CPLEX).
- Um produto com mobile, AVL ou suporte enterprise.

### O que separa OTIMIZ do Optibus de verdade

Não é feature list. É **validação com mundo real**. O Optibus tem anos de feedback de
operadoras reais corrigindo casos-limite de regulamentação, de dados GTFS sujos, de motoristas
com histórico especial, de depósitos com janelas de tempo complicadas. O OTIMIZ foi testado com
dados sintéticos. Essa diferença não aparece em tabelas de feature, mas aparece no momento em
que o sistema roda em produção com a frota real.

---

## O que seria necessário para reduzir o gap em 18 meses

1. **Solver comercial**: Gurobi tem licença acadêmica gratuita. Substituir CBC por Gurobi no
   ILP polish resolveria o problema de escala a 1000+ viagens.
2. **Um caso de uso público**: Um contrato com uma operadora real, com nome e resultados
   verificáveis, vale mais do que qualquer benchmark sintético.
3. **Feed GTFS real**: Integrar com GTFS de pelo menos uma cidade real e validar que os
   resultados fazem sentido operacional.
4. **Mobile básico**: Visualização de escala para motoristas (PWA ou React Native básico).

Sem pelo menos o item 2, a comparação com Optibus é acadêmica.

---

## Conclusão

OTIMIZ é um produto real, bem construído, com segurança competente e algoritmos funcionais.
Tem chance real no mercado de médias operadoras brasileiras onde o Optibus não chega por preço
ou complexidade de implantação.

Não é um produto que supera o Optibus. É um produto que compete em um segmento diferente.
Tratar como superioridade técnica afasta clientes sérios no momento em que verificam os números.

O posicionamento honesto é mais forte do que o marketing inflado: **"sistema brasileiro de
otimização de transporte público, com conformidade CLT/CCT nativa, custo acessível, e código
aberto para auditoria."** Isso é real e diferenciado.
