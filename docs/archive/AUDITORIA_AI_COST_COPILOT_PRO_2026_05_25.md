# AUDITORIA AI COST COPILOT PRO — 2026-05-25

## Contexto da tela/modulo

- Modulo: Planejador / AI Cost Copilot Pro
- Rota UI: `http://localhost:3000/operations/planner`
- Frontend ativo: `http://localhost:3000`
- Backend ativo: `http://localhost:3001`
- Endpoint validado: `POST /api/v1/ai/analyze`
- Rewrite validado: `POST http://127.0.0.1:3000/api/ai/analyze`
- Usuario de teste: `admin@empresa.com` / `super_admin` / `companyId=1`

## Inventario visual do drawer

| Controle | Status |
|---|---|
| Botao abrir AI Cost Copilot no Planejador | nao verificado no navegador nesta rodada |
| Botao fechar drawer | build validado, runtime visual nao verificado |
| Botao reiniciar chat | build validado |
| Barra KPI: veiculos, custo, viagens, CCT, criticos | build validado |
| Painel Perspectivas Especializadas | build validado |
| Botao Analisar tudo | API/rewrite validado; clique visual nao verificado |
| Collapse especialistas | build validado |
| Chat livre | API/rewrite validado |
| Perguntas rapidas | build validado |
| Campo de pergunta multiline | build validado |
| Botao enviar | API/rewrite validado |
| Chips de modo IA Free/Local | build validado |

## Mudancas executadas

- Backend `AiService` agora descobre modelos OpenRouter gratuitos dinamicamente e ignora modelo pago fixado salvo se `OPENROUTER_ALLOW_PAID_MODELS=true`.
- Backend tenta multiplos modelos gratuitos antes do fallback local.
- Backend inclui snapshot seguro do projeto quando a pergunta pede projeto/codigo/API/mock/testes.
- Backend removeu benchmarks/economias inventadas do fallback e exige `nao verificado` para dado ausente.
- Rota corrigida de `@Controller('api/ai')` para `@Controller('ai')`, expondo `POST /api/v1/ai/analyze`.
- Frontend expandiu especialistas para Operacoes, Otimizacao, CCT/CLT, Custos, Risco, Frota, Arquitetura, Dados/API e QA/Seguranca.
- Frontend removeu referencia a Ollama e estimativas mockadas como economia percentual, benchmark fixo e horas estimadas.
- Frontend passa `specialist` e `includeProjectContext` ao backend.

## Validacao previa por area

| Especialista | Evidencia analisada | Falha/falta | Pode mexer? |
|---|---|---|---|
| Arquiteto de Sistema | `AiController`, `AiService`, `next.config.ts` | rota duplicava `/api` | sim |
| Produto Transporte | fluxo Planejador -> Copilot | especialistas eram estreitos para projeto inteiro | sim |
| Matematico Otimizacao | prompts e fallback | nao podia declarar otimo/economia sem comparativo | sim |
| Estatistico/KPIs | campos custo, viagens, veiculos | benchmark externo sem base no payload | sim |
| OptBus/VSP/CSP | algoritmo no payload | gap/lower bound ausente deve ser nao verificado | sim |
| Backend | runtime Nest e curl | endpoint 404 antes da correcao | sim |
| Frontend | `AiCostDrawer.tsx` | prompts com estimativas e mock textual | sim |
| UI/UX | drawer e chips | build ok; browser visual nao completo | sim com observacao |
| QA/E2E | build, smoke ts-node, curl | Jest global quebra antes dos testes | sim com bloqueio registrado |
| Dados/Banco | sem migracao | sem persistencia de historico AI | sim |
| DevOps/Infra | portas 3000/3001 | frontend exigiu permissao para bind | sim |
| Seguranca/RBAC | login cookie + endpoint | auth validado com super_admin | sim |
| Performance/Escala | snapshot cache TTL | varredura limitada e cacheada | sim |
| Integracoes/APIs | Next rewrite + Nest route | rewrite validado por curl | sim |
| Compliance Brasil | CCT no prompt | detalhes por motorista ausentes marcados nao verificado | sim |
| Observabilidade | logs Nest + warnings | sem auditoria persistente de analise AI | sim com observacao |
| Documentacao/Release | status e relatorio | registrar pendencias | sim |

## Mesa operacional OTTrans

| Usuario | Fluxo analisado | Esperado | Observado | Decisao |
|---|---|---|---|---|
| Coordenador Operacoes | pergunta de custo e risco | acao objetiva sem chute | resposta nao inventa economia | aprovado |
| Planejador Escala | especialistas VSP/CSP e CCT | nao declarar otimo sem gap | prompts exigem lower bound/gap | aprovado |
| Fiscal Terminal | uso em rotina rapida | resumo claro | build e API ok; clique visual pendente | aprovado com observacao |
| Analista Frota | especialista frota | nao estimar km/horas | marca km/horas como nao verificado | aprovado |
| Administrativo/Auditoria | auth, projeto, mocks | rastreabilidade e isolamento | endpoint autenticado e snapshot registra sinais | aprovado com observacao |

