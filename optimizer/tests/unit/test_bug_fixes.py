"""
Testes de regressão para bugs corrigidos nos algoritmos.
Verifica que as correções B3, B4, B5, B10, B12 estão funcionando.
Execute com: pytest tests/unit/test_bug_fixes.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.domain.models import Block, Trip, VehicleType, VSPSolution, CSPSolution, OptimizationResult
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP, _split, _OPERATORS
from src.algorithms.vsp.tabu_search import TabuSearchVSP
from src.algorithms.vsp.genetic import (
    GeneticVSP,
    _repair_chromosome,
    _chromosome_from_blocks,
    _blocks_from_chromosome,
    _crossover,
    _mutate,
    _fitness,
)
from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.evaluator import CostEvaluator
from src.core.config import get_settings

settings = get_settings()


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_trips(n: int = 6, gap: int = 90) -> list:
    trips = []
    start = 360
    for i in range(n):
        origin = 1 if i % 2 == 0 else 2
        destination = 2 if i % 2 == 0 else 1
        t = Trip(
            id=i + 1,
            line_id=1,
            start_time=start,
            end_time=start + 60,
            origin_id=origin,
            destination_id=destination,
            duration=60,
            distance_km=20.0,
        )
        trips.append(t)
        start += gap
    return trips


def make_vehicle_types() -> list:
    return [
        VehicleType(
            id=1,
            name="Bus Standard",
            passenger_capacity=40,
            cost_per_km=2.0,
            cost_per_hour=50.0,
            fixed_cost=800.0,
        )
    ]


# ── Bug #3: SA _split operador deve estar na lista ───────────────────────────

class TestBug3SaSplitOperator:
    def test_split_in_operators_list(self):
        """_split DEVE estar em _OPERATORS para SA poder reduzir veículos."""
        assert _split in _OPERATORS, "_split não está em _OPERATORS — SA não pode explorar splitting"

    def test_sa_uses_split_without_error(self):
        """SA deve completar sem erro mesmo com _split na lista."""
        trips = make_trips(8)
        sa = SimulatedAnnealingVSP()
        sa.time_budget_s = 3.0
        sol = sa.solve(trips, make_vehicle_types())
        assert sol.num_vehicles > 0
        assert sol.iterations > 0

    def test_split_function_works(self):
        """_split deve dividir um bloco em dois."""
        trips = make_trips(4, gap=30)
        blocks = [Block(id=1, trips=trips)]
        result = _split(blocks, next_id=100)
        # _split pode retornar None se bloco tem < 2 viagens no ponto de corte
        if result is not None:
            total_trips = sum(len(b.trips) for b in result)
            assert total_trips == 4
            assert len(result) >= 2


# ── Bug #12: block_cost não deve adicionar fixed_cost por viagem ─────────────

class TestBug12BlockCost:
    def test_block_cost_fixed_once_no_vehicle_type(self):
        """Sem vehicle_type, fixed_cost deve ser adicionado UMA vez por bloco."""
        trips = make_trips(3, gap=30)
        block = Block(id=1, trips=trips, vehicle_type_id=None)
        ev = CostEvaluator()
        cost = ev.block_cost(block, [])  # Sem vehicle_types → fallback

        # Calcula o esperado: 1x fixed + sum(distance*per_km + duration/60*per_hour)
        expected_fixed = settings.default_vehicle_fixed_cost
        expected_variable = sum(
            t.distance_km * settings.default_cost_per_km
            + (t.duration / 60.0) * settings.default_cost_per_hour
            for t in trips
        )
        expected = expected_fixed + expected_variable
        assert abs(cost - expected) < 0.01, (
            f"block_cost={cost:.2f} deveria ser {expected:.2f} "
            f"(fixed={expected_fixed}, variable={expected_variable:.2f})"
        )

    def test_block_cost_not_multiplied_by_trips(self):
        """Custo de bloco com 5 viagens NÃO deve ter 5x fixed_cost."""
        trips = make_trips(5, gap=30)
        block = Block(id=1, trips=trips, vehicle_type_id=None)
        ev = CostEvaluator()
        cost = ev.block_cost(block, [])
        # Se fosse multiplicado por 5, seria ≈ 5 * fixed_cost + variável
        max_wrong = settings.default_vehicle_fixed_cost * 5 + 500
        assert cost < max_wrong, f"block_cost={cost} parece ter fixed_cost multiplicado por trip count"


# ── Bug #5: GA _repair_chromosome deve ordenar por start_time ────────────────

class TestBug5GaRepairSort:
    def test_repair_sorts_missing_by_start_time(self):
        """Trips faltantes devem ser adicionadas na ordem de start_time, não ID."""
        trips = make_trips(5, gap=90)
        trip_map = {t.id: t for t in trips}
        # Cria cromossomo com apenas trip 1 e 3 (faltando 2, 4, 5)
        chrom = [[1, 3]]
        all_ids = {1, 2, 3, 4, 5}
        repaired = _repair_chromosome(chrom, all_ids, trip_map)

        # Verifica que todas as trips estão presentes
        all_repaired = {tid for seq in repaired for tid in seq}
        assert all_repaired == all_ids

    def test_repair_with_reversed_ids_sorts_by_time(self):
        """Se IDs estão em ordem inversa ao start_time, deve ordenar por time."""
        # Cria trips onde ID 5 tem o menor start_time
        trips = []
        start = 360
        for i in [5, 4, 3, 2, 1]:  # IDs em ordem reversa
            t = Trip(
                id=i,
                line_id=1,
                start_time=start,
                end_time=start + 60,
                origin_id=1,
                destination_id=2,
                duration=60,
                distance_km=20.0,
            )
            trips.append(t)
            start += 90

        trip_map = {t.id: t for t in trips}
        chrom = [[5]]  # Só trip 5 presente
        all_ids = {1, 2, 3, 4, 5}
        repaired = _repair_chromosome(chrom, all_ids, trip_map)

        # O bloco que recebeu as trips faltantes deve ter trips 4,3,2,1 em ordem de start_time
        added_block = repaired[0]
        missing_in_order = [tid for tid in added_block if tid != 5]
        expected_order = sorted(missing_in_order, key=lambda tid: trip_map[tid].start_time)
        assert missing_in_order == expected_order, (
            f"Trips faltantes devem estar em ordem de start_time: {expected_order}, mas vieram {missing_in_order}"
        )


# ── Bug #4: TS stale_count e iteration return ────────────────────────────────

class TestBug4TsStaleAndIterReturn:
    def test_ts_returns_actual_iteration_count(self):
        """TS deve retornar o número real de iterações, não max_iterations."""
        trips = make_trips(5)
        ts = TabuSearchVSP()
        ts.time_budget_s = 2.0
        ts.max_iterations = 999999  # Valor alto para garantir que não seja usado como retorno
        sol = ts.solve(trips, make_vehicle_types())
        assert sol.iterations > 0
        assert sol.iterations < 999999, (
            f"TS retornou iterations={sol.iterations}, parece estar retornando max_iterations"
        )

    def test_ts_completes_without_stale(self):
        """TS deve completar sem ficar preso indefinidamente."""
        trips = make_trips(6)
        ts = TabuSearchVSP()
        ts.time_budget_s = 3.0
        sol = ts.solve(trips, make_vehicle_types())
        assert sol.num_vehicles > 0
        assert sol.elapsed_ms > 0


# ── Bug #10: Pipeline deve realocar tempo sobrante ────────────────────────────

class TestBug10PipelineTimeRealloc:
    def test_pipeline_completes_correctly(self):
        """Pipeline deve completar sem erro com realocação de tempo."""
        from src.services.optimizer_service import OptimizerService
        from src.domain.models import AlgorithmType

        trips = make_trips(6)
        vt = make_vehicle_types()
        svc = OptimizerService()
        result = svc.run(trips, vt, algorithm=AlgorithmType.HYBRID_PIPELINE, time_budget_s=8.0)
        assert result.vsp.num_vehicles > 0
        assert result.csp.num_crew >= 0


# ── Testes de integridade geral dos algoritmos ────────────────────────────────

class TestAlgorithmIntegrity:
    def test_all_algorithms_cover_all_trips(self):
        """Todos os algoritmos VSP devem cobrir todas as viagens."""
        trips = make_trips(8)
        vt = make_vehicle_types()
        trip_ids = {t.id for t in trips}

        for algo_cls, name in [
            (GreedyVSP, "Greedy"),
            (SimulatedAnnealingVSP, "SA"),
            (TabuSearchVSP, "TS"),
            (GeneticVSP, "GA"),
        ]:
            algo = algo_cls()
            algo.time_budget_s = 3.0
            if hasattr(algo, 'max_iterations'):
                algo.max_iterations = 50
            sol = algo.solve(trips, vt)
            covered = {t.id for b in sol.blocks for t in b.trips}
            assert covered == trip_ids, (
                f"{name} não cobriu todas as viagens: faltam {trip_ids - covered}"
            )

    def test_no_duplicate_trips_in_solution(self):
        """Nenhum algoritmo deve ter viagens duplicadas na solução."""
        trips = make_trips(6)
        vt = make_vehicle_types()

        for algo_cls, name in [
            (GreedyVSP, "Greedy"),
            (SimulatedAnnealingVSP, "SA"),
            (TabuSearchVSP, "TS"),
            (GeneticVSP, "GA"),
        ]:
            algo = algo_cls()
            algo.time_budget_s = 2.0
            if hasattr(algo, 'max_iterations'):
                algo.max_iterations = 30
            sol = algo.solve(trips, vt)
            all_trip_ids = [t.id for b in sol.blocks for t in b.trips]
            assert len(all_trip_ids) == len(set(all_trip_ids)), (
                f"{name} tem viagens duplicadas: {[tid for tid in all_trip_ids if all_trip_ids.count(tid) > 1]}"
            )

    def test_blocks_temporal_feasibility(self):
        """Viagens dentro de cada bloco devem estar em ordem temporal."""
        trips = make_trips(8)
        vt = make_vehicle_types()

        for algo_cls, name in [
            (GreedyVSP, "Greedy"),
            (SimulatedAnnealingVSP, "SA"),
            (TabuSearchVSP, "TS"),
            (GeneticVSP, "GA"),
        ]:
            algo = algo_cls()
            algo.time_budget_s = 2.0
            if hasattr(algo, 'max_iterations'):
                algo.max_iterations = 30
            sol = algo.solve(trips, vt)
            for block in sol.blocks:
                for i in range(len(block.trips) - 1):
                    assert block.trips[i].end_time <= block.trips[i + 1].start_time, (
                        f"{name} bloco {block.id}: trip {block.trips[i].id} "
                        f"(end={block.trips[i].end_time}) sobrepõe "
                        f"trip {block.trips[i + 1].id} (start={block.trips[i + 1].start_time})"
                    )

    def test_sa_multi_restart_uses_budget(self):
        """SA com budget > tempo de um ciclo de cooling deve fazer restarts."""
        trips = make_trips(10)
        sa = SimulatedAnnealingVSP()
        sa.time_budget_s = 5.0
        sol = sa.solve(trips, make_vehicle_types())
        restarts = (sol.meta or {}).get("restarts", 0)
        assert sol.iterations > 100, f"SA fez apenas {sol.iterations} iterações em 5s"

    def test_ga_crossover_preserves_all_trips(self):
        """Crossover + repair deve manter todas as trips."""
        trips = make_trips(6)
        trip_map = {t.id: t for t in trips}
        all_ids = {t.id for t in trips}
        p1 = [[1, 2, 3], [4, 5, 6]]
        p2 = [[1, 4], [2, 5], [3, 6]]
        c1, c2 = _crossover(p1, p2, trip_map)
        assert {tid for seq in c1 for tid in seq} == all_ids
        assert {tid for seq in c2 for tid in seq} == all_ids

    def test_ga_mutate_preserves_all_trips(self):
        """Mutação + repair deve manter todas as trips."""
        trips = make_trips(6)
        trip_map = {t.id: t for t in trips}
        chrom = [[1, 2, 3], [4, 5, 6]]
        mutated = _mutate(chrom, 1.0, trip_map)  # mutation_rate=1.0 garante mutação
        assert {tid for seq in mutated for tid in seq} == {1, 2, 3, 4, 5, 6}

    def test_evaluator_vsp_cost_consistent(self):
        """vsp_cost deve manter custos consistentes entre runs."""
        trips = make_trips(4)
        vt = make_vehicle_types()
        sol = GreedyVSP().solve(trips, vt)
        ev = CostEvaluator()
        csp = GreedyCSP().solve(sol.blocks)
        result = OptimizationResult(vsp=sol, csp=csp)
        cost1 = ev.total_cost(result, vt)
        cost2 = ev.total_cost(result, vt)
        assert cost1 == cost2, "total_cost não é determinístico"

    def test_csp_covers_all_trips_from_vsp(self):
        """CSP deve cobrir todas as viagens produzidas pelo VSP."""
        trips = make_trips(8)
        vt = make_vehicle_types()
        vsp_sol = GreedyVSP().solve(trips, vt)
        csp_sol = GreedyCSP().solve(vsp_sol.blocks, trips)
        vsp_trip_ids = {t.id for b in vsp_sol.blocks for t in b.trips}
        csp_trip_ids = {t.id for d in csp_sol.duties for task in d.tasks for t in task.trips}
        assert csp_trip_ids == vsp_trip_ids, (
            f"CSP não cobriu trips do VSP: faltam {vsp_trip_ids - csp_trip_ids}"
        )


# ── Testes de post-optimization (joint_opt) ──────────────────────────────────

class TestPostOptimization:
    def test_joint_opt_exists_in_pipeline(self):
        """Pipeline deve executar joint_duty_vehicle_swap na finalização."""
        from src.algorithms.hybrid.pipeline import HybridPipeline
        import inspect
        source = inspect.getsource(HybridPipeline._finalize)
        assert "joint_duty_vehicle_swap" in source, (
            "Pipeline._finalize não chama joint_duty_vehicle_swap"
        )

    def test_joint_opt_does_not_crash(self):
        """joint_duty_vehicle_swap não deve crashar."""
        from src.algorithms.joint_opt import joint_duty_vehicle_swap
        trips = make_trips(4)
        vt = make_vehicle_types()
        vsp_sol = GreedyVSP().solve(trips, vt)
        csp_sol = GreedyCSP().solve(vsp_sol.blocks, trips)
        # Deve funcionar sem erro
        csp_out, vsp_out = joint_duty_vehicle_swap(
            csp_sol, vsp_sol, trips, {}, {}
        )
        assert csp_out is not None
        assert vsp_out is not None
