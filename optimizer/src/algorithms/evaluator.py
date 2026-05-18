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

import logging
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, List, Sequence, Tuple

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

logger = logging.getLogger(__name__)

# Configurar contexto decimal para alta precisão
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

settings = get_settings()

# ── Constantes financeiras calibradas para transporte coletivo urbano brasileiro ──
#
# BASE SALARIAL (R$/h):
#   Motorista: ~R$2.800–3.500/mês ÷ 220 h = ~R$13–16/h.
#   Encargos sociais (FGTS 8 %, INSS patronal 20 %, férias, 13°, FGTS-multa) ≈ 70 %.
#   Custo efetivo total: ~R$22–27/h  →  default R$25/h.
_DEFAULT_CREW_COST_PER_HOUR = Decimal("25.0")

# MULTA TRABALHISTA POR VIOLAÇÃO CCT (R$ por ocorrência):
#   Autuação do MTE + indenização convencional: R$500–1000 por evento.
#   Mantemos R$500 como piso conservador.
_CCT_VIOLATION_PENALTY = Decimal("500.0")

# INTERVALO IMPRODUTIVO (split-duty):
#   Limite a partir do qual o intervalo não-pago começa a ser penalizado.
#   90 min é o máximo típico negociado em CCT; acima disso o split custa caro.
_LONG_UNPAID_BREAK_LIMIT_MINUTES = 90

# PESO DA PENALIDADE POR MINUTO DE INTERVALO EXCESSIVO (R$/min):
#   Calibrado para que 60 min de excesso (150 min de break total) custe ≈ R$25,
#   tornando o split competitivo com uma nova jornada (cost_duty ≈ R$500)
#   apenas quando realmente vale a pena (break > ~6 h).
#   Antes estava em 0.05 → splits longos custavam R$10 independente do tamanho.
_LONG_UNPAID_BREAK_PENALTY_WEIGHT = Decimal("0.25")

# ADICIONAL PADRÃO DE HORA EXTRA (usado como fallback quando CCT não especifica):
#   CLT art. 59: +50 % para primeiras 2 h; acima disso +100 %.
#   O método _overtime_cost implementa a escada; este pct é o fallback flat.
_DEFAULT_OVERTIME_EXTRA_PCT = Decimal("0.5")

# CUSTO FIXO POR JORNADA (R$):
#   Representa o overhead fixo diário por tripulante além do custo horário:
#   administração, uniformes, treinamento, aviso prévio amortizado, etc.
#   Default R$500 ≈ 20 h × R$25/h (custo-dia equivalente de um motorista).
#   Anteriormente era 0 no __init__, o que zerava a penalidade por # de duties.
_DEFAULT_COST_DUTY = Decimal("500.0")


def _R(v) -> float:
    """Converte para Decimal antes de arredondar, aceitando float ou Decimal."""
    if v is None:
        return 0.0
    try:
        return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0.0


