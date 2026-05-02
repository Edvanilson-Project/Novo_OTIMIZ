# Plano de Ação: Preparação para Venda - 4-5 Semanas

## 🎯 OBJETIVO
Transformar o Novo_OTIMIZ em um produto **pronto para produção** e **vendável**

---

## 📅 SEMANA 1: DOCUMENTAÇÃO + SEGURANÇA

### 1.1 Documentação Técnica (3 dias)
**Arquivos a criar:**

#### `README.md` (na raiz)
```markdown
# Novo_OTIMIZ - Otimizador de Transporte Coletivo

## Visão Geral
Descrição do projeto, features principais, arquitetura de alto nível

## Quick Start
- Pré-requisitos: Docker, Docker Compose
- Clone o repo
- docker-compose up -d
- Acesse http://localhost:3000

## Stack Técnico
- Frontend: Next.js 15, React 19, MUI v9
- Backend: NestJS 11, TypeORM, PostgreSQL
- Optimizer: Python FastAPI, PuLP, Celery
- Cache: Redis

## Documentação
- [Installation Guide](./docs/INSTALLATION.md)
- [Configuration Guide](./docs/CONFIG.md)
- [API Documentation](./docs/API.md)
- [Troubleshooting](./docs/TROUBLESHOOTING.md)
```

#### `docs/INSTALLATION.md`
- Sistema operacional support (Linux, macOS, Windows)
- Docker setup step-by-step
- Database initialization
- Environment variables setup
- Port requirements
- Troubleshooting comum

#### `docs/CONFIG.md`
- Environment variables para cada layer
- Parameter configuration para optimizer
- Database connection setup
- JWT configuration
- Redis configuration
- CORS setup

#### `docs/API.md` (OpenAPI/Swagger)
- Endpoints principais
- Authentication
- Rate limits
- Error codes
- Examples para cada endpoint

#### `docs/TROUBLESHOOTING.md`
- Database connection errors
- Backend startup issues
- Optimizer timeouts
- Frontend build errors
- Common permission issues

### 1.2 API Documentation - Swagger (1 dia)
**O que fazer:**
- [ ] Instalar `@nestjs/swagger` e `swagger-ui-express`
- [ ] Adicionar decoradores `@ApiOperation`, `@ApiResponse` em todos endpoints
- [ ] Gerar documentação automática em `/api/docs`
- [ ] Testar documentação no Swagger UI

**Exemplo:**
```typescript
@Post('optimize')
@ApiOperation({ summary: 'Run optimization' })
@ApiResponse({ status: 201, description: 'Optimization started' })
async runOptimization() { ... }
```

### 1.3 Security Hardening (2 dias)

#### Backend Security:
- [ ] Adicionar Helmet.js para headers seguros
```bash
npm install helmet
```
- [ ] Rate limiting com `express-rate-limit`
- [ ] CORS whitelist configuration
- [ ] Input validation + sanitization
- [ ] SQL injection prevention (já tem com TypeORM, validar)
- [ ] XSS prevention (já tem, validar)
- [ ] Environment variables encryption
- [ ] HTTPS redirection (para produção)

#### Checklist de Security:
- [ ] JWT secret > 32 caracteres
- [ ] Passwords hashed com bcrypt
- [ ] No secrets em .env.example
- [ ] CORS apenas para domínios permitidos
- [ ] Rate limit: 100 req/min por IP
- [ ] Error messages não expõem estrutura
- [ ] SQL queries parametrizadas

---

## 📅 SEMANA 2: OBSERVABILIDADE + CI/CD

### 2.1 Logging Centralizado (2 dias)

#### Setup Winston (Backend)
```bash
npm install winston winston-daily-rotate-file
```

**Configuração:**
```typescript
// src/config/logger.ts
import * as winston from 'winston';

export const createLogger = () => {
  return winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: winston.format.json(),
    transports: [
      new winston.transports.Console(),
      new winston.transports.DailyRotateFile({
        filename: 'logs/application-%DATE%.log',
        datePattern: 'YYYY-MM-DD',
        maxSize: '20m',
        maxFiles: '14d'
      })
    ]
  });
};
```

