# OTIMIZ — Otimizador de Transporte Coletivo Urbano

Sistema de programação operacional de veículos e motoristas para transporte público.
Otimiza escalas com algoritmos VSP/CSP, valida restrições legais (CLT/CCT) e gera relatórios operacionais completos.

---

## Funcionalidades Principais

- **Otimização de escalas** — VSP (greedy, genetic, tabu search, MCNF) + CSP híbrido
- **Validação regulatória** — 8 regras: descanso, jornada máxima, refeição, CCT
- **Relatórios operacionais** — KPIs, custo/benefício, equidade Gini, exportação PDF/Excel
- **Mapa operacional** — visualização de terminais e viagens em tempo real
- **What-if / Cenários** — simule mudanças de parâmetros antes de publicar
- **Importação GTFS** — carga de dados de viagens no padrão aberto
- **Relatórios customizados** — builder visual com preview e exportação CSV/PDF
- **Multi-tenant** — isolamento completo por empresa via JWT

---

## Stack Técnico

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js 15, React 19, MUI v9, Leaflet |
| Backend | NestJS 11, TypeORM, PostgreSQL 15 |
| Optimizer | Python 3.11, FastAPI, Celery, PuLP |
| Cache/Queue | Redis 7 |
| Auth | JWT (RS256), HttpOnly cookies |
| Testes | Jest (221 specs), pytest (342 specs), Playwright e2e |

---

## Quick Start (Docker)

```bash
# 1. Clone e configure
git clone <repo-url>
cd Novo_OTIMIZ
cp .env.example .env          # edite com suas credenciais
cp optimizer/.env.example optimizer/.env

# 2. Suba os serviços
docker-compose up -d

# 3. Execute migrations
docker-compose exec backend npm run migration:run

# 4. Crie usuário admin
docker-compose exec backend npm run seed

# 5. Acesse
# Frontend: http://localhost:3000
# API docs:  http://localhost:3001/api/v1/docs  (apenas dev)
```

**Pré-requisitos:** Docker 24+, Docker Compose v2.

---

## Variáveis de Ambiente Obrigatórias

### Backend (`.env`)

| Variável | Descrição | Exemplo |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@db:5432/otimiz` |
| `JWT_SECRET` | Segredo JWT (mínimo 32 chars) | gerado com `openssl rand -hex 32` |
| `INTERNAL_OPTIMIZER_KEY` | Chave de autenticação interna NestJS→Optimizer | gerado com `openssl rand -hex 32` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `OPTIMIZER_URL` | URL interna do optimizer | `http://optimizer:8000` |
| `CORS_ALLOWED_ORIGINS` | Origins permitidas (vírgula) | `https://app.suaempresa.com` |

### Optimizer (`optimizer/.env`)

| Variável | Descrição |
|---|---|
| `INTERNAL_OPTIMIZER_KEY` | Deve ser o mesmo valor do backend |
| `DATABASE_URL` | Mesma string do backend (para persistência) |
| `REDIS_URL` | Mesma string do backend |

> **Segurança:** Nunca deixe `INTERNAL_OPTIMIZER_KEY` com o valor padrão. O sistema recusa iniciar se detectar o default.

---

## Estrutura do Projeto

```
Novo_OTIMIZ/
├── backend/          # NestJS API
│   ├── src/
│   │   ├── modules/  # operations, reports, vehicles, auth, gtfs...
│   │   └── common/   # middleware, guards, entities base
│   └── src/main.ts   # bootstrap (Swagger, Helmet, CORS, ValidationPipe)
├── frontend/         # Next.js App Router
│   ├── src/app/
│   │   ├── (DashboardLayout)/operations/  # planner, map, reporting
│   │   └── components/shared/            # KPITrendAnalytics, DutyStatsPanel...
│   └── e2e/          # Playwright smoke tests
├── optimizer/        # FastAPI + Celery
│   ├── src/
│   │   ├── algorithms/  # vsp/, csp/, hybrid/
│   │   └── services/    # optimizer_service, solution_validator...
│   └── tests/unit/   # 342 testes pytest
└── docker-compose.yml
```

---

## Desenvolvimento

```bash
# Backend
cd backend && npm install && npm run start:dev

# Frontend
cd frontend && npm install && npm run dev

# Optimizer
cd optimizer && pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
celery -A src.core.celery_app worker --loglevel=info
```

### Testes

```bash
# Backend (221 specs)
cd backend && npm test

# Optimizer (342 specs)
cd optimizer && python -m pytest tests/unit/ -q

# E2E (requer servidores rodando)
cd frontend && npx playwright test
```

### API Docs (Swagger)

Com o backend em modo dev, acesse: `http://localhost:3001/api/v1/docs`

---

## Arquitetura de Segurança

- **Multi-tenant**: `TenantContext` injeta `companyId` em todas as queries — cross-tenant impossível
- **JWT**: verificado em cada request via `JwtAuthGuard`; `decode()` nunca usado sem `verify()`
- **Helmet**: headers HTTP de segurança em todas as respostas (`X-Frame-Options`, `HSTS`, etc.)
- **Rate limiting**: login 10 req/min, otimização 5 req/5min (ThrottlerGuard)
- **Roles**: `COMPANY_ADMIN` obrigatório para criar/editar usuários
- **INTERNAL_OPTIMIZER_KEY**: fail-fast na inicialização se ausente ou padrão

---

## Roadmap

- [ ] Notificações push (WebSocket já implementado)
- [ ] Integração com sistemas AVL/GPS em tempo real
- [ ] Módulo de relatórios de conformidade regulatória
- [ ] API pública com rate limiting por API key

---

## Licença

Proprietary — © 2026 OTIMIZ. Todos os direitos reservados.
