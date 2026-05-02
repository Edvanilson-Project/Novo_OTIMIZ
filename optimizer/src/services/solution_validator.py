"""Validador Independente de Soluções de Otimização"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence
from dataclasses import dataclass
from enum import Enum


class ErrorSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    WARNING = "WARNING"


@dataclass
class ValidationError:
    error_type: str
    severity: ErrorSeverity
    vehicle_id: Optional[int] = None
    duty_id: Optional[int] = None
    trip_ids: Optional[List[int]] = None
    detail: str = ""
    suggested_fix: Optional[str] = None

    def to_dict(self):
        return {
            "type": self.error_type,
            "severity": self.severity.value,
            "vehicle_id": self.vehicle_id,
            "duty_id": self.duty_id,
            "trip_ids": self.trip_ids,
            "detail": self.detail,
            "suggested_fix": self.suggested_fix
        }


@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    stats: Dict[str, Any]

    def to_dict(self):
        return {
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "stats": self.stats
        }


class SolutionValidator:
    def __init__(self, tolerance_minutes: int = 5):
        self.tolerance = tolerance_minutes

    def validate(
        self,
        blocks: Sequence[Dict[str, Any]],
        duties: Sequence[Dict[str, Any]],
        trips: Sequence[Dict[str, Any]],
        params: Dict[str, Any]
    ) -> ValidationResult:
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        errors.extend(self._check_time_overlaps(blocks))
        errors.extend(self._check_deadhead_gaps(blocks))
        errors.extend(self._check_max_shift(duties, params))
        warnings.extend(self._check_meal_break_position(duties, params))

        stats = self._calculate_stats(blocks, duties, trips)
        is_valid = len(errors) == 0

        return ValidationResult(valid=is_valid, errors=errors, warnings=warnings, stats=stats)

    def _check_time_overlaps(self, blocks: Sequence[Dict[str, Any]]) -> List[ValidationError]:
        errors: List[ValidationError] = []
        for block in blocks:
            vehicle_id = block.get("vehicle_id") or block.get("block_id")
            trips = block.get("items") or block.get("trips") or []
            sorted_trips = sorted(trips, key=lambda t: t.get("start_time", 0))

            for i in range(len(sorted_trips) - 1):
                trip1, trip2 = sorted_trips[i], sorted_trips[i + 1]
                end1, start2 = trip1.get("end_time"), trip2.get("start_time")
                if end1 and start2 and end1 > start2:
                    errors.append(ValidationError(
                        error_type="TIME_OVERLAP",
                        severity=ErrorSeverity.CRITICAL,
                        vehicle_id=vehicle_id,
                        trip_ids=[trip1.get("tripId"), trip2.get("tripId")],
                        detail=f"Trip {trip1.get('tripId')} ends at {end1}, Trip {trip2.get('tripId')} starts at {start2}"
                    ))
        return errors

    def _check_deadhead_gaps(self, blocks: Sequence[Dict[str, Any]]) -> List[ValidationError]:
        errors: List[ValidationError] = []
        for block in blocks:
            vehicle_id = block.get("vehicle_id") or block.get("block_id")
            trips = block.get("items") or block.get("trips") or []
            sorted_trips = sorted(trips, key=lambda t: t.get("start_time", 0))

            for i in range(len(sorted_trips) - 1):
                trip1, trip2 = sorted_trips[i], sorted_trips[i + 1]
                end1, start2 = trip1.get("end_time"), trip2.get("start_time")
                if end1 and start2:
                    gap = start2 - end1
                    if gap < self.tolerance:
                        errors.append(ValidationError(
                            error_type="INSUFFICIENT_DEADHEAD",
                            severity=ErrorSeverity.HIGH,
                            vehicle_id=vehicle_id,
                            trip_ids=[trip1.get("tripId"), trip2.get("tripId")],
                            detail=f"Gap {gap}min < required {self.tolerance}min"
                        ))
        return errors

    def _check_max_shift(self, duties: Sequence[Dict[str, Any]], params: Dict[str, Any]) -> List[ValidationError]:
        errors: List[ValidationError] = []
        max_shift = params.get("max_shift_minutes", 600)

        for duty in duties:
            start, end = duty.get("start_time"), duty.get("end_time")
            if start is not None and end is not None:
                spread = end - start
                if spread > max_shift:
                    errors.append(ValidationError(
                        error_type="MAX_SHIFT_EXCEEDED",
                        severity=ErrorSeverity.HIGH,
                        duty_id=duty.get("duty_id"),
                        detail=f"Duty spread {spread}min > max {max_shift}min"
                    ))
        return errors

    def _check_meal_break_position(self, duties: Sequence[Dict[str, Any]], params: Dict[str, Any]) -> List[ValidationError]:
        return []

    def _calculate_stats(self, blocks: Sequence[Dict[str, Any]], duties: Sequence[Dict[str, Any]], trips: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        allocated_trips = set()
        for block in blocks:
            trips_list = block.get("items") or block.get("trips") or []
            for trip in trips_list:
                trip_id = trip.get("tripId") or trip.get("trip_id")
                if trip_id:
                    allocated_trips.add(trip_id)

        total_trips = len(trips)
        total_operator_hours = sum((d.get("end_time", 0) - d.get("start_time", 0)) / 60 for d in duties if d.get("start_time") and d.get("end_time"))

        return {
            "total_trips": total_trips,
            "allocated_trips": len(allocated_trips),
            "unallocated_trips": total_trips - len(allocated_trips),
            "allocation_percentage": (len(allocated_trips) / total_trips * 100) if total_trips > 0 else 0,
            "total_vehicles": len(blocks),
            "total_duties": len(duties),
            "total_operator_hours": round(total_operator_hours, 2),
            "avg_duty_hours": round(total_operator_hours / len(duties), 2) if len(duties) > 0 else 0
        }


class UncoveredTripExplainer:
    """Explica por quê cada viagem não foi coberta"""
    
    def __init__(self):
        self.reasons = {}
    
    def explain_uncovered_trips(
        self,
        all_trips: Sequence[Dict[str, Any]],
        allocated_trip_ids: set,
        blocks: Sequence[Dict[str, Any]],
        params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Retorna lista de viagens não cobertas com explicações detalhadas
        
        Tenta entender POR QUÊ cada viagem não foi alocada a um veículo
        """
        explanations = []
        unallocated = [t for t in all_trips if t.get("id") not in allocated_trip_ids]
        
        for trip in unallocated:
            trip_id = trip.get("id")
            reasons = self._find_why_uncovered(trip, blocks, all_trips, params)
            
            explanations.append({
                "trip_id": trip_id,
                "uncovered": True,
                "reasons": reasons,
                "priority": "HIGH" if not reasons else "MEDIUM"
            })
        
        return explanations
    
    def _find_why_uncovered(
        self,
        trip: Dict[str, Any],
        blocks: Sequence[Dict[str, Any]],
        all_trips: Sequence[Dict[str, Any]],
        params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Encontra razões por que uma viagem não foi alocada"""
        reasons = []
        
        trip_start = trip.get("start_time")
        trip_end = trip.get("end_time")
        trip_origin = trip.get("origin_id")
        trip_dest = trip.get("destination_id")
        
        # Razão 1: Nenhum veículo disponível no terminal de origem
        vehicles_at_origin = []
        for block in blocks:
            # Se temos items, verificar posição final do último item
            items = block.get("items") or block.get("trips") or []
            if items:
                last_item = items[-1]
                last_dest = last_item.get("destination_id")
                if last_dest == trip_origin:
                    vehicles_at_origin.append(block.get("block_id"))
        
        if not vehicles_at_origin:
            reasons.append({
                "reason": "NO_VEHICLE_AT_ORIGIN",
                "detail": f"No vehicle at terminal {trip_origin}",
                "severity": "CRITICAL"
            })
        
        # Razão 2: Tempo insuficiente para deadhead
        max_shift = params.get("max_shift_minutes", 600)
        tolerance = 5  # minutos
        
        for block in blocks:
            items = block.get("items") or block.get("trips") or []
            if not items:
                continue
            
            last_item = items[-1]
            last_end = last_item.get("end_time")
            
            if last_end and trip_start:
                gap = trip_start - last_end
                if gap < tolerance:
                    reasons.append({
                        "reason": "INSUFFICIENT_DEADHEAD",
                        "detail": f"Last vehicle trip ends at {last_end}, next trip starts at {trip_start} (gap {gap}min < {tolerance}min)",
                        "severity": "HIGH"
                    })
        
        # Razão 3: Jornada seria excedida
        for block in blocks:
            items = block.get("items") or block.get("trips") or []
            if items:
                first_start = items[0].get("start_time")
                last_end = items[-1].get("end_time")
                
                if first_start and trip_end:
                    potential_spread = trip_end - first_start
                    if potential_spread > max_shift:
                        reasons.append({
                            "reason": "MAX_SHIFT_WOULD_EXCEED",
                            "detail": f"Adding trip would make shift {potential_spread}min > max {max_shift}min",
                            "severity": "HIGH"
                        })
        
        # Se não encontrou razão específica
        if not reasons:
            reasons.append({
                "reason": "UNKNOWN_REASON",
                "detail": "Could not determine specific reason (may be combination of factors)",
                "severity": "MEDIUM"
            })
        
        return reasons


class MealBreakValidator:
    """Valida posição de almoço obrigatório"""
    
    @staticmethod
    def validate_meal_break_position(duties, params):
        """
        Valida que almoço está em posição legal.
        
        Regra: Se jornada > 6h, almoço DEVE estar entre 11:30-14:00
        Razão: Lei trabalhista (CCT brasileiro)
        """
        errors = []
        meal_break_min = params.get("meal_break_minutes", 60)
        
        # Horários legais de almoço (em minutos desde início do dia)
        legal_meal_start_hour = 11.5 * 60    # 11:30 = 690 min
        legal_meal_end_hour = 14.0 * 60      # 14:00 = 840 min
        
        for duty in duties:
            duty_id = duty.get("duty_id") or duty.get("id")
            start = duty.get("start_time")
            end = duty.get("end_time")
            
            if not start or not end:
                continue
            
            spread = (end - start) / 60  # Em horas
            
            # Só valida se spread > 6h
            if spread <= 6:
                continue
            
            # Se tem campo meal_break_time (horário do almoço)
            meal_time = duty.get("meal_break_time")
            
            if meal_time is not None:
                # Converter para hora do dia
                meal_hour_minutes = meal_time % (24 * 60)
                
                if not (legal_meal_start_hour <= meal_hour_minutes <= legal_meal_end_hour):
                    errors.append({
                        "type": "ILLEGAL_MEAL_POSITION",
                        "severity": "WARNING",
                        "duty_id": duty_id,
                        "detail": f"Meal at {meal_time}min (hour {meal_time/60:.1f}), legal range 11:30-14:00",
                        "suggested_fix": "Reschedule meal break to 11:30-14:00"
                    })
            else:
                # Sem informação de meal_break_time, não conseguimos validar
                # Mas se tem trip_ids, deveríamos ter essa informação
                if duty.get("trip_ids") or duty.get("trips"):
                    errors.append({
                        "type": "MISSING_MEAL_TIME_INFO",
                        "severity": "WARNING",
                        "duty_id": duty_id,
                        "detail": f"Duty > 6h but no meal_break_time recorded",
                        "suggested_fix": "Add meal_break_time to duty record"
                    })
        
        return errors


class RestIntegrityValidator:
    """Valida integridade do repouso obrigatório"""
    
    @staticmethod
    def validate_rest_not_interrupted(duties, params):
        """
        Valida que repouso obrigatório não foi interrompido.
        
        Regra: Repouso de 30min não pode ter viagem no meio.
        """
        errors = []
        
        for duty in duties:
            duty_id = duty.get("duty_id") or duty.get("id")
            
            # Se tem eventos/events, verificar se há repouso interrompido
            events = duty.get("events") or []
            
            in_rest = False
            rest_start = None
            
            for event in events:
                event_type = event.get("type") or event.get("kind")
                
                if event_type in ["BREAK", "REST", "MEAL", "MANDATORY_REST"]:
                    in_rest = True
                    rest_start = event.get("start_time")
                elif event_type in ["TRIP", "DEADHEAD"] and in_rest:
                    # Viagem no meio do repouso!
                    errors.append({
                        "type": "REST_INTERRUPTED",
                        "severity": "HIGH",
                        "duty_id": duty_id,
                        "detail": f"Rest period started at {rest_start} interrupted by trip",
                        "suggested_fix": "Complete rest period before starting trip"
                    })
                    in_rest = False
                elif event_type not in ["TRIP", "DEADHEAD"]:
                    in_rest = False
        
        return errors


class OperatorSkillValidator:
    """Valida skill matching do operador"""
    
    @staticmethod
    def validate_operator_skills(blocks, duties, trips, operator_skills):
        """
        Valida que cada operador tem skill necessário para as viagens.
        
        operator_skills: Dict[operator_id -> List[skills]]
        """
        errors = []
        
        if not operator_skills:
            # Sem dados de skill, não conseguimos validar
            return errors
        
        for duty in duties:
            duty_id = duty.get("duty_id") or duty.get("id")
            operator_id = duty.get("operator_id")
            
            if not operator_id:
                continue
            
            operator_skill_list = operator_skills.get(operator_id, [])
            trip_ids = duty.get("trip_ids") or duty.get("trips") or []
            
            # Verificar cada viagem do operador
            for trip_id in trip_ids:
                # Encontrar trip nos blocks
                trip_data = None
                for block in blocks:
                    items = block.get("items") or block.get("trips") or []
                    for item in items:
                        if item.get("tripId") == trip_id or item.get("id") == trip_id:
                            trip_data = item
                            break
                
                if trip_data:
                    required_skill = trip_data.get("required_skill")
                    
                    if required_skill and required_skill not in operator_skill_list:
                        errors.append({
                            "type": "SKILL_MISMATCH",
                            "severity": "WARNING",
                            "duty_id": duty_id,
                            "trip_ids": [trip_id],
                            "detail": f"Operator {operator_id} lacks skill '{required_skill}' for trip {trip_id}",
                            "suggested_fix": f"Assign trip to operator with '{required_skill}' skill"
                        })
        
        return errors


class DeadheadTimeValidator:
    """Calcula tempo REAL de deadhead entre terminais"""
    
    def __init__(self, terminal_distances=None):
        """
        terminal_distances: Dict[(origin_id, dest_id) -> distance_km]
        Usa: distância * 0.5 min/km como estimativa de tempo
        """
        self.terminal_distances = terminal_distances or {}
        self.avg_speed_min_per_km = 0.5  # 2km/min = 120km/h
    
    def calculate_deadhead_time(self, origin_id, dest_id):
        """Calcula tempo de deadhead em minutos"""
        
        # Se temos distância real
        if (origin_id, dest_id) in self.terminal_distances:
            distance = self.terminal_distances[(origin_id, dest_id)]
            return max(5, int(distance * self.avg_speed_min_per_km))  # Mínimo 5min
        
        # Senão, usar default de 5min (mesmo terminal)
        return 5
    
    def validate_real_deadhead(self, blocks):
        """Valida usando tempo REAL de deadhead"""
        errors = []
        tolerance = 5  # minutos
        
        for block in blocks:
            vehicle_id = block.get("vehicle_id") or block.get("block_id")
            trips = block.get("items") or block.get("trips") or []
            
            sorted_trips = sorted(trips, key=lambda t: t.get("start_time", 0))
            
            for i in range(len(sorted_trips) - 1):
                trip1 = sorted_trips[i]
                trip2 = sorted_trips[i + 1]
                
                end1 = trip1.get("end_time")
                start2 = trip2.get("start_time")
                dest1 = trip1.get("destination_id")
                origin2 = trip2.get("origin_id")
                
                if not (end1 and start2 and dest1 and origin2):
                    continue
                
                available_gap = start2 - end1
                required_deadhead = self.calculate_deadhead_time(dest1, origin2)
                
                if available_gap < required_deadhead + tolerance:
                    errors.append({
                        "type": "INSUFFICIENT_REAL_DEADHEAD",
                        "severity": "HIGH",
                        "vehicle_id": vehicle_id,
                        "trip_ids": [trip1.get("tripId"), trip2.get("tripId")],
                        "detail": f"Real deadhead {required_deadhead}min + 5min tolerance > available gap {available_gap}min",
                        "suggested_fix": "Increase gap or use vehicle with nearby terminal"
                    })
        
        return errors
