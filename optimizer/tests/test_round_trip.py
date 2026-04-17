import pytest
from optimizer.src.algorithms.integrated.vcsp_solver import VCSPJointSolver
from optimizer.src.domain.models import Trip, VehicleType

def test_force_round_trip_pruning():
    # Setup: 3 Trips
    # T1: A -> B (08:00 - 09:00)
    # T2: B -> A (09:10 - 10:10) <- Viagem Casada com T1
    # T3: C -> D (09:10 - 10:10) <- Exige deadhead de B pra C
    
    t1 = Trip(id=1, line_id=101, start_time=480, end_time=540, origin_id=1, destination_id=2)
    t2 = Trip(id=2, line_id=101, start_time=550, end_time=610, origin_id=2, destination_id=1)
    t3 = Trip(id=3, line_id=102, start_time=550, end_time=610, origin_id=3, destination_id=4)
    
    # Simular deadhead B -> C = 5 min
    t1.deadhead_times[3] = 5
    
    v_type = VehicleType(id=1, name="Standard", passenger_capacity=40)
    
    # 1. Sem force_round_trip: T1 pode conectar com T2 ou T3
    solver_no_force = VCSPJointSolver(cct_params={"force_round_trip": False})
    paths_no_force = solver_no_force._generate_paths([t1, t2, t3])
    
    has_t1_t3 = any(len(p["trips"]) == 2 and p["trips"][0].id == 1 and p["trips"][1].id == 3 for p in paths_no_force)
    assert has_t1_t3 is True, "Sem force_round_trip, T1+T3 deveria ser possível."

    # 2. Com force_round_trip: T1 SÓ pode conectar com T2 (origem 2 == destino 2)
    solver_force = VCSPJointSolver(cct_params={"force_round_trip": True})
    paths_force = solver_force._generate_paths([t1, t2, t3])
    
    has_t1_t3_forced = any(len(p["trips"]) == 2 and p["trips"][0].id == 1 and p["trips"][1].id == 3 for p in paths_force)
    assert has_t1_t3_forced is False, "Com force_round_trip, T1+T3 deveria ser PODADO."
    
    has_t1_t2_forced = any(len(p["trips"]) == 2 and p["trips"][0].id == 1 and p["trips"][1].id == 2 for p in paths_force)
    assert has_t1_t2_forced is True, "Com force_round_trip, T1+T2 deve ser mantido."

if __name__ == "__main__":
    pytest.main([__file__])