#### Setup Python Logging (Optimizer)
```python
# src/config/logger.py
import logging
from logging.handlers import RotatingFileHandler

def setup_logger():
    logger = logging.getLogger('optimizer')
    handler = RotatingFileHandler(
        'logs/optimizer.log',
        maxBytes=20*1024*1024,  # 20MB
        backupCount=10
    )
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
```

### 2.2 Error Tracking (Sentry) (1 dia)

#### Backend:
```bash
npm install @sentry/node @sentry/integrations
```

```typescript
// main.ts
import * as Sentry from "@sentry/node";

const app = await NestFactory.create(AppModule);
Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.NODE_ENV,
  tracesSampleRate: 0.1
});
app.use(Sentry.Handlers.requestHandler());
app.use(Sentry.Handlers.errorHandler());
```

#### Optimizer:
```bash
pip install sentry-sdk
```

### 2.3 Health Check Endpoints (1 dia)
```typescript
// src/health/health.controller.ts
@Controller('health')
export class HealthController {
  @Get()
  check() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      version: process.env.VERSION,
      services: {
        database: await checkDB(),
        redis: await checkRedis(),
        optimizer: await checkOptimizer()
      }
    };
  }
}
```

### 2.4 CI/CD Pipeline com GitHub Actions (2 dias)

#### `.github/workflows/test.yml`
```yaml
name: Test & Build

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
      redis:
        image: redis:alpine
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Install dependencies
        run: npm install
      
      - name: Run tests
        run: npm test -- --coverage
      
      - name: Build
        run: npm run build
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

#### `.github/workflows/deploy.yml`
```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker image
        run: docker build -t novo-otimiz:latest .
      - name: Push to registry
        run: docker push ${{ secrets.DOCKER_REGISTRY }}/novo-otimiz:latest
      - name: Deploy to production
        run: ssh ${{ secrets.PROD_SERVER }} 'docker pull ... && docker-compose up -d'
```

---

## 📅 SEMANA 3: TESTES E2E

### 3.1 Setup Playwright/Cypress (1 dia)
```bash
npm install --save-dev @playwright/test
npx playwright install
```

### 3.2 E2E Test Suites (2 dias)

#### `e2e/auth.spec.ts`
- Login flow
- Logout
- Password reset
- Session expiration

#### `e2e/optimization.spec.ts`
- Start optimization
- Monitor progress
- Complete optimization
- View results
- Export CSV

#### `e2e/admin.spec.ts`
- User management
- Company management
- Parameter configuration

### 3.3 Load Testing (1 dia)
```bash
npm install --save-dev artillery
```

```yaml
# load-test.yml
config:
  target: "http://localhost:3001"
  phases:
    - duration: 60
      arrivalRate: 10  # 10 req/sec
scenarios:
  - name: "Optimization Flow"
    flow:
      - post:
          url: "/api/v1/operations/optimize"
          json:
            companyId: 16
```

---

## 📅 SEMANA 4: OPERAÇÕES + COMPLIANCE

### 4.1 Backup Automation (1 dia)

#### Database Backup Script
```bash
#!/bin/bash
# backup-db.sh
BACKUP_DIR="/backups/postgresql"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

pg_dump -h localhost -U otimiz_admin otimiz_db > \
  $BACKUP_DIR/backup_$TIMESTAMP.sql

# Keep only last 30 days
find $BACKUP_DIR -name "backup_*.sql" -mtime +30 -delete
```

#### Docker Compose Backup Service
```yaml
backup:
  image: postgres:16
  volumes:
    - ./backup-db.sh:/backup-db.sh
    - backups:/backups
  command: /bin/bash -c "while true; do /backup-db.sh; sleep 86400; done"
