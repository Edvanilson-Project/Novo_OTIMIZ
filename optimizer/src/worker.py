"""
worker.py — Ponto de entrada para o worker Celery do OTIMIZ Optimizer.

Uso:
    celery -A src.worker worker --loglevel=info
"""
from src.core.celery_app import celery_app

# Este arquivo serve apenas como bootstrap para o worker, 
# garantindo que o celery_app seja importado corretamente.
if __name__ == "__main__":
    celery_app.start()
