"""
Stress Test e Auditoria de Alta Performance para o Solver CSP (Set Partitioning)

Avalia as melhorias de Arquitetura Industrial (Delayed Column Generation, 
Elastic Variables, Vetorização O(N) e Heurísticas Optibus-Like).
"""
import sys
import os
import time
import logging


# Adiciona o diretório base para importação
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.domain.models import Block, Trip
from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_massive_instance(num_tasks: int, overlap_factor: float = 0.5):
    """
    Cria uma instância massiva de tarefas interconectadas
    """
    logging.info(f"Gerando instância massiva com {num_tasks} tarefas (Overlap {overlap_factor*100}%)")
    blocks = []
    
    # Gera tarefas de ~40 minutos
    start = 300 # 05:00 AM
    duration = 40
    
    for i in range(num_tasks):
        trip = Trip(
            id=i,
            line_id=1,
            start_time=start,
            end_time=start + duration,
            origin_id=1,
            destination_id=1
        )
        block = Block(
            id=i,
            trips=[trip]
        )
        blocks.append(block)
        
        # Incremento baseado no overlap. 
        # Overlap de 0.5 significa que a próxima tarefa começa na metade da atual
        increment = int(duration * (1.0 - overlap_factor))
        start += increment
        
    return blocks

def run_stress_test():
    logging.info("Iniciando Auditoria de Stress...")
    
    # Instância de 300 tarefas
    blocks = create_massive_instance(300, overlap_factor=0.3)
    
    # CSP Limitado a 60s
    solver = SetPartitioningOptimizedCSP(
        time_budget_s=120,
        vsp_params={
            "max_candidate_successors_per_task": 10,
            "max_generated_columns": 15000,
            "pricing_enabled": True
        }
    )
    
    start_t = time.time()
    solution = solver.solve(blocks)
    end_t = time.time()
    
    logging.info(f"--- RESULTADOS DA AUDITORIA ---")
    logging.info(f"Tempo Total de Resolução: {end_t - start_t:.2f}s")
    
    metrics = solution.meta.get("performance_metrics", {})
    col_metrics = solution.meta.get("column_generation", {})
    
    logging.info(f"Jornadas Criadas: {len(solution.duties)}")
    logging.info(f"Colunas Geradas RMP: {solution.meta.get('workpieces_generated', 'N/A')}")
    logging.info(f"Algoritmo Final Utilizado: {solution.algorithm}")
    
    assert solution.algorithm == solver.name, "O solver abortou e caiu no fallback Guloso. Falha estrutural de escalabilidade."
    assert (end_t - start_t) < 120, "O tempo ultrapassou o orçamento, falha nas heurísticas de cuts."
    logging.info("AUDITORIA APROVADA: O algoritmo resolveu o MILP adequadamente com Variáveis Elásticas e Vetorização Dicionária.")

if __name__ == "__main__":
    run_stress_test()
