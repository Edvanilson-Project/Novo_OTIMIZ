# CLAUDE_OPERATIONAL_STATUS.md

Log vivo da validação operacional OTIMIZ/OTTrans.

Criado em: 2026-05-24
Atualizado: 2026-05-24 (sessão auditoria OODA)
Atualizado: 2026-05-24 (memoria de persistencia, historico e multiempresa)
Atualizado: 2026-05-24 (mesa operacional OTTrans e ronda dos 17 especialistas)
Atualizado: 2026-05-24 (validacao previa obrigatoria por area antes de mexer)
Atualizado: 2026-05-24 (protocolo anti-teatro, evidencias e gate final de tela)
Atualizado: 2026-05-24 (instrucoes equivalentes para Codex e GitHub Copilot)
Atualizado: 2026-05-24 (execucao runtime do planejador via Codex)
Atualizado: 2026-05-25 (AI Cost Copilot Pro com modelos free, snapshot de projeto e rota corrigida)
Atualizado: 2026-05-25 (OpenRouter key validada e modelo gratuito ajustado)
Atualizado: 2026-05-28 (Análise profunda do Optimizer e execução completa da suíte de testes verde)
Atualizado: 2026-05-29 (Validação real ponta a ponta: 3 suítes verdes, prova de otimização, round-trip HTTP+Celery; fix P1 do build do backend)
Atualizado: 2026-05-29 (Product polish: healthcheck optimizer, limpeza raiz 31→8 md, audit_correctness reescrito, polish UI, auditoria 6 módulos, fix dado Mapa)
Atualizado: 2026-05-29 (parte 4 — bench real dos 17 algoritmos: fix correctness regional + alinhamento de objetivo SA/Tabu)

---

## Sessão 2026-05-29 (parte 4) — Bench real de TODOS os algoritmos + 2 correções

### O que foi feito (execução real in-process, mesmo code path do worker)
- Novo harness `optimizer/scratch/bench_all_algorithms.py`: roda os 17 algoritmos
  registrados (`AlgorithmType`) numa instância Salvador e checa invariantes por algo:
  cobertura total, zero overlaps, custo positivo/finito, veículos vs lower bound de
  concorrência, runtime. Rodado em 40 trips (LB 6) e 160 trips (LB 20).
- Resultado: **17/17 viáveis** (cobertura 100%, 0 overlaps) após as correções abaixo.

### BUG-REGIONAL-DUP-01 (P1, correctness) — CORRIGIDO
- `regional` cobria **41/40 trips (duplicado)** → viola invariante set-partition `==1`
  (CLAUDE.md). Causa: `_group_by_time_window` faz overlap de 30 min entre janelas; cada
  janela é resolvida isolada e o merge concatenava blocos **sem dedup** → trip de borda
  coberta 2x.
- Fix cirúrgico em `src/algorithms/vsp/regional_decomposition.py` (merge): dedup por
  `trip.id` (mantém a 1ª cobertura, remove duplicata das janelas seguintes) e
  `unassigned` = complemento real (trips de entrada não cobertas). Preserva o intuito do
  overlap (encadear blocos na fronteira) sem duplicar.
- Validação: bench 41→**40/40, 0 overlaps**; `test_regional_decomposition.py` +
  `test_regional_parallel_benchmark.py` **14 passed**.

### IMP-SATABU-DEADHEAD-01 (qualidade do objetivo) — IMPLEMENTADO
- SA/Tabu/joint_solver atingiam a mesma frota do greedy (24 veh) mas com custo
  **~36% maior (R$68k vs R$50k)**. Causa: o proxy `quick_cost_from_trips` (utils.py) era
  **cego a deadhead** — só cobrava idle (gap*idle_rate), igual para conexão no mesmo
  terminal ou cruzando terminais. SA/Tabu reduziam gap encadeando cross-terminal de alto
  custo real.
- Fix em `src/algorithms/utils.py`: termo `deadhead_cost_per_minute=3.0` (default) somando
  `deadhead*peso` quando há matriz `deadhead_times` (mesma chave de `is_connection_feasible`).
  No-op quando `deadhead_times` vazio (instância sintética sem coords); **ativo em dados
  reais/GTFS** que populam deadhead. Micro-teste: chain cross-terminal passa a custar mais.
- Default aplica automaticamente → corrige SA, Tabu, genetic e ALNS sem tocar nos 4 sites.

### Achados NÃO corrigidos (documentados, fora de escopo cirúrgico)
- `regional` super-fragmenta em instâncias pequenas/médias (78 veh em 160 trips): janelas
  temporais não reaproveitam veículo entre janelas. Só auto-seleciona >1000 trips e é
  suplantado pelo path de stitching em escala. Refazer reuse temporal = mudança grande.
- `vcsp_pulp` super-provisiona só no toy de 40 trips (12v); no caso realista de 160 fica
  em 24v (OK). Baixa prioridade.

