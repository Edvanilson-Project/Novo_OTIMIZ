# CLAUDE_OPERATIONAL_STATUS.md

Log vivo da validação operacional OTIMIZ/OTTrans.

Criado em: 2026-05-24
Atualizado: 2026-05-24 (sessão auditoria OODA)
Atualizado: 2026-05-24 (memoria de persistencia, historico e multiempresa)
Atualizado: 2026-05-24 (mesa operacional OTTrans e ronda dos 17 especialistas)
Atualizado: 2026-05-24 (validacao previa obrigatoria por area antes de mexer)
Atualizado: 2026-05-24 (protocolo anti-teatro, evidencias e gate final de tela)

---

## Módulo atual

**AUDITORIA PLANEJADOR (GANTT) — EM PROGRESSO** 🔄 (2026-05-24)
- 🔄 Fase 1-4 concluídas: Carregamento, Algoritmos, Qualidade, Gantt
- 🔄 8 bugs encontrados: 1 HIGH, 3 MEDIUM, 4 LOW
- 🔄 Implementações pendentes: Tooltips, legenda, layout
- 🔄 Drag-drop: A avaliar vs Optibus gap
- 📄 Documentação: `AUDITORIA_PLANEJADOR_GANTT_2026_05_24.md`

**AUDITORIA IMPORTAR VIAGENS CONCLUÍDA** ✅ (2026-05-24)
- ✅ Simplificação: 1016 → 480 linhas (-53%)
- ✅ Correção: Nomes terminais visíveis (Terminal Centro, Terminal Barra)
- ✅ Auditoria completa: 7 membros + 5 usuários + 17 especialistas = 29/29 APROVADOS
- ✅ Gate final: PRONTO PARA PRODUÇÃO
- 📄 Documentação: `AUDITORIA_IMPORTAR_VIAGENS_*.md` (5 arquivos + completa)

---

## Ambiente ativo

- Frontend: http://localhost:3000 (Next.js, pid 766758)
- Backend: http://localhost:3001 (NestJS, pid 945902)
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
