"""
Avaliador de custo de soluções VSP e CSP.
Função objetivo: custo_frota + custo_tripulação + penalidade_violações

NOTA DE PRECISÃO: Todos os cálculos internos agora usam Decimal para evitar
drift de ponto flutuante. Arredondamento apenas na saída final.

Melhorias implementadas:
- Precisão decimal em todos os cálculos monetários
- Big-M dinâmico baseado no tamanho do problema
- Cache sincronizado com parâmetros de custo
- Tratamento robusto de erros
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, List

from ..core.config import get_settings
from ..core.rule_engine import DynamicRuleEngine
from ..domain.interfaces import ICostEvaluator
from ..domain.models import (
    Block,
    CSPSolution,
    OptimizationResult,
    VehicleType,
    VSPSolution,
)

# Configurar contexto decimal para alta precisão
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

settings = get_settings()

# Custo horário padrão caso o tipo de veículo não informe custo de tripulante
_DEFAULT_CREW_COST_PER_HOUR = Decimal('25.0')
_CCT_VIOLATION_PENALTY = Decimal('500.0')   # multa por violação de CCT (por ocorrência)
_LONG_UNPAID_BREAK_LIMIT_MINUTES = 90
_LONG_UNPAID_BREAK_PENALTY_WEIGHT = Decimal('0.05')
_DEFAULT_OVERTIME_EXTRA_PCT = Decimal('0.5')


def _R(v) -> float:
    """Converte para Decimal antes de arredondar, aceitando float ou Decimal."""
    return float(Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class CostEvaluator(ICostEvaluator):
    """Calcula o custo total de uma solução com precisão decimal."""

    def __init__(
        self,
        crew_cost_per_hour: float = float(_DEFAULT_CREW_COST_PER_HOUR),
        violation_penalty: float = float(_CCT_VIOLATION_PENALTY),
        long_unpaid_break_limit_minutes: int = _LONG_UNPAID_BREAK_LIMIT_MINUTES,
        long_unpaid_break_penalty_weight: float = float(_LONG_UNPAID_BREAK_PENALTY_WEIGHT),
        idle_cost_per_minute: float = 0.25,
        overtime_extra_pct: float = float(_DEFAULT_OVERTIME_EXTRA_PCT),
    ):
        # Converter todos os parâmetros para Decimal
        self.crew_cost_per_hour = Decimal(str(crew_cost_per_hour))
        self.violation_penalty = Decimal(str(violation_penalty))
        self.long_unpaid_break_limit_minutes = max(0, int(long_unpaid_break_limit_minutes))
        self.long_unpaid_break_penalty_weight = Decimal(str(long_unpaid_break_penalty_weight))
        self.idle_cost_per_minute = Decimal(str(idle_cost_per_minute))
        self.overtime_extra_pct = Decimal(str(overtime_extra_pct))
        self._dynamic_rules: list = []  # Populado externamente via set_dynamic_rules()
        
        # Pesos de custo dinâmicos
        self.cost_vehicle = Decimal(str(settings.default_vehicle_fixed_cost))
        self.cost_km = Decimal(str(settings.default_cost_per_km))
        self.cost_duty = Decimal('0.0')  # Default 0 para compatibilidade

    def set_costs(self, cost_vehicle: float = 1000.0, cost_km: float = 1.0, cost_duty: float = 500.0) -> None:
        """Define os pesos de custo dinâmicos recebidos via API."""
        self.cost_vehicle = Decimal(str(cost_vehicle))
        self.cost_km = Decimal(str(cost_km))
        self.cost_duty = Decimal(str(cost_duty))

    def _to_decimal(self, value: Any) -> Decimal:
        """Converte qualquer valor para Decimal de forma segura."""
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal('0.0')
        return Decimal(str(value))

    def _long_unpaid_break_penalty(self, unpaid_break_minutes: int) -> Decimal:
        """Piecewise-linear penalty.

        Faixas após o limite base:
        - primeiros 30 min de excesso: 1x peso
        - próximos 60 min: 3x peso
        - acima disso: 10x peso
        """
        excess = max(0, int(unpaid_break_minutes) - self.long_unpaid_break_limit_minutes)
        if excess <= 0:
            return Decimal('0.0')

        tier1 = min(excess, 30)
        tier2 = min(max(0, excess - 30), 60)
        tier3 = max(0, excess - 90)
        return self.long_unpaid_break_penalty_weight * Decimal(
            tier1 * 1.0
            + tier2 * 3.0
            + tier3 * 10.0
        )

    def set_dynamic_rules(self, rules: list) -> None:
        """Define regras dinâmicas para esta instância do avaliador.

        Chamado pelo OptimizerService após receber os cct_params do payload.
        As regras são compiladas uma única vez pelo DynamicRuleEngine e
        aplicadas em cada duty durante o csp_cost_breakdown.

        Se rules estiver vazio ou None, o motor não faz nada (zero impacto).
        """
        self._dynamic_rules = list(rules) if rules else []

    # ── Frota ─────────────────────────────────────────────────────────────────

    def _vehicle_trip_components(self, vt: VehicleType | None, trip) -> Dict[str, Decimal]:
        if vt:
            return {
                "distance": self._to_decimal(vt.cost_per_km) * self._to_decimal(trip.distance_km),
                "time": self._to_decimal(vt.cost_per_hour) * (self._to_decimal(trip.duration) / Decimal('60.0')),
            }
        return {
            "distance": self._to_decimal(trip.distance_km) * self.cost_km,
            "time": (self._to_decimal(trip.duration) / Decimal('60.0')) * self._to_decimal(settings.default_cost_per_hour),
        }

    def vsp_cost_breakdown(self, solution: VSPSolution, vehicle_types: List[VehicleType]) -> Dict[str, Any]:
        vt_map: Dict[int, VehicleType] = {vt.id: vt for vt in vehicle_types}
        blocks: List[Dict[str, Any]] = []
        activation = Decimal('0.0')
        connection = Decimal('0.0')
        distance = Decimal('0.0')
        time = Decimal('0.0')
        idle_cost = Decimal('0.0')

        for block in solution.blocks:
            vt = vt_map.get(block.vehicle_type_id or 0)  # type: ignore[arg-type]
            block_activation = self._to_decimal(
                block.meta.get(
                    "activation_cost",
                    self.cost_vehicle if not vt else Decimal(str(vt.fixed_cost)),
                )
            )
            block_connection = self._to_decimal(block.meta.get("connection_cost", 0.0))
            block_distance = Decimal('0.0')
            block_time = Decimal('0.0')
            start_buffer = self._to_decimal(max(0, int(block.meta.get("start_buffer_minutes", 0) or 0)))
            end_buffer = self._to_decimal(max(0, int(block.meta.get("end_buffer_minutes", 0) or 0)))
            has_boundary_buffers = "start_buffer_minutes" in block.meta or "end_buffer_minutes" in block.meta
            block_idle_cost = (start_buffer + end_buffer) * self.idle_cost_per_minute if has_boundary_buffers else Decimal('0.0')

            for trip in block.trips:
                components = self._vehicle_trip_components(vt, trip)
                block_distance += components["distance"]  # Já é Decimal
                block_time += components["time"]          # Já é Decimal
                if not has_boundary_buffers:
                    idle_before = self._to_decimal(trip.idle_before_minutes)
                    idle_after = self._to_decimal(trip.idle_after_minutes)
                    block_idle_cost += (idle_before + idle_after) * self.idle_cost_per_minute

            activation += block_activation
            connection += block_connection
            distance += block_distance
            time += block_time
            idle_cost += block_idle_cost
            blocks.append(
                {
                    "block_id": block.id,
                    "vehicle_type_id": block.vehicle_type_id,
                    "num_trips": len(block.trips),
                    "activation": _R(block_activation),
                    "connection": _R(block_connection),
                    "distance": _R(block_distance),
                    "time": _R(block_time),
                    "idle_cost": _R(block_idle_cost),
                    "total": _R(block_activation + block_connection + block_distance + block_time + block_idle_cost),
                    "start_buffer_minutes": start_buffer,
                    "end_buffer_minutes": end_buffer,
                    "advisory_idle_proxy_cost": _R(block_idle_cost),
                }
            )

        total = activation + connection + distance + time + idle_cost
        return {
            "total": _R(total),
            "activation": _R(activation),
            "connection": _R(connection),
            "distance": _R(distance),
            "time": _R(time),
            "idle_cost": _R(idle_cost),
            "num_blocks": len(solution.blocks),
            "num_unassigned_trips": len(solution.unassigned_trips),
            "advisory_idle_proxy_cost": _R(idle_cost),
            "advisory_infeasibility_penalty": _R(self.infeasibility_penalty(solution)),
            "blocks": blocks,
        }

    def vsp_cost(self, solution: VSPSolution, vehicle_types: List[VehicleType]) -> float:
        """
        Custo total da frota:
          Σ_blocos f_k + Σ_conexões c_ij + Σ_viagens(custo_km + custo_hora)
        """
        return float(self.vsp_cost_breakdown(solution, vehicle_types)["total"])

    # ── Tripulação ────────────────────────────────────────────────────────────

    def csp_cost_breakdown(self, solution: CSPSolution) -> Dict[str, Any]:
        duties: List[Dict[str, Any]] = []
        
        # Acumuladores em Decimal
        work_cost = Decimal('0.0')
        guaranteed_cost = Decimal('0.0')
        waiting_cost = Decimal('0.0')
        overtime_cost = Decimal('0.0')
        long_unpaid_break_penalty = Decimal('0.0')
        nocturnal_extra = Decimal('0.0')
        holiday_extra = Decimal('0.0')
        cct_penalties = Decimal('0.0')

        # ── Compilar regras dinâmicas UMA VEZ (reutilizada em todos os duties) ─
        rule_engine = DynamicRuleEngine(self._dynamic_rules)
        has_dynamic_rules = rule_engine.rule_count > 0
        dynamic_adjustments_total = Decimal('0.0')

        for duty in solution.duties:
            duty_work_cost = (self._to_decimal(duty.work_time) / Decimal('60.0')) * self.crew_cost_per_hour
            guaranteed_minutes = max(
                self._to_decimal(duty.work_time),
                self._to_decimal(duty.meta.get("guaranteed_minutes", duty.work_time) or duty.work_time),
            )
            paid_minutes = max(self._to_decimal(duty.paid_minutes or 0), guaranteed_minutes)
            guaranteed_extra_minutes = max(Decimal('0.0'), guaranteed_minutes - self._to_decimal(duty.work_time))
            paid_waiting_minutes = max(Decimal('0.0'), paid_minutes - guaranteed_minutes)
            duty_guaranteed_cost = (guaranteed_extra_minutes / Decimal('60.0')) * self.crew_cost_per_hour
            duty_waiting_cost = (paid_waiting_minutes / Decimal('60.0')) * self.crew_cost_per_hour
            duty_overtime_cost = (
                (self._to_decimal(max(0, int(duty.overtime_minutes or 0))) / Decimal('60.0'))
                * self.crew_cost_per_hour
                * self._to_decimal(duty.meta.get("overtime_extra_pct", self.overtime_extra_pct))
            )
            unpaid_break_minutes = max(
                Decimal('0.0'),
                self._to_decimal(duty.meta.get("unpaid_break_total_minutes", max(0, duty.spread_time - duty.work_time)) or 0),
            )
            duty_long_break_penalty = self._long_unpaid_break_penalty(unpaid_break_minutes)
            duty_nocturnal_extra = Decimal('0.0')
            if duty.nocturnal_minutes > 0:
                duty_nocturnal_extra = (
                    (self._to_decimal(duty.nocturnal_minutes) / Decimal('60.0'))
                    * self.crew_cost_per_hour
                    * self._to_decimal(duty.meta.get("nocturnal_extra_pct", Decimal('0.20')))
                )
            duty_holiday_extra = Decimal('0.0')
            if duty.meta.get("holiday_extra_pct"):
                duty_holiday_extra = (
                    (self._to_decimal(duty.work_time) / Decimal('60.0'))
                    * self.crew_cost_per_hour
                    * self._to_decimal(duty.meta.get("holiday_extra_pct", Decimal('0.0')))
                )
            duty_cct_penalties = (duty.rest_violations + duty.shift_violations) * self.violation_penalty
            if duty.meta.get("illegal_relief"):
                duty_cct_penalties += 1_000_000.0  # Big-M penalty for illegal terminal relief

            # ── REGRAS DINÂMICAS: aplicar modificadores APÓS custos base ──────
            # Custos base estão todos calculados. As regras dinâmicas atuam como
            # modificadores (multiply, add, subtract, set) sobre os valores.
            # Se nenhuma regra está definida, este bloco é um no-op.
            if has_dynamic_rules:
                # Construir contexto do duty de forma BLINDADA (evita AttributeError)
                duty_context: Dict[str, Any] = {
                    # Campos temporais
                    "work_time": getattr(duty, "work_time", 0),
                    "spread_time": getattr(duty, "spread_time", 0),
                    "paid_minutes": getattr(duty, "paid_minutes", 0),
                    "overtime_minutes": getattr(duty, "overtime_minutes", 0),
                    "nocturnal_minutes": getattr(duty, "nocturnal_minutes", 0),
                    "start_time": getattr(duty, "start_time", None),
                    "end_time": getattr(duty, "end_time", None),
                    "start_hour": (getattr(duty, "start_time", 0) // 60) if getattr(duty, "start_time", None) is not None else 0,
                    "end_hour": (getattr(duty, "end_time", 0) // 60) if getattr(duty, "end_time", None) is not None else 0,

                    # Campos de violação
                    "rest_violations": getattr(duty, "rest_violations", 0),
                    "shift_violations": getattr(duty, "shift_violations", 0),
                    "continuous_driving_violation": getattr(duty, "continuous_driving_violation", False),

                    # Campos de meta do duty (com fallback para inspeção de viagens)
                    "is_holiday": bool(
                        getattr(duty, "meta", {}).get("is_holiday", False)
                        or any(getattr(t, "is_holiday", False) for t in getattr(duty, "all_trips", getattr(duty, "trips", [])))
                    ),
                    "is_sunday": bool(
                        getattr(duty, "meta", {}).get("is_sunday", False)
                        or any(getattr(t, "service_day", -1) == 0 for t in getattr(duty, "all_trips", getattr(duty, "trips", [])))
                    ),
                    "is_nocturnal": getattr(duty, "nocturnal_minutes", 0) > 0,
                    "has_overtime": (getattr(duty, "overtime_minutes", 0) or 0) > 0,

                    # Contagens (protegidas com fallbacks para diferentes nomes de atributos)
                    "num_blocks": len(getattr(duty, "tasks", getattr(duty, "blocks", []))),
                    "num_trips": len(getattr(duty, "all_trips", getattr(duty, "trips", []))),

                    # Custos base (para condições baseadas em valor)
                    "base_work_cost": duty_work_cost,
                    "base_overtime_cost": duty_overtime_cost,
                    "base_total": (
                        duty_work_cost + duty_guaranteed_cost + duty_waiting_cost
                        + duty_overtime_cost + duty_long_break_penalty
                        + duty_nocturnal_extra + duty_holiday_extra + duty_cct_penalties
                    ),
                }

                # Dicionário de custos mutável (o engine modifica in-place)
                mutable_costs = {
                    "work_cost": duty_work_cost,
                    "guaranteed_cost": duty_guaranteed_cost,
                    "waiting_cost": duty_waiting_cost,
                    "overtime_cost": duty_overtime_cost,
                    "long_unpaid_break_penalty": duty_long_break_penalty,
                    "nocturnal_extra": duty_nocturnal_extra,
                    "holiday_extra": duty_holiday_extra,
                    "cct_penalties": duty_cct_penalties,
                }

                # Soma antes da aplicação (para calcular delta)
                sum_before = sum(mutable_costs.values())

                # Aplicar regras (degradação graciosa interna)
                rule_engine.apply(duty_context, mutable_costs)

                # Atualizar variáveis locais com os valores modificados
                duty_work_cost = mutable_costs["work_cost"]
                duty_guaranteed_cost = mutable_costs["guaranteed_cost"]
                duty_waiting_cost = mutable_costs["waiting_cost"]
                duty_overtime_cost = mutable_costs["overtime_cost"]
                duty_long_break_penalty = mutable_costs["long_unpaid_break_penalty"]
                duty_nocturnal_extra = mutable_costs["nocturnal_extra"]
                duty_holiday_extra = mutable_costs["holiday_extra"]
                duty_cct_penalties = mutable_costs["cct_penalties"]

                dynamic_adjustments_total += sum(mutable_costs.values()) - sum_before

            work_cost += duty_work_cost
            guaranteed_cost += duty_guaranteed_cost
            waiting_cost += duty_waiting_cost
            overtime_cost += duty_overtime_cost
            long_unpaid_break_penalty += duty_long_break_penalty
            nocturnal_extra += duty_nocturnal_extra
            holiday_extra += duty_holiday_extra
            cct_penalties += duty_cct_penalties
            duties.append(
                {
                    "duty_id": duty.id,
                    "work_cost": _R(duty_work_cost),
                    "guaranteed_cost": _R(duty_guaranteed_cost),
                    "waiting_cost": _R(duty_waiting_cost),
                    "overtime_cost": _R(duty_overtime_cost),
                    "long_unpaid_break_penalty": _R(duty_long_break_penalty),
                    "nocturnal_extra": _R(duty_nocturnal_extra),
                    "holiday_extra": _R(duty_holiday_extra),
                    "cct_penalties": _R(duty_cct_penalties),
                    "total": _R(
                        duty_work_cost
                        + duty_guaranteed_cost
                        + duty_waiting_cost
                        + duty_overtime_cost
                        + duty_long_break_penalty
                        + duty_nocturnal_extra
                        + duty_holiday_extra
                        + duty_cct_penalties
                        + self.cost_duty,
                    ),
                }
            )

        total = (
            work_cost
            + guaranteed_cost
            + waiting_cost
            + overtime_cost
            + long_unpaid_break_penalty
            + nocturnal_extra
            + holiday_extra
            + cct_penalties
            + (len(solution.duties) * self.cost_duty)
        )
        result = {
            "total": _R(total),
            "work_cost": _R(work_cost),
            "guaranteed_cost": _R(guaranteed_cost),
            "waiting_cost": _R(waiting_cost),
            "overtime_cost": _R(overtime_cost),
            "long_unpaid_break_penalty": _R(long_unpaid_break_penalty),
            "nocturnal_extra": _R(nocturnal_extra),
            "holiday_extra": _R(holiday_extra),
            "cct_penalties": _R(cct_penalties),
            "num_duties": len(solution.duties),
            "num_uncovered_blocks": len(solution.uncovered_blocks),
            "duties": duties,
        }
        if has_dynamic_rules:
            result["dynamic_rules_applied"] = rule_engine.rule_count
            result["dynamic_adjustments_total"] = _R(dynamic_adjustments_total)
            if rule_engine.warnings:
                result["dynamic_rules_warnings"] = rule_engine.warnings
        return result

    def csp_cost(self, solution: CSPSolution) -> float:
        """
        Custo total de tripulação:
          Σ_deveres (horas_efetivas × custo_hora) + Σ_violações × penalidade
        """
        return float(self.csp_cost_breakdown(solution)["total"])

    # ── Total ─────────────────────────────────────────────────────────────────

    def total_cost(
        self,
        result: OptimizationResult,
        vehicle_types: List[VehicleType],
    ) -> float:
        return float(self.total_cost_breakdown(result, vehicle_types)["total"])

    def total_cost_breakdown(
        self,
        result: OptimizationResult,
        vehicle_types: List[VehicleType],
    ) -> Dict[str, Any]:
        vsp = self.vsp_cost_breakdown(result.vsp, vehicle_types)
        csp = self.csp_cost_breakdown(result.csp)
        total = float(vsp["total"]) + float(csp["total"])
        return {
            "total": _R(total),
            "vsp": vsp,
            "csp": csp,
            "shares": {
                "vsp": round((float(vsp["total"]) / total), 4) if total > 0 else 0.0,
                "csp": round((float(csp["total"]) / total), 4) if total > 0 else 0.0,
            },
        }

    # ── Penalidade de inviabilidade ───────────────────────────────────────────

    def infeasibility_penalty(self, solution: VSPSolution) -> float:
        """Penalidade para viagens não atribuídas (usada nos метаheurísticos)."""
        return len(solution.unassigned_trips) * self.violation_penalty * 10

    def block_cost(self, block: Block, vehicle_types: List[VehicleType]) -> float:
        """Custo de um único bloco (utilizado no CSP Set Partitioning).
        Inclui custo de tempo ocioso (pull-out/pull-back e idle entre viagens)."""
        vt_map = {vt.id: vt for vt in vehicle_types}
        vt = vt_map.get(block.vehicle_type_id or 0)  # type: ignore[arg-type]
        cost = Decimal('0.0')
        idle_cost_per_min = self.idle_cost_per_minute
        if vt:
            cost += self._to_decimal(vt.fixed_cost)
            for trip in block.trips:
                components = self._vehicle_trip_components(vt, trip)
                cost += components["distance"] + components["time"]  # Já são Decimal
                # Custo do tempo ocioso antes/depois da viagem (pull-out/pull-back)
                cost += (self._to_decimal(trip.idle_before_minutes) + self._to_decimal(trip.idle_after_minutes)) * idle_cost_per_min
        else:
            # Custo fixo de ativação é por bloco, não por viagem
            cost += self.cost_vehicle
            for trip in block.trips:
                components = self._vehicle_trip_components(None, trip)
                cost += components["distance"] + components["time"]  # Já são Decimal
                cost += (self._to_decimal(trip.idle_before_minutes) + self._to_decimal(trip.idle_after_minutes)) * idle_cost_per_min
        return float(cost)