## Matriz funcionarios/perfis

| Persona | Empresa | Perfil | Pode fazer | Nao pode fazer | Resultado |
|---|---|---|---|---|---|
| Admin E2E | companyId 1 | super_admin | login e chamar AI endpoint | acessar sem token | aprovado |
| Operador planejamento | nao verificado | operacional | usar drawer apos login | alterar outra empresa | nao verificado |
| Usuario sem permissao | nao verificado | sem role | nenhum acesso esperado | chamar endpoint autenticado | nao verificado |
| Funcionario frota | nao verificado | frota | ler analise frota | editar parametros globais | nao verificado |
| Auditor | nao verificado | auditoria | revisar resposta e evidencias | publicar escala | nao verificado |

## QA destrutivo controlado

| Cenario | Evidencia | Resultado |
|---|---|---|
| Backend build | `pnpm run build` em `backend` | aprovado |
| Frontend build | `pnpm run build` em `frontend` | aprovado com warnings preexistentes |
| Fallback sem chave OpenRouter | `ts-node` smoke `fallback_ok` | aprovado |
| Failover entre modelos free | `ts-node` smoke `free_failover_ok provider/free-big:free,provider/free-small:free` | aprovado |
| Snapshot do projeto | `ts-node` smoke `project_context_ok` | aprovado |
| Endpoint antigo | curl retornou 404 em `/api/v1/ai/analyze` antes do fix | bug confirmado |
| Endpoint corrigido | curl autenticado em `/api/v1/ai/analyze` | aprovado |
| Rewrite Next | curl em `http://127.0.0.1:3000/api/ai/analyze` | aprovado |
| Tela Planejador | GET `http://127.0.0.1:3000/operations/planner` | 200 OK |
| Jest backend | `pnpm exec jest app.controller.spec.ts` | bloqueado: erro interno `clearMocksOnScope` tambem em teste antigo |

## Bugs

| ID | Severidade | Dono | Evidencia | Status |
|---|---|---|---|---|
| BUG-AI-ROUTE-01 | P1 | Backend | controller mapeado como `/api/v1/api/ai/analyze` | corrigido e retestado |
| RISK-AI-JEST-01 | P2 | QA/DevOps | Jest falha antes de executar testes em spec novo e antigo | bloqueado externo |
| RISK-AI-AUDIT-01 | P3 | Produto/Dados | analises AI nao persistem historico/auditoria | aberto |

## Ronda final dos 17 especialistas

| Especialista | Parecer |
|---|---|
| Arquiteto de Sistema | aprovado: rota e responsabilidade backend/frontend corrigidas |
| Produto Transporte | aprovado: especialistas mais uteis para rotina real |
| Matematico Otimizacao | aprovado: nao declara otimo sem evidencia |
| Estatistico/KPIs | aprovado: removeu benchmark inventado |
| OptBus/VSP/CSP | aprovado com observacao: comparar algoritmos continua pendente |
| Backend | aprovado: endpoint real 200 via curl |
| Frontend | aprovado: build e rewrite ok |
| UI/UX | aprovado com observacao: falta screenshot/browser click completo |
| QA/E2E | aprovado com bloqueio: Jest global quebrado |
| Dados/Banco | aprovado com observacao: sem persistencia historica AI |
| DevOps/Infra | aprovado: servidores ativos 3000/3001 |
| Seguranca/RBAC | aprovado: endpoint requer login/cookie |
| Performance/Escala | aprovado: snapshot tem limite e cache |
| Integracoes/APIs | aprovado: Next rewrite validado |
| Compliance Brasil | aprovado: ausencia de dado vira nao verificado |
| Observabilidade | aprovado com observacao: logs existem, auditoria de analise pendente |
| Documentacao/Release | aprovado: relatorio/status atualizados |

## Gate final

- Tela/rota: `/operations/planner` / AI Cost Copilot Pro
- Dados testados: payload sintetico realista com 2 veiculos, 10 viagens, R$3738.40, CCT 0
- Perfis testados: `super_admin` companyId 1
- CRUD completo: nao aplicavel
- Persistencia/historico validado: nao aplicavel para analise instantanea; persistencia historica pendente
- Multiempresa/funcionarios validado: auth tenant via login validado; matriz completa nao verificada
- Bugs P0/P1 abertos: nenhum
- Bugs P2/P3 abertos: `RISK-AI-JEST-01`, `RISK-AI-AUDIT-01`
- Testes executados: backend build, frontend build, ts-node smokes, curl auth/API/rewrite
- Evidencias principais: endpoint `/api/v1/ai/analyze` 200; rewrite `/api/ai/analyze` 200; builds verdes
- Decisao final: aprovado com observacoes
- Proxima tela permitida: Planejador permanece permitido; proxima melhoria sugerida e persistir historico/auditoria das analises AI
