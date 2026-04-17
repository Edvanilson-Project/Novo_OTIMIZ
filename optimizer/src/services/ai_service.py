"""
AiService — Gera insights em linguagem natural para resultados de otimização.

Princípios de design:
- DEGRADAÇÃO GRACIOSA: qualquer falha retorna None silenciosamente.
- SEGURANÇA: a chave de API é lida exclusivamente via variável de ambiente.
- ASSÍNCRONO: usa httpx.AsyncClient para não bloquear o event loop.
- FALLBACK: usa roteamento de modelos do OpenRouter (array 'models') para
  evitar ponto único de falha quando um modelo :free está offline.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# URL base da API OpenRouter (compatível com OpenAI)
_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modelos gratuitos em ordem de preferência (fallback automático pelo OpenRouter)
_FREE_MODELS = [
    "google/gemini-2.5-flash:free",
    "meta-llama/llama-3-8b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
]

# System prompt: instrui o LLM a agir como Diretor de Operações de Transporte
# e a responder EXCLUSIVAMENTE em texto plano (sem Markdown) para evitar que
# asteriscos e hashes apareçam crus no React.
_SYSTEM_PROMPT = (
    "Voce e um Diretor de Operacoes de Transporte Publico experiente. "
    "Analise o resumo JSON de resultados de frota e tripulacao fornecido. "
    "Responda com EXATAMENTE 3 linhas de texto plano, sem nenhuma formatacao Markdown "
    "(sem asteriscos, sem hashtags, sem negrito). "
    "Use um hifen (-) no inicio de cada linha como bullet point. "
    "Linha 1: elogie algo que esta bom no resultado (ex: veiculos bem utilizados). "
    "Linha 2: identifique onde se esta perdendo dinheiro (ex: deadhead alto, tempo ocioso, horas extras). "
    "Linha 3: sugira UM parametro especifico que o operador pode alterar na proxima otimizacao. "
    "Seja direto, objetivo e pratico. Responda em Portugues do Brasil."
)


class AiService:
    """Serviço de geração de insights via OpenRouter."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai_service")

    # ── API pública ──────────────────────────────────────────────────────────

    def generate_insight_sync(self, metrics: Dict[str, Any]) -> Optional[str]:
        """
        Versão síncrona para ser chamada do OptimizerService (que é síncrono).
        Executa o código assíncrono em um thread pool para não bloquear.
        Retorna None em qualquer cenário de falha.
        """
        if not self._settings.openrouter_api_key:
            logger.debug("[AiService] OPENROUTER_API_KEY não configurada — insight ignorado.")
            return None

        try:
            # Roda o coroutine em um loop de evento isolado dentro de outra thread,
            # evitando conflito com o event loop existente do FastAPI.
            future = self._executor.submit(self._run_async, metrics)
            return future.result(timeout=15)  # 5s de folga além do timeout interno de 10s
        except Exception as exc:
            logger.warning("[AiService] Falha ao gerar insight (não crítico): %s", exc)
            return None

    # ── Implementação interna ─────────────────────────────────────────────────

    def _run_async(self, metrics: Dict[str, Any]) -> Optional[str]:
        """Executa o coroutine assíncrono num novo event loop (dentro de thread pool)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._call_openrouter(metrics))
        finally:
            loop.close()

    async def _call_openrouter(self, metrics: Dict[str, Any]) -> Optional[str]:
        """Chamada assíncrona à API do OpenRouter com fallback de modelos e timeout rigoroso."""
        api_key = self._settings.openrouter_api_key
        if not api_key:
            return None

        user_message = self._build_user_message(metrics)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:3000",  # Identificação da origem (ajuste para domínio real em prod)
            "X-Title": "OTIMIZ Optimizer",
            "Content-Type": "application/json",
        }

        payload = {
            "models": _FREE_MODELS,    # Roteamento com fallback automático do OpenRouter
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 300,         # 3 bullet points curtos — sem desperdício de tokens
            "temperature": 0.4,        # Baixa temperatura = respostas mais consistentes e factuais
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    _OPENROUTER_API_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip() if content else None
        except httpx.TimeoutException:
            logger.warning("[AiService] Timeout ao chamar OpenRouter (>10s) — insight ignorado.")
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[AiService] OpenRouter retornou HTTP %d — insight ignorado. Detalhe: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return None
        except Exception as exc:
            logger.warning("[AiService] Erro inesperado ao chamar OpenRouter: %s", repr(exc))
            return None

    @staticmethod
    def _build_user_message(metrics: Dict[str, Any]) -> str:
        """Formata um resumo compacto das métricas para enviar ao LLM."""
        lines = [
            "Resumo dos resultados de otimizacao:",
            f"- Veiculos utilizados: {metrics.get('vehicles', 'N/A')}",
            f"- Tripulantes (crew): {metrics.get('crew', 'N/A')}",
            f"- Jornadas (duties): {metrics.get('duties', 'N/A')}",
            f"- Custo total: R$ {metrics.get('total_cost', 0):.2f}",
            f"- Custo VSP (frota): R$ {metrics.get('vsp_cost', 0):.2f}",
            f"- Custo CSP (tripulacao): R$ {metrics.get('csp_cost', 0):.2f}",
            f"- Viagens cobertas: {metrics.get('covered_trips', 'N/A')} / {metrics.get('total_trips', 'N/A')}",
            f"- Violacoes CCT: {metrics.get('cct_violations', 0)}",
            f"- Minutos de trabalho total: {metrics.get('work_minutes', 0)}",
            f"- Minutos pagos total: {metrics.get('paid_minutes', 0)}",
            f"- Componente de custo dominante VSP: {metrics.get('dominant_vsp', 'N/A')}",
            f"- Componente de custo dominante CSP: {metrics.get('dominant_csp', 'N/A')}",
            f"- Status da solucao: {metrics.get('status', 'N/A')}",
        ]
        return "\n".join(lines)
