# Guia de Instalação — OTIMIZ

## Pré-requisitos

| Software | Versão mínima | Verificação |
|---|---|---|
| Docker | 24.0 | `docker --version` |
| Docker Compose | 2.20 | `docker compose version` |
| (Dev) Node.js | 20 LTS | `node --version` |
| (Dev) Python | 3.11 | `python3 --version` |

---

## Instalação com Docker (Recomendado)

### 1. Variáveis de ambiente

```bash
# Gere chaves seguras
export JWT_SECRET=$(openssl rand -hex 32)
export INTERNAL_OPTIMIZER_KEY=$(openssl rand -hex 32)
```

Crie `.env` na raiz do projeto:

```env
# Banco de dados
DATABASE_URL=postgresql://otimiz:senha_forte@db:5432/otimiz_db
POSTGRES_USER=otimiz
POSTGRES_PASSWORD=senha_forte
POSTGRES_DB=otimiz_db

# Auth
JWT_SECRET=<resultado do openssl acima>

# Comunicação interna
INTERNAL_OPTIMIZER_KEY=<resultado do openssl acima>
OPTIMIZER_URL=http://optimizer:8000

# Redis
REDIS_URL=redis://redis:6379/0

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:3001

# CORS (em produção, coloque apenas seus domínios)
CORS_ALLOWED_ORIGINS=http://localhost:3000
NODE_ENV=development
```

Crie `optimizer/.env`:

```env
INTERNAL_OPTIMIZER_KEY=<mesmo valor do .env principal>
DATABASE_URL=postgresql://otimiz:senha_forte@db:5432/otimiz_db
REDIS_URL=redis://redis:6379/0
```

### 2. Subir serviços

```bash
docker compose up -d
```

Aguarde todos os containers ficarem `healthy` (~60s):

```bash
docker compose ps
```

### 3. Migrations e seed

```bash
# Criar tabelas
docker compose exec backend npm run migration:run

# Criar empresa e usuário admin
docker compose exec backend npm run seed
```

O seed cria:
- Empresa: `Empresa Demonstração` (id=1)
- Admin: `admin@empresa.com` / `admin123` — **troque a senha após o primeiro login**

### 4. Verificar

```bash
# Health check
curl http://localhost:3001/api/v1/health

# Optimizer
curl http://localhost:8000/health
```

Acesse o frontend em `http://localhost:3000`.

---

## Instalação para Desenvolvimento (sem Docker)

### Backend

```bash
cd backend
npm install

# Configure o banco local
createdb otimiz_dev

# Copie e edite .env
cp .env.example .env  # ajuste DATABASE_URL para localhost

npm run migration:run
npm run seed
npm run start:dev     # porta 3001
```

### Optimizer

```bash
cd optimizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # ajuste DATABASE_URL, REDIS_URL

# Em terminais separados:
uvicorn src.main:app --reload --port 8000
celery -A src.core.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # porta 3000
```

---

## Portas padrão

| Serviço | Porta | URL |
|---|---|---|
| Frontend | 3000 | `http://localhost:3000` |
| Backend API | 3001 | `http://localhost:3001/api/v1` |
| Swagger UI | 3001 | `http://localhost:3001/api/v1/docs` |
| Optimizer | 8000 | `http://localhost:8000` (interno) |
| PostgreSQL | 5432 | interno |
| Redis | 6379 | interno |

---

## Troubleshooting

### `INTERNAL_OPTIMIZER_KEY must be set`
O sistema recusa iniciar com a chave padrão. Gere uma nova: `openssl rand -hex 32`.

### `Connection refused` no optimizer
O optimizer precisa de Redis e PostgreSQL antes de iniciar. Verifique: `docker compose ps` e aguarde todos ficarem `healthy`.

### Migrations falham
Certifique-se de que `DATABASE_URL` aponta para o PostgreSQL correto e que o banco existe.

### Frontend não conecta ao backend
Verifique `NEXT_PUBLIC_API_URL` e `CORS_ALLOWED_ORIGINS`. Em dev, ambos devem referenciar `localhost`.

### Otimização trava
Verifique se o Celery worker está rodando: `docker compose logs optimizer-worker`. O Redis deve estar acessível.