### IMP-SATABU-DEADHEAD-01 — refinamento + PROVA empírica (2026-05-29 parte 4b)
- Achado de consistência: `deadhead_cost_per_minute` já é param usado em greedy, mcnf,
  assignment, joint_timetable, branch_and_price, hybrid — **default 1.0** em todos. Meu
  termo no proxy usava 3.0 hardcoded (divergente). Corrigido: default 1.0 em
  `quick_cost_from_trips` + SA e Tabu passam `vsp_params.get("deadhead_cost_per_minute",1.0)`.
- **Verificado (não bug em produção)**: `Trip.deadhead_times` é `Dict[int,int]` em dataclass
  SEM coerção; dados de entrada usam chave string. Consumidores fazem `.get(origin_id:int)`.
  MAS o path de API coerce em `converters.py:38` (`{int(k):v}`) + schema Pydantic
  `Dict[int,int]`. Logo em produção as chaves chegam int e o deadhead funciona. O miss
  só ocorre quando se constrói `Trip` direto de dict string-keyed (tests/scratch).
- **Prova empírica** (`scratch/exp_deadhead_proxy.py`, 90 trips, deadhead cross-terminal
  25min, mesma path `OptimizerService.run`): com peso 0 (proxy antigo cego) SA/Tabu fazem
  **9 conexões cross-terminal, R$27.262 (pior que greedy 25.658)**; com peso 1.0 (fix)
  **0 cross-terminal, R$24.728 (bate o greedy)**. Peso 3.0 = mesmo que 1.0 (1.0 basta).

### Validação executada (de verdade)
- `pytest proof_of_optimization_suite + test_regional_decomposition + tests/unit`:
  **491 passed, 2 skipped, 1 warning** (warning = advisory esperado de greedy-gap).
- `pytest test_cost_gap_investigation + test_violation_comparison`: **9 passed, 1 skipped**.
- Após refinamento (default 1.0 + wiring SA/Tabu): `pytest unit/test_algorithms +
  unit/test_vsp_tolerance_and_multiline + test_cost_gap_investigation +
  proof_of_optimization_suite`: **68 passed, 1 skipped**.
- Artefatos não-commit: `optimizer/scratch/bench_all_algorithms.py`,
  `optimizer/scratch/exp_deadhead_proxy.py`.

## Sessão 2026-05-29 (parte 3) — Product polish + auditoria dos módulos restantes

### 4 frentes executadas (2 por subagentes Sonnet, browser por mim)
- **Limpeza + healthcheck (CONCLUÍDO)**: 23 relatórios de sessão movidos p/ `docs/archive`
  (raiz 31→8 .md, só essencial de produto). Healthcheck do optimizer `wget`→`python`
  (`docker-compose.yml:80`) — imagem python não tinha wget. Container recriado:
  `otimiz-v2-optimizer` agora **healthy** (era unhealthy). Fecha OBS-OPT-HEALTH-01.
- **audit_correctness.py (CONCLUÍDO)**: suíte apodrecida (API antiga Evaluator/Driver)
  reescrita contra API atual (CostEvaluator/GreedyVSP/GreedyCSP/HybridPipeline) → **11 passed**.
  Adicionada ao `pytest.ini` (coleta 678→**689**). Asserts: custo>0/monotônico, deadhead,
  optimality gap, cobertura 100% em 3 algoritmos.
- **Polish UI (CONCLUÍDO)**: OBS-EMP-01 `window.confirm`→MUI Dialog em companies/page.tsx;
  OBS-SIDEBAR-01 scrollbar do simplebar estilizada (track+thumb) em theme/Components.tsx;
  OBS-GLOBAL-01 `variant="filled"` em Snackbars de terminals/lines/data/map. `tsc` rc=0.
