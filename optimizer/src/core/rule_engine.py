"""
DynamicRuleEngine — Motor de Regras Dinâmicas para o OTIMIZ Optimizer.

PROPÓSITO:
Permite que o payload JSON envie regras de custo dinâmicas (ex: "Se for feriado
e tiver hora extra, multiplique overtime_cost por 1.5") que são compiladas em
funções callable SEGURAS e aplicadas como modificadores APÓS o CostEvaluator
calcular os custos base.

────────────────────────────────────────────────────────────────────────────────
MODELO DE SEGURANÇA:
────────────────────────────────────────────────────────────────────────────────

1. ZERO eval() / exec():
   Nenhuma string é executada dinamicamente. Usamos um mapa explícito de
   operadores via o módulo `operator` nativo do Python (operator.eq, operator.gt,
   etc.). Apenas os operadores listados em _SAFE_OPERATORS são permitidos.

2. DEGRADAÇÃO GRACIOSA:
   Se uma regra for malformada, tiver campos desconhecidos ou falhar durante
   a avaliação, ela é silenciosamente ignorada com um logger.warning().
   Os custos base calculados pelo CostEvaluator NUNCA são afectados por uma
   regra defeituosa.

3. WHITELIST DE TARGETS:
   Apenas campos de custo específicos (work_cost, overtime_cost, etc.) podem
   ser modificados. Campos internos ou de identificação (duty_id, block_id, etc.)
   estão blindados.

4. LIMITES DE SEGURANÇA:
   - Multiplicadores são clampados entre 0.0 e 10.0 (evita custos negativos ou
     explosão numérica acidental).
   - Valores absolutos de add/subtract são clampados a ±100000.
   - Máximo 50 regras por execução.

────────────────────────────────────────────────────────────────────────────────
FORMATO DA REGRA (JSON):
────────────────────────────────────────────────────────────────────────────────

{
    "condition": {
        "field": "is_holiday",   // campo do contexto do duty
        "op": "==",              // operador de comparação
        "value": true            // valor a comparar
    },
    "action": {
        "target": "overtime_cost",  // campo de custo a modificar
        "type": "multiply",         // "multiply" | "add" | "subtract" | "set"
        "value": 1.5                // valor a aplicar
    }
}

CONDIÇÕES COMPOSTAS (AND lógico — todas devem ser verdadeiras):

{
    "conditions": [
        {"field": "is_holiday", "op": "==", "value": true},
        {"field": "start_hour", "op": ">=", "value": 22}
    ],
    "action": {"target": "overtime_cost", "type": "multiply", "value": 1.5}
}

────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import logging
import operator
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Operadores seguros: mapa explícito (NUNCA usa eval/exec) ──────────────────
_SAFE_OPERATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}

# ── Campos de custo que podem ser modificados pelas regras dinâmicas ──────────
# Qualquer target fora desta lista é rejeitado na compilação.
_MODIFIABLE_COST_FIELDS = frozenset({
    "work_cost",
    "guaranteed_cost",
    "waiting_cost",
    "overtime_cost",
    "long_unpaid_break_penalty",
    "nocturnal_extra",
    "holiday_extra",
    "cct_penalties",
})

# ── Tipos de ação suportados ──────────────────────────────────────────────────
_VALID_ACTION_TYPES = frozenset({"multiply", "add", "subtract", "set"})

# ── Limites de segurança contra explosão numérica ────────────────────────────
_MAX_RULES = 50
_MULTIPLY_MIN = 0.0
_MULTIPLY_MAX = 10.0
_ABSOLUTE_VALUE_LIMIT = 100000.0


class _CompiledCondition:
    """Condição compilada a partir de um dicionário JSON. Segura e imutável."""

    __slots__ = ("field", "op_fn", "op_str", "value")

    def __init__(self, field: str, op_fn: Callable, op_str: str, value: Any) -> None:
        self.field = field
        self.op_fn = op_fn
        self.op_str = op_str
        self.value = value

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Avalia a condição contra o contexto. Retorna False se o campo não existir."""
        actual = context.get(self.field)
        if actual is None:
            return False
        try:
            return bool(self.op_fn(actual, self.value))
        except (TypeError, ValueError):
            return False


