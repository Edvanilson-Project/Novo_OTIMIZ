import time
import logging
import pulp
from typing import List, Dict, Any, Tuple

from ...domain.models import (
    Duty, 
    OperatorProfile, 
    RosteringRule, 
    NominalAssignment, 
    NominalRosteringSolution
)
from .evaluator import RosteringEvaluator

logger = logging.getLogger(__name__)

class NominalRosteringSolver:
    """
    Resolve o Problema de Atribuição Global (Linear Assignment Problem).
    
    Usa programação linear (PuLP) para encontrar o emparelhamento que 
    maximiza a satisfação total dos motoristas e da empresa, respeitando
    as regras mandatórias.
    """
    
    def solve(
        self, 
        operators: List[OperatorProfile], 
        duties: List[Duty], 
        rules: List[RosteringRule],
        inter_shift_rest_minutes: int = 660
    ) -> NominalRosteringSolution:
        start_time = time.time()
        evaluator = RosteringEvaluator(rules)
        
        # ── 1. Pré-Cálculo de Afinidade (Scoring Matrix) ────────────────────
        affinity_matrix = {}
        explanation_matrix = {}
        valid_pairs = []
        
        for i, op in enumerate(operators):
            for j, duty in enumerate(duties):
                score, expl = evaluator.evaluate(op, duty, inter_shift_rest_minutes)
                
                # Se o score for proibitivo (violação HARD), não criamos variável
                if score < -1e6:
                    continue
                
                affinity_matrix[(i, j)] = score
                explanation_matrix[(i, j)] = expl
                valid_pairs.append((i, j))

        if not valid_pairs:
            return NominalRosteringSolution(
                logs=["AVISO: Nenhum emparelhamento válido encontrado (violações generalizadas de descanso?)."],
                elapsed_ms=(time.time() - start_time) * 1000
            )

        # ── 2. Formulação PuLP ──────────────────────────────────────────────
        prob = pulp.LpProblem("Nominal_Rostering_Assignment", pulp.LpMaximize)
        
        # x_i_j = 1 se motorista i faz jornada j
        x = pulp.LpVariable.dicts("x", valid_pairs, cat="Binary")
        
        # Objetivo: Max Utility
        prob += pulp.lpSum(x[i, j] * affinity_matrix[(i, j)] for (i, j) in valid_pairs)
        
        # Restrição 1: Cada jornada deve ter exatamente 1 motorista (se possível)
        # Usamos <= 1 para permitir que jornadas fiquem desatribuidas se faltar pessoal
        for j in range(len(duties)):
            possible_ops = [x[i_p, j_p] for (i_p, j_p) in valid_pairs if j_p == j]
            if possible_ops:
                prob += pulp.lpSum(possible_ops) <= 1, f"duty_cover_{j}"

        # Restrição 2: Cada motorista pode assumir no máximo 1 jornada
        for i in range(len(operators)):
            possible_duties = [x[i_p, j_p] for (i_p, j_p) in valid_pairs if i_p == i]
            if possible_duties:
                prob += pulp.lpSum(possible_duties) <= 1, f"operator_capacity_{i}"

        # ── 3. Resolução ────────────────────────────────────────────────────
        try:
            # CBC Solver (Quiet mode)
            solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=20)
            prob.solve(solver)
        except Exception as e:
            logger.exception("Falha no solver de Rostering: %s", e)
            return NominalRosteringSolution(
                logs=[f"ERRO CRÍTICO no Solver: {str(e)}"],
                elapsed_ms=(time.time() - start_time) * 1000
            )

        # ── 4. Reconstrução da Solução ───────────────────────────────────────
        assignments = []
        assigned_duties = set()
        logs = []
        
        if prob.status == pulp.constants.LpStatusOptimal:
            for (i, j) in valid_pairs:
                if pulp.value(x[i, j]) > 0.5:
                    op = operators[i]
                    duty = duties[j]
                    score = affinity_matrix[(i, j)]
                    expl = explanation_matrix[(i, j)]
                    
                    assignments.append(NominalAssignment(
                        operator_id=op.id,
                        duty_id=duty.id,
                        score=score,
                        explanations=expl
                    ))
                    assigned_duties.add(j)
                    logs.append(
                        f"MATCH: {op.name} ({op.cp}) -> Jornada #{duty.id} | "
                        f"Score={score} | Motivo: {'; '.join(expl) if expl else 'Base'}"
                    )
        else:
            logs.append(f"Solver Status Inesperado: {pulp.LpStatus[prob.status]}")

        unassigned_duties = [d.id for j, d in enumerate(duties) if j not in assigned_duties]
        
        end_time = time.time()
        
        return NominalRosteringSolution(
            assignments=assignments,
            unassigned_duties=unassigned_duties,
            total_utility=float(pulp.value(prob.objective) or 0.0) if prob.status == pulp.constants.LpStatusOptimal else 0.0,
            elapsed_ms=(end_time - start_time) * 1000,
            logs=logs
        )
