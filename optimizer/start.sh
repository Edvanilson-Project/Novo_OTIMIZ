#!/bin/sh
# Inicia o Celery worker em background e depois o uvicorn em foreground
# Usado como CMD do container do optimizer

set -e

echo "[startup] Iniciando Celery worker..."
celery -A src.core.celery_app.celery_app worker \
  --loglevel=info \
  -Q optimizer \
  --concurrency=2 \
  --detach \
  --logfile=/tmp/celery-worker.log \
  --pidfile=/tmp/celery-worker.pid

echo "[startup] Celery worker iniciado. Logs em /tmp/celery-worker.log"
echo "[startup] Iniciando uvicorn..."

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
