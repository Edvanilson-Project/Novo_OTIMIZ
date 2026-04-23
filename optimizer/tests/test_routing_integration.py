import pytest
from unittest.mock import MagicMock, patch
from src.algorithms.integrated.vcsp_solver import VCSPJointSolver
from src.domain.models import Trip, VehicleType


def test_vcsp_anti_teleportation():
    """
    Testa se o solver impede a conexão de duas viagens geograficamente inviáveis.

    Trip 1: 08:00 - 09:00 (Nó A, destination_id=2)
    Trip 2: 09:10 - 10:10 (Nó B, origin_id=3)
    Gap temporal: 10 minutos.
    Tempo de deslocamento real A → B: 30 minutos (mockado via matriz).

    O Solver deve perceber a inviabilidade e separar em DOIS veículos.
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

    # Mockar MATRIZ: deadhead de dest_id=2 para origin_id=3 = 30 min (inviavel no gap de 10 min)
    mock_matrix = {(2, 3): 30.0, (2, 1): 0.0, (2, 4): 60.0}
    with patch.object(solver.routing, 'get_route_matrix', return_value=mock_matrix):
        result = solver.solve([t1, t2], [vt])

        assert result.meta["solver_status"] == "Optimal"
        assert len(result.vsp.blocks) == 2, "O solver permitiu teletransporte geograficamente inviavel!"
        for block in result.vsp.blocks:
            assert len(block.trips) == 1
        print("Teste Anti-Teletransporte: APROVADO")


def test_vcsp_feasible_connection_with_routing():
    """
    Cenario oposto: deadhead de 5 min para gap de 10 min → viavel → 1 bloco.
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

    # Mockar MATRIZ: deadhead de dest_id=2 para origin_id=3 = 5 min (viavel)
    mock_matrix = {(2, 3): 5.0, (2, 1): 0.0, (2, 4): 15.0}
    with patch.object(solver.routing, 'get_route_matrix', return_value=mock_matrix):
        result = solver.solve([t1, t2], [vt])

        assert len(result.vsp.blocks) == 1
        assert len(result.vsp.blocks[0].trips) == 2
        print("Teste Conexao Viavel: APROVADO (Otimizacao com roteamento real)")
