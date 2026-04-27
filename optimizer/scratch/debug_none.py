import logging
import time
from decimal import Decimal
from src.services.optimizer_service import OptimizerService
from src.api.schemas import OptimizationParametersDTO
from src.domain.models import AlgorithmType, Trip, VehicleType

logging.basicConfig(level=logging.INFO)

def create_mock_data():
    t1 = Trip(id=1, line_id=101, start_time=1380, end_time=1480, origin_id=1, destination_id=2, distance_km=25.0, trip_group_id=1001)
    t2 = Trip(id=2, line_id=101, start_time=1500, end_time=1600, origin_id=2, destination_id=1, distance_km=25.0, trip_group_id=1001)
    trips = [t1, t2]
    for t in trips: t.deadhead_times = {1: 10, 2: 10}
    vt = [VehicleType(id=1, name="Standard", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    return trips, vt

service = OptimizerService()
trips, v_types = create_mock_data()
params = {
    "cost_vehicle": 1000.0,
    "cost_duty": 500.0,
    "cost_km": 1.0,
    "nocturnal_factor": 1.0,
    "idle_time_is_paid": True,
    "waiting_time_pay_pct": 0.30,
}

print("Running baseline...")
try:
    result = service.run(
        trips=trips,
        vehicle_types=v_types,
        algorithm=AlgorithmType.GREEDY,
        optimization_params=params,
        cct_params={},
        vsp_params={}
    )
    print(f"Result total_cost: {result.total_cost}")
    print(f"Meta cost_breakdown: {result.meta.get('cost_breakdown')}")
except Exception as e:
    import traceback
    traceback.print_exc()
