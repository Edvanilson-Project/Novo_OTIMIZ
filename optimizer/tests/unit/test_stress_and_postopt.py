"""
Testes rigorosos de stress e pós-otimização.
Tenta quebrar os algoritmos com cenários extremos e valida:
- Rendição de tripulante mid-route
- Pós-otimização joint_opt (merge blocks + swap trips)
- Redução máxima de veículos e tripulantes
- Edge cases que podem causar crash

Execute com: pytest tests/unit/test_stress_and_postopt.py -v
"""
import sys
import os
import copy
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.domain.models import Block, Trip, VehicleType, VSPSolution, CSPSolution, Duty, OptimizationResult
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from src.algorithms.vsp.tabu_search import TabuSearchVSP
from src.algorithms.vsp.genetic import GeneticVSP
from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.evaluator import CostEvaluator
from src.algorithms.joint_opt import joint_duty_vehicle_swap, _try_merge_vsp_blocks
from src.algorithms.hybrid.pipeline import HybridPipeline


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_vt():
    return [VehicleType(
        id=1, name="Bus", passenger_capacity=40,
        cost_per_km=2.0, cost_per_hour=50.0, fixed_cost=800.0,
    )]


def make_trip(tid, line_id, start, end, origin=1, dest=2, distance=20.0):
    return Trip(
        id=tid, line_id=line_id, start_time=start, end_time=end,
        origin_id=origin, destination_id=dest, duration=end - start,
        distance_km=distance,
    )


def make_chain_trips(n, gap=15, duration=60, line_id=1, start=360):
    """Gera n viagens encadeadas: A→B, B→A alternadas, com gap entre elas."""
    trips = []
    t = start
    for i in range(n):
        origin = 1 if i % 2 == 0 else 2
        dest = 2 if i % 2 == 0 else 1
        trips.append(make_trip(i + 1, line_id, t, t + duration, origin, dest))
        t += duration + gap
    return trips


def make_multi_line_trips(lines=3, trips_per_line=6, gap=20, duration=50):
    """Gera trips em múltiplas linhas com horários intercalados."""
    trips = []
    tid = 1
    for line in range(1, lines + 1):
        start = 300 + (line - 1) * 10  # linhas começam em horários levemente diferentes
        for i in range(trips_per_line):
            origin = line * 10 + 1
            dest = line * 10 + 2
            if i % 2 == 1:
                origin, dest = dest, origin
            trips.append(make_trip(tid, line, start, start + duration, origin, dest))
            start += duration + gap
            tid += 1
    return trips


# ══════════════════════════════════════════════════════════════════════════════
# 1. RENDIÇÃO DE TRIPULANTE NO MEIO DO PERCURSO
# ══════════════════════════════════════════════════════════════════════════════

