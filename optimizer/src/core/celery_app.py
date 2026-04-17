"""
celery_app.py — Instância central do Celery para o OTIMIZ Optimizer.

Configurações chave:
- worker_prefetch_multiplier=1: garante que cada worker aceita apenas 1 tarefa de cada vez.
  Crítico para tarefas CPU-bound pesadas (VSP/CSP podem durar minutos).
- task_serializer/result_serializer="json": serialização segura e inspeccionável.
- result_expires=3600: resultados são eliminados do Redis após 1 hora.
"""
import os
from celery import Celery

from .config import get_settings

settings = get_settings()

# Prioritiza variáveis de ambiente CELERY_BROKER_URL e CELERY_RESULT_BACKEND (Padrão Cloud/Docker)
# Se não estiverem presentes, faz fallback para o settings.redis_url
broker_url = os.getenv("CELERY_BROKER_URL", settings.redis_url)
result_backend = os.getenv("CELERY_RESULT_BACKEND", settings.redis_url)

celery_app = Celery(
    "otimiz_optimizer",
    broker=broker_url,
    backend=result_backend,
    include=["src.services.optimizer_tasks"],  # Auto-descoberta da task
)

celery_app.conf.update(
    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Performance para CPU-bound
    worker_prefetch_multiplier=1,   # 1 tarefa por worker de cada vez
    task_acks_late=True,            # ACK apenas após conclusão (não perder tarefas em crash)
    # Resultados
    result_expires=3600,            # 1 hora de retenção no Redis
    result_extended=True,           # Guarda traceback e estado estendido
    # Timezone
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Nome da fila padrão (opcional, mas bom pra clareza)
    task_default_queue="optimizer",
)

