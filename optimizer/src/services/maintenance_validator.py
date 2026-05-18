"""
Vehicle maintenance constraint validator.
Ensures scheduled maintenance windows don't conflict with trip assignments.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class MaintenanceWindow:
    """Represents a vehicle maintenance/unavailability window."""

    vehicle_id: int
    start_time: datetime
    end_time: datetime
    reason: str
    description: Optional[str] = None


class MaintenanceValidator:
    """Validates vehicle availability against maintenance schedules."""

    def __init__(self, maintenance_windows: Optional[List[Dict]] = None):
        """
        Initialize validator with maintenance windows.

        Args:
            maintenance_windows: List of dicts with:
                - vehicle_id: int
                - start_time: datetime or ISO string
                - end_time: datetime or ISO string
                - reason: str (maintenance, inspection, fuel, etc)
                - description: optional str
        """
        self.windows = []
        if maintenance_windows:
            for window_data in maintenance_windows:
                self.add_window(window_data)

    def add_window(self, window_data: Dict) -> None:
        """Add a maintenance window."""
        start = window_data.get("start_time")
        end = window_data.get("end_time")

        if isinstance(start, str):
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if isinstance(end, str):
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))

        window = MaintenanceWindow(
            vehicle_id=window_data.get("vehicle_id"),
            start_time=start,
            end_time=end,
            reason=window_data.get("reason", "other"),
            description=window_data.get("description"),
        )
        self.windows.append(window)

    def is_vehicle_available(
        self,
        vehicle_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> Tuple[bool, Optional[MaintenanceWindow]]:
        """
        Check if vehicle is available for the given time period.

        Returns:
            (is_available, conflicting_window)
        """
        for window in self.windows:
            if window.vehicle_id != vehicle_id:
                continue

            # Check for time overlap
            if not (end_time <= window.start_time or start_time >= window.end_time):
                return False, window

        return True, None

    def get_unavailable_windows(self, vehicle_id: int) -> List[MaintenanceWindow]:
        """Get all maintenance windows for a vehicle."""
        return [w for w in self.windows if w.vehicle_id == vehicle_id]

    def validate_assignment(
        self,
        vehicle_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict:
        """
        Validate if vehicle can be assigned to a block/duty.

        Returns:
            {
                'valid': bool,
                'conflict': Optional[MaintenanceWindow],
                'warnings': List[str],
                'maintenance_cost_impact': float
            }
        """
        is_available, conflict = self.is_vehicle_available(vehicle_id, start_time, end_time)

        conflict_data = None
        if conflict:
            conflict_data = {
                "vehicle_id": conflict.vehicle_id,
                "start_time": conflict.start_time.isoformat(),
                "end_time": conflict.end_time.isoformat(),
                "reason": conflict.reason,
                "description": conflict.description,
            }

        result = {
            "valid": is_available,
            "conflict": conflict_data,
            "warnings": [],
            "maintenance_cost_impact": 0.0,
        }

        # Check for upcoming maintenance that might cause rescheduling
        upcoming = self._get_upcoming_maintenance(vehicle_id, start_time, days=7)
        if upcoming:
            result["warnings"].append(
                f"Vehicle has maintenance scheduled in next 7 days: "
                f"{upcoming[0].reason} on {upcoming[0].start_time.date()}"
            )

        return result

    def _get_upcoming_maintenance(
        self,
        vehicle_id: int,
        after_date: datetime,
        days: int = 7,
    ) -> List[MaintenanceWindow]:
        """Get maintenance windows for vehicle within N days after given date."""
        cutoff = after_date + timedelta(days=days)
        return [w for w in self.get_unavailable_windows(vehicle_id) if after_date <= w.start_time <= cutoff]

    def calculate_maintenance_impact_cost(
        self,
        vehicle_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """
        Calculate cost impact of maintenance constraints.
        Returns additional cost due to maintenance scheduling constraints.
        """
        windows = self.get_unavailable_windows(vehicle_id)
        if not windows:
            return 0.0

        # Simple heuristic: if maintenance is scheduled soon, increase cost slightly
        # to encourage choosing vehicles with no upcoming maintenance
        for window in windows:
            days_until = (window.start_time - start_time).days
            if 0 <= days_until <= 7:
                # Penalty increases as maintenance gets closer
                # Max penalty is 10% of a typical day cost (assumed ~800)
                return max(0, (7 - days_until) / 7 * 80)

        return 0.0

    def get_report(self) -> Dict:
        """Generate a maintenance report."""
        vehicles_with_maintenance = {}

        for window in self.windows:
            if window.vehicle_id not in vehicles_with_maintenance:
                vehicles_with_maintenance[window.vehicle_id] = []

            vehicles_with_maintenance[window.vehicle_id].append(
                {
                    "start_time": window.start_time.isoformat(),
                    "end_time": window.end_time.isoformat(),
                    "reason": window.reason,
                    "description": window.description,
                }
            )

        return {
            "total_maintenance_windows": len(self.windows),
            "vehicles_with_maintenance": len(vehicles_with_maintenance),
            "windows_by_vehicle": vehicles_with_maintenance,
        }
