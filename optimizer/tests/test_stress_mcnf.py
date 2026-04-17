import pytest
import time
import logging
from typing import List

from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.mcnf import MCNFVSP
from src.domain.models import Block, Trip, VehicleType

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def generate_chaotic_trips(num_trips: int = 600) -> List[Trip]:
    trips = []
    # Cria uma malha hiper-conectada, intercalando terminals curtos
    start_time = 300  # 05:00
    for i in range(num_trips):
        direction = i % 2
        origin_id = 1 if direction == 0 else 2
        destination_id = 2 if direction == 0 else 1
        
        # Deadhead time default = 15. Mas para interconectar terminais = 20
        deadheads = {
            1: 0 if destination_id == 1 else 20,
            2: 0 if destination_id == 2 else 20
        }
        
        trips.append(Trip(
            id=i,
            line_id=1,
            start_time=start_time,
            end_time=start_time + 40,
            origin_id=origin_id,
            destination_id=destination_id,
            deadhead_times=deadheads
        ))
        
        start_time += 7  # Viagens partem a cada 7 minutos
        
    return trips

def test_mcnf_vs_greedy_stress_reduction():
    logger.info("Iniciando MCNF vs Greedy Benchmark...")
    trips = generate_chaotic_trips(600)
    vehicle = VehicleType(id=1, name="PadraoDiesel", passenger_capacity=80, fixed_cost=1000.0)
    
    # Executa o Greedy original
    greedy_solver = GreedyVSP(vsp_params={"min_layover_minutes": 5, "max_vehicle_shift_minutes": 960})
    t0 = time.time()
    greedy_sol = greedy_solver.solve(trips, [vehicle])
    greedy_t = time.time() - t0
    
    # Executa o Exato (MCNF)
    mcnf_solver = MCNFVSP(vsp_params={"min_layover_minutes": 5, "max_vehicle_shift_minutes": 960})
    t0 = time.time()
    mcnf_sol = mcnf_solver.solve(trips, [vehicle])
    mcnf_t = time.time() - t0
    
    logger.info("=== RESULTADOS VSP (600 Trips) ===")
    logger.info(f"Greedy: {len(greedy_sol.blocks)} veículos. Tempo: {greedy_t:.3f}s. Unassigned: {len(greedy_sol.unassigned_trips)}")
    logger.info(f"MCNF:   {len(mcnf_sol.blocks)} veículos. Tempo: {mcnf_t:.3f}s. Unassigned: {len(mcnf_sol.unassigned_trips)}")
    
    # Asserções matemáticas para Enterprise
    assert len(mcnf_sol.blocks) <= len(greedy_sol.blocks), "MCNF *tem* que achar o global ótimo igual ou inferior ao guloso."
    assert len(mcnf_sol.unassigned_trips) == 0, "MCNF deve cobrir tudo em um setting standard."
    assert mcnf_t < 15.0, "MCNF Linear Sum Assignment em 600 trips deveria resolver em <1s"

if __name__ == "__main__":
    test_mcnf_vs_greedy_stress_reduction()