- **Auditoria 6 módulos (CONCLUÍDO)** — browser (https://localhost via nginx, login real):
  Escala Semanal, What-If, Analytics, Parâmetros CCT (101 campos), Frota → **renderizam
  limpos com dados reais, sem marcadores de erro**.
  - **Mapa Operacional — achado + fix**: código CORRETO (degrada com empty-state honesto e
    só monta Leaflet com coords). Gap era de DADOS: 10 terminais com `latitude/longitude`
    NULL. Populadas coords **reais e públicas de Salvador** dos 4 terminais genuínos
    (Lapa, Pituba, Paripe, Alto de Coutos) no banco dev → mapa agora monta Leaflet com
    4 marcadores ("4 de 10 terminais com coordenadas"). Tiles OSM cinza = servidor de
    tiles inacessível no sandbox (ambiente, não bug). Terminais de teste seguem sem coord.

### Validação executada de verdade (esta sessão)
- Frontend vitest: **26 passed** (2 arquivos). `tsc --noEmit` rc=0.
- Optimizer coleta: **689 testes** (integridade do pytest.ini OK após +audit_correctness).
- Suítes de garantia: **37 passed** (audit_correctness 11 + proof_of_optimization 26),
  exit 0. 1 warning = aviso de qualidade ESPERADO (greedy gap 40%>25% → usar SA/Tabu/Hybrid).
- Backend Jest NÃO re-rodado: nenhum arquivo backend foi tocado nesta sessão (honesto).

### Notas
- Ação em dado dev (coords dos terminais) NÃO é versionada; em produção as coords vêm do
  CRUD de terminais / import GTFS (`fixtures/sunt_salvador/stops.txt` tem coords reais).
- Artefatos não-commit desta sessão: nenhum novo além dos já listados em sessões anteriores.

## Sessão 2026-05-29 — Validação real de produção + fix de build

### Ground truth de testes (executados de verdade nesta sessão)
- Optimizer pytest (`tests/`): **630 passed, 10 skipped** (379s) — `venv/bin/python` (Py 3.14.5).
- Backend Jest (suite completa): **545 passed, 59 suites** — RISK-AI-JEST-01 RESOLVIDO
  (skew de versões sumiu após reinstalação com pnpm; jest-circus 30.4.2 consistente).
- Frontend vitest: **26 passed** (2 arquivos).
- Proof-of-optimization suite (`tests/proof_of_optimization_suite.py`, real, sem mock):
  **26 passed** — lower bound VSP, cobertura total, sem overlaps, supera baseline naive,
  gap aceitável, custo positivo/monotônico, SLAs de runtime.

### Correção da otimização verificada em execução real
- `OptimizerService().run()` in-process (mesmo code path do worker Celery) numa instância
  Salvador sintética (160 viagens): mcnf=25v e branch_and_price=24v, **160/160 cobertas,
  0 overlaps, custo positivo**, B&P < MCNF. Gap vs lower bound de concorrência (20) é
  ESPERADO por restrições de deadhead (ver CLAUDE.md: 14 vs 10 na instância real 298).
- Script: `optimizer/scratch/verify_correctness_298.py`.

### Caminho de produção HTTP+Celery (limpa parte do RISK-AI-RUNTIME-02)
- Optimizer FastAPI sobe limpo: `/health/` → status ok, redis ok, 18 algoritmos.
- Worker Celery ativo (Redis nativo :6379). Round-trip real:
  `POST /optimize/` → task enfileirada → worker → `GET /optimize/status/{id}` = **completed**,
  `vehicles=3 crew=3 total_cost=2988.92` (12 viagens, 2 terminais).
- Nota de ambiente: rodar nativo exige `REDIS_URL=redis://localhost:6379/0` (default do
  config é hostname docker `redis:6379`). docker-compose cobre produção.

### BUG-BUILD-01 (P1) — CORRIGIDO
- `nest build` quebrado: 10 erros TS em `backend/src/modules/ai/ai.service.ts` (Dirent
  `<string>` vs `<NonSharedBuffer>`), regressão do `@types/node@22.19.19` puxado pelo
  reinstall pnpm. Anotação `Awaited<ReturnType<typeof fs.readdir>>` resolvia overload
  errado.
- Fix cirúrgico: `const entries = await fs.readdir(d,{withFileTypes:true}).catch(()=>null);
  if(!entries) return;` (inferência correta), 2 ocorrências (linhas ~666 e ~714).
- Validação: `nest build` rc=0; `jest src/modules/ai` 4/4; `tsc --noEmit` frontend rc=0.

### Follow-ups executados (aprovados pelo usuário) — 2026-05-29
- **CI proof suites**: `pytest.ini` agora coleta `proof_of_optimization_suite.py` (26) e
  `qa_advanced_2026.py` (12) → 678 testes coletados (era 640). `audit_correctness.py`
  ficou de fora: está rotado (API antiga — `Evaluator`/`OptimizationRequest`/`Driver`
  não existem mais); precisa de reescrita, não de patch de import.
- **sklearn**: `scikit-learn>=1.5.0` adicionado ao `requirements.txt` e instalado no venv
  (1.8.0, wheel cp314). `_SKLEARN_AVAILABLE=True`, `test_demand_forecaster` 9/9.
- **RISK-AI-AUDIT-01 — IMPLEMENTADO**: entidade `AiAnalysis` (`ai_analyses`), repo
  `AiAnalysisRepository` (BaseRepository, filtro por tenant), migração
  `1716800000000-CreateAiAnalyses`. `AiService.analyze()` persiste best-effort
  (pula sem companyId, nunca falha a resposta) + `listHistory()`. `GET /ai/history`
  guardado por `JwtAuthGuard`. app.module/ai.module atualizados.
  Validação: `nest build` rc=0; `jest src/modules/ai` 9/9; suite backend completa
  **550 passed** (era 545). Migração aplica no boot (migrationsRun:true) — pendente
  rodar contra o banco real (bloqueado, ver abaixo).

### BLOQUEIO — Validação de UI no navegador (RISK-AI-RUNTIME-02)
- Backend não sobe nativo: `.env` aponta DB role `otimiz_admin`, que só existe no
  Postgres do docker-compose. Postgres nativo (:5432) tem só `postgres` + bancos não
  relacionados (`otmiz_new` etc.). Backend tentou conectar e falhou: `role
  "otimiz_admin" não existe`.
- Docker daemon **inativo** (`systemctl is-active docker` = inactive, socket ausente).
  `docker`/`docker compose` (v5.1.4) instalados. Subir exige `sudo systemctl start
  docker` (somente o usuário pode autorizar). NÃO provisionei role/DB nativo à mão
  para não criar um banco divergente nem adivinhar segredo do `.env`.
- Desbloqueio limpo: `sudo systemctl start docker` →
  `docker compose up -d postgres redis optimizer backend frontend` → então validar UI.
- Já provado nesta sessão sem o stack docker: optimizer FastAPI sobe limpo, round-trip
  HTTP+Celery completa, e o backend **compila e inicia** (só falta o DB).

### DESBLOQUEADO — Validação de UI no navegador (RISK-AI-RUNTIME-02 FECHADO) — 2026-05-29
- Usuário iniciou docker (`sudo systemctl start docker`). Stack subido:
  postgres, redis, optimizer, celery-worker x2, backend, frontend, nginx.
- Login real (UI form) → Dashboard → Planner(Gantt) → AI Cost Copilot validados no
  navegador (Puppeteer headless:false). Evidência por screenshots.
- **Dashboard com dados reais**: 298 viagens, 14 motoristas/veículos necessários,
  5 motoristas cadastrados. Última otimização: `mcnf_vsp`, 14 blocos, 298 cobertas,
  R$52.572,47, **0 violações CCT**. → Confirma o ótimo documentado (298 trips → 14v).
- **Planner**: 14 veículos, 298 viagens, 0 hard/0 soft issues, Gini 0.214.
  OBS-GAP-01: KPI "Gap de Otimalidade 40%" compara com lower bound de concorrência (10);
  14 é o ótimo real (deadhead). Métrica pode alarmar usuário — melhorar apresentação.
- **AI Cost Copilot Pro**: drawer abre com 9 especialistas e dados reais; pergunta
  enviada pela UI → backend `/ai/analyze` → OpenRouter (`nvidia/nemotron...`) →
  **persistida em `ai_analyses`** (row id=2, companyId=16). Migração aplicada no boot
  do backend rebuildado. RISK-AI-AUDIT-01 validado ponta a ponta no navegador.
  OBS-AICHAT-01: a chamada de chat pela UI exibiu erro 500 (timeout do proxy Next do
  harness host na chamada lenta do modelo free) ENQUANTO o backend concluiu e persistiu;
  o frontend degradou de forma honesta (sem alucinar). Em prod (nginx) o /ai/analyze
  direto retornou 200. Avaliar timeout do axios do chat vs modelos free lentos.

### BUGS/Achados adicionais 2026-05-29 (Docker/deploy)
- **BUG-LOCK-BE (P1, CORRIGIDO)**: `backend/package-lock.json` dessincronizado
  (faltava `@nestjs/axios@4.0.1`, jest 30.3.0 vs 30.4.x) → `npm ci` do Dockerfile falhava.
  Fix: `npm install --package-lock-only`. Imagem backend rebuildou e subiu OK.
- **BUG-LOCK-FE (P1, ABERTO)**: `frontend/package-lock.json` também dessincronizado →
  `npm ci` do Dockerfile do frontend falha. `npm install --package-lock-only` quebrou
  com erro do próprio npm (`Cannot read properties of null (reading 'matches')`).
  Recomendação: regenerar com npm compatível OU migrar Dockerfile do frontend p/ pnpm
  (dev já usa pnpm). Não bloqueia dev local (host build OK).
- **OBS-JWT-01**: backend novo (hardening em main.ts) recusa subir com JWT_SECRET fraco
  do `.env` (`FATAL: JWT_SECRET ... ≥32 chars`). Correto. Dev precisa de JWT_SECRET forte
  no `.env`. Workaround local: `docker-compose.override.yml` (NÃO commitar; contém segredo dev).
- **OBS-PG-VOL-01**: volume do postgres docker estava com senha antiga ≠ `.env`
  (`your_secure_password_here`). Corrigido via `ALTER USER otimiz_admin PASSWORD ...`
  (não-destrutivo, preservou dados: 5 empresas, 5 usuários).

## Sessão 2026-05-29 (parte 2) — Correção dos achados abertos + OpenRouter robusto

### OpenRouter — seleção sempre no melhor modelo free disponível (pedido do usuário)
- `AiService` reescrito: descobre modelos free, ranqueia por contexto+família+modalidade,
  **cooldown por modelo** (429/cota → 30min; outras falhas 3min) → migra automaticamente
  para o melhor modelo DISPONÍVEL e se recupera sozinho quando a cota renova. Cache 30min.
- **Filtro de saída de texto**: só usa modelos que GERAM texto no chat (exclui geradores
  de música/imagem como lyria); a lista completa (incl. multimodais de entrada) fica
  exposta em `GET /ai/models` para mostrar as possibilidades (texto/imagem/áudio/vídeo).
- `OPENROUTER_MODEL` vazio → sem pin, sempre o melhor ranqueado. Chave do usuário no
  `docker-compose.override.yml` (backend+optimizer+worker). `OPENROUTER_FREE_MODEL_ATTEMPTS=6`.
- Validado ao vivo: `/ai/models` retornou **27 modelos free** ranqueados (active=qwen3-coder),
  multimodais aparecem (lyria text+image); `/ai/analyze` escolhe melhor modelo de texto
  funcionando (owl-alpha) com failover e fallback honesto. Backend 552 testes, AI 11/11.

### Achados corrigidos
- **BUG-LOCK-FE — CORRIGIDO**: Dockerfile do frontend migrado para pnpm (corepack
  pnpm@9.15.0, `pnpm install --frozen-lockfile`). Imagem rebuilda e sobe **healthy**.
  `package-lock.json` npm ficou obsoleto e não regenera — pnpm é o caminho correto.
- **OBS-GAP-01 — CORRIGIDO (apresentação)**: `DashboardKPIs.tsx` — quando o único LB é
  Bodin&Golden (concorrência, frouxo), o KPI mostra `≤ X% (teórico)` em cor info (não
  alarme vermelho) e o tooltip explica que reflete restrição operacional, não subotimalidade.
- **OBS-AICHAT-01 — MITIGADO**: timeout explícito de 120s na chamada do chat (frontend) +
  timeout por modelo no backend 45s→30s (limita o tempo total bem abaixo dos 300s do nginx).
  O 500 visto no harness host era timeout do proxy de rewrite do Next (não é bug de prod;
  nginx tem proxy_read_timeout 300s e o /ai/analyze direto retorna 200).
- **OBS-JWT-01 — RESOLVIDO (dev)**: JWT_SECRET forte via `docker-compose.override.yml`.
  Recomendação permanente: definir JWT_SECRET forte (≥32 chars) no `.env`.
- **Build context**: adicionados `.dockerignore` em frontend e backend (build estava
  enviando ~141MB incl. node_modules).
- **Frontend Dockerfile** agora aceita `ARG NEXT_PUBLIC_API_URL` (default same-origin
  `https://localhost/api/v1`) — evita CORS/mixed-content do bundle do cliente em prod.

### Validação final no navegador (https://localhost via nginx) — TUDO OK
- Login (form) → Dashboard (298 viagens, 14 veículos, 0 CCT) → Planner → AI Copilot.
- **OBS-GAP-01 confirmado na tela**: KPI mostra "≤ 40.0% (teórico)" em azul/info (sem
  alarme vermelho). Generalizado: lb_method ausente (formato legado) também é tratado
  como bound frouxo de concorrência.
- **AI Copilot chat funcionando no navegador** (sem 500): retornou análise real e honesta
  (cobertura total, 0 CCT, Gini 0.214, custo/viagem) usando o melhor modelo free; análise
  persistida em `ai_analyses` (8 linhas).
- Frontend Docker rebuildado com `--build-arg NEXT_PUBLIC_API_URL=https://localhost/api/v1`
  (same-origin, sem mixed-content).

### Incidentes/achados desta etapa
- **DISCO 100%**: rebuilds repetidos de imagem encheram o disco (87/89G) → postgres caiu
  (`No space left on device`). Resolvido com `docker image prune -f` + `docker builder
  prune -f` (recuperou 19,6GB → 77%). Dados do banco preservados (era só lock-file).
  Lição: usar `.dockerignore` (adicionado) e limpar imagens antigas após rebuilds.
- **OBS-OPT-HEALTH-01 (pré-existente)**: healthcheck do container optimizer usa `wget`
  que não existe na imagem (`wget: not found`) → fica "unhealthy" embora o serviço esteja
  OK (/health responde status ok, 3 workers, 18 algoritmos). Trocar por python/curl no
  healthcheck do docker-compose.

### Estado da stack (deixada rodando)
- docker: postgres :5444, redis :6388, optimizer :8000, backend :3001, nginx :80/:443.
- host frontend: :3000 (build latest). Login UI: admin@otimiz.com / Otimiz@123 (senha de
  TESTE setada nesta sessão no banco dev; trocar/remover depois).
- Artefatos locais NÃO-commit: `docker-compose.override.yml`, `nginx/certs/*.pem`,
  `optimizer/scratch/verify_correctness_298.py`.

---

## Módulo atual

**AI COST COPILOT PRO — APROVADO COM OBSERVAÇÕES** ✅ (2026-05-25)
- ✅ Backend `AiService` atualizado para descobrir modelos OpenRouter gratuitos,
  ignorar modelos pagos por padrao e tentar failover entre free models antes do fallback.
- ✅ Fallback local refeito para nao inventar benchmark, economia, km, horas ou regra
  ausente; campos faltantes viram `nao verificado`.
- ✅ Snapshot seguro do projeto adicionado para perguntas sobre arquitetura, APIs,
  testes, frontend, backend, otimizador e sinais de mock/demo.
- ✅ Frontend `AiCostDrawer` expandido para 9 especialistas: Operacoes, Otimizacao
  VSP/CSP, CCT/CLT, Custos, Risco, Frota, Arquitetura, Dados/API e QA/Seguranca.
- ✅ Dados mockados/estimativas no Copilot removidos: sem Ollama, sem "15%",
  sem benchmark fixo e sem horas estimadas quando nao existem no payload.
- ✅ BUG-AI-ROUTE-01 corrigido: `@Controller('api/ai')` mapeava
  `/api/v1/api/ai/analyze`; agora `@Controller('ai')` expõe `/api/v1/ai/analyze`.
- ✅ Runtime validado: login `admin@empresa.com`, curl autenticado em
  `/api/v1/ai/analyze` retornou 200; rewrite do Next em
  `http://127.0.0.1:3000/api/ai/analyze` retornou 200; GET do Planejador em
  `http://127.0.0.1:3000/operations/planner` retornou 200.
- ✅ Builds: `pnpm run build` backend e frontend verdes.
- ✅ Smoke direto: fallback sem chave, failover de modelos gratuitos e snapshot de
  projeto passaram via `ts-node`.
- ✅ OpenRouter: chave local presente no `.env` e validada sem exposicao do segredo;
  `/models` retornou HTTP 200 com 357 modelos.
- ✅ `OPENROUTER_MODEL` ajustado de `qwen/qwen3-coder:free` para
  `nvidia/nemotron-3-super-120b-a12b:free` apos evidencia de HTTP 429 no modelo
  anterior e HTTP 200 no novo modelo.
- ⚠️ RISK-AI-RUNTIME-02: backend local nao estava acessivel em `127.0.0.1:3001`
  durante o reteste; Docker daemon indisponivel (`/var/run/docker.sock` ausente),
  entao falta reiniciar backend e validar `/api/v1/ai/analyze` ponta a ponta.
- ⚠️ RISK-AI-JEST-01: Jest backend falha antes de executar testes com
  `this._moduleMocker.clearMocksOnScope is not a function`; confirmado tambem em
  `app.controller.spec.ts`, portanto bloqueio global do runner, nao do spec novo.
- ⚠️ RISK-AI-AUDIT-01: historico/auditoria persistente de analises AI ainda nao
  implementado.
- URLs ativas: frontend `http://localhost:3000`, backend `http://localhost:3001`.
- 📄 Documentação: `AUDITORIA_AI_COST_COPILOT_PRO_2026_05_25.md`

**AUDITORIA PLANEJADOR (GANTT) — SPRINT CONCLUÍDO** ✅ (2026-05-24)
- ✅ feat(gantt) commit 7b0043f: Regional badge + rendição markers + troca_motorista highlight
- ✅ feat(tests) commit cfce84a: relief estimator tests alinhados com Duty.add_task() API
- ✅ feat(optimizer) commit c2cac5b: OR-Tools MCF solver (6-9x faster) + relief estimator fix
- ✅ 631 passed, 9 skipped — suite completa verde
- ✅ Validação browser: Gantt carrega, 2 veículos, 14 viagens, Viável, sem Regional badge (correto)
- ✅ EventSubRows: Início Jornada / Soltura (verde) / Viagens IDA+VOLTA / Intervalo normal
- ✅ No rendição markers (correto — MCNF VSP puro sem run-cutting)
- ✅ TypeScript: zero erros em TabGantt.tsx (2525 linhas)
- ✅ 29/29 participantes aprovaram: 7 técnicos + 5 OTTrans + 17 especialistas
- ✅ Execução runtime Codex: frontend em `http://localhost:3005`, login E2E OK,
  smoke do planner OK, selectors + aba Gantt OK
- ✅ Evidência backend: `latest-schedule` retornou schedule `id=4`, `2 veículos`,
  `10 viagens`, `totalCost=3628.40`, `hardIssues=0`, `softIssues=0`
- ⚠️ BUG-PLANNER-CORS-01 encontrado: backend dev antigo não aceitava frontend em
  portas locais como `3003`; fix aplicado em `backend/src/main.ts` e
  `backend/src/modules/operations/optimization.gateway.ts`
- 📄 Documentação: `AUDITORIA_PLANEJADOR_GANTT_2026_05_24.md`

**AUDITORIA IMPORTAR VIAGENS CONCLUÍDA** ✅ (2026-05-24)
- ✅ Simplificação: 1016 → 480 linhas (-53%)
- ✅ Correção: Nomes terminais visíveis (Terminal Centro, Terminal Barra)
- ✅ Auditoria completa: 7 membros + 5 usuários + 17 especialistas = 29/29 APROVADOS
- ✅ Gate final: PRONTO PARA PRODUÇÃO
- 📄 Documentação: `AUDITORIA_IMPORTAR_VIAGENS_*.md` (5 arquivos + completa)

---

## Ambiente ativo

- Frontend principal da validacao atual: http://localhost:3005
- Frontend auxiliar observado: http://localhost:3003
- Backend validado por API: http://localhost:3001
- PostgreSQL: :5432 ✓
- Redis: :6379 ✓

---

## Regras permanentes adicionadas

- Validar persistencia real dos dados apos refresh, logout/login, API e reinicio
  quando aplicavel.
- Preservar historico, auditoria e rastreabilidade de dados operacionais importantes.
- Evitar exclusao destrutiva quando inativacao, arquivamento, soft delete ou status
  auditavel fizerem mais sentido.
- Validar multiempresa/multitenant para impedir mistura ou vazamento de dados.
- Validar funcionarios, perfis, permissoes e responsabilidades conectados aos fluxos.
- Remover dados, telas ou funcionalidades sem sentido somente com evidencia, consenso
  da equipe afetada, plano de preservacao/exclusao auditavel e reteste completo.
- Consolidar o sistema com estrutura clara, dados confiaveis, modulos conectados e
  funcionalidades realmente necessarias para producao.
- Em cada tela/modulo, registrar interacao realista dos 5 usuarios operacionais da
  OTTrans, matriz de funcionarios/perfis quando aplicavel e ronda obrigatoria dos
  17 especialistas.
- Nenhuma tela pode ser aprovada sem parecer final de cada usuario operacional e de
  cada especialista, mesmo que a decisao seja `nao aplicavel` com justificativa.
- Antes de mexer em codigo, dados, layout, configuracao, seed, migracao ou teste,
  cada area deve validar suas obrigacoes, registrar evidencia, apontar o que funciona,
  o que falha, o risco e se pode mexer agora.
- A interacao entre usuarios OTTrans e especialistas deve gerar evidencia, decisao
  ou acao objetiva. Falas genericas sem teste real nao aprovam tela.
- Cada tela deve passar por gate final com dados testados, perfis, CRUD, persistencia,
  historico, multiempresa, bugs P0/P1, decisoes dos 5 usuarios, decisoes dos 17
  especialistas, testes executados e proxima tela permitida.
- Codex deve seguir `AGENTS.md`; GitHub Copilot deve seguir
  `.github/copilot-instructions.md`; ambos devem obedecer tambem
  `CLAUDE_OPERATIONAL_MEMORY.md` e `CLAUDE_OPERATIONAL_STATUS.md`.

---

## Validações concluídas

### FASE 1 — Autenticação / Login ✅ APROVADA

| Controle | Status |
|---|---|
| Form vazio → validação | ✅ "Preencha e-mail e senha." |
| Email formato inválido | ✅ HTML5 nativo |
| Credenciais erradas | ✅ "Credenciais inválidas" (seguro) |
| Login válido → redirect /dashboard | ✅ |
| Mostrar/ocultar senha | ✅ |
| Link "Esqueci minha senha" | ✅ /auth/forgot-password |
| Banner de erro visível | ✅ CORRIGIDO (filled) |

**BUG-LOGIN-01 CORRIGIDO**: `Alert severity="error"` → `variant="filled"` em `login/page.tsx:151`

---

### FASE 2 — Dashboard ✅ APROVADA

| Controle | Status |
|---|---|
| KPIs carregam | ✅ |
| Motoristas Necessários (era 0, agora 2) | ✅ CORRIGIDO |
| Botão Atualizar | ✅ |
| Acesso Rápido (4 botões) | ✅ hrefs corretos |
| Última Otimização card | ✅ |
| Sidebar scroll (17 links) | ✅ scrollável |
| Zero erros de rede | ✅ |
| ⚠️ Sidebar scroll não óbvio visualmente | observação |

**BUG-DASH-01 CORRIGIDO**: `??` → `||` em `dashboard/page.tsx:231` (rosterCount=0 agora mostra totalBlocks)

---

### FASE 3 — Empresas ✅ APROVADA

| Controle | Status |
|---|---|
| Listagem | ✅ |
| Busca (positiva e vazia) | ✅ |
| Nova Empresa CREATE | ✅ |
| Validação obrigatórios | ✅ |
| Editar UPDATE | ✅ |
| Excluir DELETE + confirmação | ✅ (window.confirm) |
| Persistência após refresh | ✅ |

**BUG-EMP-01 CORRIGIDO**: `InputProps` → `slotProps.input` em `AppDataGrid.tsx:35`
**OBS-EMP-01**: `window.confirm()` → deveria ser MUI Dialog (médio, funcional)

---

### FASE 4 — Usuários ✅ APROVADA

| Controle | Status |
|---|---|
| Listar usuários | ✅ |
| Busca (positiva e vazia) | ✅ |
| Criar novo usuário (CREATE) | ✅ |
| Validação obrigatórios | ✅ |
| Editar usuário (UPDATE) | ✅ |
| Excluir usuário (DELETE) | ✅ |
| Persistência após refresh | ✅ |

---

### FASE 5 — Terminais ✅ APROVADA

| Controle | Status |
|---|---|
| Listagem (8 terminais reais de Salvador) | ✅ |
| Busca ("Lapa" → 1 resultado) | ✅ |
| Validação obrigatórios | ✅ |
| Criar terminal (CREATE) | ✅ |
| Excluir terminal (DELETE) | ✅ |
| Persistência após refresh | ✅ |

---

### FASE 6 — Linhas ✅ APROVADA

| Controle | Status |
|---|---|
| Listagem (1 linha real) | ✅ |
| Busca (positiva) | ✅ |
| Validação obrigatórios | ✅ |
| Criar linha (CREATE) | ✅ |
| Editar linha (UPDATE) | ✅ |
| Excluir linha (DELETE) | ✅ |
| Persistência após refresh | ✅ |

---

### FASE 7 — Importar Viagens ✅ FUNCIONAL

| Controle | Status |
|---|---|
| Página carrega | ✅ |
| 10 viagens pré-carregadas | ✅ |
| Grid com dados reais | ✅ |
| Aba Viagens funciona | ✅ |
| Aba Motoristas (estrutura pronta, 0 dados) | ✅ |

---

### FASE 8 — Planejador (Gantt) ✅ APROVADA

| Controle | Status |
|---|---|
| KPIs carregam (2 veículos, 10 viagens, R$ 3.738,40) | ✅ |
| Gap Optimalidade (0% — Ótimo) | ✅ |
| Hard/Soft Issues (0) | ✅ |
| Gantt visual renderiza | ✅ |
| Veículos visíveis na timeline | ✅ |
| Zoom e controles funcionam | ✅ |
| Abas (Gantt, Veículos, Motoristas, Viagens) | ✅ |

---

## Bugs corrigidos nesta sessão

| ID | Arquivo | Descrição |
|---|---|---|
| BUG-LOGIN-01 | `src/app/auth/login/page.tsx:151` | Alert filled — visível no tema escuro |
| BUG-DASH-01 | `src/app/(DashboardLayout)/dashboard/page.tsx:231` | rosterCount \|\| totalBlocks (era ??) |
| BUG-EMP-01 | `src/components/AppDataGrid.tsx:35` | slotProps.input (era InputProps) |
| BUG-USR-02 | `src/app/(DashboardLayout)/settings/users/page.tsx:219` | Alert filled em dialog |
| BUG-TERM-01 | `src/app/(DashboardLayout)/operations/terminals/page.tsx:105` | Alert filled em validação |
| BUG-LINES-01 | `src/app/(DashboardLayout)/operations/lines/page.tsx:217` | Alert filled em validação |

---

## Banco de dados (estado atual)

- Companies: 1 (Ottrans Transportes Urbanos Ltda — ID 1)
- Users: admin@empresa.com / admin123 (super_admin, companyId 1)
- Terminals: 0 (limpos)
- Lines: 0 (limpos)
- Trips: 10 (dados de teste)
- Vehicles: 2 (de otimização anterior)

---

## Resumo final da auditoria

✅ **8/8 Fases concluídas com sucesso**

- Autenticação & Login: Formulário, validações, redirecionamento
- Dashboard: KPIs, última otimização, acesso rápido
- Empresas: CRUD completo + busca + persistência
- Usuários: CRUD completo + roles/permissões + persistência
- Terminais: CRUD completo + busca + 8 terminais reais de Salvador
- Linhas: CRUD completo + busca + 1 linha real
- Importar Viagens: 10 viagens carregadas, interface funcional
- Planejador (Gantt): Otimização VSP+CSP, visualização temporal, KPIs

**Módulos não auditados (fora do escopo OODA):**
- Escala Semanal
- Análises What-If
- Mapa Operacional
- Analytics & Relatórios
- Parâmetros CCT
- Frota & Manutenção

---

## Pendências / Observações

- OBS-EMP-01: window.confirm → MUI Dialog no delete de empresas (médio)
- OBS-SIDEBAR-01: Scroll não óbvio visualmente no sidebar (low)
- OBS-GLOBAL-01: Alert standard em dark theme tem baixo contraste (workaround: usar variant="filled")
- OBS-DATA-01: Toda fase pendente deve validar persistencia, historico, auditoria,
  multiempresa, funcionarios/perfis e risco de perda de dados antes de aprovar.
- OBS-INTERACTION-01: Toda fase pendente deve registrar a mesa operacional OTTrans,
  matriz de funcionarios/perfis quando aplicavel e ronda dos 17 especialistas antes
  de ser marcada como aprovada.
- OBS-PREFLIGHT-01: Toda fase pendente deve iniciar com validacao previa por area
  antes de qualquer correcao ou implementacao.
- OBS-GATE-01: Toda fase pendente deve usar severidade P0/P1/P2/P3, dono tecnico,
  evidencia, reteste e gate final de tela antes de seguir.
- OBS-PLANNER-01: pendente retestar o fix de CORS/WebSocket em runtime com backend
  reiniciado na mesma porta usada pelo frontend alternativo (`3003` ou similar).
