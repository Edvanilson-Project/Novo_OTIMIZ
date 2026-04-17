import sys
import os
import unittest
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.domain.models import Block, Trip
from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.algorithms.evaluator import CostEvaluator

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

class TestFretamentoDoisTurnos(unittest.TestCase):
    def test_fretamento_dois_turnos(self):
        """
        No Fretamento de fábrica típico, o motorista vai das 05h00 às 08h00, 
        fica parado até as 16h00 e volta das 16h00 às 19h00.
        Total de Spread = 14 horas. O algoritmo Híbrido deve empacotar as duas viagens em 1 Jornada!
        """
        # Criando o cenário
        blocks = []
        
        # Turno Manhã (Puxada Fábrica)
        trip1 = Trip(id=1, line_id=100, start_time=300, end_time=480, duration=180, origin_id=1, destination_id=2, distance_km=80.0)
        block1 = Block(id=1, trips=[trip1])
        blocks.append(block1)
        
        # Turno Tarde (Retorno Fábrica)
        trip2 = Trip(id=2, line_id=100, start_time=960, end_time=1140, duration=180, origin_id=2, destination_id=1, distance_km=80.0)
        block2 = Block(id=2, trips=[trip2])
        blocks.append(block2)

        # Regras CCT configuradas para Fretamento
        solver = SetPartitioningOptimizedCSP(
            time_budget_s=30,
            vsp_params={
                "pricing_enabled": True
            },
            max_shift_minutes=900,             # 15h de limite máx de spread total
            legal_max_shift_minutes=900,       # sobrescreve o legal de 12h para fretamento
            max_work_minutes=480,              # 8h de limite normal sem hora extra
            max_unpaid_break_minutes=600,      # Pode ter quebra de até 10 horas
            waiting_time_pay_pct=0.30,         # Lei do Motorista: 30% em hora de espera
            allow_relief_points=True,
            operator_change_terminals_only=False, # Relaxar esta regra para permitir embolo na fábrica
            idle_time_is_paid=True
        )
        solution = solver.solve(blocks)
        
        logging.info("--- Extension Diagnostics ---")
        logging.info(solver.greedy._extension_diagnostics_snapshot())
        
        self.assertIsNotNone(solution)
        self.assertEqual(len(solution.duties), 1, "O solver deveria ter empacotado as 2 viagens em UMA ÚNICA jornada de 2 turnos.")
        
        duty = solution.duties[0]
        self.assertEqual(duty.work_time, 360, "O tempo efetivo de direção é 6h (2x 3h).")
        self.assertEqual(duty.spread_time, 860, "O spread da ponta inicial à ponta final é de 14h20m (04h50 às 19h10).")
        
        evaluator = CostEvaluator(
            crew_cost_per_hour=20.0,
            overtime_extra_pct=0.5
        )
        costs = evaluator.csp_cost_breakdown(solution)
        
        self.assertGreaterEqual(costs['total'], 0)
        logging.info("================ FRETAMENTO DOIS TURNOS ================")
        logging.info(f"Custo de Trabalho: {costs['work_cost']}")
        logging.info(f"Horas Extras: {costs['overtime_cost']}")
        logging.info(f"Custo de Espera (30% sobre tempo morto): {costs['waiting_cost']}")
        logging.info(f"Custo Total CSP da Frota Fretada: {costs['total']}")
        logging.info("Validado com Sucesso: O CSP Híbrido permitiu Empacotamento de Split-Shift! 1 Motorista alocado ao invés de 2!")

if __name__ == '__main__':
    unittest.main()
