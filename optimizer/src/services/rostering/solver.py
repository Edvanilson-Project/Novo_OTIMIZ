import time
import logging
import pulp
from typing import List, Dict, Any, Optional, Tuple

from ...domain.models import Duty, OperatorProfile, RosteringRule, NominalAssignment, NominalRosteringSolution
from .evaluator import RosteringEvaluator
from ...core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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
        inter_shift_rest_minutes: int = 660,
        cct_params: Optional[Dict[str, Any]] = None,
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
                elapsed_ms=(time.time() - start_time) * 1000,
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

        # Restrição 3 (opcional/HARD): Operador fixo no veículo durante o turno.
        # Cada Duty pode conter múltiplos Blocks (veículos físicos distintos).
        # Quando operator_single_vehicle_only=True, garantimos que um operador
        # só pode receber duties cujos blocks sejam de UM único veículo.
        operator_single_vehicle_only = bool((cct_params or {}).get("operator_single_vehicle_only", False))
        if operator_single_vehicle_only:
            duty_vehicles: Dict[int, set] = {}
            for j, duty in enumerate(duties):
                vids = set()
                for blk in duty.tasks:
                    vid = blk.id  # block.id é proxy estável de "veículo físico"
                    if vid is not None:
                        vids.add(vid)
                duty_vehicles[j] = vids

            # Para cada operador i e cada veículo v, criamos y[i,v] binária:
            # se y[i,v]=1, operador i pode atender duties que tocam v.
            # Restrição: sum_v y[i,v] <= 1 (operador só toca 1 veículo).
            # E: para cada (i,j) com v em vehicles(j), x[i,j] <= y[i,v].
            ops_vehicles_seen: Dict[int, set] = {}
            for i, j in valid_pairs:
                ops_vehicles_seen.setdefault(i, set()).update(duty_vehicles.get(j, set()))

            y_vars: Dict[Tuple[int, int], Any] = {}
            for i, vehicles in ops_vehicles_seen.items():
                for vid in vehicles:
                    y_vars[(i, vid)] = pulp.LpVariable(f"y_op{i}_v{vid}", cat="Binary")

            for i, j in valid_pairs:
                vids = duty_vehicles.get(j, set())
                if not vids:
                    continue
                # x[i,j] <= y[i,v] para cada veículo v que duty j toca
                for vid in vids:
                    prob += x[i, j] <= y_vars[(i, vid)], f"link_x{i}_{j}_v{vid}"

            for i, vehicles in ops_vehicles_seen.items():
                if vehicles:
                    prob += pulp.lpSum(y_vars[(i, vid)] for vid in vehicles) <= 1, f"op_single_vehicle_{i}"

        # ── 3. Resolução do Modelo ──────────────────────────────────────────
        timeout_s = int((cct_params or {}).get("rostering_timeout_seconds", 120))
        logger.info(f"Resolvendo Rostering com {len(operators)} ops e {len(duties)} duties (timeout={timeout_s}s)")

        try:
            # CBC Solver (Quiet mode)
            solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=timeout_s, threads=settings.ilp_threads)
            prob.solve(solver)
        except Exception as e:
            logger.exception("Falha no solver de Rostering: %s", e)
            return NominalRosteringSolution(
                logs=[f"ERRO CRÍTICO no Solver: {str(e)}"], elapsed_ms=(time.time() - start_time) * 1000
            )

        # ── 4. Reconstrução da Solução ───────────────────────────────────────
        assignments = []
        assigned_duties = set()
        logs = []

        if prob.status == pulp.constants.LpStatusOptimal:
            for i, j in valid_pairs:
                if pulp.value(x[i, j]) > 0.5:
                    op = operators[i]
                    duty = duties[j]
                    score = affinity_matrix[(i, j)]
                    expl = explanation_matrix[(i, j)]

                    assignments.append(
                        NominalAssignment(operator_id=op.id, duty_id=duty.id, score=score, explanations=expl)
                    )
                    assigned_duties.add(j)
                    logs.append(
                        f"MATCH: {op.name} ({op.cp}) -> Jornada #{duty.id} | "
                        f"Score={score} | Motivo: {'; '.join(expl) if expl else 'Base'}"
                    )
        else:
            status_str = pulp.LpStatus[prob.status]
            logs.append(f"Solver Status Inesperado: {status_str} - Iniciando Fallback Greedy")

            # --- FALLBACK GREEDY ---
            # Ordenar valid_pairs por score descendente
            sorted_pairs = sorted(valid_pairs, key=lambda p: affinity_matrix[p], reverse=True)
            used_ops = set()
            used_duties = set()

            for i, j in sorted_pairs:
                if i not in used_ops and j not in used_duties:
                    op = operators[i]
                    duty = duties[j]
                    score = affinity_matrix[(i, j)]
                    expl = explanation_matrix[(i, j)]

                    assignments.append(
                        NominalAssignment(operator_id=op.id, duty_id=duty.id, score=score, explanations=expl)
                    )
                    assigned_duties.add(j)
                    used_ops.add(i)
                    used_duties.add(j)
                    logs.append(f"FALLBACK MATCH: {op.name} -> Jornada #{duty.id} | Score={score}")

            fallback_meta = {
                "fallback_used": True,
                "fallback_reason": status_str,
                "original_solver": "nominal_assignment_pulp",
                "fallback_solver": "greedy_priority_assignment",
                "assigned_count": len(assignments),
            }

        unassigned_duties = [d.id for j, d in enumerate(duties) if j not in assigned_duties]

        end_time = time.time()

        return NominalRosteringSolution(
            assignments=assignments,
            unassigned_duties=unassigned_duties,
            total_utility=(
                float(pulp.value(prob.objective) or 0.0) if prob.status == pulp.constants.LpStatusOptimal else 0.0
            ),
            elapsed_ms=(end_time - start_time) * 1000,
            logs=logs,
            meta=locals().get("fallback_meta", {}),
        )
