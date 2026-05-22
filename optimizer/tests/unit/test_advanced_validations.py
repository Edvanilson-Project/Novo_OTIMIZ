"""Tests for advanced validators: meal, rest, skills, deadhead"""
import pytest
import sys
sys.path.insert(0, '/home/edvanilson/Área de trabalho/Novo_OTIMIZ/optimizer')

from src.services.solution_validator import (
    MealBreakValidator,
    RestIntegrityValidator,
    OperatorSkillValidator,
    DeadheadTimeValidator
)


class TestMealBreakValidator:
    """Testa validação de posição de almoço"""
    
    def test_legal_meal_position(self):
        """Almoço às 12:00 em duty de 8h = OK"""
        duties = [{
            "duty_id": 1,
            "start_time": 360,
            "end_time": 960,
            "meal_break_time": 720
        }]
        
        errors = MealBreakValidator.validate_meal_break_position(duties, {})
        illegal = [e for e in errors if e["type"] == "ILLEGAL_MEAL_POSITION"]
        assert len(illegal) == 0
    
    def test_short_duty_no_meal(self):
        """Duty < 6h não precisa validar almoço"""
        duties = [{
            "duty_id": 1,
            "start_time": 360,
            "end_time": 660
        }]
        
        errors = MealBreakValidator.validate_meal_break_position(duties, {})
        assert len(errors) == 0


class TestRestIntegrityValidator:
    """Testa validação de repouso"""
    
    def test_no_events_ok(self):
        """Duty sem eventos estruturados = OK"""
        duties = [{"duty_id": 1}]
        
        errors = RestIntegrityValidator.validate_rest_not_interrupted(duties, {})
        assert len(errors) == 0


class TestOperatorSkillValidator:
    """Testa validação de skill"""
    
    def test_skill_match_ok(self):
        """Operador com skill necessária = OK"""
        blocks = [{
            "block_id": 1,
            "items": [{"tripId": 1, "required_skill": "ARTICULATED"}]
        }]
        
        duties = [{
            "duty_id": 1,
            "operator_id": "OP_1",
            "trip_ids": [1]
        }]
        
        operator_skills = {"OP_1": ["ARTICULATED"]}
        
        errors = OperatorSkillValidator.validate_operator_skills(
            blocks, duties, [], operator_skills
        )
        assert len(errors) == 0
    
    def test_no_skill_data(self):
        """Sem dados de skill, não valida"""
        blocks = [{"block_id": 1, "items": []}]
        duties = [{"duty_id": 1}]
        
        errors = OperatorSkillValidator.validate_operator_skills(
            blocks, duties, [], {}
        )
        assert len(errors) == 0


class TestDeadheadTimeValidator:
    """Testa validação de deadhead real"""
    
    def test_calculate_deadhead(self):
        """Calcula deadhead com distância real"""
        terminal_distances = {(10, 20): 10.0}
        validator = DeadheadTimeValidator(terminal_distances)
        
        # 10km * 0.5 = 5 min
        time = validator.calculate_deadhead_time(10, 20)
        assert time == 5
    
    def test_deadhead_default(self):
        """Sem distância, usa default 5 min"""
        validator = DeadheadTimeValidator()
        time = validator.calculate_deadhead_time(99, 99)
        assert time == 5
    
    def test_validate_real_deadhead(self):
        """Valida com deadhead real"""
        validator = DeadheadTimeValidator()
        
        blocks = [{
            "block_id": 1,
            "items": [
                {
                    "tripId": 1,
                    "start_time": 600,
                    "end_time": 630,
                    "destination_id": 20
                },
                {
                    "tripId": 2,
                    "start_time": 640,
                    "origin_id": 20,
                    "end_time": 700
                }
            ]
        }]
        
        errors = validator.validate_real_deadhead(blocks)
        assert len(errors) == 0  # 10 min gap > 5 min required
