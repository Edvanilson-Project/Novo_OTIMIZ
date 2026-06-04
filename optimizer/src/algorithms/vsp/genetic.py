"""
VSP — Algoritmo Genético (GA).

Representação cromossômica:
  chromosome[i] = índice da viagem que a viagem i segue no roteiro
                  Se chromosome[i] == -1, a viagem i inicia um novo bloco.

Operadores:
  - Seleção por torneio (k=3)
  - Cruzamento por ponto (Order Crossover adaptado para blocos)
  - Mutação: troca de atribuição de veículo / reordenação local
  - Elitismo: 10% melhores sobrevivem diretamente
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Dict, List, Optional, Tuple


def _copy_chrom(chrom: "Chromosome") -> "Chromosome":
    """Shallow copy of chromosome (list of lists of ints)."""
    return [seq[:] for seq in chrom]


from ...core.config import get_settings

from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from ..evaluator import CostEvaluator
from ..utils import (
    is_block_feasible,
    preferred_pair_penalty,
    preferred_pair_penalty_from_trips,
    quick_cost_sorted,
    quick_cost_from_trips,
    sort_block_trips,
    is_connection_feasible,
    select_vehicle_type,
)
from .greedy import GreedyVSP, build_preferred_pairs

settings = get_settings()
evaluator = CostEvaluator()

# Tipo: lista de IDs de viagem ordenados em cada bloco (cromossomo = lista de listas)
Chromosome = List[List[int]]


def _trips_by_id(trips: List[Trip]) -> Dict[int, Trip]:
    return {t.id: t for t in trips}


def _chromosome_from_blocks(blocks: List[Block]) -> Chromosome:
    return [[t.id for t in b.trips] for b in blocks]


def _blocks_from_chromosome(
    chrom: Chromosome,
    trip_map: Dict[int, Trip],
    vehicle_types: List[VehicleType],
    start_id: int = 1,
) -> List[Block]:
    blocks = []
    for i, seq in enumerate(chrom):
        block_trips = [trip_map[tid] for tid in seq if tid in trip_map]
        if block_trips:
            b = Block(id=start_id + i, trips=block_trips)
            _depot = block_trips[0].depot_id if block_trips else None
            _vt = select_vehicle_type(vehicle_types, _depot)
            if _vt:
                b.vehicle_type_id = _vt.id
            blocks.append(b)
    return blocks


def _fitness(
    chrom: Chromosome,
    trip_map: Dict[int, Trip],
    vt: List[VehicleType],
    fixed_vehicle_cost: float = 800.0,
    idle_cost_per_minute: float = 0.5,
    max_work_minutes: float = 480.0,
    crew_cost_weight: float = 400.0,
    preferred_pairs: Optional[Dict[int, int]] = None,
    pair_break_penalty: float = 1000.0,
    paired_trip_bonus: float = 40.0,
    hard_pairing_penalty: float = 0.0,
    min_gap: int = 8,
    min_break: int = 30,
    enforce_min_interval: bool = False,
    connection_tolerance: int = 0,
    deadhead_cost_per_minute: float = 1.0,
) -> float:
    """Menor custo estimado = maior fitness (retorna negativo do custo).
    Otimizado para evitar instanciar objetos Block.
    """
    # 1. Converter IDs em Trips e ordenar para garantir viabilidade temporal
    sequences: List[List[Trip]] = []
    for seq in chrom:
        trips = [trip_map[tid] for tid in seq if tid in trip_map]
        if trips:
            trips.sort(key=lambda t: t.start_time)
            sequences.append(trips)

    # 2. Penaliza viagens não cobertas
    covered_tids = {tid for seq in chrom for tid in seq if tid in trip_map}
    missing = len(trip_map) - len(covered_tids)

    # 3. Cálculo de custos direcional (float ultra-rápido)
    base_cost = quick_cost_from_trips(
        sequences, fixed_vehicle_cost, idle_cost_per_minute, max_work_minutes, crew_cost_weight,
        deadhead_cost_per_minute,
    )

    base_cost += preferred_pair_penalty_from_trips(
        sequences,
        preferred_pairs or {},
        pair_break_penalty,
        paired_trip_bonus,
        hard_pairing_penalty,
    )

    # 4. Penalidade por duplicatas
    all_tids_flat = [tid for seq in chrom for tid in seq]
    duplicates = len(all_tids_flat) - len(set(all_tids_flat))

    # 5. Penalidade por blocos com deadhead inviável
    v_params = {
        "min_layover_minutes": min_gap,
        "min_break_minutes": min_break,
        "enforce_min_interval": enforce_min_interval,
        "connection_tolerance_minutes": connection_tolerance,
    }
    infeasible_count = sum(1 for trips in sequences if not is_block_feasible(trips, v_params))

    # 6. Big-M Penalties Dinâmicos
    num_trips = len(trip_map)
    base_big_m = max(1000000.0, num_trips * fixed_vehicle_cost * 10.0)

    missing_penalty = base_big_m * 10.0
    duplicate_penalty = base_big_m * 10.0
    infeasible_penalty = base_big_m

    return -(
        base_cost + missing * missing_penalty + duplicates * duplicate_penalty + infeasible_count * infeasible_penalty
    )


def _tournament(population: List[Chromosome], scores: List[float], k: int = 3) -> Chromosome:
    k = min(k, len(population))
    contestants = random.sample(range(len(population)), k)
    best = max(contestants, key=lambda i: scores[i])
    return _copy_chrom(population[best])


def _repair_chromosome(
    chrom: Chromosome,
    all_trip_ids: set,
    trip_map: Dict[int, Trip] = None,
    **kwargs,
) -> Chromosome:
    """
    Repara um cromossomo após crossover/mutação:
    1. Remove trip_ids duplicados (mantém a primeira ocorrência no cromossomo)
    2. Adiciona trip_ids ausentes ao menor bloco existente
    Correção Bug B2: evita trips duplicadas entre blocos.
    """
    seen: set = set()
    repaired: Chromosome = []
    for seq in chrom:
        new_seq = []
        for tid in seq:
            if tid not in seen:
                seen.add(tid)
                new_seq.append(tid)
        if new_seq:
            repaired.append(new_seq)

    # Adiciona trips ausentes ao bloco com melhor fit temporal (ou cria novo)
    missing = all_trip_ids - seen
    if missing:
        # Ordena por start_time para manter viabilidade temporal do bloco
        if trip_map:
            sorted_missing = sorted(missing, key=lambda tid: (trip_map[tid].start_time, tid))
        else:
            sorted_missing = sorted(missing)
        same_depot_req = bool(kwargs.get("same_depot_required", False))
        if repaired and trip_map:
            # BUG-GA-04 fix: comentrio era "mais perto antes" mas o código faz break
            # na PRIMEIRA conexão viável, não na melhor. Comentário corrigido.
            # Insere cada trip no primeiro bloco compatível com is_connection_feasible.
            for tid in sorted_missing:
                # BUG-GA-03 fix: trip_map[tid].start_time e float('inf') eram dead code
                # (valores calculados e descartados). Removidos.
                trip_depot = trip_map[tid].depot_id if tid in trip_map else None
                best_idx = None
                for i, seq in enumerate(repaired):
                    last_tid = seq[-1]
                    if last_tid not in trip_map:
                        continue
                    # Depot check: skip block if depot mismatch when required
                    if same_depot_req and trip_depot is not None:
                        block_depot = trip_map[seq[0]].depot_id if trip_map[seq[0]].depot_id is not None else None
                        if block_depot is not None and block_depot != trip_depot:
                            continue
                    if is_connection_feasible(
                        trip_map[last_tid],
                        trip_map[tid],
                        min_layover=kwargs.get("min_gap", 8),
                        min_break=kwargs.get("min_break", 30),
                        enforce_min_interval=kwargs.get("enforce_min_interval", False),
                        connection_tolerance=kwargs.get("connection_tolerance", 0),
                    ):
                        best_idx = i
                        break
                if best_idx is not None:
                    repaired[best_idx].append(tid)
                else:
                    # No compatible block found — create new block (depot isolation)
                    repaired.append([tid])
        elif repaired:
            smallest = min(range(len(repaired)), key=lambda i: len(repaired[i]))
            repaired[smallest].extend(sorted_missing)
        else:
            repaired.append(sorted_missing)

    # BUG-GA-01 fix: fallback `[sorted(all_trip_ids)]` criava um \u00fanico bloco gigante com
    # todas as trips \u2014 invi\u00e1vel e altamente penalizado, for\u00e7ando o GA a sempre usar o Greedy.
    # Correto: cada trip em seu pr\u00f3prio bloco \u2014 sempre vi\u00e1vel (sem conex\u00f5es), e o GA
    # pode consolidar nas gera\u00e7\u00f5es seguintes atrav\u00e9s dos operadores de cruzamento/muta\u00e7\u00e3o.
    return repaired if repaired else [[tid] for tid in sorted(all_trip_ids)]


def _crossover(
    parent1: Chromosome, parent2: Chromosome, trip_map: Dict[int, Trip] = None, **kwargs
) -> Tuple[Chromosome, Chromosome]:
    """Troca um bloco aleatório entre pais, com reparo de duplicatas (corrige B2)."""
    if not parent1 or not parent2:
        return _copy_chrom(parent1), _copy_chrom(parent2)
    # Usa set completo de trip_ids do trip_map (fonte da verdade) para garantir
    # que nenhuma trip se perca mesmo que os pais estejam corrompidos.
    all_tids = (
        set(trip_map.keys())
        if trip_map
        else ({tid for seq in parent1 for tid in seq} | {tid for seq in parent2 for tid in seq})
    )

    idx1 = random.randint(0, len(parent1) - 1)
    idx2 = random.randint(0, len(parent2) - 1)
    child1 = _copy_chrom(parent1)
    child2 = _copy_chrom(parent2)
    seq1, seq2 = parent1[idx1][:], parent2[idx2][:]
    child1[idx1] = seq2
    child2[idx2] = seq1

    # Repara duplicatas e trips ausentes — CORREÇÃO B2
    child1 = _repair_chromosome(child1, all_tids, trip_map, **kwargs)
    child2 = _repair_chromosome(child2, all_tids, trip_map, **kwargs)
    return child1, child2


def _mutate(
    chrom: Chromosome,
    mutation_rate: float,
    trip_map: Dict[int, Trip] = None,
    min_gap: int = 8,
    **kwargs,
) -> Chromosome:
    """Operador de mutação com split, move e merge. Re-ordena para garantir factibilidade."""
    if random.random() > mutation_rate:
        return chrom

    # CORREÇÃO: Usar a fonte da verdade se disponível para evitar perda de viagens
    if trip_map:
        all_tids = set(trip_map.keys())
    else:
        all_tids = {tid for seq in chrom for tid in seq}

    chrom_copy = _copy_chrom(chrom)

    # Se só tem 1 bloco: split ou não faz nada
    if len(chrom_copy) == 1:
        if len(chrom_copy[0]) <= 1:
            return chrom_copy  # Não pode dividir bloco com 0 ou 1 viagem
        # Divide o bloco em dois
        src_block = chrom_copy[0]
        split_point = random.randint(1, len(src_block) - 1)
        new_block = src_block[split_point:]
        chrom_copy[0] = src_block[:split_point]
        chrom_copy.append(new_block)
    else:
        # Escolher aleatoriamente entre move (50%) e merge (50%)
        if random.random() < 0.5:
            # Move: move viagem entre blocos
            src = random.randint(0, len(chrom_copy) - 1)
            if not chrom_copy[src]:
                return chrom_copy
            trip_idx = random.randint(0, len(chrom_copy[src]) - 1)
            trip_id = chrom_copy[src].pop(trip_idx)
            # BUG-GA-05 fix: dst=random.randint podia ser igual a src (no-op).
            # Agora escolhe dst diferente de src para garantir movimento real.
            other_idxs = [i for i in range(len(chrom_copy)) if i != src]
            if other_idxs:
                dst = random.choice(other_idxs)
            else:
                dst = src  # fallback: apenas um bloco, no-op inevitável
            chrom_copy[dst].append(trip_id)
        else:
            # Merge: combina dois blocos se factível
            if len(chrom_copy) >= 2:
                i, j = random.sample(range(len(chrom_copy)), 2)
                # Garantir i < j para remoção correta
                if i > j:
                    i, j = j, i

                # Verificar factibilidade se trip_map disponível
                should_merge = True
                if trip_map:
                    # Criar bloco combinado temporário para verificar factibilidade
                    combined_trip_ids = chrom_copy[i] + chrom_copy[j]
                    # Converter para Block para verificar factibilidade
                    combined_trips = [trip_map[tid] for tid in combined_trip_ids if tid in trip_map]
                    if combined_trips:
                        # Ordenar viagens por start_time
                        combined_trips.sort(key=lambda t: t.start_time)
                        v_params = {
                            "min_layover_minutes": min_gap,
                            "min_break_minutes": kwargs.get("min_break", 30),
                            "enforce_min_interval": kwargs.get("enforce_min_interval", False),
                            "connection_tolerance_minutes": kwargs.get("connection_tolerance", 0),
                        }
                        if not is_block_feasible(combined_trips, v_params):
                            should_merge = False

                if should_merge:
                    # Combinar blocos j em i
                    chrom_copy[i].extend(chrom_copy[j])
                    del chrom_copy[j]

        # Remove blocos vazios
        chrom_copy = [seq for seq in chrom_copy if seq]

    return _repair_chromosome(chrom_copy, all_tids, trip_map, **kwargs)  # Garante consistência


class GeneticVSP(BaseAlgorithm, IVSPAlgorithm):
    """
    GA para VSP com elitismo 10%, torneio k=3,
    cruzamento de blocos e mutação de realocação.
    """

    def __init__(self, vsp_params=None):
        super().__init__(
            name="genetic_vsp",
            time_budget_s=settings.hybrid_time_budget_seconds,
        )
        self.pop_size = settings.ga_population_size
        self.generations = settings.ga_generations
        self.mutation_rate = settings.ga_mutation_rate
        self.vsp_params = vsp_params or {}

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)
        random_seed = self.vsp_params.get("random_seed")
        if random_seed is not None:
            random.seed(int(random_seed))

        trip_map = _trips_by_id(trips)

        # Custos parametrizáveis
        fvc = float(self.vsp_params.get("fixed_vehicle_activation_cost", 800.0))
        icpm = float(self.vsp_params.get("idle_cost_per_minute", 0.5))
        max_work = float(self.vsp_params.get("max_work_minutes", 480.0))
        crew_cw = float(self.vsp_params.get("crew_cost_weight", fvc * 0.5))
        pair_break_penalty = float(self.vsp_params.get("pair_break_penalty", fvc * 1.25))
        paired_trip_bonus = float(self.vsp_params.get("paired_trip_bonus", fvc * 0.05))
        preferred_pairs = (
            build_preferred_pairs(
                trips,
                int(self.vsp_params.get("min_layover_minutes") if self.vsp_params.get("min_layover_minutes") is not None else 8),
                int(self.vsp_params.get("preferred_pair_window_minutes", 120) or 120),
            )
            if bool(self.vsp_params.get("preserve_preferred_pairs", True))
            else {}
        )
        hard_pairing_penalty = (
            float(self.vsp_params.get("hard_pairing_penalty", max(pair_break_penalty * 10.0, fvc * 25.0)))
            if bool(self.vsp_params.get("hard_pairing_vehicle_level", False))
            else 0.0
        )
        min_gap = int(self.vsp_params.get("min_layover_minutes") if self.vsp_params.get("min_layover_minutes") is not None else 8)

        # Parâmetros de conexão do vsp_params
        min_break = int(self.vsp_params.get("min_break_minutes", 30) or 30)
        enforce_min_interval = bool(self.vsp_params.get("enforce_min_interval", False))
        connection_tolerance = int(self.vsp_params.get("connection_tolerance_minutes", 0) or 0)
        same_depot_req = bool(self.vsp_params.get("same_depot_required", False))

        dhc = float(self.vsp_params.get("deadhead_cost_per_minute", 1.0))

        def fit_fn(c):
            return _fitness(
                c,
                trip_map,
                vehicle_types,
                fvc,
                icpm,
                max_work,
                crew_cw,
                preferred_pairs,
                pair_break_penalty,
                paired_trip_bonus,
                hard_pairing_penalty,
                min_gap,
                min_break,
                enforce_min_interval,
                connection_tolerance,
                dhc,
            )

        # Semente inicial — greedy já factível
        seed = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types)
        seed_chrom = _chromosome_from_blocks(seed.blocks)

        # Gera população inicial com diversidade real (mover trips entre blocos)
        all_tids = {tid for seq in seed_chrom for tid in seq}
        population: List[Chromosome] = [seed_chrom]
        for p in range(self.pop_size - 1):
            variant = _copy_chrom(seed_chrom)
            # Número crescente de perturbações para diversidade
            n_moves = min(1 + p, len(trips) // 3)
            for _ in range(n_moves):
                # Se só tem 1 bloco, temos que criar um novo bloco (split)
                if len(variant) == 1:
                    if len(variant[0]) <= 1:
                        break  # Não pode dividir bloco com 0 ou 1 viagem
                    # Divide o bloco em dois
                    src_block = variant[0]
                    split_point = random.randint(1, len(src_block) - 1)
                    new_block = src_block[split_point:]
                    variant[0] = src_block[:split_point]
                    variant.append(new_block)
                else:
                    src = random.randint(0, len(variant) - 1)
                    if not variant[src]:
                        continue
                    tid = variant[src].pop(random.randint(0, len(variant[src]) - 1))
                    dst = random.choice([i for i in range(len(variant)) if i != src])
                    variant[dst].append(tid)
            variant = [seq for seq in variant if seq]
            if not variant:
                variant = _copy_chrom(seed_chrom)
            variant = _repair_chromosome(
                variant,
                all_tids,
                trip_map,
                min_gap=min_gap,
                min_break=int(min_break) if min_break is not None else 30,
                enforce_min_interval=enforce_min_interval,
                connection_tolerance=connection_tolerance,
                same_depot_required=same_depot_req,
            )
            population.append(variant)

        best_chrom = _copy_chrom(seed_chrom)
        best_score = fit_fn(best_chrom)

        elitism_n = max(1, self.pop_size // 10)
        scores = [fit_fn(c) for c in population]

        for gen in range(self.generations):
            if self._check_timeout():
                break

            # Elitismo
            elite_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:elitism_n]
            new_pop: List[Chromosome] = [_copy_chrom(population[i]) for i in elite_idx]

            # Reprodução
            while len(new_pop) < self.pop_size:
                p1 = _tournament(population, scores)
                p2 = _tournament(population, scores)
                c1, c2 = _crossover(
                    p1,
                    p2,
                    trip_map,
                    min_gap=min_gap,
                    min_break=min_break,
                    enforce_min_interval=enforce_min_interval,
                    connection_tolerance=connection_tolerance,
                    same_depot_required=same_depot_req,
                )
                new_pop.append(
                    _mutate(
                        c1,
                        self.mutation_rate,
                        trip_map,
                        min_gap,
                        min_break=int(min_break) if min_break is not None else 30,
                        enforce_min_interval=enforce_min_interval,
                        connection_tolerance=connection_tolerance,
                        same_depot_required=same_depot_req,
                    )
                )
                if len(new_pop) < self.pop_size:
                    new_pop.append(
                        _mutate(
                            c2,
                            self.mutation_rate,
                            trip_map,
                            min_gap,
                            min_break=int(min_break) if min_break is not None else 30,
                            enforce_min_interval=enforce_min_interval,
                            connection_tolerance=connection_tolerance,
                            same_depot_required=same_depot_req,
                        )
                    )

            population = new_pop
            scores = [fit_fn(c) for c in population]
            gen_best_idx = max(range(len(scores)), key=lambda i: scores[i])
            gen_best_score = scores[gen_best_idx]
            if gen_best_score > best_score:
                best_score = gen_best_score
                best_chrom = _copy_chrom(population[gen_best_idx])

        blocks = _blocks_from_chromosome(best_chrom, trip_map, vehicle_types)
        sort_block_trips(blocks)

        # Repara blocos com deadhead inviável: divide em sub-blocos
        _next_id = max((b.id for b in blocks), default=0) + 1
        repaired: List[Block] = []
        for b in blocks:
            if not b.trips:
                continue
            cur_trips = [b.trips[0]]
            for t in b.trips[1:]:
                prev = cur_trips[-1]
                if not is_connection_feasible(
                    prev,
                    t,
                    min_layover=min_gap,
                    min_break=int(min_break) if min_break is not None else 30,
                    enforce_min_interval=enforce_min_interval,
                    connection_tolerance=connection_tolerance,
                ):
                    new_b = Block(id=_next_id, trips=list(cur_trips))
                    if b.vehicle_type_id is not None:
                        new_b.vehicle_type_id = b.vehicle_type_id
                    repaired.append(new_b)
                    _next_id += 1
                    cur_trips = [t]
                else:
                    cur_trips.append(t)
            last_b = Block(id=b.id, trips=cur_trips)
            if b.vehicle_type_id is not None:
                last_b.vehicle_type_id = b.vehicle_type_id
            repaired.append(last_b)
        blocks = repaired

        # Safety net: se GA ficou pior que greedy, usa greedy.
        # BUG-GA-01 (corrigido): comparação usava quick_cost_sorted que NÃO inclui
        # deadhead_cost_per_minute, enquanto _fitness usa quick_cost_from_trips que
        # INCLUI deadhead. Com deadhead alto (ex: R$10/min), o GA encontrava soluções
        # com menos deadhead (melhor por fitness), mas o safety net as descartava por
        # não contabilizar deadhead na comparação → GA sempre retornava o Greedy.
        # Fix: usar quick_cost_from_trips (mesma função que _fitness) em ambos os lados.
        def _blocks_to_seqs(blk_list):
            return [[t for t in b.trips] for b in blk_list if b.trips]

        ga_seqs = _blocks_to_seqs(blocks)
        seed_seqs = _blocks_to_seqs(seed.blocks)

        ga_cost = quick_cost_from_trips(ga_seqs, fvc, icpm, max_work, crew_cw, dhc) + preferred_pair_penalty(
            blocks,
            preferred_pairs,
            pair_break_penalty,
            paired_trip_bonus,
            hard_pairing_penalty,
        )
        greedy_cost = quick_cost_from_trips(seed_seqs, fvc, icpm, max_work, crew_cw, dhc) + preferred_pair_penalty(
            seed.blocks,
            preferred_pairs,
            pair_break_penalty,
            paired_trip_bonus,
            hard_pairing_penalty,
        )
        if ga_cost > greedy_cost:
            blocks = deepcopy(seed.blocks)

        return VSPSolution(
            blocks=blocks,
            algorithm=self.name,
            iterations=self.generations,
            elapsed_ms=self._elapsed_ms(),
        )
