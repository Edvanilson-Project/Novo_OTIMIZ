import sys
import os

# Append the project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from optimizer.src.services.optimizer_service import OptimizerService
from optimizer.src.domain.models import AlgorithmType, Trip, VehicleType

trips = [
    Trip(
        id=1, line_id=1, start_time=0, end_time=30, 
        origin_id=1, destination_id=2, duration=30, distance_km=10
    ),
    Trip(
        id=2, line_id=1, start_time=31, end_time=60, 
        origin_id=2, destination_id=1, duration=30, distance_km=10
    )
]
vehicle_types = [VehicleType(id=1, name="Bus", passenger_capacity=40, fixed_cost=100.0)]

res = OptimizerService().run(
    trips=trips,
    vehicle_types=vehicle_types,
    algorithm=AlgorithmType.GREEDY,
    cct_params={"apply_cct": True, "enforce_min_interval": True, "min_break_minutes": 5, "connection_tolerance_minutes": 10},
    vsp_params={"min_layover_minutes": 0, "fixed_vehicle_activation_cost": 100.0},
    optimization_params={}
)
print("With tolerance=10:", [len(b.trips) for b in res.vsp.blocks])

res2 = OptimizerService().run(
    trips=trips,
    vehicle_types=vehicle_types,
    algorithm=AlgorithmType.GREEDY,
    cct_params={"apply_cct": True, "enforce_min_interval": True, "min_break_minutes": 5, "connection_tolerance_minutes": 0},
    vsp_params={"min_layover_minutes": 0, "fixed_vehicle_activation_cost": 100.0},
    optimization_params={}
)
print("With tolerance=0:", [len(b.trips) for b in res2.vsp.blocks])
