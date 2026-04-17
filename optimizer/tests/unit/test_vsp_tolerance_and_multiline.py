"""
Auditoria: connection_tolerance_minutes e allowMultiLineBlock nos algoritmos VSP.

Cobre GreedyVSP, MCNFVSP e _try_merge_vsp_blocks (joint_opt).
Grupo 2 do PLANO_COPILOT_WEB_OPT.md — Regras Operacionais de Grafo.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.domain.models import Trip, Block, VSPSolution
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.mcnf import MCNFVSP
from src.algorithms.joint_opt import _try_merge_vsp_blocks


# ─── Helpers ─────────────────────────────────────────────

def make_trip(id: int, start: int, end: int, origin: int, dest: int, line_id=16, deadhead_to_dest=10):
    """Cria uma Trip mínima para testes de grafo VSP."""
    return Trip(
        id=id,
        line_id=line_id,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        deadhead_times={dest: deadhead_to_dest},
    )


def make_block(id: int, trips: list) -> Block:
    b = Block(id=id, trips=trips)
    return b


def make_vsp_solution(blocks: list) -> VSPSolution:
    return VSPSolution(blocks=blocks, unassigned_trips=[])


# ─── GreedyVSP ─────────────────────────────────────────

class TestGreedyVSPConnectionTolerance:
    def test_no_tolerance_blocks_tight_gap(self):
        """Sem tolerância: gap < deadhead → nova viagem NÃO deve ser encadeada."""
        # T1: 0→60, destino=2 (deadhead=15). T2: começa em 70. gap=10 < need=15 → novo bloco
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=15)
        t2 = make_trip(2, 70, 130, 2, 1, deadhead_to_dest=15)
        solver = GreedyVSP(vsp_params={"min_layover_minutes": 5, "connection_tolerance_minutes": 0})
        sol = solver.solve([t1, t2], [])
        # Com gap=10 < deadhead=15, devem ser blocos separados
        assert len(sol.blocks) == 2, f"Esperado 2 blocos separados, obteve {len(sol.blocks)}"

    def test_tolerance_allows_tight_connection(self):
        """Com tolerância: gap + tolerance >= deadhead → deve encadear no mesmo bloco."""
        # T1: 0→60, destino=2 (deadhead=15). T2: começa em 70. gap=10, tolerance=5 → 10+5=15 >= 15 ✅
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=15)
        t2 = make_trip(2, 70, 130, 2, 1, deadhead_to_dest=15)
        solver = GreedyVSP(vsp_params={"min_layover_minutes": 5, "connection_tolerance_minutes": 5})
        sol = solver.solve([t1, t2], [])
        assert len(sol.blocks) == 1, f"Esperado 1 bloco (tolerância satisfeita), obteve {len(sol.blocks)}"

    def test_tolerance_insufficient_still_separates(self):
        """Tolerância insuficiente: gap + tolerance < deadhead → ainda separa."""
        # gap=8, tolerance=3, deadhead=15 → 8+3=11 < 15 → deve separar
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=15)
        t2 = make_trip(2, 68, 128, 2, 1, deadhead_to_dest=15)
        solver = GreedyVSP(vsp_params={"min_layover_minutes": 5, "connection_tolerance_minutes": 3})
        sol = solver.solve([t1, t2], [])
        assert len(sol.blocks) == 2

    def test_allow_multi_line_false_prevents_cross_line(self):
        """allowMultiLineBlock=False: veículo NÃO pode mudar de linha."""
        t1 = make_trip(1, 0, 60, 1, 2, line_id=10, deadhead_to_dest=5)
        t2 = make_trip(2, 70, 130, 2, 1, line_id=20, deadhead_to_dest=5)
        solver = GreedyVSP(vsp_params={"min_layover_minutes": 5, "allow_multi_line_block": False})
        sol = solver.solve([t1, t2], [])
        # Linhas diferentes com multi_line=False → devem ficar em blocos separados
        assert len(sol.blocks) == 2

    def test_allow_multi_line_true_allows_cross_line(self):
        """allowMultiLineBlock=True (default): veículo PODE mudar de linha."""
        t1 = make_trip(1, 0, 60, 1, 2, line_id=10, deadhead_to_dest=5)
        t2 = make_trip(2, 70, 130, 2, 1, line_id=20, deadhead_to_dest=5)
        solver = GreedyVSP(vsp_params={"min_layover_minutes": 5, "allow_multi_line_block": True})
        sol = solver.solve([t1, t2], [])
        # Com multi_line=True e gap suficiente → encadeia
        assert len(sol.blocks) == 1

    def test_all_trips_covered(self):
        """Nenhuma viagem deve ser perdida — total de trips nos blocos = input."""
        trips = [
            make_trip(1, 360, 420, 1, 2, deadhead_to_dest=10),
            make_trip(2, 435, 495, 2, 1, deadhead_to_dest=10),
            make_trip(3, 510, 570, 1, 2, deadhead_to_dest=10),
        ]
        solver = GreedyVSP(vsp_params={"min_layover_minutes": 5})
        sol = solver.solve(trips, [])
        total_assigned = sum(len(b.trips) for b in sol.blocks) + len(sol.unassigned_trips)
        assert total_assigned == len(trips), "Viagens não cobertas detectadas"


# ─── MCNFVSP ─────────────────────────────────────────────

class TestMCNFVSPConnectionTolerance:
    def test_tolerance_enables_merge_in_cost_matrix(self):
        """MCNF deve criar conexão quando gap + tolerance >= deadhead."""
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=15)
        t2 = make_trip(2, 70, 130, 2, 1, deadhead_to_dest=15)
        solver_no_tol = MCNFVSP(vsp_params={"min_layover_minutes": 5, "connection_tolerance_minutes": 0})
        solver_with_tol = MCNFVSP(vsp_params={"min_layover_minutes": 5, "connection_tolerance_minutes": 5})
        sol_no = solver_no_tol.solve([t1, t2], [])
        sol_yes = solver_with_tol.solve([t1, t2], [])
        # Com tolerância, deve usar menos veículos
        assert len(sol_yes.blocks) <= len(sol_no.blocks)

    def test_no_unassigned_trips_basic(self):
        """MCNF não deve deixar viagens sem cobertura em cenário simples."""
        trips = [
            make_trip(1, 360, 420, 1, 2, deadhead_to_dest=8),
            make_trip(2, 432, 492, 2, 1, deadhead_to_dest=8),
        ]
        solver = MCNFVSP(vsp_params={"min_layover_minutes": 5})
        sol = solver.solve(trips, [])
        assert len(sol.unassigned_trips) == 0


# ─── _try_merge_vsp_blocks (joint_opt) ───────────────────

class TestMergeVSPBlocksConnectionTolerance:
    """
    Bug corrigido: _try_merge_vsp_blocks ignorava connection_tolerance_minutes.
    Antes: gap < needed → não fundia, mesmo com tolerância.
    Depois: gap + tolerance >= needed → funde corretamente.
    """

    def _make_vsp_with_two_blocks(self, gap: int) -> VSPSolution:
        """Cria uma VSPSolution com 2 blocos separados pelo gap especificado."""
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=15)
        t2 = make_trip(2, 60 + gap, 120 + gap, 2, 1, deadhead_to_dest=5)
        b1 = make_block(1, [t1])
        b2 = make_block(2, [t2])
        return make_vsp_solution([b1, b2])

    def test_merge_without_tolerance_gap_too_small(self):
        """gap=10 < needed=15 → sem tolerância NÃO deve fundir."""
        sol = self._make_vsp_with_two_blocks(gap=10)
        params = {"min_layover_minutes": 5, "connection_tolerance_minutes": 0}
        result = _try_merge_vsp_blocks(sol, params)
        assert len(result.blocks) == 2, "Não deveria fundir sem tolerância suficiente"

    def test_merge_with_tolerance_sufficient(self):
        """gap=10, tolerance=5 → 10+5=15 >= 15 needed → DEVE fundir."""
        sol = self._make_vsp_with_two_blocks(gap=10)
        params = {"min_layover_minutes": 5, "connection_tolerance_minutes": 5}
        result = _try_merge_vsp_blocks(sol, params)
        assert len(result.blocks) == 1, "Deveria fundir com connection_tolerance=5"
        assert len(result.blocks[0].trips) == 2

    def test_merge_multi_line_prevented_when_false(self):
        """allow_multi_line_block=False NÃO deve fundir blocos de linhas diferentes."""
        t1 = make_trip(1, 0, 60, 1, 2, line_id=10, deadhead_to_dest=5)
        t2 = make_trip(2, 70, 130, 2, 1, line_id=20, deadhead_to_dest=5)
        b1 = make_block(1, [t1])
        b2 = make_block(2, [t2])
        sol = make_vsp_solution([b1, b2])
        params = {"min_layover_minutes": 5, "allow_multi_line_block": False}
        result = _try_merge_vsp_blocks(sol, params)
        assert len(result.blocks) == 2

    def test_merge_multi_line_allowed_when_true(self):
        """allow_multi_line_block=True COM gap suficiente → funde mesmo com linhas diferentes."""
        t1 = make_trip(1, 0, 60, 1, 2, line_id=10, deadhead_to_dest=5)
        t2 = make_trip(2, 70, 130, 2, 1, line_id=20, deadhead_to_dest=5)
        b1 = make_block(1, [t1])
        b2 = make_block(2, [t2])
        sol = make_vsp_solution([b1, b2])
        params = {"min_layover_minutes": 5, "allow_multi_line_block": True}
        result = _try_merge_vsp_blocks(sol, params)
        assert len(result.blocks) == 1

    def test_merge_preserves_chronological_order(self):
        """Após merge, as viagens no bloco devem estar em ordem cronológica."""
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=5)
        t2 = make_trip(2, 70, 130, 2, 1, deadhead_to_dest=5)
        b1 = make_block(1, [t1])
        b2 = make_block(2, [t2])
        sol = make_vsp_solution([b1, b2])
        params = {"min_layover_minutes": 5, "allow_multi_line_block": True}
        result = _try_merge_vsp_blocks(sol, params)
        if len(result.blocks) == 1:
            merged_trips = result.blocks[0].trips
            for i in range(len(merged_trips) - 1):
                assert merged_trips[i].start_time <= merged_trips[i + 1].start_time

    def test_no_merge_when_shift_exceeded(self):
        """Não deve fundir se a duração total exceder max_vehicle_shift."""
        t1 = make_trip(1, 0, 60, 1, 2, deadhead_to_dest=5)
        t2 = make_trip(2, 70, 500, 2, 1, deadhead_to_dest=5)
        b1 = make_block(1, [t1])
        b2 = make_block(2, [t2])
        sol = make_vsp_solution([b1, b2])
        # max_vehicle_shift=400 mas b1.start=0, b2.end=500 → total=500 > 400
        params = {"min_layover_minutes": 5, "max_vehicle_shift_minutes": 400}
        result = _try_merge_vsp_blocks(sol, params)
        assert len(result.blocks) == 2
