"""
Testes para Validador Independente de Soluções

Testa cada validação com casos reais e edge cases.
"""
import pytest
import sys
sys.path.insert(0, '/home/edvanilson/Área de trabalho/Novo_OTIMIZ/optimizer')

from src.services.solution_validator import SolutionValidator, ErrorSeverity


@pytest.fixture
def validator():
    """Instancia validador com tolerância padrão"""
    return SolutionValidator(tolerance_minutes=5)


class TestTimeOverlapDetection:
    """Testa detecção de sobreposição de horário"""

    def test_no_overlap_with_sequential_trips(self, validator):
        """Viagens sequenciais sem sobreposição devem ser válidas"""
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "start_time": 600, "end_time": 630},
                    {"tripId": 2, "start_time": 640, "end_time": 700}
                ]
            }
        ]

        result = validator.validate(blocks, [], [], {})
        assert result.valid
        overlap_errors = [e for e in result.errors if e.error_type == "TIME_OVERLAP"]
        assert len(overlap_errors) == 0

    def test_detects_overlap_same_vehicle(self, validator):
        """Deve detectar sobreposição: trip1 até 660, trip2 começa em 650"""
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "start_time": 600, "end_time": 660},
                    {"tripId": 2, "start_time": 650, "end_time": 720}
                ]
            }
        ]

        result = validator.validate(blocks, [], [], {})
        assert not result.valid
        overlap_errors = [e for e in result.errors if e.error_type == "TIME_OVERLAP"]
        assert len(overlap_errors) == 1

    def test_insufficient_gap(self, validator):
        """Gap de 2 minutos com tolerância 5 = ERRO"""
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "start_time": 600, "end_time": 630},
                    {"tripId": 2, "start_time": 632, "end_time": 700}
                ]
            }
        ]

        result = validator.validate(blocks, [], [], {})
        gap_errors = [e for e in result.errors if e.error_type == "INSUFFICIENT_DEADHEAD"]
        assert len(gap_errors) == 1

    def test_max_shift_exceeded(self, validator):
        """Jornada de 11h com max 10h = ERRO"""
        duties = [
            {
                "duty_id": 1,
                "start_time": 360,
                "end_time": 1020
            }
        ]
        params = {"max_shift_minutes": 600}

        result = validator.validate([], duties, [], params)
        shift_errors = [e for e in result.errors if e.error_type == "MAX_SHIFT_EXCEEDED"]
        assert len(shift_errors) == 1

    def test_allocation_stats(self, validator):
        """Testa cálculo de estatísticas"""
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "start_time": 600, "end_time": 630},
                    {"tripId": 2, "start_time": 640, "end_time": 700}
                ]
            }
        ]
        trips = [{"id": 1}, {"id": 2}, {"id": 3}]

        result = validator.validate(blocks, [], trips, {})
        assert result.stats["total_trips"] == 3
        assert result.stats["allocated_trips"] == 2
        assert result.stats["unallocated_trips"] == 1


class TestUncoveredTripExplanation:
    """Testa explicação de por que viagem não foi coberta"""
    
    def test_explains_no_vehicle_at_origin(self):
        """Explica quando nenhum veículo está no terminal de origem"""
        from src.services.solution_validator import UncoveredTripExplainer
        
        explainer = UncoveredTripExplainer()
        
        all_trips = [
            {"id": 1, "origin_id": 10, "destination_id": 20, "start_time": 600, "end_time": 630},
            {"id": 2, "origin_id": 30, "destination_id": 40, "start_time": 640, "end_time": 700}  # Not allocated
        ]
        
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "destination_id": 20, "start_time": 600, "end_time": 630}
                ]
            }
        ]
        
        allocated = {1}
        reasons = explainer.explain_uncovered_trips(all_trips, allocated, blocks, {})
        
        assert len(reasons) == 1
        assert reasons[0]["trip_id"] == 2
        assert reasons[0]["uncovered"] == True
        assert len(reasons[0]["reasons"]) > 0
    
    def test_explains_insufficient_deadhead(self):
        """Explica quando não há tempo para deadhead"""
        from src.services.solution_validator import UncoveredTripExplainer
        
        explainer = UncoveredTripExplainer()
        
        all_trips = [
            {"id": 1, "origin_id": 10, "destination_id": 20, "start_time": 600, "end_time": 630},
            {"id": 2, "origin_id": 20, "destination_id": 30, "start_time": 632, "end_time": 700}  # Gap 2min
        ]
        
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "destination_id": 20, "start_time": 600, "end_time": 630}
                ]
            }
        ]
        
        allocated = {1}
        reasons = explainer.explain_uncovered_trips(all_trips, allocated, blocks, {"max_shift_minutes": 600})
        
        assert len(reasons) == 1
        assert reasons[0]["trip_id"] == 2
        
        deadhead_reasons = [r for r in reasons[0]["reasons"] if r["reason"] == "INSUFFICIENT_DEADHEAD"]
        assert len(deadhead_reasons) > 0


