import pytest
from unittest.mock import MagicMock, patch
from optimizer.src.algorithms.integrated.vcsp_solver import VCSPJointSolver
from optimizer.src.domain.models import Trip, VehicleType

def test_vcsp_anti_teleportation():
    """
    Testa se o solver impede a conexão de duas viagens geograficamente inviáveis.
    
    Trip 1: 08:00 - 09:00 (Nó A)
    Trip 2: 09:10 - 10:10 (Nó B)
    Gap temporal: 10 minutos.
    Tempo de deslocamento real A -> B: 30 minutos.
    
    O Solver deve perceber a inviabilidade e separar em DOIS veículos/equipes.
    """
    vt = VehicleType(id=1, name="Padrao", passenger_capacity=40, cost_per_km=1.0, cost_per_hour=10.0, fixed_cost=100.0)

    # Coordenadas irrelevantes pois vamos mockar o retorno do client
    t1 = Trip(id=1, line_id=1, start_time=480, end_time=540, origin_id=1, destination_id=2, 
              origin_latitude=-23.5, origin_longitude=-46.6, destination_latitude=-23.6, destination_longitude=-46.7)
    t2 = Trip(id=2, line_id=1, start_time=550, end_time=610, origin_id=3, destination_id=4,
              origin_latitude=-23.8, origin_longitude=-46.8, destination_latitude=-23.9, destination_longitude=-46.9)

    solver = VCSPJointSolver(
        time_budget_s=5.0,
        cct_params={"max_work_minutes": 480, "max_shift_minutes": 720, "meal_break_minutes": 60}
    )

    # Mockar o routing client para dizer que a viagem leva 30 minutos entre os pontos
    # (Enquanto o gap é de apenas 10 minutos)
    with patch.object(solver.routing, 'get_route', return_value=(20.0, 30.0)):
        result = solver.solve([t1, t2], [vt])
        
        # 1. Deve ser ótimo
        assert result.meta["solver_status"] == "Optimal"
        
        # 2. NÃO deve ter conseguido juntar no mesmo bloco (teletransporte barrado)
        # Se juntasse, teríamos 1 bloco. Como é inviável, deve ter 2 blocos.
        assert len(result.vsp.blocks) == 2, "O solver permitiu o teletransporte entre viagens geograficamente distantes!"
        
        # 3. Cada viagem deve estar em seu próprio bloco
        for block in result.vsp.blocks:
            assert len(block.trips) == 1
            
        print("Teste Anti-Teletransporte: APROVADO (Geografia urbana respeitada)")

def test_vcsp_feasible_connection_with_routing():
    """
    Cenário oposto: O roteamento diz que é viável (5 min de viagem para 10 min de gap).
    O solver deve UNIR as viagens.
    """
    vt = VehicleType(id=1, name="Padrao", passenger_capacity=40, cost_per_km=1.0, cost_per_hour=10.0, fixed_cost=100.0)

    t1 = Trip(id=1, line_id=1, start_time=480, end_time=540, origin_id=1, destination_id=2, 
              origin_latitude=-23.5, origin_longitude=-46.6, destination_latitude=-23.6, destination_longitude=-46.7)
    t2 = Trip(id=2, line_id=1, start_time=550, end_time=610, origin_id=3, destination_id=4,
              origin_latitude=-23.8, origin_longitude=-46.8, destination_latitude=-23.9, destination_longitude=-46.9)

    solver = VCSPJointSolver(
        time_budget_s=5.0,
        cct_params={"max_work_minutes": 480, "max_shift_minutes": 720, "meal_break_minutes": 60}
    )

    # Mockar routing para 5 min (viável no gap de 10 min)
    with patch.object(solver.routing, 'get_route', return_value=(2.0, 5.0)):
        result = solver.solve([t1, t2], [vt])
        
        # Deve ter unido no mesmo veículo para economizar custo fixo (100.0)
        assert len(result.vsp.blocks) == 1
        assert len(result.vsp.blocks[0].trips) == 2
        print("Teste Conexão Viável: APROVADO (Otimização com roteamento real)")