class _CompiledAction:
    """Ação compilada a partir de um dicionário JSON. Aplica modificador ao custo."""

    __slots__ = ("target", "action_type", "value")

    def __init__(self, target: str, action_type: str, value: float) -> None:
        self.target = target
        self.action_type = action_type
        self.value = value

    def apply(self, costs: Dict[str, float]) -> None:
        """Aplica a ação ao dicionário de custos in-place. Ignora targets inexistentes."""
        if self.target not in costs:
            return

        current = costs[self.target]

        if self.action_type == "multiply":
            costs[self.target] = current * self.value
        elif self.action_type == "add":
            costs[self.target] = current + self.value
        elif self.action_type == "subtract":
            costs[self.target] = current - self.value
        elif self.action_type == "set":
            costs[self.target] = self.value


class _CompiledRule:
    """Regra compilada: lista de condições (AND lógico) + ação."""

    __slots__ = ("conditions", "action", "source_index")

    def __init__(
        self,
        conditions: List[_CompiledCondition],
        action: _CompiledAction,
        source_index: int,
    ) -> None:
        self.conditions = conditions
        self.action = action
        self.source_index = source_index

    def matches(self, context: Dict[str, Any]) -> bool:
        """Todas as condições devem ser verdadeiras (AND lógico)."""
        return all(c.evaluate(context) for c in self.conditions)