class TestMealBreakValidator:
    """Testa validação de posição de almoço"""
    
    def test_illegal_meal_position_too_early(self):
        """Almoço às 10:00 em duty de 8h = ERRO"""
        from src.services.solution_validator import MealBreakValidator
        
        duties = [
            {
                "duty_id": 1,
                "start_time": 360,      # 06:00
                "end_time": 960,        # 16:00 (10h > 6h)
                "meal_break_time": 600  # 10:00 ❌ < 11:30
            }
        ]
        
        errors = MealBreakValidator.validate_meal_break_position(duties, {})
        
        assert len(errors) > 0
        assert errors[0]["type"] == "ILLEGAL_MEAL_POSITION"
    
    def test_legal_meal_position(self):
        """Almoço às 12:00 em duty de 8h = OK"""
        from src.services.solution_validator import MealBreakValidator
        
        duties = [
            {
                "duty_id": 1,
                "start_time": 360,      # 06:00
                "end_time": 960,        # 16:00 (10h)
                "meal_break_time": 720  # 12:00 ✅
            }
        ]
        
        errors = MealBreakValidator.validate_meal_break_position(duties, {})
        
        # Pode ter MISSING_MEAL_TIME_INFO se não tiver trip_ids, mas não ILLEGAL_MEAL_POSITION
        illegal = [e for e in errors if e["type"] == "ILLEGAL_MEAL_POSITION"]
        assert len(illegal) == 0
    
    def test_no_validation_for_short_duty(self):
        """Duty < 6h não precisa ter almoço"""
        from src.services.solution_validator import MealBreakValidator
        
        duties = [
            {
                "duty_id": 1,
                "start_time": 360,      # 06:00
                "end_time": 720,        # 12:00 (6h exata)
                # Sem meal_break_time
            }
        ]
        
        errors = MealBreakValidator.validate_meal_break_position(duties, {})
        
        # Não deve validar se < 6h
        assert len(errors) == 0


class TestRestIntegrityValidator:
    """Testa validação de repouso não interrompido"""
    
    def test_detects_interrupted_rest(self):
        """Valida que repouso não pode ter viagem no meio"""
        from src.services.solution_validator import RestIntegrityValidator
        
        duties = [
            {
                "duty_id": 1,
                "events": [
                    {"type": "TRIP", "start_time": 600},
                    {"type": "BREAK", "start_time": 630},  # Repouso começa
                    {"type": "TRIP", "start_time": 660},   # ❌ Viagem no meio do repouso!
                ]
            }
        ]
        
        errors = RestIntegrityValidator.validate_rest_not_interrupted(duties, {})
        
        assert len(errors) > 0
        assert errors[0]["type"] == "REST_INTERRUPTED"
    



class TestOperatorSkillValidator:
    """Testa validação de skill do operador"""
    
    def test_skill_mismatch_detection(self):
        """Operador sem skill requerida = ERRO"""
        from src.services.solution_validator import OperatorSkillValidator
        
        blocks = [
            {
                "block_id": 1,
                "items": [
                    {"tripId": 1, "required_skill": "ARTICULATED"}
                ]
            }
        ]
        
        duties = [
            {
                "duty_id": 1,
                "operator_id": "OP_1",
                "trip_ids": [1]
            }
        ]
        
        operator_skills = {
            "OP_1": ["STANDARD"]  # Não tem ARTICULATED ❌
        }
        
        errors = OperatorSkillValidator.validate_operator_skills(
            blocks, duties, [], operator_skills
        )
