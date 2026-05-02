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
