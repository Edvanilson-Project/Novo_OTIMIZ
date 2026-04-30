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
    # Serialização e Compressão (GZIP previne OOM no Redis em grandes payloads)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json", "application/json"],
    task_compression="gzip",
    result_compression="gzip",
    # Performance para CPU-bound
    worker_prefetch_multiplier=1,   # 1 tarefa por worker de cada vez
    task_acks_late=True,            # ACK apenas após conclusão (não perder tarefas em crash)
    # Timeouts de segurança: evita workers bloqueados por solvers CBC/PuLP travados.
    # soft_time_limit dispara SoftTimeLimitExceeded (capturável); time_limit envia SIGKILL.
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    task_reject_on_worker_lost=True,  # Evita loop infinito se worker morrer por OOM
    # Reinicia o processo após cada otimização pesada para devolver RAM ao SO.
    worker_max_tasks_per_child=1,
    worker_max_memory_per_child=800000,  # ~800 MB em KB
    # Resultados e Caching
    result_expires=43200,           # 12 horas de retenção no Redis para habilitar Smart Caching
    result_extended=True,           # Guarda traceback e estado estendido
    # Timezone
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Nome da fila padrão
    task_default_queue="optimizer",
)
