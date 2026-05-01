# Fluxo Operacional OTIMIZ - Documentação

Esta documentação descreve o fluxo técnico e lógico responsável por transformar um conjunto bruto de viagens em escalas e jornadas operacionais consistentes, culminando na seleção autônoma do melhor cenário.

## 1. Fluxo Completo da Plataforma (E2E)

A arquitetura do processo de otimização opera da seguinte maneira:

1. **Frontend**: Usuário (ex: Operador/Admin) configura e dispara uma nova otimização indicando a Empresa, data e perfil de algoritmo/heurísticas.
2. **Backend (NestJS)**: Recebe a requisição, valida autorização (JWT), injeta metadados da empresa (CCT e VSP rules) a partir do banco (PostgreSQL) e insere uma tarefa na fila para processamento assíncrono.
3. **Celery Worker**: Consome a requisição através do broker Redis e inicia o contêiner do Optimizer.
4. **Optimizer (Python)**: Carrega o grafo, dispara os solvers matemáticos e heurísticas para criar blocos e jornadas. Encadeia o mecanismo de pós-otimização e as avaliações de qualidade operacional.
5. **Redis / PostgreSQL**: O worker reporta status durante o processamento. Ao concluir, o `OptimizationResult` é serializado, os objetos persistidos relacionalmente e os sumários e logs gravados na tabela `schedules`.
6. **latest-schedule**: O Frontend ou outro cliente faz polling da API REST (`/operations/latest-schedule`) recuperando a taxonomia e os sumários do cenário final construído.

## 2. Etapas Internas do Optimizer

1. **Ingestão de Trips**: Agrupamento das viagens base, pré-processamento de *trip groups* (espinhas/rosters) e inferência de restrições de garagem e deslocamento.
2. **VSP (Vehicle Scheduling Problem - Blocos)**: Encadeamento geométrico e matemático das viagens (MCNF - Min Cost Network Flow), criando os "Blocos" (veículos). Busca minimizar a ociosidade da frota, pull-outs e pull-backs.
3. **CSP (Crew Scheduling Problem - Duties)**: Fatiamento dos blocos em jornadas individuais (*duties*). Aplicação do algoritmo *Greedy CSP* com aderência às regras de CLT/CCT (intervalos, repousos).
4. **Pós-Opt**: Algoritmos de busca local e heurísticas de refinamento operam sobre as jornadas iniciais (ex: swap, split, merge, tail relocation) visando reduzir sobreposição e uso excessivo de tripulantes.
5. **Cálculo Semântico**: Avaliação minuciosa da escala produzida mapeando violações críticas, contadores operacionais e pontuações financeiras.
6. **Decisão Operacional**: Geração e comparação de cenários variantes (ex: `current_plan` vs `plus_one_duty`). A engine escolhe se vale a pena trocar a opção "mais barata" pela opção que oferece mais saúde para a escala.

## 3. Glossário e Conceitos Operacionais

* **Idle (Ociosidade)**: Tempo entre duas viagens produtivas onde o veículo ou motorista está parado aguardando sem operar efetivamente no passageiro.
* **Normal Break (Intervalo Intrajornada)**: Período padrão destinado à refeição ou descanso não-remunerado do operador durante sua jornada.
* **Mandatory Rest (Descanso Obrigatório)**: Exigência legal (ex: DSR ou interjornada mínima) que define obrigatoriamente um teto de trabalho contínuo do tripulante antes que precise ser afastado da condução. Falhas neste geram violações de CCT ("mandatory rest missing").
* **Pullout / Pullback**: O movimento logístico inicial (da garagem para o início da linha) e final (da linha de volta para a garagem). Esses percursos ("deadhead") geram custos fixos.
* **Utilization (Taxa de Utilização)**: Proporção do tempo do motorista gasto executando serviço comercial útil versus tempo pago total da jornada. Quanto mais perto de 100%, melhor (exceção para trânsitos fixos).
* **Spread**: Tempo cronológico transcorrido desde o exato minuto em que o tripulante se apresenta (início da jornada) até sua liberação total (fim). Pode incluir tempos de repouso longo no meio do dia.

## 4. Explicação da Decisão (Decision Engine)

A essência do módulo de Qualidade Operacional é evitar a entrega de cenários matematicamente perfeitos mas inviáveis para os sindicatos ou operadores humanos.

**Exemplo Prático (Empresa 16)**:
- A Engine produziu o plano "matematicamente mais barato" (`current_plan`), mas este apresentava 2 jornadas hiper-curtas (<25%), 9 motoristas rodando >12h, e 169min de idle.
- O Solver explorou a injeção de 1 tripulação extra (`plus_one_duty`).
- Com um novo motorista, o sistema diluiu a carga de trabalho.
- O algoritmo identificou:
   - ↓ Duties < 25%: caiu de 2 para 1.
   - ↓ Duties > 12h: caiu de 9 para 8.
   - ↓ Idle Médio: caiu para 130 min.
   - ↓ Rest Missing: caiu de 2 para 1.
- *Log do Sistema*: "Escolhemos plus_one_duty porque melhorou 4 KPIs operacionais sem aumentar as regressões estruturais e bloqueantes."
- O sistema declarou o candidato como `materially_better=True` e substituiu a publicação oficial.
