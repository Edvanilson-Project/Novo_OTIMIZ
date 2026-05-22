"""
AiService — Gera insights em linguagem natural para resultados de otimização.

Princípios de design:
- MODELOS DINÂMICOS: busca em tempo real TODOS os modelos gratuitos do OpenRouter,
  ordena por potência estimada e tenta cada um sequencialmente.
- DEGRADAÇÃO GRACIOSA: se todos os modelos falharem, responde localmente com dados reais.
- SEGURANÇA: a chave de API é lida exclusivamente via variável de ambiente.
- ASSÍNCRONO: usa httpx.AsyncClient para não bloquear o event loop.
- CACHE TTL: a lista de modelos é atualizada automaticamente a cada 1 hora.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# URL base da API OpenRouter (compatível com OpenAI)
_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Lista estática de segurança — usada APENAS se a API de modelos do OpenRouter falhar
_FALLBACK_MODELS = [
    "openrouter/auto",  # Roteamento inteligente do próprio OpenRouter
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen3-coder:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]

# URL da API de listagem de modelos do OpenRouter
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Palavras-chave para estimar potência de um modelo pelo seu ID
# (maior número de parâmetros = maior prioridade)
_SIZE_HINTS = [
    ("405b", 9),
    ("70b", 8),
    ("72b", 8),
    ("32b", 7),
    ("27b", 7),
    ("30b", 7),
    ("26b", 6),
    ("13b", 5),
    ("12b", 5),
    ("9b", 4),
    ("8b", 4),
    ("7b", 3),
    ("4b", 2),
    ("3b", 2),
    ("1b", 1),
]

# System prompt: instrui o LLM a agir como Diretor de Operações de Transporte
_SYSTEM_PROMPT = (
    "Você é o Diretor de Estratégia da OTIMIZ e especialista em algoritmos de transporte público. "
    "Sua missão é realizar uma auditoria técnica profunda dos resultados JSON fornecidos. "
    "\n\n### GLOSSÁRIO DE PARÂMETROS (TRADUZA SEMPRE PARA ESTES NOMES):"
    "\n- 'max_shift_minutes' -> Jornada Máxima Diária"
    "\n- 'min_break_minutes' -> Intervalo de Descanso Mínimo"
    "\n- 'max_driving_minutes' -> Tempo Máximo de Direção Contínua"
    "\n- 'inter_shift_rest_minutes' -> Descanso Interjornada (11h)"
    "\n- 'pullout_minutes' -> Tempo de Preparação (Saída da Garagem)"
    "\n- 'pullin_minutes' -> Tempo de Recolhimento (Entrada na Garagem)"
    "\n- 'min_layover_minutes' -> Intervalo Mínimo no Terminal (Layover)"
    "\n- 'mandatory_break_after_minutes' -> Descanso após direção contínua"
    "\n- 'preferred_pair_window_minutes' -> Janela de Pareamento de Viagens"
    "\n- 'allow_relief_points' -> Pontos de Rendição (Troca em Trânsito)"
    "\n- 'max_wait_minutes' -> Tempo Máximo de Espera"
    "\n- 'vsp' -> Planejamento de Veículos (Frota)"
    "\n- 'csp' -> Planejamento de Tripulação (Motoristas)"
    "\n- 'deadhead' -> KM Morto / Viagem em Vazio"
    "\n\n### INSTRUÇÕES CRÍTICAS DE RESPOSTA:"
    "\n1. PROIBIÇÃO TOTAL: Nunca use nomes com underline (ex: min_break_minutes). Se não souber o nome, invente um nome em Português que faça sentido."  # noqa: E501
    "\n2. NÃO USE TABELAS: Use apenas listas com tópicos (•) e negritos."
    "\n3. FOCO EM SOLUÇÃO: Dê sugestões de como reduzir custos mudando os parâmetros acima."
)

_TRANSLATE_PROMPT = (
    "Você é um parser inteligente para um sistema de roteirização de ônibus. "
    "Sua função é traduzir regras de negócio escritas em linguagem natural "
    "para um objeto JSON simples de configuração."
    "\n\nRegras de mapeamento:"
    "\n- Jornada máxima (em horas ou min) -> max_shift_minutes (int)"
    "\n- Pausa ou descanso obrigatório (em min ou horas) -> min_break_minutes (int)"
    "\n- Direção contínua (ex: dirigir máx 4h) -> max_driving_minutes (int)"
    "\n- Intervalo interjornada (ex: descanso entre dias de 11h) -> inter_shift_rest_minutes (int)"
    "\n- Limite semanal -> weekly_driving_limit_minutes (int) ou weekly_rest_minutes (int)"
    "\n\nInstrução Crítica: Retorne APENAS um objeto JSON válido, sem nenhum texto ao redor, "
    "sem marcação ```json, apenas as chaves e valores numéricos em minutos."
)


class AiService:
    """Serviço de geração de insights via OpenRouter com seleção dinâmica de modelos."""

    def __init__(self) -> None:
        self._settings = get_settings()
        # Cache de traduções: SHA256(regras) -> Dict resultado
        self._translation_cache: Dict[str, Dict[str, Any]] = {}
        # Cache dinâmico de modelos gratuitos disponíveis no OpenRouter
        self._dynamic_models: List[str] = []
        self._models_fetched_at: float = 0.0  # timestamp Unix da última busca
        self._models_ttl: float = 3600.0  # atualiza a lista a cada 1 hora

    # ── Descoberta dinâmica de modelos ────────────────────────────────────────

    def _estimate_model_power(self, model_id: str) -> int:
        """Estima a potência de um modelo pelo tamanho indicado no ID (ex: 70b > 7b)."""
        model_lower = model_id.lower()
        for hint, score in _SIZE_HINTS:
            if hint in model_lower:
                return score
        return 0  # Modelo sem tamanho identificável (prioridade mais baixa)

    async def _fetch_free_models_async(self) -> List[str]:
        """
        Busca TODOS os modelos gratuitos do OpenRouter em tempo real.
        Ordena do mais potente para o menos potente por estimativa de tamanho.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(_OPENROUTER_MODELS_URL)
                if response.status_code != 200:
                    logger.warning(
                        "[AiService] Falha ao buscar lista de modelos (%d). Usando fallback estático.",
                        response.status_code,
                    )
                    return _FALLBACK_MODELS

                all_models = response.json().get("data", [])
                free_models = [m["id"] for m in all_models if ":free" in m.get("id", "")]

                if not free_models:
                    logger.warning("[AiService] Nenhum modelo gratuito encontrado. Usando fallback estático.")
                    return _FALLBACK_MODELS

                # Ordena do mais potente para o menos potente
                free_models.sort(key=lambda m: self._estimate_model_power(m), reverse=True)
                logger.info("[AiService] %d modelos gratuitos descobertos e ordenados por potência.", len(free_models))
                return free_models

        except Exception as exc:
            logger.warning("[AiService] Erro ao buscar modelos dinâmicos: %s. Usando fallback estático.", repr(exc))
            return _FALLBACK_MODELS

    async def _get_models_async(self) -> List[str]:
        """Versão assíncrona e segura para obter modelos."""
        # Se um modelo específico foi configurado, use-o com prioridade máxima
        pinned_model = getattr(self._settings, "openrouter_model", None)

        now = time.time()
        if (now - self._models_fetched_at) < self._models_ttl and self._dynamic_models:
            models = self._dynamic_models
        else:
            models = await self._fetch_free_models_async()
            self._dynamic_models = models
            self._models_fetched_at = now

        if pinned_model:
            # Garante que o modelo fixado seja o primeiro, sem duplicatas
            return [pinned_model] + [m for m in models if m != pinned_model]

        return models

    # ── API pública ──────────────────────────────────────────────────────────

    async def generate_insight_async(self, metrics: Dict[str, Any]) -> Optional[str]:
        """Gera insight automático de forma assíncrona."""
        if not self._settings.openrouter_api_key:
            return None
        try:
            return await self._call_openrouter(metrics)
        except Exception as exc:
            logger.warning("[AiService] Falha ao gerar insight: %s", exc)
            return None

    def generate_insight_sync(self, metrics: Dict[str, Any]) -> Optional[str]:
        """Wrapper síncrono para generate_insight_async.

        Funciona tanto em contexto sync (Celery worker) quanto async
        (FastAPI com wait_for_completion=True). Se um event loop já estiver
        rodando, executa em uma thread separada para evitar conflito.
        """
        if not self._settings.openrouter_api_key:
            return None
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.generate_insight_async(metrics)).result()
        except RuntimeError:
            return asyncio.run(self.generate_insight_async(metrics))

    async def translate_rules_async(self, rules: List[str]) -> Dict[str, Any]:
        """Traduz regras de forma assíncrona com cache."""
        if not self._settings.openrouter_api_key or not rules:
            return {}

        cache_key = hashlib.sha256("|||".join(sorted(str(r) for r in rules)).encode()).hexdigest()
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        try:
            result = await self._call_openrouter_translate(rules)
            if result:
                clean_json = result.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean_json)
            else:
                parsed = {}

            self._translation_cache[cache_key] = parsed
            return parsed
        except Exception:
            return {}

    def translate_rules_sync(self, rules: List[str]) -> Dict[str, Any]:
        """Wrapper síncrono para translate_rules_async.

        Mesma estratégia de generate_insight_sync: detecta event loop ativo e
        executa em thread separada quando necessário. Sem chave API, retorna {}
        imediatamente para que o caller use o fallback de regex.
        """
        if not self._settings.openrouter_api_key or not rules:
            return {}
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.translate_rules_async(rules)).result()
        except RuntimeError:
            return asyncio.run(self.translate_rules_async(rules))

    async def chat_async(self, metrics: Dict[str, Any], question: str) -> str:
        """Endpoint principal para o chat assíncrono."""
        if not self._settings.openrouter_api_key:
            return "IA não configurada."
        try:
            return await self._call_openrouter_chat(metrics, question)
        except Exception as exc:
            logger.warning("[AiService] Erro no chat_async: %s", repr(exc))
            return self._local_fallback_answer(metrics, question)

    # ── Implementação interna ─────────────────────────────────────────────────

    async def _call_openrouter_chat(self, metrics: Dict[str, Any], question: str) -> str:
        """Tenta cada modelo da lista individualmente até um responder."""
        api_key = self._settings.openrouter_api_key
        user_context = self._build_user_message(metrics)
        models = await self._get_models_async()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "OTIMIZ AI Chat",
            "Content-Type": "application/json",
        }

        messages = [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT
                + "\nAgora, responda especificamente à pergunta do usuário usando os dados acima.",
            },
            {"role": "assistant", "content": f"Contexto da Otimização:\n{user_context}"},
            {"role": "user", "content": question},
        ]

        async with httpx.AsyncClient(timeout=60.0) as client:
            for model in models:
                try:
                    payload = {
                        "model": model,
                        "messages": messages,
                        "max_tokens": 3000,
                        "temperature": 0.5,
                    }
                    response = await client.post(_OPENROUTER_API_URL, headers=headers, json=payload)
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        if content:
                            logger.info("[AiService] Chat respondido pelo modelo: %s", model)
                            return content.strip()

                    err_body = response.text[:150]
                    logger.warning(
                        "[AiService] Modelo %s retornou HTTP %d (%s) — tentando próximo em 0.5s.",
                        model,
                        response.status_code,
                        err_body,
                    )
                    await asyncio.sleep(0.5)
                except Exception as exc:
                    logger.warning("[AiService] Modelo %s falhou (%s) — tentando próximo.", model, repr(exc))
                    await asyncio.sleep(0.3)

        return self._local_fallback_answer(metrics, question)

    def _run_async(self, metrics: Dict[str, Any]) -> Optional[str]:
        """Executa o coroutine assíncrono de forma segura."""
        try:
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(self._call_openrouter(metrics), loop)
                return future.result(timeout=25.0)
            except RuntimeError:
                return asyncio.run(self._call_openrouter(metrics))
        except Exception as exc:
            logger.warning("[AiService] Falha ao gerar insight (não crítico): %s", repr(exc))
            return None

    def _run_translate_async(self, rules: List[str]) -> Optional[str]:
        """Tradutor assíncrono compatível com múltiplos ambientes de loop."""
        try:
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(self._call_openrouter_translate(rules), loop)
                return future.result(timeout=15.0)
            except RuntimeError:
                return asyncio.run(self._call_openrouter_translate(rules))
        except Exception as exc:
            logger.warning("[AiService] Falha na tradução: %s", repr(exc))
            return None

    async def _call_openrouter_translate(self, rules: List[str]) -> Optional[str]:
        api_key = self._settings.openrouter_api_key
        if not api_key:
            return None

        user_message = "Traduza as seguintes regras:\n" + "\n".join(f"- {r}" for r in rules)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "OTIMIZ Optimizer",
            "Content-Type": "application/json",
        }

        payload = {
            "model": ",".join(await self._get_models_async()),
            "messages": [
                {"role": "system", "content": _TRANSLATE_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 150,
            "temperature": 0.1,  # Baixíssima temperatura para evitar alucinações no JSON
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(_OPENROUTER_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip() if content else None
        except Exception as exc:
            logger.warning("[AiService] Erro na API OpenRouter (Translate): %s", repr(exc))
            return None

    async def _call_openrouter(self, metrics: Dict[str, Any]) -> Optional[str]:
        """Tenta cada modelo individualmente. Fallback garantido — nunca retorna erro ao usuário."""
        api_key = self._settings.openrouter_api_key
        if not api_key:
            return None

        user_message = self._build_user_message(metrics)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "OTIMIZ Optimizer",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            for model in await self._get_models_async():
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.4,
                    }
                    response = await client.post(_OPENROUTER_API_URL, headers=headers, json=payload)
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        if content:
                            logger.info("[AiService] Insight gerado pelo modelo: %s", model)
                            return content.strip()
                    logger.warning(
                        "[AiService] Modelo %s retornou HTTP %d — tentando próximo.", model, response.status_code
                    )
                except Exception as exc:
                    logger.warning("[AiService] Modelo %s falhou (%s) — tentando próximo.", model, repr(exc))

        return None  # Insight ignorado silenciosamente (não é crítico para a operação)

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
        if metrics.get("current_parameters"):
            lines.append("\nParametros Atuais (Regras CCT):")
            for k, v in metrics["current_parameters"].items():
                lines.append(f"- {k}: {v}")

        return "\n".join(lines)

    def _local_fallback_answer(self, metrics: Dict[str, Any], question: str) -> str:
        """
        Resposta inteligente local gerada a partir dos dados reais da otimização.
        Usada como ÚLTIMO RECURSO quando todos os modelos de IA externos estão indisponíveis.
        O usuário NUNCA verá uma mensagem de erro genérica.
        """
        total_cost = metrics.get("total_cost", 0)
        vehicles = metrics.get("vehicles", "?")
        crew = metrics.get("crew", "?")
        cct_violations = metrics.get("cct_violations", 0)
        cb = metrics.get("cost_breakdown", {})
        params = metrics.get("current_parameters", {})

        # Análise local baseada nos dados reais
        vsp_total = (cb.get("vsp") or {}).get("total", 0)
        csp_total = (cb.get("csp") or {}).get("total", 0)
        overtime = (cb.get("csp") or {}).get("overtime_cost", 0)
        deadhead = (cb.get("vsp") or {}).get("connection", 0)

        q = question.lower()
        response_lines = ["📊 **Análise com base na sua otimização atual:**\n"]

        if any(w in q for w in ["custo", "reduzir", "economizar", "melhorar"]):
            dominante = "frota (VSP)" if vsp_total > csp_total else "tripulação (CSP)"
            response_lines.append(f"**Custo total: R$ {total_cost:,.2f}** dividido em:")
            response_lines.append(f"- Frota: R$ {vsp_total:,.2f} | Tripulação: R$ {csp_total:,.2f}")
            response_lines.append(f"\n💡 O maior gasto está em **{dominante}**.")
            if overtime > 0:
                response_lines.append(
                    f"- Horas extras representam R$ {overtime:,.2f}. Considere aumentar o número de turnos."
                )
            if deadhead > 0:
                response_lines.append(f"- KM morto custa R$ {deadhead:,.2f}. Ative `force_round_trip` para reduzir.")

        elif any(w in q for w in ["motorista", "tripulação", "crew", "escala"]):
            response_lines.append(f"**{crew} motoristas** alocados com **{vehicles} veículos**.")
            if cct_violations > 0:
                response_lines.append(
                    f"⚠️ {cct_violations} violações de CCT detectadas — revise as janelas de descanso."
                )
            if params.get("max_shift_minutes"):
                response_lines.append(
                    f"- Jornada máxima: {params['max_shift_minutes']} min ({params['max_shift_minutes']//60}h)"
                )
            response_lines.append(
                "\n💡 Para reduzir motoristas: diminua `min_layover_minutes` e ative `prefer_fewer_duties`."
            )

        elif any(w in q for w in ["parâmetro", "parametro", "configuração", "cct", "regra"]):
            if params:
                response_lines.append("**Parâmetros ativos na sua operação:**")
                for k, v in list(params.items())[:10]:
                    response_lines.append(f"- `{k}`: {v}")
                response_lines.append(
                    "\n💡 Experimente reduzir `min_layover_minutes` ou `pullout_minutes` para ganhar flexibilidade."
                )
            else:
                response_lines.append(
                    "Não foram encontrados parâmetros específicos. Configure na tela de Parâmetros da Empresa."
                )

        else:
            response_lines.append(
                f"Sua otimização: **{vehicles} veículos**, **{crew} motoristas**, custo total **R$ {total_cost:,.2f}**."
            )
            response_lines.append("\n💡 Posso analisar: custos, motoristas, parâmetros CCT e sugestões de melhoria.")
            response_lines.append("Reformule sua pergunta e responderei com os dados da sua programação.")

        return "\n".join(response_lines)
