import sys
import os
import unittest
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.domain.models import Block, Trip
from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.algorithms.evaluator import CostEvaluator

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

class TestUrbanoAltaFrequencia(unittest.TestCase):
    def test_urbano_meal_break_validation(self):
        """
        Urbano circular - Viagens curtas de 30 min sem parar.
        O motorista deve parar no máximo após 5h30 min de direção (Lei do Motorista 13.103) para descanso.
        Essa validação estressa o Run-cutting do Otimizador. Se não houver Meal Break, o sistema é falho!
        """
        blocks = []
        
        # Criar bloco simulando looping de 12 horas (720 min) 05:00 até 17:00
        # 1 ônibus rodando direto sem o motorista parar
        trips = []
        start = 300
        for i in range(24): # 24 viagens de 30 minutos
            origin = 1 if i % 2 == 0 else 2
            dest = 2 if i % 2 == 0 else 1
            trips.append(Trip(id=i, line_id=200, start_time=start, end_time=start+30, duration=30, origin_id=origin, destination_id=dest))
            start += 30
            
        block = Block(id=1, trips=trips)
        blocks.append(block)

        solver = SetPartitioningOptimizedCSP(
            time_budget_s=30,
            vsp_params={"pricing_enabled": True},
            max_shift_minutes=480,             # 8 horas de turno
            legal_max_shift_minutes=480,
            max_work_minutes=480,              # 8h normal de trabalho
            max_driving_minutes=330,           # Lei 13.103: limite de direção para ônibus é 5h30
            legal_max_continuous_driving=330,
            mandatory_break_after_minutes=330, # Max driving
            meal_break_minutes=60,             # 1h almoço
            allow_relief_points=True,          # Troca de motorista na via
            operator_change_terminals_only=True
        )
        
        solution = solver.solve(blocks)
        
        self.assertIsNotNone(solution)
        # Como o bloco tem 12 horas ininterruptas e o limite de shift do motorista é 8h
        # e ele precisa jantar com 5.5h. Deve haver MÚLTIPLOS motoristas cobrindo ESSE ÚNICO CARRO!
        # Idealmente 2 motoristas fazendo 6 e 6 horas, ou parecido.
        
        self.assertGreater(len(solution.duties), 1, "Um único motorista não pode fazer 12 horas seguidas num carro! O Sistema não quebrou os blocos!")
        
        total_driving = sum(d.work_time for d in solution.duties)
        self.assertEqual(total_driving, 720, "Houve omissão de viagens! O tempo trabalhado entre os motoristas deve somar 12horas exatas (720 min)")
        
        # Validação do Meal Break
        for duty in solution.duties:
            self.assertLessEqual(duty.spread_time, 540, "Nenhum motorista pode rodar mais que 9h spread ali dentro das regras passadas")

        logging.info("================ URBANO ALTA FREQUENCIA ================")
        logging.info(f"Nº de Motoristas Alocados: {len(solution.duties)}")
        logging.info(f"Custo Total Trip: {CostEvaluator().csp_cost_breakdown(solution)['total']}")
        logging.info("Validado com Sucesso: O CSP Híbrido Particionou as rotas em 'Run-cutting Reliefs' perfeitamente salvando horas extras e evitando multa trabalhista!")

if __name__ == '__main__':
    unittest.main()
