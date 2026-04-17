from typing import Any, Dict, List, Tuple
from ...domain.models import Duty, OperatorProfile, RosteringRule, RuleType

class RosteringEvaluator:
    """
    Calcula a 'Afinidade' entre um Motorista e uma Jornada (Duty)
    baseado em regras flexíveis definidas via Metadados e Tags.
    
    Data-Driven: O código não conhece as regras específicas, ele interpreta 
    o JSON de regras e os metadados do motorista.
    """
    def __init__(self, rules: List[RosteringRule]):
        self.rules = rules

    def evaluate(
        self, 
        operator: OperatorProfile, 
        duty: Duty, 
        inter_shift_rest: int = 660
    ) -> Tuple[float, List[str]]:
        """
        Retorna o score de utilidade e uma lista de explicações para o log.
        Se uma regra HARD for violada, retorna score negativo massivo (-1e9).
        """
        score = 100.0  # Base score para evitar empates puramente em 0
        explanations = []

        # ── 1. HARD CONSTRAINT: Descanso Mínimo ──────────────────────────────
        # Duty start_time é em minutos desde meia-noite do dia atual.
        # last_shift_end pode ser do dia anterior (valor negativo ou 0-1440).
        gap = duty.start_time - operator.last_shift_end
        if gap < inter_shift_rest:
            return -1e9, [f"VIOLAÇÃO HARD: Descanso insuficiente ({gap}min < {inter_shift_rest}min)"]

        # ── 2. Regras Dinâmicas (Strategy Pattern) ──────────────────────────
        for rule in self.rules:
            # Regras baseadas em TAGS no Metadata
            if rule.rule_id in operator.metadata:
                val = operator.metadata[rule.rule_id]
                
                # Se a tag for booleana ou se for um valor de pontuação direta
                match_found = False
                if val is True:
                    match_found = True
                elif isinstance(val, (int, float)) and val > 0:
                    match_found = True
                
                if match_found:
                    boost = rule.weight
                    score += boost
                    explanations.append(f"Regra Tag '{rule.rule_id}' ativa: +{boost}")

            # Regras Especializadas: Afinidade de Linha
            if rule.rule_id == "line_affinity":
                preferred_lines = operator.metadata.get("preferred_line_ids", [])
                if not isinstance(preferred_lines, list):
                    preferred_lines = []
                
                duty_lines = {t.line_id for t in duty.all_trips}
                if any(lid in preferred_lines for lid in duty_lines):
                    boost = rule.weight
                    score += boost
                    explanations.append(f"Regra Afinidade de Linha: +{boost}")

            # Regras Especializadas: Afinidade de Horário (Turno)
            if rule.rule_id == "shift_affinity":
                preferred_shifts = operator.metadata.get("preferred_shift_types", [])
                # Ex simples: duty.start_time < 720 (12:00) -> Morning
                duty_shift = "morning" if duty.start_time < 720 else "afternoon"
                if duty_shift in preferred_shifts:
                    boost = rule.weight
                    score += boost
                    explanations.append(f"Regra Afinidade de Turno ({duty_shift}): +{boost}")

        return round(score, 2), explanations
