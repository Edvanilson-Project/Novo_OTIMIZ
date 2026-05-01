# Demonstração para Cliente - O Valor do Motor de Decisão OTIMIZ

Esta apresentação demonstra como o módulo de Decisão Operacional foca ativamente na usabilidade da frota, não parando no menor custo cego, mas sim no cenário que realmente engaja e respeita a vida do tripulante e o cumprimento de regras logísticas.

## 1. O Problema nas Operações

Tradicionalmente, solvers puramente matemáticos produzem o que chamamos de "escravização do ótimo global": espremem todas as jornadas disponíveis no limite legal absoluto para gastar 1 centavo a menos. O resultado real?
- **Ociosidade excessiva (Idle):** Motoristas aguardando longos períodos improdutivos nas garagens ou terminais.
- **Jornadas extremas:** Picos massivos de turnos com mais de 12h de "spread" cronológico em que o motorista permanece à disposição da empresa, porém sendo sub-utilizado nas horas pagas.
- **Descanso mal distribuído:** Impossibilidade de fechar os 11h de interjornada ou intervalos mínimos por conta da compactação severa, o que acarreta risco de passivos trabalhistas.

## 2. Antes: A "Armadilha" do Menor Custo (`current_plan`)

No cálculo primário da inteligência artificial, identificamos o plano com o mínimo teórico de despesa, utilizando *menos tripulantes*. Contudo, as métricas subjacentes operacionais denunciam as falhas:

| Indicador Crítico | Resultado (`current_plan`) | Análise Prática |
| :--- | :--- | :--- |
| Custo Total | R$ 256.510 | ✅ Ótimo matemático teórico |
| **Duties < 25% uso** | **2 jornadas** | ❌ Escalas pagas para a equipe trabalhar pouco ou nada |
| **Duties > 12h** | **9 jornadas** | ❌ 9 motoristas presos na empresa o dia quase todo |
| **Idle Médio** | **169 min** | ❌ Quase 3 horas improdutivas de espera por pessoa |
| **Mandatory Rests** | **2 quebras** | ❌ Faltou encaixe para os descansos regulamentares |

Neste estado de "exemplo de duty extrema", os algoritmos engessados publicariam esta escala. O operador teria a dor de cabeça de retalhar manualmente a grade gerada no dia seguinte.

## 3. Depois: A Resposta Operacional OTIMIZ (`plus_one_duty`)

Reconhecendo as dores em tempo real, a nova Engine de Decisão entra em ação gerando alternativas. Ela detecta a viabilidade de flexibilizar o headcount (ex: injetar +1 tripulação tática) para desafogar a operação.

Com a alternativa na mesa, a IA toma a decisão por conta própria através das melhorias atestadas em 4 KPIs, alterando a publicação:

| Indicador Crítico | Novo Resultado (`plus_one_duty`) | Análise Prática |
| :--- | :--- | :--- |
| Custo Total | R$ 252.674 | ✅ Benefício colateral financeiro (ou estável em outros cenários) |
| **Duties < 25% uso** | **1 jornada** | ✅ Redução de 50% de jornadas lixo |
| **Duties > 12h** | **8 jornadas** | ✅ Alívio na fadiga crônica do setor |
| **Idle Médio** | **130 min** | ✅ Recuperação de +39 min de utilidade líquida |
| **Mandatory Rests** | **1 quebra** | ✅ Maior proteção de passivo e conformidade |

## 4. Explicação Automática (Auditabilidade)

O cliente jamais fica "no escuro" imaginando por que a IA sugeriu gastar com +1 motorista. O OTIMIZ relata a justificativa de forma inteligível:

> *"Escolhemos plus_one_duty e adicionamos este tripulante à escala porque reduziu o ociosidade da frota em 39 min/média, salvou um motorista da infração de descanso obrigatório e extinguiu jornadas vazias ou abusivas (>12h). A melhoria operacional é matematicamente comprovável."*

## 5. Qual o Valor Adquirido para a Empresa?

- **Redução Oculta de Custo Indireto**: Horas paradas e passivos de fiscalização de descanso são custos bilionários não inseridos nas faturas tradicionais.
- **Melhor Qualidade de Escala**: Escalas fáceis atraem e retêm talentos em um mercado onde motoristas estão em escassez.
- **Automação e Conformidade Operacional**: Substitui horas do planejador "consertando o robô" por uma IA que entrega uma grade já pensada nas regras sindicalistas locais.
