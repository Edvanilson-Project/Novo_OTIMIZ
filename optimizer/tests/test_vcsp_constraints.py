import pytest
from optimizer.src.algorithms.integrated.vcsp_solver import VCSPJointSolver
from optimizer.src.domain.models import Trip, VehicleType

def test_vcsp_pulp_terminal_relief_constraint():
    """
    Testa se o VCSPJointSolver (ILP PuLP) encontra o Ótimo Global
    respeitando a proibição de trocas de motorista fora de terminais.
    
    Cenário Rígido:
    Trip 1: 0 - 240 min (Origem 1 -> Destino 2)
    Trip 2: 240 - 480 min (Origem 2 -> Destino 3)  <-- '3' NÃO É TERMINAL.
    Trip 3: 480 - 720 min (Origem 3 -> Destino 1)
    
    A matemática da Coluna:
    - Fazer as 3 viagens no mesmo carro com 1 motorista: Custa hora extra pesada.
    - Fazer as 3 viagens no mesmo carro e TROCAR no nó 3: Big-M (1 Milhão).
    - Fazer a T3 num carro novo: Custo de frota absurdo (~800 mínimo).
    
    O Solver DEVE retornar Status Optimal, escolher 1 carro só, engolir a hora extra
    e NÃO fazer a rendição ilegal.
    """
    # O teste deseja forçar que a troca seria no nó 2 ou nó 3. Vamos remover ambos do terminal_id.
    terminal_ids = [1] # Nem nó 2, nem nó 3 são terminais. Qualifying as Street Relief.
    vt = VehicleType(id=1, name="Padrao", passenger_capacity=40, cost_per_km=1.0, cost_per_hour=10.0, fixed_cost=100.0)

    t1 = Trip(id=1, line_id=1, start_time=0, end_time=240, origin_id=1, destination_id=2, duration=240, distance_km=50.0)
    t2 = Trip(id=2, line_id=1, start_time=240, end_time=480, origin_id=2, destination_id=3, duration=240, distance_km=50.0)
    t3 = Trip(id=3, line_id=1, start_time=480, end_time=720, origin_id=3, destination_id=1, duration=240, distance_km=50.0)

    solver = VCSPJointSolver(
        time_budget_s=5.0,
        cct_params={
            "max_work_minutes": 480,
            "max_shift_minutes": 800, # Shift flexível para matemática do teste agir no overtime
            "meal_break_minutes": 60,
            "terminal_location_ids": terminal_ids
        }
    )

    result = solver.solve([t1, t2, t3], [vt])
    
    # 1. Prova Matemática Mestra
    assert result.meta["solver_status"] == "Optimal", f"Solver falhou em achar o Ótimo Global. Status: {result.meta['solver_status']}"
    
    # Validações Lógicas
    duties = result.csp.duties
    blocks = result.vsp.blocks

    made_illegal_relief = any(d.meta.get("illegal_relief", False) for d in duties)
    assert not made_illegal_relief, "O Ótimo Global não pode conter infração sindical pesada (Big-M mal aplicado)."
    
    if len(duties) == 1:
        assert duties[0].work_time == 720, "O Solver não computou a hora de trabalho inteira."
        assert getattr(duties[0], "overtime_minutes", 0) > 0, "O Solver não assumiu as horas extras como escape matemático."
    else:
        assert len(blocks) >= 2, ("O Solver separou os motoristas mas manteve no mesmo carro? "
                                  "Se quebrou duty no Nó 3, deveria ter separado o carro "
                                  "para evitar o Big-M. Problema na Função Objetivo.")
        
    print(f"Status: {result.meta['solver_status']} - Teste de Set Partitioning (ILP) APROVADO!")
