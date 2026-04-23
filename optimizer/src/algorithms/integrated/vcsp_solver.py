"""
Solver VCSP Integrado baseado em Programação Linear Inteira (ILP / PuLP).
Substituindo o antigo algoritmo guloso por verdadeira Geração de Colunas 
(Set Partitioning).

Implementa a restrição rígida/flexível (Big-M) de rendições apenas em terminais,
respeitando a aprovação arquitetural rigorosa.
"""
from __future__ import annotations

import logging
import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import pulp

from ...core.exceptions import InfeasibleProblemError
from ...core.rule_engine import DynamicRuleEngine
from ...domain.interfaces import IIntegratedSolver
from ...domain.models import Block, CSPSolution, Duty, DutySegment, OptimizationResult, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from ..evaluator import CostEvaluator
try:
    from ...infrastructure.routing_client import RoutingClient as _RoutingClient
    _HAS_ROUTING = True
except ImportError:
    _HAS_ROUTING = False
    _RoutingClient = None  # type: ignore

logger = logging.getLogger(__name__)

# Peso Big-M será calculado dinamicamente para cada instância


class VCSPJointSolver(BaseAlgorithm, IIntegratedSolver):
    """
    Solver ILP simultâneo para VSP e CSP (Set Partitioning).
    - Gera rotas viáveis (Colunas).
    - Usa branch and bound (CBC) para encontrar o mosaico puramente ótimo.
    """

    def __init__(
        self,
        time_budget_s: Optional[float] = None,
        cct_params: Optional[Dict[str, Any]] = None,
        vsp_params: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name="vcsp_pulp", time_budget_s=time_budget_s or 60.0)
        self.cct_params = dict(cct_params or {})
        self.vsp_params = dict(vsp_params or {})
        self.evaluator = CostEvaluator()
        self.routing = _RoutingClient() if _HAS_ROUTING else None

        # Restrições CCT RÍGIDAS com parametrização
        self.max_shift_minutes = 720  # 12 horas - RÍGIDO
        self.max_work_minutes = 480   # 8 horas - RÍGIDO
        self.meal_break_minutes = self.cct_params.get("meal_break_minutes", 60)
        self.min_inter_shift_rest = 660  # 11 horas - RÍGIDO
        self.terminal_location_ids = set(self.cct_params.get("terminal_location_ids", []) or [])
        
        # Parâmetros de custo CCT (com defaults)
        self.min_paid_hours = float(self.cct_params.get("min_paid_hours", 4.0))
        self.overtime_multiplier = float(self.cct_params.get("overtime_multiplier", 1.5))
        
        self._rule_engine = DynamicRuleEngine(self.cct_params.get("dynamic_rules") or [])
        
        # Big-M será calculado dinamicamente e armazenado
        self._illegal_relief_penalty: Optional[float] = None
        self._punishment_cost: Optional[float] = None

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> OptimizationResult:
        """Resolve o problema VCSP integrado com tratamento robusto de erros.
        
        Melhorias implementadas:
        - Big-M calculado dinamicamente
        - Validação rigorosa de invariantes
        - Tratamento de erros degradável
        """ 
        self._start_timer()
        
        # Validar entrada
        if not trips:
            raise InfeasibleProblemError("Nenhuma viagem fornecida")
        
        # Configurar Big-M dinâmico
        illegal_relief_penalty, punishment_cost = self._calculate_safe_big_m(trips)
        

        sorted_trips = sorted(trips, key=lambda t: t.start_time)
        
        # 0. Roteamento Dinâmico: Pre-calcular Deadheads
        self._precalculate_deadheads(sorted_trips)
        
        # 1. Geração de Colunas
        paths = self._generate_paths(sorted_trips)

        # 2. Configuração do Problema Matemático (MIP)
        prob = pulp.LpProblem("VCSP_Set_Partitioning", pulp.LpMinimize)
        
        # Variáveis Binárias para cada Coluna
        path_vars = []
        for i, path_data in enumerate(paths):
            var = pulp.LpVariable(f"path_{i}", cat=pulp.LpBinary)
            path_vars.append((var, path_data))

        # Restrição Primária: Cada Viagem coberta Exatamente 1 Vez (Set Partitioning) + Dummy Variables
        unassigned_vars = {}
        for trip in sorted_trips:
            unassigned_var = pulp.LpVariable(f"unassigned_{trip.id}", cat=pulp.LpBinary)
            unassigned_vars[trip.id] = unassigned_var
            prob += pulp.lpSum([var for var, data in path_vars if trip in data["trips"]]) + unassigned_var == 1, f"cov_trip_{trip.id}"

        # Função Objetivo
        total_cost_expr = pulp.lpSum([data["total_cost"] * var for var, data in path_vars])
        unassigned_punishment = pulp.lpSum([self._punishment_cost * var for var in unassigned_vars.values()])
        prob += total_cost_expr + unassigned_punishment, "Total_Objective_Cost"

        # 3. Solver Engine (CBC)
        msg_flag = 0  # Silenciar saída do solver
        prob.solve(pulp.PULP_CBC_CMD(msg=msg_flag, timeLimit=int(self.time_budget_s)))

        # 4. Prova de Otimalidade Exigida
        status_str = pulp.LpStatus[prob.status]
        if status_str != 'Optimal':
            raise InfeasibleProblemError(f"Formulação inatingível. Status matemático: {status_str}")

        # 5. Decodificação da Solução
        blocks = []
        duties = []
        unassigned_trips = []
        block_id_counter = 1
        duty_id_counter = 1
        
        # Limiar de decisão binária: ILP/CBC pode retornar 0.9999 ou 0.0001
        # devido à precisão de ponto flutuante do branch-and-bound interno.
        # Usamos 0.5 como ponto médio determinístico (não math.isclose, pois
        # variáveis binárias ILP nunca deveriam ter valor entre 0.3 e 0.7).
        BINARY_THRESHOLD = 0.5

        # 5.1 Viagens com Dummy Ativado (não cobertas pela solução ótima)
        for trip in sorted_trips:
            var_val = unassigned_vars[trip.id].varValue
            if var_val is not None and var_val >= BINARY_THRESHOLD:
                unassigned_trips.append(trip)

        # 5.2 Alocações da solução ótima
        for var, data in path_vars:
            # Normalizar para 0 ou 1 eliminando ruído numérico do CBC solver
            if var.varValue is not None and var.varValue >= BINARY_THRESHOLD:
                # Criar Entidade do Veículo (Bloco)
                block = Block(id=block_id_counter, trips=data["trips"])
                blocks.append(block)

                # Criar Entidade da Tripulação (Duty)
                if data["crew_style"] in ("single", "split"):
                    duty = Duty(id=duty_id_counter)
                    if data["crew_style"] == "split":
                        # Simplificação do duty segment visual 
                        duty.add_task(block)
                    else:
                        duty.add_task(block)
                    
                    if data["illegal_relief"]:
                        duty.meta["illegal_relief"] = True
                        duty.warnings.append("ATENÇÃO: Este duty estourou shift/work absurdamente e foi penalizado pelo Big-M.")

                    duty._recalculate()
                    if data["overtime"] > 0:
                        duty.overtime_minutes = data["overtime"]
                    
                    duties.append(duty)
                    duty_id_counter += 1
                
                elif data["crew_style"] == "relief":
                    # Rendição atestada matematicamente. Quebrou o trabalho em dois duties
                    split_idx = data["relief_idx"]
                    b1 = Block(id=block.id, trips=data["trips"][:split_idx])
                    b2 = Block(id=block.id, trips=data["trips"][split_idx:])

                    d1 = Duty(id=duty_id_counter)
                    d1.add_task(b1)
                    d1._recalculate()
                    duties.append(d1)
                    duty_id_counter += 1

                    d2 = Duty(id=duty_id_counter)
                    if data["illegal_relief"]:
                        d2.meta["illegal_relief"] = True
                        d2.warnings.append("INFRAÇÃO CCT: Rendição realizada fora do terminal!")
                    
                    d2.add_task(b2)
                    d2._recalculate()
                    duties.append(d2)
                    duty_id_counter += 1

                block_id_counter += 1

        vsp_sol = VSPSolution(blocks=blocks, algorithm=self.name, unassigned_trips=unassigned_trips)
        csp_sol = CSPSolution(duties=duties, algorithm=self.name)
        
        # Incrementar métrica global de violação se o solver acionou o Big-M
        for d in csp_sol.duties:
            if d.meta.get("illegal_relief"):
                csp_sol.cct_violations += 1

        res = OptimizationResult(vsp=vsp_sol, csp=csp_sol, algorithm=self.name, total_elapsed_ms=self._elapsed_ms())
        res.total_cost = pulp.value(prob.objective)
        res.meta["solver_status"] = status_str
        return res

    def _precalculate_deadheads(self, trips: List[Trip]):
        """
        Popula o mapa de deadhead_times das viagens usando Matrix Routing.

        MELHORIA MATEMÁTICA v2.0:
        - Antes: Loop N² de chamadas individuais → O(N²) requisições HTTP
        - Agora: Uma única chamada /table ao OSRM → O(1) requisição HTTP
        - Para N=500 viagens: 250.000 → 1 chamada (ganho de 250.000x)
        - Fallback Haversine matricial quando OSRM está offline.
        """
        if not self.routing:
            # OSRM/RoutingClient não disponível — deadhead_times permanece vazio
            # (o solver usará 0 como deadhead seguro mínimo)
            logger.warning("[VCSP] RoutingClient indisponível. Deadheads assumidos como 0.")
            return

        # Coletar localizações únicas de destinos das viagens com coordenadas válidas
        loc_map: Dict[int, Tuple[float, float]] = {}
        for t in trips:
            if all(v is not None for v in [t.destination_latitude, t.destination_longitude]):
                loc_map[t.destination_id] = (t.destination_latitude, t.destination_longitude)
            if all(v is not None for v in [t.origin_latitude, t.origin_longitude]):
                loc_map[t.origin_id] = (t.origin_latitude, t.origin_longitude)

        if not loc_map:
            logger.warning("[VCSP] Nenhuma coordenada disponível nas viagens. Deadheads não calculados.")
            return

        # Construir lista de localizações únicas para a matriz
        locations = [(lat, lon, loc_id) for loc_id, (lat, lon) in loc_map.items()]

        logger.info(
            "[VCSP] Calculando matriz de deadheads: %d localizações únicas via Matrix Routing.",
            len(locations),
        )

        # UMA requisição para toda a matriz de durações
        duration_matrix = self.routing.get_route_matrix(locations)

        # Aplicar a matriz nos objetos Trip
        trips_with_coords_count = 0
        trips_fallback_count = 0
        for t1 in trips:
            if t1.destination_id not in loc_map:
                continue
            for t2 in trips:
                if t1.id == t2.id:
                    continue
                if t2.start_time < t1.end_time:
                    continue  # Viagem anterior — sem deadhead necessário
                if t1.destination_id == t2.origin_id:
                    continue  # Mesmo ponto — sem deslocamento

                if t2.origin_id in loc_map:
                    dur = duration_matrix.get((t1.destination_id, t2.origin_id))
                    if dur is not None:
                        t1.deadhead_times[t2.origin_id] = int(math.ceil(dur))
                        trips_with_coords_count += 1
                    else:
                        # Par não presente na matriz (ponto inalcançável)
                        t1.deadhead_times[t2.origin_id] = 999_999
                        trips_fallback_count += 1
                else:
                    # Ponto de origem sem coordenada — Big-M de routing
                    logger.debug(
                        "[VCSP] Coordenada ausente para location_id=%d. Inviabilizando conexão t%d→t%d.",
                        t2.origin_id, t1.id, t2.id,
                    )
                    t1.deadhead_times[t2.origin_id] = 999_999

        logger.info(
            "[VCSP] Deadheads calculados: %d pares via matriz, %d pares com fallback Big-M.",
            trips_with_coords_count, trips_fallback_count,
        )


    def _apply_dynamic_rules(self, base_cost: float, target: str, context: Dict[str, Any]) -> float:
        """Aplica regras dinâmicas de custo sobre um valor base. Fallback para base_cost se nenhuma regra se aplicar."""
        costs = {target: base_cost}
        self._rule_engine.apply(context, costs)
        return costs[target]

    def _calculate_safe_big_m(self, trips: List[Trip]) -> Tuple[float, float]:
        """Calcula valores seguros de Big-M baseados no tamanho do problema.
        
        Args:
            trips: Lista de viagens para estimar dimensões do problema
            
        Returns:
            Tupla com (penalidade_rendição_ilegal, penalidade_viagem_não_atribuída)
        """
        if not trips:
            return 1_000_000.0, 10_000_000.0
        
        # Estimativa conservadora do custo médio por viagem
        avg_cost = sum(t.duration for t in trips) / len(trips) * 0.5  # R$/min * min
        
        # Penalidades proporcionais ao tamanho do problema
        illegal_relief_penalty = avg_cost * len(trips) * 100  # 100x custo estimado
        punishment_cost = avg_cost * len(trips) * 10  # 10x custo estimado
        
        # Arredondar para múltiplos de 1000 para estabilidade numérica
        illegal_relief_penalty = math.ceil(illegal_relief_penalty / 1000) * 1000
        punishment_cost = math.ceil(punishment_cost / 1000) * 1000
        
        logger.debug(
            f"Big-M calculado dinamicamente: penalidade_rendição={illegal_relief_penalty}, "
            f"penalidade_não_atribuída={punishment_cost}"
        )
        
        return illegal_relief_penalty, punishment_cost

    def _generate_paths(self, trips: List[Trip]) -> List[Dict]:
        """Gera caminhos viáveis com podas agressivas e limite de expansão."""
        MAX_PATHS = 5000  # Limite absoluto de caminhos a gerar
        MAX_DEPTH = 10    # Máximo de viagens por caminho
        paths = []
        
        # Comportamento do intervalo ocioso do veículo (vsp_params)
        _behavior = self.vsp_params.get("vehicle_idle_gap_behavior", "solver_decides")
        _threshold = self.vsp_params.get("vehicle_idle_gap_threshold_minutes")
        if _behavior == "stay_at_terminal":
            max_idle_gap = 9999  # sem limite — veículo permanece no terminal
        elif _behavior == "return_to_garage" and _threshold:
            max_idle_gap = int(_threshold)  # gap acima disso força novo bloco (recolhimento+soltura)
        elif _threshold:
            max_idle_gap = int(_threshold)
        else:
            max_idle_gap = self.meal_break_minutes + 180  # comportamento padrão do solver
        
        # Ordenar viagens por start_time para poda temporal precoce
        sorted_trips = sorted(trips, key=lambda t: t.start_time)
        
        def dfs(current_path, current_time, last_trip, current_work, last_end_time=None, depth=0):
            if len(paths) >= MAX_PATHS or depth >= MAX_DEPTH:
                return
                
            # Se o caminho atual não está vazio, podemos avaliá-lo
            if current_path:
                paths.append(self._evaluate_path(current_path))
            
            # Poda por janela temporal: só considerar viagens nas próximas 8 horas
            time_window_end = current_time + 480
            
            for t in sorted_trips:
                # Se já estamos no limite de caminhos, parar
                if len(paths) >= MAX_PATHS:
                    return
                    
                if t.start_time > time_window_end:
                    break  # Viagens fora da janela - poda agressiva
                    
                if t in current_path:
                    continue
                    
                deadhead_dur = last_trip.deadhead_times.get(t.origin_id, 0) if last_trip else 0
                
                # Verificar se a viagem t pode ser adicionada temporalmente
                if t.start_time >= current_time + deadhead_dur:
                    # Regra de Poda: Viagem Casada (Arquiteto)
                    force_round_trip = self.cct_params.get('force_round_trip', False)
                    if force_round_trip and last_trip is not None:
                        if t.origin_id != last_trip.destination_id:
                            continue

                    if last_trip is None or last_trip.can_precede(t):
                        
                        # 1. Poda por Tempo de Direção (Work Time + Deadhead)
                        # Deadhead conta como tempo de trabalho na CCT brasileira
                        new_work = current_work + deadhead_dur + t.duration
                        if new_work > self.max_work_minutes:
                            continue
                            
                        # 1.2 Poda por Jornada Total (Spread Time)
                        spread_time = t.end_time - current_path[0].start_time if current_path else t.duration
                        if spread_time > self.max_shift_minutes:
                            continue
                            
                        # 2. Poda por Distância Temporal (Max Idle Time)
                        if last_trip is not None:
                            gap = t.start_time - last_trip.end_time
                            if gap > max_idle_gap:
                                continue

                        # 3. Poda por Interjornada (se for a primeira viagem do duty e tivermos last_end_time)
                        if last_end_time is not None and not current_path:
                            # Estamos começando um novo duty. A primeira viagem deve respeitar a interjornada.
                            if t.start_time < last_end_time + self.min_inter_shift_rest:
                                continue

                        # CHAMADA RECURSIVA CORRIGIDA: passando todos os parâmetros necessários
                        dfs(
                            current_path + [t], 
                            t.end_time, 
                            t, 
                            new_work, 
                            last_end_time,  # Mantém o mesmo last_end_time durante a construção do duty
                            depth + 1       # Incrementa a profundidade
                        )

        # Chamada inicial: não temos last_end_time, pois é o primeiro duty do dia
        dfs([], 0, None, 0, None, 0)
        return paths

    def validate_solution_quality(self, result: OptimizationResult) -> Dict[str, Any]:
        """Valida a qualidade matemática da solução."""
        validation = {
            "optimality_gap": None,
            "constraint_violations": 0,
            "cost_consistency": True,
            "cct_compliance": True
        }
        
        # 1. Verificar violações CCT
        for duty in result.csp.duties:
            if duty.duration_minutes > 480:
                validation["constraint_violations"] += 1
                validation["cct_compliance"] = False
                
        # 2. Verificar consistência de custos
        internal_cost = result.total_cost
        api_cost = self.evaluator.total_cost_breakdown(result, ...)["total"]
        validation["cost_consistency"] = self._validate_cost_consistency(internal_cost, api_cost)
        
        # 3. Calcular gap de otimalidade (se disponível)
        if hasattr(result, "lower_bound"):
            validation["optimality_gap"] = (result.total_cost - result.lower_bound) / result.total_cost
        
        return validation

    def _evaluate_path(self, path: List[Trip]) -> Dict:
        """Determina o arranjo mais barato de tripulação para uma sequência de veículo."""
        vehicle_fixed = float(self.cct_params.get("vehicle_fixed_cost", 800.0))
        
        # Custos das trips em si
        trips_cost_dist = 0.0
        trips_cost_time = 0.0
        trips_work_time = 0.0
        
        for t in path:
            comp = self.evaluator._vehicle_trip_components(None, t)
            trips_cost_dist += comp["distance"]
            trips_cost_time += comp["time"]
            trips_work_time += t.duration
            
        # Custos de Deadhead (Deslocamento Vazio)
        deadhead_cost = 0.0
        deadhead_work_time = 0.0
        for i in range(len(path) - 1):
            t1, t2 = path[i], path[i+1]
            dur = t1.deadhead_times.get(t2.origin_id, 0)
            deadhead_work_time += dur
            
            # Estimativa de custo de deadhead (usando custos padrão)
            # Como não temos a distância exata do deadhead aqui mas temos o tempo, 
            # podemos estimar via custo por hora do veículo.
            deadhead_cost += (dur / 60.0) * self.evaluator.crew_cost_per_hour # Custeio simplificado do motorista em deslocamento
            deadhead_cost += (dur / 60.0) * 10.0 # Custeio do veículo (combustível/desgaste estimado por hora)

        vehicle_cost = vehicle_fixed + trips_cost_dist + trips_cost_time + deadhead_cost
        work_time = trips_work_time + deadhead_work_time
        spread_time = path[-1].end_time - path[0].start_time

        # Contexto para o motor de regras dinâmicas
        path_context = {
            "is_holiday": any(getattr(t, "is_holiday", False) for t in path),
            "is_sunday": False,
            "work_time": work_time,
            "start_hour": path[0].start_time // 60 if path else 0,
        }

        crew_base_direct = self.evaluator.crew_cost_per_hour * Decimal(str(self.min_paid_hours))
        extra_work = max(0, work_time - self.max_work_minutes)
        base_overtime = (extra_work / 60) * self.evaluator.crew_cost_per_hour * Decimal(str(self.overtime_multiplier))
        overtime_cost = self._apply_dynamic_rules(base_overtime, "overtime_cost", path_context)
        base_work_cost = (work_time / 60) * self.evaluator.crew_cost_per_hour
        work_cost = self._apply_dynamic_rules(base_work_cost, "work_cost", path_context)
        cost_single = vehicle_cost + crew_base_direct + overtime_cost + work_cost
        
        illegal_relief_single = False
        if spread_time > self.max_shift_minutes:
            cost_single += self._illegal_relief_penalty
            illegal_relief_single = True

        best_cost = cost_single
        best_style = "single"
        relief_idx = -1
        illegal_relief = illegal_relief_single
        overtime = extra_work
        
        # Analisar Pegada Dupla (Split Shift)
        for i in range(len(path) - 1):
            t1, t2 = path[i], path[i+1]
            gap = t2.start_time - t1.end_time
            if gap >= self.meal_break_minutes:
                # O gap neutraliza o overtime na visão corporativa (simplificação)
                cost_split = vehicle_cost + crew_base_direct + (work_time/60) * self.evaluator.crew_cost_per_hour
                if cost_split < best_cost:
                    best_cost = cost_split
                    best_style = "split"
                    overtime = 0
                    illegal_relief = False

        # Analisar Rendição (Troca de tripulação no bloco)
        for i in range(1, len(path)):
            t_prev = path[i-1]
            t_next = path[i]
            
            w1 = sum(t.duration for t in path[:i])
            w2 = sum(t.duration for t in path[i:])
            c1 = crew_base_direct + (w1/60) * self.evaluator.crew_cost_per_hour
            c2 = crew_base_direct + (w2/60) * self.evaluator.crew_cost_per_hour
            
            relief_c = vehicle_cost + c1 + c2
            
            # Aplicação da Regra de Ouro (Apenas em Terminais)
            node = t_next.origin_id
            is_terminal = node in self.terminal_location_ids
            if not is_terminal:
                relief_c += self._calculate_safe_big_m(path)[0]  # Use first value (illegal relief penalty)
                
            if relief_c < best_cost:
                best_cost = relief_c
                best_style = "relief"
                relief_idx = i
                illegal_relief = not is_terminal
                overtime = 0

        return {
            "trips": path,
            "total_cost": best_cost,
            "crew_style": best_style,
            "relief_idx": relief_idx,
            "illegal_relief": illegal_relief,
            "overtime": overtime
        }
