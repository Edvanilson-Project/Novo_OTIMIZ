# Release Notes - v1.0.0-operational-decision-baseline

**Commit Hash:** `(latest-local-commit)`
**Data/Hora:** 30 de Abril de 2026, 14:50 (GMT-3)

## Resumo Técnico da Versão
A versão `v1.0.0-operational-decision-baseline` marca o congelamento da arquitetura do motor de otimização OTIMIZ com foco na tomada de decisão operacional autônoma. O sistema não toma mais decisões baseadas puramente no custo cego, mas sim integrando KPIs operacionais reais (jornadas extremas, ociosidade e descansos) para escolher o cenário que oferece melhor qualidade de vida para a frota e tripulação sem prejudicar os SLAs da operação. 

O fluxo End-to-End foi 100% estabilizado passando por todos os componentes (Backend NestJS -> Celery -> Redis -> Python Optimizer -> PostgreSQL).

## Módulos Estáveis
- **`optimizer_service`**: Fluxo maduro de coordenação, invocação dos solvers e comparação explícita de cenários.
- **CSP Greedy + Pós-Opt**: Motor de empacotamento de jornadas com consolidação por busca local heurística.
- **`operational_time_service`**: Cálculos corretos de tempo efetivo, spread, idle, repousos obrigatórios e violações.
- **Decision Engine**: Lógica rígida de seleção (`materially_better=True` se ≥ 2 melhorias operacionais sem regressão).
- **Backend Persistência**: TypeORM gravando adequadamente as informações na tabela `schedules`.
- **Latest-Schedule**: Endpoint servindo o sumário consolidado com rastreabilidade da decisão operacional.

## Limitações Conhecidas & O que NÃO está resolvido
- A otimização heurística no modo `strict` pode não lidar perfeitamente com reparações de `GROUP_SPLIT` sem criar novas violações pontuais, resultando no cenário caindo de volta para a base.
- O tempo de processamento para matrizes gigantes (> 5000 viagens) continua dependendo das restrições de timeout impostas no ambiente, exigindo tuning do cluster Celery e instâncias maiores para não dropar.
- A justificativa da decisão encontra-se contida de forma serializada no metadata do resultado do PostgreSQL, necessitando deserialização no backend se o front-end for consumir ativamente e renderizar os trade-offs.

## Riscos
- Mudar regras de CCT no modo "production" pode invalidar o ganho operacional e inflar artificialmente o número de violations. É crítico não mexer nos parâmetros consolidados de testes no core sem re-validar as baterias.
- Concorrência intensa de submissões (>5 requisições de otimização paralelas) pode esgotar a RAM do worker Celery, dado que cada processo mantém um pipeline MCNF pesado na memória.
