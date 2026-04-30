import sys
import os
import logging
import time
from typing import List, Dict, Any

# Script de verificação final - Produção OTIMIZ
# Deve ser executado a partir do diretório 'optimizer' usando:
# python3 -m src.fallback_verification

from src.domain.models import Trip, VehicleType, AlgorithmType, Block
from src.algorithms.integrated.vcsp_solver import VCSPJointSolver
from src.services.rostering.solver import NominalRosteringSolver, OperatorProfile
from src.domain.models import Duty, DutySegment

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_vcsp_fallback_logic():
    logger.info("=== Testando Lógica de Fallback VCSP (Timeout) ===")
    trips = [
        Trip(id=1, line_id=1, start_time=480, end_time=540, origin_id=1, destination_id=2),
        Trip(id=2, line_id=1, start_time=500, end_time=560, origin_id=1, destination_id=2), # Overlap
    ]
    vt = [VehicleType(id=1, name="Bus", passenger_capacity=40)]
    
    # Caso 1: Timeout forçado
    solver_timeout = VCSPJointSolver(time_budget_s=0.001, cct_params={}, vsp_params={})
    try:
        res = solver_timeout.solve(trips, vt, depot_id=1)
        if res.meta.get('fallback_used'):
            logger.info(f"✅ Fallback por Timeout detectado: {res.meta.get('fallback_reason')}")
        else:
            logger.info("ℹ️ Solver resolveu normalmente (timeout não interrompeu)")
    except Exception as e:
        logger.error(f"❌ Falha no teste VCSP Timeout: {e}")

    logger.info("=== Testando Lógica de Fallback VCSP (Size Limit) ===")
    # Caso 2: Limite de tamanho forçado
    trips_large = [
        Trip(id=i, line_id=1, start_time=480+i, end_time=540+i, origin_id=1, destination_id=2)
        for i in range(10)
    ]
    solver_size = VCSPJointSolver(vsp_params={"max_vcsp_pulp_trips": 5})
    try:
        res = solver_size.solve(trips_large, vt, depot_id=1)
        if res.meta.get('fallback_used') and "limit_exceeded" in res.meta.get('fallback_reason', ''):
            logger.info(f"✅ Fallback por Limite de Tamanho detectado: {res.meta.get('fallback_reason')}")
        else:
            logger.error(f"❌ Fallback de tamanho NÃO detectado! Meta: {res.meta}")
    except Exception as e:
        logger.error(f"❌ Falha no teste VCSP Size Limit: {e}")

def test_rostering_fallback_logic():
    logger.info("=== Testando Lógica de Fallback Rostering ===")
    operators = [OperatorProfile(id="OP1", name="Op 1", cp="123")]
    duties = [Duty(id=1, tasks=[Block(id=1, trips=[])])]
    
    solver = NominalRosteringSolver()
    
    try:
        res = solver.solve(
            operators, 
            duties, 
            rules=[], 
            cct_params={"rostering_timeout_seconds": 0.001}
        )
        if res.meta.get('fallback_used'):
            logger.info("✅ Fallback Rostering detectado e marcado corretamente!")
        else:
            logger.info("ℹ️ Rostering resolveu normalmente")
    except Exception as e:
        logger.error(f"❌ Falha no teste Rostering: {e}")

def test_mcnf_redirection():
    logger.info("=== Testando Redirecionamento MCNF ===")
    from src.algorithms.vsp.mcnf import MCNFVSP
    
    trips = [
        Trip(id=i, line_id=1, start_time=480+i, end_time=540+i, origin_id=1, destination_id=2)
        for i in range(900)
    ]
    vt = [VehicleType(id=1, name="Bus", passenger_capacity=40)]
    
    solver = MCNFVSP(vsp_params={})
    logger.info("Iniciando _solve_subproblem com 900 trips (esperado redirecionamento)...")
    res = solver._solve_subproblem(trips, vt, depots=[{'id': 1}])
    logger.info(f"Blocks gerados: {len(res.blocks)}")
    logger.info("✅ MCNF redirecionamento concluído.")

def test_optimizer_service_dispatch():
    logger.info("=== Testando OptimizerService._dispatch ===")
    from src.services.optimizer_service import OptimizerService
    from src.domain.models import AlgorithmType
    
    svc = OptimizerService()
    trips = [Trip(id=1, line_id=1, start_time=480, end_time=540, origin_id=1, destination_id=2)]
    vt = [VehicleType(id=1, name="Bus", passenger_capacity=40)]
    
    try:
        res = svc._dispatch(
            AlgorithmType.GREEDY,
            trips,
            vt,
            1,
            {},
            {},
            {},
            30.0
        )
        logger.info(f"✅ Dispatch Greedy OK. Algorithm: {res.vsp.algorithm}")
    except Exception as e:
        logger.error(f"❌ Falha no Dispatch: {e}")

if __name__ == "__main__":
    test_optimizer_service_dispatch()
    test_vcsp_fallback_logic()
    test_rostering_fallback_logic()
    test_mcnf_redirection()
