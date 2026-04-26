# Inventário Técnico de Conexões e Integração: OTIMIZ V2

Este documento detalha **exatamente** o que está conectado, o que existe mas está "isolado" e como os dados fluem entre cada serviço.

---

## 🏗️ 1. O que está CONECTADO (Ativo)

### A. Frontend ↔️ Backend (O Elo do Usuário)
-   **REST API**: Conectado via Axios. O Frontend busca dados de viagens, motoristas e dispara otimizações no Backend.
-   **WebSockets (Socket.io)**: Ativo. O Backend envia atualizações de progresso ("Calculando...", "Salvando...") que aparecem na barra de progresso do Frontend.
-   **Segurança**: O `Authorization: Bearer <JWT>` é enviado em cada cabeçalho para garantir que os dados sejam filtrados pelo `companyId`.

### B. Backend ↔️ Optimizer (O Elo de Comando)
-   **Orquestração**: O Backend envia o conjunto de viagens e regras CCT via POST HTTP para o Optimizer.
-   **Sincronização de Tarefas**: O Backend recebe um `taskId` e fica consultando (polling) o Optimizer até que a tarefa termine.

### C. Optimizer ↔️ Infraestrutura (O Elo de Performance)
-   **Redis (Cache)**: O Optimizer usa o Redis para salvar cálculos de distância entre pontos. Se você calcular a rota entre Terminal A e B uma vez, a próxima será instantânea (via cache).
-   **Redis (Mensageria)**: O Celery usa o Redis para gerenciar a fila de cálculos pesados.
-   **PostgreSQL**: O Optimizer acessa o banco diretamente em alguns fluxos de "Cenários" (What-If) para buscar dados históricos rapidamente.

---

## ⚠️ 2. O que existe mas NÃO ESTÁ CONECTADO (Gaps)

Existem funcionalidades prontas no código que ainda não estão sendo utilizadas ou dependem de infraestrutura externa:

### A. OSRM (Motor de Roteamento Real)
-   **O que temos**: O código (`routing_client.py`) está pronto para calcular distâncias exatas usando mapas reais via OSRM.
-   **Situação**: Está **Desconectado**. Como não há um servidor OSRM rodando, o sistema usa um **Fallback Haversine** (uma fórmula matemática que assume uma velocidade média de 15km/h em linha reta).
-   **Impacto**: Os tempos de viagem entre garagens e terminais são estimativas simplificadas, não baseadas em trânsito real.

### B. Notificações Externas
-   **O que temos**: O Backend possui estrutura para logs de auditoria.
-   **Situação**: Não há conexão com **servidores de E-mail (SMTP/SES)**. O sistema não consegue enviar avisos de "Otimização Concluída" por e-mail ou SMS ainda.

### C. Monitoramento de Performance (Grafana/Prometheus)
-   **O que temos**: O Optimizer está "instrumentado" (ele gera métricas de tempo de CPU e uso de memória).
-   **Situação**: Não há um coletor central. Os dados são gerados mas ninguém os está "lendo" para gerar gráficos de performance.

### D. IA Insights (OpenRouter)
-   **O que temos**: Integração completa com modelos GPT-4 e Claude via OpenRouter.
-   **Situação**: Depende de uma **Chave de API** no arquivo `.env`. Se não estiver lá, o sistema usa o **Fallback Local** (uma análise lógica simples feita pelo próprio código Python).

---

## 🗺️ 3. Mapa de Dependências Técnicas (Portas)

| Origem | Destino | Porta | Protocolo | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend** | Backend | `3001` | HTTP/WS | ✅ Ativo |
| **Backend** | Optimizer | `8000` | HTTP | ✅ Ativo |
| **Optimizer** | Redis | `6388` | TCP | ✅ Ativo |
| **Optimizer** | Postgres | `5444` | TCP | ✅ Ativo |
| **Optimizer** | OpenRouter | `443` | HTTPS | ⚠️ Requer Chave |
| **Optimizer** | OSRM | `5000` | HTTP | ❌ Desconectado |

---

## 🛠️ 4. O que falta para "Fechar o Circuito"?

Para que o sistema use 100% do potencial já programado, seriam necessários:
1.  **Subir um container OSRM** (porta 5000) com o mapa da sua região.
2.  **Configurar uma API Key** no `.env` para habilitar a IA completa.
3.  **Configurar um servidor de e-mail** no Backend.

**Conclusão**: O sistema já tem o "músculo" (algoritmos) e o "esqueleto" (conexões base) prontos e funcionando. As partes desconectadas são "sensores" e "periféricos" que podem ser ligados conforme a necessidade de precisão (como o OSRM) ou inteligência (como a IA externa).



e como previnir essa situação 

O culpado é um processo "zumbi" do Celery Worker (ID 453884), que faz parte do seu motor de otimização em Python.

O que está acontecendo:
Explosão Combinatória: Esse processo tentou rodar uma otimização que provavelmente era complexa demais para os parâmetros atuais (muitas viagens ou muitas combinações de escalas possíveis).
Uso Extremo de RAM: Ele alocou 15.5 GB de RAM (78% da memória total do sistema) para tentar criar as matrizes de cálculo.
Tarefa Interrompida: O sistema detectou que ele passou de 20 minutos rodando e enviou um sinal de interrupção (Timeout).
Por que continua comendo memória? Como o cálculo está travado em uma operação matemática muito pesada (nível C/C++ do NumPy ou do Solver), o Python não consegue "ouvir" o comando de parar imediatamente. Ele está tentando limpar essa memória gigantesca ou está simplesmente travado nela.
Recomendação:
Como essa tarefa já deu erro de timeout nos logs, esse processo não vai entregar nenhum resultado útil e está apenas travando seu sistema.

Posso matar esse processo para você e liberar esses 15GB de memória agora?