def _nocturnal_overlap(start: int, end: int, noct_start_h: int, noct_end_h: int) -> int:
    """
    Calcula minutos noturnos entre start e end (minutos absolutos desde a meia-noite base).
    Suporta janelas noturnas que cruzam a meia-noite (ex: 22h-5h).
    """
    if start >= end:
        return 0
    start_noct = (noct_start_h % 24) * 60
    end_noct = (noct_end_h % 24) * 60
    wraps_midnight = start_noct > end_noct

    total = 0
    # Iterar pelos dias cobertos pelo intervalo [start, end]
    # day_base representa a meia-noite de cada dia
    day_start = (start // 1440) * 1440
    day_end = ((end + 1439) // 1440) * 1440

    for day_base in range(day_start, day_end, 1440):
        if wraps_midnight:
            # Janela noturna dividida em duas partes: [start_noct, 1440] e [0, end_noct]
            # Parte A: do início noturno até meia-noite
            ws_a, we_a = day_base + start_noct, day_base + 1440
            # Parte B: da meia-noite até o fim noturno
            ws_b, we_b = day_base + 1440, day_base + 1440 + end_noct

            for ws, we in [(ws_a, we_a), (ws_b, we_b)]:
                ov_s = max(start, ws)
                ov_e = min(end, we)
                if ov_e > ov_s:
                    total += ov_e - ov_s
        else:
            # Janela noturna contígua (ex: 01h às 05h no mesmo dia)
            ws, we = day_base + start_noct, day_base + end_noct
            ov_s = max(start, ws)
            ov_e = min(end, we)
            if ov_e > ov_s:
                total += ov_e - ov_s

    return total


def _gini_coefficient(values: List[float]) -> float:
    """Coeficiente de Gini sobre uma distribuição. 0 = perfeitamente igual, 1 = max desigual."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    total = sum(sorted_v)
    if total <= 0:
        return 0.0
    cumsum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return round((2.0 * cumsum) / (n * total) - (n + 1) / n, 4)


def _percentile(sorted_values: List[float], p: float) -> float:
    """Percentil simples (linear interpolation). p em [0,100]."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (p / 100.0) * (len(sorted_values) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _compute_fairness_metrics(duties_objs: Sequence[Any], duties_costs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Métricas de equidade entre motoristas (workload balance).

    Optbus expõe esse tipo de informação para o gestor identificar duties muito
    desiguais. Aqui só computamos e expomos — não penalizamos automaticamente
    (mudar custo muda a busca, comportamento já documentado em sprint anterior).
    """
    if not duties_objs:
        return {
            "num_duties": 0,
            "work_time": {
                "min": 0,
                "max": 0,
                "mean": 0,
                "median": 0,
                "stddev": 0,
                "cv": 0,
                "p5": 0,
                "p95": 0,
                "gini": 0,
            },
            "total_cost": {"min": 0, "max": 0, "mean": 0, "stddev": 0, "cv": 0, "gini": 0},
            "imbalance": {"duties_below_50pct_avg": 0, "duties_above_150pct_avg": 0},
        }

    work_times = [int(d.work_time or 0) for d in duties_objs]
    cost_totals = [float(c.get("total", 0.0) or 0.0) for c in duties_costs]

    def _stats(values: List[float]) -> Dict[str, float]:
        if not values:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "stddev": 0, "cv": 0, "p5": 0, "p95": 0, "gini": 0}
        sv = sorted(values)
        n = len(sv)
        mean = sum(sv) / n
        median = sv[n // 2] if n % 2 == 1 else (sv[n // 2 - 1] + sv[n // 2]) / 2
        var = sum((v - mean) ** 2 for v in sv) / n
        stddev = var**0.5
        cv = stddev / mean if mean > 0 else 0.0
        return {
            "min": round(float(sv[0]), 2),
            "max": round(float(sv[-1]), 2),
            "mean": round(float(mean), 2),
            "median": round(float(median), 2),
            "stddev": round(float(stddev), 2),
            "cv": round(float(cv), 4),
            "p5": round(_percentile(sv, 5), 2),
            "p95": round(_percentile(sv, 95), 2),
            "gini": _gini_coefficient([float(v) for v in sv]),
        }

    work_stats = _stats([float(w) for w in work_times])
    cost_stats = _stats(cost_totals)
    # Agora removemos campos inadequados de cost (median/p5/p95 são úteis, mas mantemos só os essenciais)
    cost_simple = {k: cost_stats[k] for k in ("min", "max", "mean", "stddev", "cv", "gini")}

    # Imbalance: quantas duties estão muito abaixo ou muito acima da média
    avg_work = work_stats["mean"]
    below_50 = sum(1 for w in work_times if avg_work > 0 and w < avg_work * 0.5)
    above_150 = sum(1 for w in work_times if avg_work > 0 and w > avg_work * 1.5)

    return {
        "num_duties": len(duties_objs),
        "work_time": work_stats,
        "total_cost": cost_simple,
        "imbalance": {
            "duties_below_50pct_avg": below_50,
            "duties_above_150pct_avg": above_150,
        },
    }


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

        # Parâmetros de negócio (Injetados via OptimizationConfig)
        self.nocturnal_start_hour = 22
        self.nocturnal_end_hour = 5
        self.nocturnal_factor = Decimal("1.0")
        self.nocturnal_extra_pct = Decimal("0.20")
        self.waiting_time_pay_pct = Decimal("0.30")
        self.idle_time_is_paid = True
        self.holiday_extra_pct = Decimal("1.0")
        self.sunday_off_weight = Decimal("0.0")

        # Pesos de custo dinâmicos
        self.cost_vehicle = Decimal(str(settings.default_vehicle_fixed_cost))
        self.cost_km = Decimal(str(settings.default_cost_per_km))
        self.cost_duty = _DEFAULT_COST_DUTY

    def set_costs(self, config: Any) -> None:
        """
        Define os pesos de custo e regras de negócio usando um objeto OptimizationConfig (ou dict).
        Ponto central para evitar parâmetros 'fantasma'.
        """
        if config is None:
            return

        # Converter para dict se for um objeto Pydantic ou similar
        params = config.dict() if hasattr(config, "dict") else config
        if not isinstance(params, dict):
            return

        # Mapeamento de pesos e custos base
        self.cost_vehicle = self._to_decimal(
            params.get(
                "cost_vehicle",
                params.get("fixed_vehicle_activation_cost", params.get("vehicle_fixed_cost", self.cost_vehicle)),
            )
        )
        self.cost_km = self._to_decimal(params.get("cost_km", self.cost_km))
        self.cost_duty = self._to_decimal(params.get("cost_duty", self.cost_duty))
        self.violation_penalty = self._to_decimal(params.get("cct_violation_penalty", self.violation_penalty))
        self.idle_cost_per_minute = self._to_decimal(params.get("idle_cost_per_minute", self.idle_cost_per_minute))

        # Custos por minuto (Mapeamento Direto do Frontend)
        driver_cost = params.get("driver_cost_per_minute") or 0.0
        collector_cost = params.get("collector_cost_per_minute") or 0.0
        if driver_cost > 0 or collector_cost > 0:
            total_per_minute = self._to_decimal(driver_cost) + self._to_decimal(collector_cost)
            self.crew_cost_per_hour = total_per_minute * Decimal("60.0")

        # Parâmetros de Regras de Negócio (Sincronização Fundamental)
        self.nocturnal_start_hour = int(params.get("nocturnal_start_hour", self.nocturnal_start_hour))
        self.nocturnal_end_hour = int(params.get("nocturnal_end_hour", self.nocturnal_end_hour))
        self.nocturnal_factor = self._to_decimal(params.get("nocturnal_factor", self.nocturnal_factor))
        self.nocturnal_extra_pct = self._to_decimal(params.get("nocturnal_extra_pct", self.nocturnal_extra_pct))
        self.waiting_time_pay_pct = self._to_decimal(params.get("waiting_time_pay_pct", self.waiting_time_pay_pct))
        self.idle_time_is_paid = bool(params.get("idle_time_is_paid", self.idle_time_is_paid))
        self.holiday_extra_pct = self._to_decimal(params.get("holiday_extra_pct", self.holiday_extra_pct))
        self.sunday_off_weight = self._to_decimal(params.get("sunday_off_weight", self.sunday_off_weight))

        # Limites de Intervalo
        configured_long_break_limit = params.get("long_unpaid_break_limit_minutes")
        if configured_long_break_limit is None and params.get("max_unpaid_break_minutes") is not None:
            configured_long_break_limit = params.get("max_unpaid_break_minutes")
        if configured_long_break_limit is not None:
            self.long_unpaid_break_limit_minutes = int(configured_long_break_limit)
        self.long_unpaid_break_penalty_weight = self._to_decimal(
            params.get("long_unpaid_break_penalty_weight", self.long_unpaid_break_penalty_weight)
        )

    def _to_decimal(self, value: Any) -> Decimal:
        """Converte qualquer valor para Decimal com precisão garantida.

        Args:
            value: Valor a ser convertido (str, float, int, None)

        Returns:
            Decimal inicializado via string para perfeita exatidão

        Raises:
            ValueError: Se não puder converter para numérico
        """
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0.0")
        try:
            # Remove notação científica e formata com 8 casas decimais
            formatted = "{0:.8f}".format(float(value))
            return Decimal(formatted.strip())
        except (TypeError, ValueError) as e:
            logger.error(f"Falha ao converter valor para Decimal: {value}")
            raise ValueError(f"Valor não conversível para Decimal: {value}") from e

    def _long_unpaid_break_penalty(self, unpaid_break_minutes: int) -> Decimal:
        """Piecewise-linear penalty.

        Faixas após o limite base:
        - primeiros 30 min de excesso: 1x peso
        - próximos 60 min: 3x peso
        - acima disso: 10x peso
        """
        excess = max(0, int(unpaid_break_minutes) - self.long_unpaid_break_limit_minutes)
        if excess <= 0:
            return Decimal("0.0")

        tier1 = min(excess, 30)
        tier2 = min(max(0, excess - 30), 60)
        tier3 = max(0, excess - 90)
        return self.long_unpaid_break_penalty_weight * Decimal(tier1 * 1.0 + tier2 * 3.0 + tier3 * 10.0)

    def _overtime_cost(
        self,
        overtime_minutes: int,
        extra_pct_override: Decimal | None = None,
    ) -> Decimal:
        """Adicional de hora extra com escada CLT (art. 59) ou pct flat via CCT.

        Escada padrão (sem override):
          - 0 a 120 min: +50 % sobre a hora normal  (CLT: primeiras 2 h extras)
          - > 120 min:   +100 % sobre a hora normal  (CLT: horas adicionais)

        Quando a CCT define um percentual diferente (ex: 60 %, 75 %), ele é passado
        via extra_pct_override e aplicado flat sobre todo o bloco de overtime.
        """
        if overtime_minutes <= 0:
            return Decimal("0.0")
        if extra_pct_override is not None:
            # Override por CCT/contrato: percentual flat negociado
            return Decimal(str(overtime_minutes)) / Decimal("60.0") * self.crew_cost_per_hour * extra_pct_override
        # Escada CLT: tier1 = primeiras 2h (+50 %); tier2 = além disso (+100 %)
        tier1 = Decimal(str(min(overtime_minutes, 120)))
        tier2 = Decimal(str(max(0, overtime_minutes - 120)))
        return (tier1 / Decimal("60.0")) * self.crew_cost_per_hour * Decimal("0.50") + (
            tier2 / Decimal("60.0")
        ) * self.crew_cost_per_hour * Decimal("1.00")

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
                "time": self._to_decimal(vt.cost_per_hour) * (self._to_decimal(trip.duration) / Decimal("60.0")),
            }
        return {
            "distance": self._to_decimal(trip.distance_km) * self.cost_km,
            "time": (self._to_decimal(trip.duration) / Decimal("60.0"))
            * self._to_decimal(settings.default_cost_per_hour),
        }

    def vsp_cost_breakdown(self, solution: VSPSolution, vehicle_types: List[VehicleType]) -> Dict[str, Any]:
        vt_map: Dict[int, VehicleType] = {vt.id: vt for vt in vehicle_types}
        blocks: List[Dict[str, Any]] = []
        activation = Decimal("0.0")
        connection = Decimal("0.0")
        distance = Decimal("0.0")
        time = Decimal("0.0")
        idle_cost = Decimal("0.0")

        for block in solution.blocks:
            vt = vt_map.get(block.vehicle_type_id or 0)  # type: ignore[arg-type]
            block_activation = self._to_decimal(
                block.meta.get(
                    "activation_cost",
                    self.cost_vehicle if not vt else Decimal(str(vt.fixed_cost)),
                )
            )
            block_connection = self._to_decimal(block.meta.get("connection_cost", 0.0))
            block_distance = Decimal("0.0")
            block_time = Decimal("0.0")
            start_buffer = self._to_decimal(max(0, int(block.meta.get("start_buffer_minutes", 0) or 0)))
            end_buffer = self._to_decimal(max(0, int(block.meta.get("end_buffer_minutes", 0) or 0)))
            has_boundary_buffers = "start_buffer_minutes" in block.meta or "end_buffer_minutes" in block.meta
            block_idle_cost = (
                (start_buffer + end_buffer) * self.idle_cost_per_minute if has_boundary_buffers else Decimal("0.0")
            )

            block_deadhead_min = 0
            for trip in block.trips:
                components = self._vehicle_trip_components(vt, trip)
                block_distance += components["distance"]  # Já é Decimal
                block_time += components["time"]  # Já é Decimal
                if not has_boundary_buffers:
                    idle_before = self._to_decimal(trip.idle_before_minutes)
                    idle_after = self._to_decimal(trip.idle_after_minutes)
                    block_idle_cost += (idle_before + idle_after) * self.idle_cost_per_minute

            # Deadhead inter-viagens: retorno à garagem e transferências entre pontos.
            # Ativado apenas quando o solver VSP não populou idle_before/idle_after
            # (fallback para solvers que não modelam pull-out/pull-back explicitamente).
            if not has_boundary_buffers and len(block.trips) > 1:
                _any_idle_set = any((t.idle_before_minutes or 0) + (t.idle_after_minutes or 0) > 0 for t in block.trips)
                if not _any_idle_set:
                    for k in range(len(block.trips) - 1):
                        gap = block.trips[k + 1].start_time - block.trips[k].end_time
                        if gap > 0:
                            block_deadhead_min += gap
                            block_idle_cost += self._to_decimal(gap) * self.idle_cost_per_minute

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
                    "deadhead_minutes": block_deadhead_min,
                    "total": _R(block_activation + block_connection + block_distance + block_time + block_idle_cost),
                    "start_buffer_minutes": start_buffer,
                    "end_buffer_minutes": end_buffer,
                    "advisory_idle_proxy_cost": _R(block_idle_cost),
                }
            )

        total = activation + connection + distance + time + idle_cost
        total_deadhead_min = sum(b.get("deadhead_minutes", 0) for b in blocks)
        return {
            "total": _R(total),
            "activation": _R(activation),
            "connection": _R(connection),
            "distance": _R(distance),
            "time": _R(time),
            "idle_cost": _R(idle_cost),
            "total_deadhead_minutes": total_deadhead_min,
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
        work_cost = Decimal("0.0")
        guaranteed_cost = Decimal("0.0")
        waiting_cost = Decimal("0.0")
        overtime_cost = Decimal("0.0")
        long_unpaid_break_penalty = Decimal("0.0")
        nocturnal_extra = Decimal("0.0")
        holiday_extra = Decimal("0.0")
        cct_penalties = Decimal("0.0")

        # ── Compilar regras dinâmicas UMA VEZ (reutilizada em todos os duties) ─
        rule_engine = DynamicRuleEngine(self._dynamic_rules)
        has_dynamic_rules = rule_engine.rule_count > 0
        dynamic_adjustments_total = Decimal("0.0")

        for duty in solution.duties:
            duty_cct_penalties = self._to_decimal(duty.rest_violations + duty.shift_violations) * self.violation_penalty

            # Cálculo de Minutos Noturnos Robusto (Trata virada da meia-noite)
            noct_minutes = 0
            for t in getattr(duty, "all_trips", getattr(duty, "trips", [])):
                noct_minutes += _nocturnal_overlap(
                    int(t.start_time), int(t.end_time), self.nocturnal_start_hour, self.nocturnal_end_hour
                )

            # Aplica o nocturnal_factor no trabalho efetivo regulamentar
            regulatory_work_minutes = self._to_decimal(duty.work_time)
            if self.nocturnal_factor > 1.0:
                extension = self._to_decimal(noct_minutes) * (self.nocturnal_factor - Decimal("1.0"))
                regulatory_work_minutes += extension

            duty_work_cost = (regulatory_work_minutes / Decimal("60.0")) * self.crew_cost_per_hour

            # Minutos Garantidos e Espera (Idle)
            guaranteed_minutes = max(
                regulatory_work_minutes,
                self._to_decimal(
                    duty.meta.get("guaranteed_minutes", regulatory_work_minutes) or regulatory_work_minutes
                ),
            )

            # Idle time pay logic
            paid_minutes = self._to_decimal(duty.paid_minutes or 0)
            if paid_minutes == 0:
                # Se o solver não calculou paid_minutes, estimamos baseados no spread e idle
                paid_minutes = guaranteed_minutes
                if self.idle_time_is_paid:
                    idle_minutes = max(Decimal("0.0"), self._to_decimal(duty.spread_time) - regulatory_work_minutes)
                    paid_minutes += idle_minutes * self.waiting_time_pay_pct

            guaranteed_extra_minutes = max(Decimal("0.0"), guaranteed_minutes - regulatory_work_minutes)
            paid_waiting_minutes = max(Decimal("0.0"), paid_minutes - guaranteed_minutes)

            duty_guaranteed_cost = (guaranteed_extra_minutes / Decimal("60.0")) * self.crew_cost_per_hour
            duty_waiting_cost = (paid_waiting_minutes / Decimal("60.0")) * self.crew_cost_per_hour

            # Adicional de hora extra
            _ot_pct_override = (
                self._to_decimal(duty.meta["overtime_extra_pct"]) if "overtime_extra_pct" in (duty.meta or {}) else None
            )
            duty_overtime_cost = self._overtime_cost(
                max(0, int(duty.overtime_minutes or 0)),
                extra_pct_override=_ot_pct_override,
            )

            unpaid_break_minutes = max(
                Decimal("0.0"),
                self._to_decimal(
                    duty.meta.get("unpaid_break_total_minutes", max(0, duty.spread_time - duty.work_time)) or 0
                ),
            )
            duty_long_break_penalty = self._long_unpaid_break_penalty(unpaid_break_minutes)

            # Adicional Noturno Monetário
            duty_nocturnal_extra = Decimal("0.0")
            if noct_minutes > 0:
                duty_nocturnal_extra = (
                    (self._to_decimal(noct_minutes) / Decimal("60.0"))
                    * self.crew_cost_per_hour
                    * self.nocturnal_extra_pct
                )

            duty_holiday_extra = Decimal("0.0")
            is_holiday = bool(
                duty.meta.get("is_holiday", False)
                or any(getattr(t, "is_holiday", False) for seg in duty.segments for t in seg.trips)
            )
            is_sunday = bool(
                duty.meta.get("is_sunday", False)
                or any(bool(getattr(t, "is_sunday", False)) for seg in duty.segments for t in seg.trips)
            )

            if is_holiday or is_sunday:
                duty_holiday_extra = (
                    (regulatory_work_minutes / Decimal("60.0")) * self.crew_cost_per_hour * self.holiday_extra_pct
                )
                if is_sunday and self.sunday_off_weight > 0:
                    duty_cct_penalties += self.sunday_off_weight
            if duty.meta.get("illegal_relief"):
                duty_cct_penalties += Decimal("1000000")  # Big-M penalty for illegal terminal relief

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
                    "start_hour": (
                        (getattr(duty, "start_time", 0) // 60) if getattr(duty, "start_time", None) is not None else 0
                    ),
                    "end_hour": (
                        (getattr(duty, "end_time", 0) // 60) if getattr(duty, "end_time", None) is not None else 0
                    ),
                    # Campos de violação
                    "rest_violations": getattr(duty, "rest_violations", 0),
                    "shift_violations": getattr(duty, "shift_violations", 0),
                    "continuous_driving_violation": getattr(duty, "continuous_driving_violation", False),
                    # Campos de meta do duty (com fallback para inspeção de viagens)
                    "is_holiday": bool(
                        getattr(duty, "meta", {}).get("is_holiday", False)
                        or any(
                            getattr(t, "is_holiday", False)
                            for t in getattr(duty, "all_trips", getattr(duty, "trips", []))
                        )
                    ),
                    "is_sunday": bool(
                        getattr(duty, "meta", {}).get("is_sunday", False)
                        or any(
                            bool(getattr(t, "is_sunday", False))
                            for t in getattr(duty, "all_trips", getattr(duty, "trips", []))
                        )
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
                        duty_work_cost
                        + duty_guaranteed_cost
                        + duty_waiting_cost
                        + duty_overtime_cost
                        + duty_long_break_penalty
                        + duty_nocturnal_extra
                        + duty_holiday_extra
                        + duty_cct_penalties
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

        # duty_overhead_cost: custo fixo por jornada (overhead administrativo).
        # Exposto como componente nomeado para que o cliente da API consiga
        # validar total = soma_dos_componentes (e não como termo "fantasma").
        duty_overhead_cost = Decimal(str(len(solution.duties))) * self.cost_duty
        total = (
            work_cost
            + guaranteed_cost
            + waiting_cost
            + overtime_cost
            + long_unpaid_break_penalty
            + nocturnal_extra
            + holiday_extra
            + cct_penalties
            + duty_overhead_cost
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
            "duty_overhead_cost": _R(duty_overhead_cost),
            "num_duties": len(solution.duties),
            "num_uncovered_blocks": len(solution.uncovered_blocks),
            "duties": duties,
            "fairness": _compute_fairness_metrics(solution.duties, duties),
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
        breakdown = {
            "total": _R(total),
            "vsp": vsp,
            "csp": csp,
            "shares": {
                "vsp": round((float(vsp["total"]) / total), 4) if total > 0 else 0.0,
                "csp": round((float(csp["total"]) / total), 4) if total > 0 else 0.0,
            },
        }
        # Auditoria 2026-05-17: adiciona gap de otimalidade vs lower bound.
        # Sem isso, o cliente não sabe se a solução está perto do ótimo ou longe.
        breakdown["optimality"] = self._optimality_metrics(result)
        return breakdown

    def _optimality_metrics(self, result: OptimizationResult) -> Dict[str, Any]:
        """Calcula lower bound de Bodin & Golden (1981) e gap de otimalidade VSP.

        Lower bound = max(número de viagens simultâneas).
        Toda solução viável deve usar ≥ LB veículos; gap = (actual - LB) / LB × 100.

        Referência: Bodin L., Golden B. (1981) "Classification in vehicle routing
        and scheduling", Networks 11(2):97-108.
        """
        try:
            all_trips = [t for b in result.vsp.blocks for t in b.trips]
            if result.vsp.unassigned_trips:
                all_trips.extend(result.vsp.unassigned_trips)
            if not all_trips:
                return {"vsp_lower_bound": 0, "vsp_actual": 0, "vsp_gap_pct": 0.0}
            events: List[Tuple[int, int]] = []
            for t in all_trips:
                events.append((int(t.start_time), 1))
                events.append((int(t.end_time), -1))
            events.sort(key=lambda e: (e[0], e[1]))
            concurrent = peak = 0
            for _, delta in events:
                concurrent += delta
                if concurrent > peak:
                    peak = concurrent
            actual = len(result.vsp.blocks)
            gap_pct = ((actual - peak) / peak * 100.0) if peak > 0 else 0.0
            return {
                "vsp_lower_bound": peak,
                "vsp_actual": actual,
                "vsp_gap_pct": round(gap_pct, 2),
                "vsp_gap_explained": (
                    "Gap = (veículos usados - peak concurrent trips) / peak × 100. "
                    "Gap=0 significa ótimo na cota inferior de Bodin & Golden (1981); "
                    "gap > 0 pode ser otimização subótima OU restrição operacional (max_shift, etc)."
                ),
            }
        except Exception as exc:  # pragma: no cover - defesa contra erro inesperado
            logger.warning("[OPTIMALITY] cálculo falhou: %s", exc)
            return {"vsp_lower_bound": None, "vsp_actual": None, "vsp_gap_pct": None}

    # ── Penalidade de inviabilidade ───────────────────────────────────────────

    def infeasibility_penalty(self, solution: VSPSolution) -> float:
        """Penalidade para viagens não atribuídas (usada nos метаheurísticos)."""
        return len(solution.unassigned_trips) * self.violation_penalty * 10

    def block_cost(self, block: Block, vehicle_types: List[VehicleType]) -> float:
        """Custo de um único bloco (utilizado no CSP Set Partitioning).
        Inclui custo de tempo ocioso (pull-out/pull-back e idle entre viagens)."""
        vt_map = {vt.id: vt for vt in vehicle_types}
        vt = vt_map.get(block.vehicle_type_id or 0)  # type: ignore[arg-type]
        cost = Decimal("0.0")
        idle_cost_per_min = self.idle_cost_per_minute
        if vt:
            cost += self._to_decimal(vt.fixed_cost)
            for trip in block.trips:
                components = self._vehicle_trip_components(vt, trip)
                cost += components["distance"] + components["time"]  # Já são Decimal
                # Custo do tempo ocioso antes/depois da viagem (pull-out/pull-back)
                cost += (
                    self._to_decimal(trip.idle_before_minutes) + self._to_decimal(trip.idle_after_minutes)
                ) * idle_cost_per_min
        else:
            # Custo fixo de ativação é por bloco, não por viagem
            cost += self.cost_vehicle
            for trip in block.trips:
                components = self._vehicle_trip_components(None, trip)
                cost += components["distance"] + components["time"]  # Já são Decimal
                cost += (
                    self._to_decimal(trip.idle_before_minutes) + self._to_decimal(trip.idle_after_minutes)
                ) * idle_cost_per_min
        return float(cost)
