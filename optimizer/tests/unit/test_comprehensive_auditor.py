"""Tests for comprehensive solution auditor"""
import pytest
import sys
sys.path.insert(0, '/home/edvanilson/Área de trabalho/Novo_OTIMIZ/optimizer')

from src.services.comprehensive_auditor import ComprehensiveAuditor, audit_solution_quick


class TestComprehensiveAuditor:
    """Testa auditor completo"""
    
    def test_valid_solution_audit(self):
        """Solução válida deve retornar valid=true"""
        auditor = ComprehensiveAuditor()
        
        blocks = [{
            "block_id": 1,
            "items": [
                {"tripId": 1, "start_time": 600, "end_time": 630, "destination_id": 20},
                {"tripId": 2, "start_time": 640, "end_time": 700, "origin_id": 20}
            ]
        }]
        
        duties = [{
            "duty_id": 1,
            "start_time": 360,
            "end_time": 900
        }]
        
        trips = [{"id": 1}, {"id": 2}]
        params = {"max_shift_minutes": 600}
        
        report = auditor.audit_solution(blocks, duties, trips, params)
        
        assert report["summary"]["valid"] == True
        assert report["summary"]["errorCount"] == 0
    
    def test_invalid_solution_with_overlap(self):
        """Solução com sobreposição deve retornar valid=false"""
        auditor = ComprehensiveAuditor()
        
        blocks = [{
            "block_id": 1,
            "items": [
                {"tripId": 1, "start_time": 600, "end_time": 660},
                {"tripId": 2, "start_time": 650, "end_time": 720}  # OVERLAP
            ]
        }]
        
        duties = [{"duty_id": 1, "start_time": 360, "end_time": 900}]
        trips = [{"id": 1}, {"id": 2}]
        
        report = auditor.audit_solution(blocks, duties, trips, {})
        
        assert report["summary"]["valid"] == False
        assert report["summary"]["errorCount"] > 0
    
    def test_audit_report_structure(self):
        """Report tem toda estrutura necessária"""
        auditor = ComprehensiveAuditor()
        
        report = auditor.audit_solution(
            [{"block_id": 1, "items": []}],
            [{"duty_id": 1, "start_time": 360, "end_time": 900}],
            [],
            {}
        )
        
        assert "auditId" in report
        assert "timestamp" in report
        assert "summary" in report
        assert "errors" in report
        assert "warnings" in report
        assert "stats" in report
        assert "recommendations" in report
        assert report["auditId"].startswith("AUD_")
    
    def test_quick_audit(self):
        """Quick audit função works"""
        report = audit_solution_quick(
            [{"block_id": 1, "items": []}],
            [{"duty_id": 1, "start_time": 360, "end_time": 900}],
            [],
            {}
        )
        
        assert report["summary"]["valid"] == True
