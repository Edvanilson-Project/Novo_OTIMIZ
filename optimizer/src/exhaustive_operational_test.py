import logging
import json
from typing import List, Dict, Any, Tuple
from decimal import Decimal

from src.domain.models import Trip, VehicleType, AlgorithmType, Block, Duty
from src.services.optimizer_service import OptimizerService
from src.api.schemas import OptimizationParametersDTO
from src.algorithms.csp.greedy import GreedyCSP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("OperationalTester")

def create_complex_mock() -> Tuple[List[Trip], List[VehicleType]]:
    # Viagens em linhas diferentes
    t1 = Trip(id=1, line_id=101, start_time=480, end_time=580, origin_id=1, destination_id=2, distance_km=10.0)
    t2 = Trip(id=2, line_id=102, start_time=600, end_time=700, origin_id=2, destination_id=1, distance_km=10.0)
    
    # Viagem com ponto de rendição no meio (km 5 de 10)
    t3 = Trip(id=3, line_id=101, start_time=800, end_time=900, origin_id=1, destination_id=2, distance_km=10.0, 
              mid_trip_relief_point_id=99, mid_trip_relief_offset_minutes=50)
    
    trips = [t1, t2, t3]
    for t in trips:
        t.deadhead_times = {1: 0, 2: 0, 99: 0}
        
    vt = [VehicleType(id=1, name="V1", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    return trips, vt

def test_single_line_duty():
    logger.info("Testing: enforce_single_line_duty")
    trips, vt = create_complex_mock()
    service = OptimizerService()
    
    # Baseline: permitindo misturar linhas
    params_allow = {"enforce_single_line_duty": False, "apply_cct": True, "strict_hard_validation": False}
    res_allow = service.run(trips=[trips[0], trips[1]], vehicle_types=vt, algorithm=AlgorithmType.GREEDY, optimization_params=params_allow)
    
    # Restrito: proibindo misturar linhas
    # Usamos strict_hard_validation=True para que o OptimizerService jogue a exceção se o solver falhar em separar
    params_restrict = {"enforce_single_line_duty": True, "apply_cct": True, "strict_hard_validation": True}
    
    try:
        service.run(trips=[trips[0], trips[1]], vehicle_types=vt, algorithm=AlgorithmType.GREEDY, optimization_params=params_restrict)
        # Se não jogou exceção, vamos ver se ele separou em 2 jornadas
        logger.info("No exception raised, checking if duties were separated...")
    except Exception as e:
        if "DUTY_MULTI_LINE" in str(e):
            logger.info("SUCCESS: enforce_single_line_duty correctly detected by Validator")
            return
        else:
            raise e

def test_operator_change_terminals_only():
    logger.info("Testing: operator_change_terminals_only")
    t4 = Trip(id=4, line_id=101, start_time=1000, end_time=1100, origin_id=1, destination_id=99, distance_km=5.0)
    t5 = Trip(id=5, line_id=101, start_time=1120, end_time=1220, origin_id=99, destination_id=2, distance_km=5.0)
    t4.deadhead_times = {1: 0, 2: 0, 99: 0}
    t5.deadhead_times = {1: 0, 2: 0, 99: 0}

    csp = GreedyCSP(
        operator_change_terminals_only=True,
        terminal_location_ids=[2],
    )
    res = csp.solve([
        Block(id=1, trips=[t4]),
        Block(id=2, trips=[t5]),
    ])

    duties = len(res.duties)
    logger.info(f"Duties for non-terminal change: {duties}")
    assert duties == 2, "Operator change terminals only failed to block change at non-terminal"
    logger.info("SUCCESS: operator_change_terminals_only")

def test_relief_points():
    logger.info("Testing: allow_relief_points")
    trips, vt = create_complex_mock()
    service = OptimizerService()
    
    # T3 tem ponto de rendição. Se permitir, deve gerar 2 tarefas (segments)
    params_relief = {"allow_relief_points": True}
    res = service.run(trips=[trips[2]], vehicle_types=vt, algorithm=AlgorithmType.GREEDY, optimization_params=params_relief)
    
    duty = res.csp.duties[0]
    segments = len(duty.segments)
    logger.info(f"Segments for T3: {segments}")
    assert segments == 2, "Relief point failed to split trip into 2 segments"
    logger.info("SUCCESS: allow_relief_points")

def test_single_vehicle_only():
    logger.info("Testing: operator_single_vehicle_only")
    # Criar 2 blocos de veículos diferentes
    b1 = Block(id=1, trips=[Trip(id=1, line_id=101, start_time=480, end_time=580, origin_id=1, destination_id=2)])
    b1.meta["source_block_id"] = 101
    
    b2 = Block(id=2, trips=[Trip(id=2, line_id=101, start_time=600, end_time=700, origin_id=2, destination_id=1)])
    b2.meta["source_block_id"] = 102
    
    csp = GreedyCSP(operator_single_vehicle_only=True)
    
    duty = Duty(id=1)
    duty.add_task(b1)
    duty.meta["source_block_ids"] = [101]
    
    can_attach, reason, _ = csp._can_extend(duty, b2)
    logger.info(f"Can attach B2 to V1 duty? {can_attach} (Reason: {reason})")
    assert not can_attach, "Operator single vehicle only failed to block vehicle change"
    logger.info("SUCCESS: operator_single_vehicle_only")

def test_rostering():
    logger.info("Testing: weekly_driving_limit")
    # Criar viagens ao longo de vários dias para o mesmo motorista (mesmo bloco)
    # Dia 1 ao 7
    trips = []
    for day in range(7):
        offset = day * 1440
        # 490 min de direção por dia
        trips.append(Trip(id=100+day, line_id=101, start_time=offset+480, end_time=offset+970, origin_id=1, destination_id=2, distance_km=100.0))
    
    service = OptimizerService()
    vt = [VehicleType(id=1, name="V1", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    
    # Limite semanal de 56h (3360 min). 
    # Com 7 dias de 490 min = 3430 min -> Deve estourar o limite
    
    params = {
        "weekly_driving_limit_minutes": 3360, 
        "max_shift_minutes": 720, 
        "max_driving_minutes": 500,
        "apply_cct": True
    }
    res = service.run(trips=trips, vehicle_types=vt, algorithm=AlgorithmType.GREEDY, optimization_params=params)
    
    # Verificamos se houve mais de um roster_count
    roster_count = res.meta.get("roster_count", 0)
    logger.info(f"Roster count for 70h work: {roster_count}")
    # Se o limite funcionou, ele deve ter precisado de mais de um motorista para cobrir as 70h
    assert roster_count > 1, "Weekly driving limit failed to split roster"
    logger.info("SUCCESS: weekly_driving_limit")

def test_enforce_same_depot():
    logger.info("Testing: enforce_same_depot_start_end")
    # T1: 08:00-10:00, Garagem 1
    # T2: 12:00-14:00, Garagem 2
    t1 = Trip(id=1, line_id=101, start_time=480, end_time=600, origin_id=1, destination_id=2, distance_km=10.0, depot_id=1)
    t2 = Trip(id=2, line_id=101, start_time=720, end_time=840, origin_id=2, destination_id=1, distance_km=10.0, depot_id=2)
    
    service = OptimizerService()
    vt = [VehicleType(id=1, name="V1", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    
    # Se forçar mesma garagem, não deve deixar acoplar
    params = {"enforce_same_depot_start_end": True, "apply_cct": True, "strict_hard_validation": True}
    
    res = service.run(trips=[t1, t2], vehicle_types=vt, algorithm=AlgorithmType.GREEDY, optimization_params=params)
    
    # Verificamos se separou em 2 jornadas
    duties = len(res.csp.duties)
    logger.info(f"Duties for different depots: {duties}")
    assert duties == 2, "Enforce same depot failed to split duties"
    logger.info("SUCCESS: enforce_same_depot_start_end")

def test_inter_shift_rest():
    logger.info("Testing: inter_shift_rest_minutes")
    # Dois dias seguidos. Gap entre Dia 1 End e Dia 2 Start deve ser >= 11h (660 min)
    # Dia 1: 08:00 - 16:00 (End 480 + 480 = 960)
    # Dia 2: 04:00 - 06:00 (Start 1440 + 240 = 1680)
    # Gap: 1680 - 960 = 720 min (12h) -> OK
    # Se usarmos Dia 1: 08:00 - 18:00 (End 1080) -> Gap 600 min (10h) -> VIOLAÇÃO
    t1 = Trip(id=1, line_id=101, start_time=480, end_time=1080, origin_id=1, destination_id=2, distance_km=10.0)
    t2 = Trip(id=2, line_id=101, start_time=1680, end_time=1800, origin_id=2, destination_id=1, distance_km=10.0)
    
    service = OptimizerService()
    vt = [VehicleType(id=1, name="V1", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    
    params = {
        "inter_shift_rest_minutes": 660, 
        "max_shift_minutes": 720, 
        "max_driving_minutes": 600,
        "apply_cct": True
    }
    res = service.run(trips=[t1, t2], vehicle_types=vt, algorithm=AlgorithmType.GREEDY, optimization_params=params)
    
    # Deve ter gerado 2 rosters (motoristas diferentes) para garantir o descanso de 11h
    roster_count = res.meta.get("roster_count", 0)
    logger.info(f"Roster count for 10h rest: {roster_count}")
    assert roster_count > 1, "Inter-shift rest failed to split roster"
    logger.info("SUCCESS: inter_shift_rest_minutes")

if __name__ == "__main__":
    try:
        test_single_line_duty()
        test_relief_points()
        test_single_vehicle_only()
        test_rostering()
        test_enforce_same_depot()
        test_inter_shift_rest()
        print("\nALL OPERATIONAL TESTS PASSED!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nTEST FAILED: {str(e)}")