class DynamicRuleEngine:
    """
    Motor de Regras Dinâmicas.

    Recebe uma lista de dicionários (regras enviadas via payload JSON),
    compila-os em callables seguros, e aplica-os como modificadores de custo
    sobre os cálculos base do CostEvaluator.

    THREAD-SAFE: A instância é imutável após a compilação.
    Uso: ``engine = DynamicRuleEngine(rules_list)``
         ``engine.apply(duty_context, duty_costs)``
    """

    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        """
        Compila as regras. Regras malformadas são ignoradas com warning.

        Args:
            rules: Lista de dicionários no formato documentado acima.
                   Máximo de _MAX_RULES regras por segurança.
        """
        self._compiled: List[_CompiledRule] = []
        self._compile_warnings: List[str] = []

        if not rules:
            return

        # Limitar número de regras (proteção contra DoS)
        effective_rules = rules[:_MAX_RULES]
        if len(rules) > _MAX_RULES:
            logger.warning(
                "[RuleEngine] Truncado de %d para %d regras (limite de segurança).",
                len(rules),
                _MAX_RULES,
            )

        for idx, raw in enumerate(effective_rules):
            compiled = self._compile_rule(raw, idx)
            if compiled is not None:
                self._compiled.append(compiled)

    @property
    def rule_count(self) -> int:
        """Número de regras compiladas com sucesso."""
        return len(self._compiled)

    @property
    def warnings(self) -> List[str]:
        """Avisos gerados durante a compilação (regras ignoradas, etc.)."""
        return list(self._compile_warnings)

    def apply(
        self,
        duty_context: Dict[str, Any],
        duty_costs: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Aplica as regras ao dicionário de custos de um duty.

        DEGRADAÇÃO GRACIOSA: Se qualquer regra falhar na aplicação,
        os custos base permanecem intactos — apenas a regra defeituosa
        é ignorada.

        Args:
            duty_context: Dicionário com campos do duty (is_holiday, work_time,
                          spread_time, overtime_minutes, start_hour, etc.).
            duty_costs:   Dicionário com custos calculados (work_cost,
                          overtime_cost, etc.). Modificado IN-PLACE.

        Returns:
            O mesmo dicionário `duty_costs` (modificado in-place).
        """
        if not self._compiled:
            return duty_costs

        for rule in self._compiled:
            try:
                if rule.matches(duty_context):
                    rule.action.apply(duty_costs)
            except Exception as exc:
                logger.warning(
                    "[RuleEngine] Regra #%d falhou na aplicação (ignorada): %s",
                    rule.source_index,
                    exc,
                )
        return duty_costs

    # ── Compilação privada ────────────────────────────────────────────────────

    def _compile_rule(
        self, raw: Dict[str, Any], index: int
    ) -> Optional[_CompiledRule]:
        """Compila uma regra JSON em _CompiledRule. Retorna None se inválida."""
        if not isinstance(raw, dict):
            self._warn(index, "regra não é um dicionário")
            return None

        # ── Compilar condições ────────────────────────────────────────────────
        conditions = self._compile_conditions(raw, index)
        if conditions is None:
            return None

        # ── Compilar ação ─────────────────────────────────────────────────────
        action = self._compile_action(raw.get("action"), index)
        if action is None:
            return None

        return _CompiledRule(conditions=conditions, action=action, source_index=index)

    def _compile_conditions(
        self, raw: Dict[str, Any], index: int
    ) -> Optional[List[_CompiledCondition]]:
        """Compila condição única ou lista de condições (AND lógico)."""
        # Formato 1: "condition": {...}
        single = raw.get("condition")
        # Formato 2: "conditions": [{...}, {...}]
        multiple = raw.get("conditions")

        raw_conditions: List[Dict[str, Any]] = []

        if single and isinstance(single, dict):
            raw_conditions = [single]
        elif multiple and isinstance(multiple, list):
            raw_conditions = [c for c in multiple if isinstance(c, dict)]

        if not raw_conditions:
            self._warn(index, "nenhuma condição válida encontrada (precisa de 'condition' ou 'conditions')")
            return None

        compiled: List[_CompiledCondition] = []
        for cond_raw in raw_conditions:
            result = self._compile_single_condition(cond_raw, index)
            if result is None:
                return None  # Se qualquer condição for inválida, rejeita a regra inteira
            compiled.append(result)

        return compiled

    def _compile_single_condition(
        self, cond: Dict[str, Any], index: int
    ) -> Optional[_CompiledCondition]:
        """Compila uma única condição."""
        field = cond.get("field")
        op_str = cond.get("op")
        value = cond.get("value")

        if not isinstance(field, str) or not field:
            self._warn(index, f"campo 'field' inválido: {field!r}")
            return None

        if op_str not in _SAFE_OPERATORS:
            self._warn(index, f"operador '{op_str}' não suportado. Válidos: {list(_SAFE_OPERATORS.keys())}")
            return None

        if value is None:
            self._warn(index, f"'value' é None na condição do campo '{field}'")
            return None

        return _CompiledCondition(
            field=field,
            op_fn=_SAFE_OPERATORS[op_str],
            op_str=op_str,
            value=value,
        )

    def _compile_action(
        self, action_raw: Any, index: int
    ) -> Optional[_CompiledAction]:
        """Compila uma ação com validação de segurança rigorosa."""
        if not isinstance(action_raw, dict):
            self._warn(index, "campo 'action' ausente ou não é dicionário")
            return None

        target = action_raw.get("target")
        action_type = action_raw.get("type")
        value = action_raw.get("value")

        # Validar target na whitelist
        if target not in _MODIFIABLE_COST_FIELDS:
            self._warn(
                index,
                f"target '{target}' não permitido. Válidos: {sorted(_MODIFIABLE_COST_FIELDS)}",
            )
            return None

        # Validar tipo de ação
        if action_type not in _VALID_ACTION_TYPES:
            self._warn(
                index,
                f"tipo de ação '{action_type}' inválido. Válidos: {sorted(_VALID_ACTION_TYPES)}",
            )
            return None

        # Validar e clampar valor
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            self._warn(index, f"valor da ação não é numérico: {value!r}")
            return None

        # Limites de segurança
        if action_type == "multiply":
            numeric_value = max(_MULTIPLY_MIN, min(_MULTIPLY_MAX, numeric_value))
        elif action_type in ("add", "subtract", "set"):
            numeric_value = max(-_ABSOLUTE_VALUE_LIMIT, min(_ABSOLUTE_VALUE_LIMIT, numeric_value))

        return _CompiledAction(target=target, action_type=action_type, value=numeric_value)

    def _warn(self, index: int, message: str) -> None:
        """Loga e armazena um aviso de compilação."""
        warning = f"Regra #{index} ignorada: {message}"
        logger.warning("[RuleEngine] %s", warning)
        self._compile_warnings.append(warning)