```

### 4.2 LGPD Compliance (2 dias)

#### Checklist:
- [ ] Data retention policy (máximo X dias)
- [ ] User data export endpoint
- [ ] User data deletion endpoint
- [ ] Audit logs para acessos
- [ ] Encryption em repouso
- [ ] Privacy Policy documento
- [ ] Terms of Service documento
- [ ] Consent management (cookies)

#### API Endpoints:
```typescript
@Post('data/export')
async exportUserData(@Req() req) {
  // Retorna todos dados do usuário em JSON
}

@Delete('data')
async deleteUserData(@Req() req) {
  // Deleta todos dados do usuário (irreversível)
}
```

### 4.3 Release Management (1 dia)

#### Semantic Versioning Setup
```bash
git tag -a v0.1.0 -m "Initial release"
```

#### CHANGELOG.md
```markdown
# Changelog

## [0.2.0] - 2026-05-15
### Added
- Retry logic em persistFailure
- Security hardening

### Fixed
- Fire-and-forget bug em polling

### Changed
- Updated dependencies

## [0.1.0] - 2026-04-30
### Added
- Initial release
```

---

## 📅 SEMANA 5: FINAL POLISH

### 5.1 Admin Panel (2-3 dias)

**O que precisa ter:**
- [ ] User management (CRUD)
- [ ] Company management
- [ ] System health dashboard
- [ ] Logs viewer
- [ ] Parameter configuration UI
- [ ] Audit logs
- [ ] Backup management

### 5.2 Support & Onboarding (1-2 dias)

#### Setup:
- [ ] Zendesk ou Intercom
- [ ] Welcome email sequence
- [ ] Video tutorial
- [ ] Sample data setup
- [ ] First-run checklist
- [ ] FAQ page

### 5.3 Final Testing & Validation (1 dia)

**Checklist final:**
- [ ] All 94+ tests passing
- [ ] E2E tests passing
- [ ] Load tests < 200ms p95
- [ ] Logging working
- [ ] Backup working
- [ ] Recovery tested
- [ ] Documentation complete
- [ ] Security audit passed

---

## 🎯 DELIVERABLES FINAIS

### Documentação
- ✅ README.md
- ✅ Installation Guide
- ✅ API Documentation (Swagger)
- ✅ Configuration Guide
- ✅ Troubleshooting Guide
- ✅ Privacy Policy
- ✅ Terms of Service

### Código & Segurança
- ✅ Security hardening
- ✅ Logging & monitoring
- ✅ Error tracking
- ✅ Health checks
- ✅ Input validation

### Automação
- ✅ CI/CD pipeline (GitHub Actions)
- ✅ Automated testing
- ✅ Backup automation
- ✅ Monitoring alerts

### Testing
- ✅ Unit tests (94+)
- ✅ E2E tests
- ✅ Load tests
- ✅ Security tests

### Operações
- ✅ Admin panel
- ✅ Support system
- ✅ Onboarding flow
- ✅ Disaster recovery

---

## 📊 TIMELINE

```
SEMANA 1: Docs + Security     ████░░░░░░ 40%
SEMANA 2: Observability + CI  ████░░░░░░ 40%
SEMANA 3: E2E Tests           ████░░░░░░ 40%
SEMANA 4: Ops + Compliance    ████░░░░░░ 40%
SEMANA 5: Polish + Final      ████░░░░░░ 40%

Total: 200 horas de desenvolvimento
Pode ser reduzido com mais developers
```

---

## ✅ DEFINIÇÃO DE "PRONTO PARA VENDER"

O projeto está pronto quando:

- ✅ Código passou em segurança audit
- ✅ CI/CD pipeline está rodando
- ✅ Todos os testes passam (>90% coverage)
- ✅ Logging e monitoring funcionando
- ✅ Backup automation testado
- ✅ Documentação completa
- ✅ Admin panel funcional
- ✅ Support channels ready
- ✅ LGPD compliance validado
- ✅ Load tests dentro de specs
- ✅ Disaster recovery testado
- ✅ SLA defined and monitored