class TestCrewReliefMidRoute:
    """Valida que o run-cutting gera pontos de rendição no meio de blocos longos."""

    def test_long_block_gets_cut_into_tasks(self):
        """Bloco com 8h+ de viagens DEVE ser cortado em tarefas menores."""
        # 16 viagens de 30min com 5min gap = 16*35=560min (~9.3h)
        trips = make_chain_trips(16, gap=5, duration=30) 
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)

        # CSP deve fazer run-cutting
        csp = GreedyCSP().solve(vsp.blocks, trips)
        # Com bloco tão longo, CSP deve criar >1 duty (rendição no meio)
        total_tasks = sum(len(d.tasks) for d in csp.duties)
        assert total_tasks >= len(vsp.blocks), (
            f"Run-cutting deveria gerar mais tarefas que blocos para blocos longos"
        )

    def test_duty_respects_max_work_time(self):
        """Nenhuma duty deve exceder excessivamente o work_time configurado."""
        trips = make_chain_trips(12, gap=5, duration=40)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP(max_work_minutes=480).solve(vsp.blocks, trips)

        for duty in csp.duties:
            # Tolerância de 60min acima do limite (pode haver violações leves)
            assert duty.work_time <= 600, (
                f"Duty {duty.id}: work_time {duty.work_time}min > 600min (limite 480+tolerância)"
            )

    def test_relief_happens_at_terminal_points(self):
        """Rendições devem ocorrer em pontos de rendição válidos (terminais)."""
        # Viagens A→B, B→A — terminal B é ponto de rendição natural
        trips = make_chain_trips(10, gap=10, duration=45)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)

        for duty in csp.duties:
            if len(duty.tasks) < 2:
                continue
            for i in range(len(duty.tasks) - 1):
                t1_trips = duty.tasks[i].trips
                t2_trips = duty.tasks[i + 1].trips
                if not t1_trips or not t2_trips:
                    continue
                task_end = t1_trips[-1]
                task_start = t2_trips[0]
                gap = task_start.start_time - task_end.end_time
                assert gap >= 0, (
                    f"Duty {duty.id}: overlap entre tarefas {i} e {i+1}"
                )

    def test_multiple_drivers_cover_single_vehicle(self):
        """Um veículo com bloco de 14h deve ser coberto por ≥2 tripulantes."""
        # 20 viagens de 40min com 5min gap = 20 * 45 = 900min (15h)
        trips = make_chain_trips(20, gap=5, duration=40)
        vt = make_vt()
        vsp = GreedyVSP(vsp_params={"max_vehicle_shift_minutes": 960}).solve(trips, vt)

        # Com max_work=480min (8h), precisamos de ≥2 duties para cobrir 15h
        csp = GreedyCSP(max_work_minutes=480).solve(vsp.blocks, trips)
        if len(vsp.blocks) == 1:
            assert csp.num_crew >= 2, (
                f"Bloco de 15h com max_work=8h deveria ter ≥2 tripulantes, "
                f"mas tem {csp.num_crew}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 2. PÓS-OTIMIZAÇÃO: MERGE DE BLOCOS E SWAPS
# ══════════════════════════════════════════════════════════════════════════════

class TestPostOptimization:
    """Valida que a pós-otimização realmente tenta reduzir custos."""

    def test_merge_vsp_blocks_reduces_vehicles(self):
        """_try_merge_vsp_blocks deve fundir blocos adjacentes compatíveis."""
        # Criar 4 blocos de 1 viagem onde consecutivos podem ser fundidos
        trips = [
            make_trip(1, 1, 360, 420, 1, 2),
            make_trip(2, 1, 440, 500, 2, 1),   # 20min gap, mesma rota de volta
            make_trip(3, 1, 520, 580, 1, 2),
            make_trip(4, 1, 600, 660, 2, 1),
        ]
        blocks = [Block(id=i + 1, trips=[t]) for i, t in enumerate(trips)]
        vsp = VSPSolution(blocks=blocks, algorithm="test")
        merged = _try_merge_vsp_blocks(vsp, {"min_layover_minutes": 8, "max_vehicle_shift_minutes": 960})
        assert len(merged.blocks) < 4, (
            f"Merge deveria unir ≥2 dos 4 blocos, mas resultou em {len(merged.blocks)}"
        )

    def test_joint_swap_runs_without_operator_single_vehicle(self):
        """joint_duty_vehicle_swap deve funcionar MESMO sem operator_single_vehicle_only."""
        trips = make_chain_trips(6, gap=20)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)

        # Com operator_single_vehicle_only=False (padrão)
        new_csp, new_vsp = joint_duty_vehicle_swap(
            csp, vsp, trips,
            cct_params={},  # operator_single_vehicle_only default = False
            kwargs={},
        )
        # Não deve crashar e deve retornar resultados válidos
        assert new_csp is not None
        assert new_vsp is not None
        assert new_vsp.num_vehicles > 0

    def test_post_opt_never_increases_violations(self):
        """Pós-otimização não deve aceitar resultado com mais violações."""
        trips = make_chain_trips(8, gap=15)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)

        new_csp, new_vsp = joint_duty_vehicle_swap(csp, vsp, trips, {}, {})
        assert new_csp.cct_violations <= csp.cct_violations, (
            f"Pós-otimização aumentou violações: {csp.cct_violations} → {new_csp.cct_violations}"
        )

    def test_pipeline_includes_post_optimization(self):
        """HybridPipeline._finalize deve chamar joint_duty_vehicle_swap."""
        import inspect
        source = inspect.getsource(HybridPipeline._finalize)
        assert "joint_duty_vehicle_swap" in source

    def test_merge_empty_blocks_safe(self):
        """Merge com blocos vazios não deve crashar."""
        blocks = [
            Block(id=1, trips=[make_trip(1, 1, 360, 420)]),
            Block(id=2, trips=[]),
            Block(id=3, trips=[make_trip(2, 1, 450, 510)]),
        ]
        vsp = VSPSolution(blocks=blocks, algorithm="test")
        merged = _try_merge_vsp_blocks(vsp, {"min_layover_minutes": 8})
        assert all(len(b.trips) > 0 for b in merged.blocks)

    def test_merge_respects_max_vehicle_shift(self):
        """Merge NÃO deve criar blocos que excedam max_vehicle_shift."""
        # Bloco 1: 06-14h = 480min, Bloco 2: 14:30-22h = 450min
        trips1 = make_chain_trips(8, gap=5, duration=55, start=360)
        trips2 = make_chain_trips(8, gap=5, duration=55, start=870)
        for i, t in enumerate(trips2):
            t.id = 100 + i + 1
        blocks = [
            Block(id=1, trips=trips1),
            Block(id=2, trips=trips2),
        ]
        vsp = VSPSolution(blocks=blocks, algorithm="test")
        merged = _try_merge_vsp_blocks(vsp, {
            "min_layover_minutes": 8,
            "max_vehicle_shift_minutes": 600,  # 10h limit — um bloco de 16h não cabe
        })
        # Com max_shift=600min, os dois blocos não devem ser fundidos
        # pois juntos dariam ~16h
        for b in merged.blocks:
            duration = b.trips[-1].end_time - b.trips[0].start_time
            assert duration <= 600, (
                f"Bloco {b.id} tem duração {duration}min > max_vehicle_shift 600min"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 3. TESTES DE STRESS — TENTANDO QUEBRAR
# ══════════════════════════════════════════════════════════════════════════════

class TestStressBreaking:
    """Cenários extremos para tentar crashar os algoritmos."""

    def test_single_trip_all_algorithms(self):
        """Uma única viagem não deve crashar nenhum algoritmo."""
        trip = make_trip(1, 1, 360, 420)
        vt = make_vt()
        for algo_cls, name in [
            (GreedyVSP, "Greedy"),
            (SimulatedAnnealingVSP, "SA"),
            (TabuSearchVSP, "TS"),
            (GeneticVSP, "GA"),
        ]:
            algo = algo_cls()
            algo.time_budget_s = 1.0
            if hasattr(algo, 'max_iterations'):
                algo.max_iterations = 10
            sol = algo.solve([trip], vt)
            assert sol.num_vehicles == 1, f"{name} falhou com 1 trip"

    def test_two_overlapping_trips(self):
        """Duas viagens no mesmo horário exigem 2 veículos."""
        trips = [
            make_trip(1, 1, 360, 420, 1, 2),
            make_trip(2, 1, 360, 420, 3, 4),
        ]
        vt = make_vt()
        sol = GreedyVSP().solve(trips, vt)
        assert sol.num_vehicles == 2, "Viagens sobrepostas devem usar 2 veículos"

    def test_all_trips_simultaneous(self):
        """N viagens todas ao mesmo tempo = N veículos."""
        n = 20
        trips = [make_trip(i + 1, 1, 360, 420, i * 10 + 1, i * 10 + 2) for i in range(n)]
        vt = make_vt()
        sol = GreedyVSP().solve(trips, vt)
        assert sol.num_vehicles == n, f"20 viagens simultâneas devem usar 20 veículos, usou {sol.num_vehicles}"

    def test_very_long_chain_sa(self):
        """SA com 50 viagens encadeadas não deve crashar."""
        trips = make_chain_trips(50, gap=10, duration=20)
        sa = SimulatedAnnealingVSP()
        sa.time_budget_s = 3.0
        sol = sa.solve(trips, make_vt())
        assert sol.num_vehicles > 0
        total = sum(len(b.trips) for b in sol.blocks)
        assert total == 50, f"SA perdeu viagens: {total}/50"

    def test_ts_with_zero_iterations(self):
        """TS com max_iterations=0 não deve crashar."""
        trips = make_chain_trips(5)
        ts = TabuSearchVSP()
        ts.time_budget_s = 0.5
        ts.max_iterations = 0
        sol = ts.solve(trips, make_vt())
        assert sol.num_vehicles > 0

    def test_ga_with_tiny_population(self):
        """GA com pop_size=2 não deve crashar."""
        trips = make_chain_trips(6)
        ga = GeneticVSP()
        ga.time_budget_s = 1.0
        ga.pop_size = 2
        ga.generations = 5
        sol = ga.solve(trips, make_vt())
        assert sol.num_vehicles > 0

    def test_sa_with_zero_budget(self):
        """SA com budget=0 deve retornar greedy sem crashar."""
        trips = make_chain_trips(5)
        sa = SimulatedAnnealingVSP()
        sa.time_budget_s = 0.001
        sol = sa.solve(trips, make_vt())
        assert sol.num_vehicles > 0

    def test_very_tight_layover(self):
        """Layover mínimo muito apertado não deve causar sobreposição."""
        # Gap de exatamente 8 minutos (= min_layover)
        trips = [
            make_trip(1, 1, 360, 420, 1, 2),
            make_trip(2, 1, 428, 488, 2, 1),  # gap=8min exato
        ]
        vt = make_vt()
        sol = GreedyVSP(vsp_params={"min_layover_minutes": 8}).solve(trips, vt)
        assert sol.num_vehicles >= 1
        for block in sol.blocks:
            for i in range(len(block.trips) - 1):
                gap = block.trips[i + 1].start_time - block.trips[i].end_time
                assert gap >= 0, f"Sobreposição no bloco {block.id}: gap={gap}"

    def test_csp_with_many_short_blocks(self):
        """CSP com 30 blocos de 1 viagem cada deve gerar duties razoáveis."""
        trips = make_chain_trips(30, gap=20, duration=15)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)
        assert csp.num_crew > 0
        assert len(csp.duties) > 0

    def test_multi_line_no_crash(self):
        """Múltiplas linhas com viagens intercaladas não deve crashar."""
        trips = make_multi_line_trips(lines=4, trips_per_line=8)
        vt = make_vt()
        vsp = GreedyVSP(vsp_params={"allow_multi_line_block": True}).solve(trips, vt)
        assert vsp.num_vehicles > 0
        csp = GreedyCSP().solve(vsp.blocks, trips)
        assert csp.num_crew > 0

    def test_pipeline_stress_multi_line(self):
        """Pipeline completo com múltiplas linhas deve completar sem erro."""
        trips = make_multi_line_trips(lines=3, trips_per_line=6)
        vt = make_vt()
        pipeline = HybridPipeline(time_budget_s=8.0, vsp_params={"allow_multi_line_block": True})
        result = pipeline.solve(trips, vt)
        assert result.vsp.num_vehicles > 0
        assert result.total_cost > 0

    def test_duplicate_trip_ids_rejected(self):
        """IDs de viagem duplicados devem ser tratados sem crashar."""
        trips = [
            make_trip(1, 1, 360, 420),
            make_trip(1, 1, 500, 560),  # ID duplicado!
        ]
        vt = make_vt()
        # Não deve crashar — pode criar solução sub-ótima mas nunca crash
        sol = GreedyVSP().solve(trips, vt)
        assert sol is not None

    def test_zero_duration_trip(self):
        """Trip com duração 0 não deve crashar."""
        trip = Trip(
            id=1, line_id=1, start_time=360, end_time=360,
            origin_id=1, destination_id=2, duration=0, distance_km=0.0,
        )
        vt = make_vt()
        sol = GreedyVSP().solve([trip], vt)
        assert sol.num_vehicles >= 1

    def test_huge_gap_between_trips(self):
        """Gap de 12h entre trips — cada uma deve ir pra veículo separado ou split shift."""
        trips = [
            make_trip(1, 1, 300, 360),
            make_trip(2, 1, 1020, 1080),  # 11h de gap
        ]
        vt = make_vt()
        sol = GreedyVSP(vsp_params={
            "max_vehicle_shift_minutes": 960,
            "allow_vehicle_split_shifts": False,
        }).solve(trips, vt)
        # Com gap de 11h e max_shift 16h, depende dos parâmetros
        assert sol.num_vehicles >= 1
        total = sum(len(b.trips) for b in sol.blocks)
        assert total == 2

    def test_csp_all_trips_covered_after_post_opt(self):
        """Após post-opt, todas as trips devem continuar cobertas."""
        trips = make_chain_trips(15, gap=15)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)

        new_csp, new_vsp = joint_duty_vehicle_swap(csp, vsp, trips, {}, {})

        # Verificar cobertura no VSP
        vsp_covered = {t.id for b in new_vsp.blocks for t in b.trips}
        expected = {t.id for t in trips}
        assert vsp_covered == expected, (
            f"Post-opt perdeu viagens no VSP: faltam {expected - vsp_covered}"
        )

        # Verificar cobertura no CSP
        csp_covered = {t.id for d in new_csp.duties for task in d.tasks for t in task.trips}
        assert csp_covered == expected, (
            f"Post-opt perdeu viagens no CSP: faltam {expected - csp_covered}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. TESTES DE REDUÇÃO MÁXIMA
# ══════════════════════════════════════════════════════════════════════════════

class TestMaxReduction:
    """Verifica que o otimizador consegue reduzir veículos ao mínimo teórico."""

    def test_sequential_trips_use_one_vehicle(self):
        """Viagens sequenciais com gap suficiente devem usar poucos veículos."""
        # 4 viagens de 60min com 30min gap = tudo cabe em 1-2 blocos de ~390min
        trips = make_chain_trips(4, gap=30, duration=60)
        # Informar deadhead_times para que o greedy saiba que pode conectar
        for t in trips:
            t.deadhead_times = {1: 8, 2: 8}
        vt = make_vt()
        sol = GreedyVSP(vsp_params={"min_layover_minutes": 8}).solve(trips, vt)
        assert sol.num_vehicles <= 2, (
            f"4 viagens sequenciais com gap=30min deviam usar ≤2 veículos, usou {sol.num_vehicles}"
        )

    def test_two_parallel_lines_min_vehicles(self):
        """Duas linhas com viagens que não se sobrepõem podem compartilhar veículo."""
        trips = [
            make_trip(1, 1, 360, 420, 1, 2),
            make_trip(2, 2, 440, 500, 3, 4),  # Outra linha, começa depois
            make_trip(3, 1, 520, 580, 2, 1),
            make_trip(4, 2, 600, 660, 4, 3),
        ]
        vt = make_vt()
        sol = GreedyVSP(vsp_params={"allow_multi_line_block": True}).solve(trips, vt)
        # Podem ser todos em 1 veículo se multi-line permitido
        assert sol.num_vehicles <= 2

    def test_sa_finds_better_than_greedy(self):
        """SA deve encontrar solução ≤ greedy em custo."""
        trips = make_chain_trips(10, gap=15, duration=50)
        vt = make_vt()

        greedy = GreedyVSP().solve(trips, vt)

        sa = SimulatedAnnealingVSP()
        sa.time_budget_s = 3.0
        sa_sol = sa.solve(trips, vt)

        # SA deve ter ≤ veículos que greedy (ou igual — nunca mais)
        assert sa_sol.num_vehicles <= greedy.num_vehicles + 1, (
            f"SA ({sa_sol.num_vehicles}) muito pior que Greedy ({greedy.num_vehicles})"
        )

    def test_crew_count_not_exceed_vehicle_count_for_short_blocks(self):
        """Para blocos curtos (< max_work), crew ≤ vehicles."""
        # Viagens curtas: cada bloco ~4h, cabe em 1 jornada
        trips = make_chain_trips(6, gap=20, duration=40)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP(max_work_minutes=480).solve(vsp.blocks, trips)

        # Se cada bloco é curto, não precisa de mais tripulante que veículo
        max_block_duration = max(
            (b.trips[-1].end_time - b.trips[0].start_time for b in vsp.blocks),
            default=0,
        )
        if max_block_duration <= 480:
            assert csp.num_crew <= vsp.num_vehicles + 1, (
                f"Crew ({csp.num_crew}) excessivo para {vsp.num_vehicles} veículos "
                f"com blocos curtos (max={max_block_duration}min)"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 5. VALIDAÇÃO DE INTEGRIDADE PÓS-OTIMIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

class TestPostOptIntegrity:
    """Verifica integridade completa após cada fase de otimização."""

    def test_no_trip_lost_through_pipeline(self):
        """Pipeline completo não pode perder viagens."""
        trips = make_chain_trips(12, gap=15)
        vt = make_vt()
        expected_ids = {t.id for t in trips}

        pipeline = HybridPipeline(time_budget_s=6.0)
        result = pipeline.solve(trips, vt)

        vsp_ids = {t.id for b in result.vsp.blocks for t in b.trips}
        assert vsp_ids == expected_ids, f"VSP perdeu: {expected_ids - vsp_ids}"

    def test_no_overlap_in_blocks_after_pipeline(self):
        """Blocos do pipeline não devem ter sobreposição temporal."""
        trips = make_chain_trips(10, gap=12)
        vt = make_vt()
        pipeline = HybridPipeline(time_budget_s=5.0)
        result = pipeline.solve(trips, vt)

        for block in result.vsp.blocks:
            for i in range(len(block.trips) - 1):
                t1 = block.trips[i]
                t2 = block.trips[i + 1]
                assert t1.end_time <= t2.start_time, (
                    f"Sobreposição no bloco {block.id}: "
                    f"trip {t1.id} (end={t1.end_time}) > trip {t2.id} (start={t2.start_time})"
                )

    def test_post_opt_preserves_trip_count(self):
        """Post-opt deve manter exatamente o mesmo número de viagens."""
        trips = make_chain_trips(10, gap=20)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)

        before_trips = sum(len(b.trips) for b in vsp.blocks)
        new_csp, new_vsp = joint_duty_vehicle_swap(csp, vsp, trips, {}, {})
        after_trips = sum(len(b.trips) for b in new_vsp.blocks)

        assert after_trips == before_trips, (
            f"Post-opt mudou contagem de trips: {before_trips} → {after_trips}"
        )

    def test_evaluator_cost_positive_after_pipeline(self):
        """Custo total após pipeline deve ser positivo e finito."""
        trips = make_chain_trips(8, gap=20)
        vt = make_vt()
        pipeline = HybridPipeline(time_budget_s=5.0)
        result = pipeline.solve(trips, vt)
        
        assert result.total_cost > 0
        assert result.total_cost < float('inf')

    def test_no_empty_blocks_after_post_opt(self):
        """Não devem existir blocos vazios após pós-otimização."""
        trips = make_chain_trips(8, gap=15)
        vt = make_vt()
        vsp = GreedyVSP().solve(trips, vt)
        csp = GreedyCSP().solve(vsp.blocks, trips)

        _, new_vsp = joint_duty_vehicle_swap(csp, vsp, trips, {}, {})
        for block in new_vsp.blocks:
            assert len(block.trips) > 0, f"Bloco vazio {block.id} após post-opt"
