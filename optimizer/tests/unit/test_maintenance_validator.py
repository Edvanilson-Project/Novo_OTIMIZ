"""Tests for vehicle maintenance constraint validation."""
import pytest
from datetime import datetime, timedelta
from src.services.maintenance_validator import MaintenanceValidator, MaintenanceWindow


class TestMaintenanceValidator:
    """Test MaintenanceValidator functionality."""

    @pytest.fixture
    def validator(self):
        """Create a validator with sample maintenance windows."""
        windows = [
            {
                'vehicle_id': 1,
                'start_time': datetime(2026, 5, 15, 8, 0),
                'end_time': datetime(2026, 5, 15, 12, 0),
                'reason': 'maintenance',
            },
            {
                'vehicle_id': 1,
                'start_time': datetime(2026, 5, 20, 10, 0),
                'end_time': datetime(2026, 5, 20, 14, 0),
                'reason': 'inspection',
            },
            {
                'vehicle_id': 2,
                'start_time': datetime(2026, 5, 10, 6, 0),
                'end_time': datetime(2026, 5, 10, 8, 0),
                'reason': 'fuel',
            },
        ]
        return MaintenanceValidator(windows)

    def test_initialization(self, validator):
        """Test validator initialization."""
        assert len(validator.windows) == 3
        assert validator.windows[0].vehicle_id == 1

    def test_add_window(self, validator):
        """Test adding a maintenance window."""
        validator.add_window({
            'vehicle_id': 3,
            'start_time': datetime(2026, 5, 25, 14, 0),
            'end_time': datetime(2026, 5, 25, 16, 0),
            'reason': 'cleaning',
        })
        assert len(validator.windows) == 4

    def test_is_vehicle_available_no_conflict(self, validator):
        """Test vehicle availability when no conflict exists."""
        is_available, conflict = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 14, 0),
            end_time=datetime(2026, 5, 15, 18, 0),
        )
        assert is_available is True
        assert conflict is None

    def test_is_vehicle_available_with_conflict(self, validator):
        """Test vehicle availability when conflict exists."""
        is_available, conflict = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 10, 0),
            end_time=datetime(2026, 5, 15, 13, 0),
        )
        assert is_available is False
        assert conflict is not None
        assert conflict.reason == 'maintenance'

    def test_is_vehicle_available_exact_overlap(self, validator):
        """Test vehicle availability with exact time overlap."""
        is_available, conflict = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 8, 0),
            end_time=datetime(2026, 5, 15, 12, 0),
        )
        assert is_available is False
        assert conflict is not None

    def test_is_vehicle_available_no_overlap(self, validator):
        """Test vehicle availability with no time overlap."""
        is_available, conflict = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 12, 1),
            end_time=datetime(2026, 5, 15, 14, 0),
        )
        assert is_available is True
        assert conflict is None

    def test_get_unavailable_windows(self, validator):
        """Test getting unavailable windows for a vehicle."""
        windows = validator.get_unavailable_windows(1)
        assert len(windows) == 2
        assert all(w.vehicle_id == 1 for w in windows)

    def test_get_unavailable_windows_empty(self, validator):
        """Test getting unavailable windows for vehicle with no maintenance."""
        windows = validator.get_unavailable_windows(999)
        assert len(windows) == 0

    def test_validate_assignment_valid(self, validator):
        """Test validation of a valid assignment."""
        result = validator.validate_assignment(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 14, 0),
            end_time=datetime(2026, 5, 15, 18, 0),
        )
        assert result['valid'] is True
        assert result['conflict'] is None
        assert isinstance(result['warnings'], list)

    def test_validate_assignment_invalid(self, validator):
        """Test validation of an invalid assignment."""
        result = validator.validate_assignment(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 9, 0),
            end_time=datetime(2026, 5, 15, 11, 0),
        )
        assert result['valid'] is False
        assert result['conflict'] is not None

    def test_validate_assignment_upcoming_maintenance_warning(self, validator):
        """Test warning for upcoming maintenance."""
        # Vehicle 1 has maintenance on May 20
        result = validator.validate_assignment(
            vehicle_id=1,
            start_time=datetime(2026, 5, 19, 8, 0),
            end_time=datetime(2026, 5, 19, 18, 0),
        )
        assert result['valid'] is True
        assert len(result['warnings']) > 0
        assert 'maintenance scheduled' in result['warnings'][0].lower()

    def test_calculate_maintenance_impact_cost_no_maintenance(self, validator):
        """Test cost calculation for vehicle with no maintenance."""
        cost = validator.calculate_maintenance_impact_cost(
            vehicle_id=999,
            start_time=datetime(2026, 5, 15, 8, 0),
            end_time=datetime(2026, 5, 15, 18, 0),
        )
        assert cost == 0.0

    def test_calculate_maintenance_impact_cost_with_maintenance(self, validator):
        """Test cost calculation for vehicle with upcoming maintenance."""
        # Vehicle 1 has maintenance on May 15, checking from May 14
        cost = validator.calculate_maintenance_impact_cost(
            vehicle_id=1,
            start_time=datetime(2026, 5, 14, 8, 0),
            end_time=datetime(2026, 5, 14, 18, 0),
        )
        assert cost > 0

    def test_calculate_maintenance_impact_cost_far_future(self, validator):
        """Test cost calculation for maintenance far in the future."""
        # Maintenance on May 20, checking from May 1
        cost = validator.calculate_maintenance_impact_cost(
            vehicle_id=1,
            start_time=datetime(2026, 5, 1, 8, 0),
            end_time=datetime(2026, 5, 1, 18, 0),
        )
        assert cost == 0.0

    def test_get_report(self, validator):
        """Test maintenance report generation."""
        report = validator.get_report()
        assert report['total_maintenance_windows'] == 3
        assert report['vehicles_with_maintenance'] == 2
        assert 1 in report['windows_by_vehicle']
        assert len(report['windows_by_vehicle'][1]) == 2

    def test_add_window_with_iso_string(self):
        """Test adding window with ISO format string."""
        validator = MaintenanceValidator()
        validator.add_window({
            'vehicle_id': 1,
            'start_time': '2026-05-15T08:00:00',
            'end_time': '2026-05-15T12:00:00',
            'reason': 'maintenance',
        })
        assert len(validator.windows) == 1
        assert isinstance(validator.windows[0].start_time, datetime)

    def test_boundary_cases(self, validator):
        """Test boundary cases for time overlap detection."""
        # Test exact boundary - should NOT overlap
        is_available, _ = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 12, 0),
            end_time=datetime(2026, 5, 15, 14, 0),
        )
        assert is_available is True

        # Test one second before - should NOT overlap
        is_available, _ = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 7, 59, 59),
            end_time=datetime(2026, 5, 15, 8, 0),
        )
        assert is_available is True

    def test_multiple_vehicles(self, validator):
        """Test validator with multiple vehicles."""
        # Vehicle 1 has conflict
        is_available_1, _ = validator.is_vehicle_available(
            vehicle_id=1,
            start_time=datetime(2026, 5, 15, 9, 0),
            end_time=datetime(2026, 5, 15, 11, 0),
        )

        # Vehicle 2 should be available at same time
        is_available_2, _ = validator.is_vehicle_available(
            vehicle_id=2,
            start_time=datetime(2026, 5, 15, 9, 0),
            end_time=datetime(2026, 5, 15, 11, 0),
        )

        assert is_available_1 is False
        assert is_available_2 is True
