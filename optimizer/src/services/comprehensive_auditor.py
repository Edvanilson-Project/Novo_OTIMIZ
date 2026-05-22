"""
Comprehensive Solution Auditor

Combines all validators to produce a complete audit report of a solution.
Used for:
1. Validating optimization results
2. Comparing manual vs. optimized solutions
3. Audit trails for compliance
"""

from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime

from .solution_validator import (
    SolutionValidator,
    UncoveredTripExplainer,
)
from .solution_validator import (
    MealBreakValidator,
    RestIntegrityValidator,
    OperatorSkillValidator,
    DeadheadTimeValidator,
)


class ComprehensiveAuditor:
    """Complete solution auditor with all validators"""

    def __init__(self, terminal_distances=None):
        self.core_validator = SolutionValidator(tolerance_minutes=5)
        self.uncovered_explainer = UncoveredTripExplainer()
        self.meal_validator = MealBreakValidator()
        self.rest_validator = RestIntegrityValidator()
        self.skill_validator = OperatorSkillValidator()
        self.deadhead_validator = DeadheadTimeValidator(terminal_distances)

    def audit_solution(
        self,
        blocks: Sequence[Dict[str, Any]],
        duties: Sequence[Dict[str, Any]],
        trips: Sequence[Dict[str, Any]],
        params: Dict[str, Any],
        operator_skills: Optional[Dict[int, List[str]]] = None,
        solution_name: str = "Unknown",
    ) -> Dict[str, Any]:
        """
        Complete audit of a solution

        Returns comprehensive report with:
        - Core validations (overlap, deadhead, max shift)
        - Advanced validations (meal, rest, skills, real deadhead)
        - Uncovered trip explanations
        - Statistics and summary
        """

        timestamp = datetime.now().isoformat()

        # 1. Core validations
        core_result = self.core_validator.validate(blocks, duties, trips, params)

        # 2. Advanced validations
        meal_errors = self.meal_validator.validate_meal_break_position(duties, params)
        rest_errors = self.rest_validator.validate_rest_not_interrupted(duties, params)
        skill_errors = (
            self.skill_validator.validate_operator_skills(blocks, duties, trips, operator_skills)
            if operator_skills
            else []
        )
        deadhead_errors = self.deadhead_validator.validate_real_deadhead(blocks)

        # 3. Combine all errors
        all_errors = list(core_result.errors)
        all_errors.extend(meal_errors)
        all_errors.extend(deadhead_errors)

        all_warnings = list(core_result.warnings)
        all_warnings.extend(rest_errors)
        all_warnings.extend(skill_errors)

        # 4. Uncovered trip explanations
        allocated_ids = set()
        for block in blocks:
            items = block.get("items") or block.get("trips") or []
            for item in items:
                trip_id = item.get("tripId") or item.get("id")
                if trip_id:
                    allocated_ids.add(trip_id)

        uncovered_explanations = self.uncovered_explainer.explain_uncovered_trips(trips, allocated_ids, blocks, params)

        # 5. Assemble final report
        return {
            "auditId": self._generate_audit_id(),
            "timestamp": timestamp,
            "solutionName": solution_name,
            "summary": {
                "valid": len(all_errors) == 0,
                "errorCount": len(all_errors),
                "warningCount": len(all_warnings),
                "totalIssues": len(all_errors) + len(all_warnings),
            },
            "errors": [self._format_issue(e) for e in all_errors],
            "warnings": [self._format_issue(w) for w in all_warnings],
            "uncoveredTrips": uncovered_explanations,
            "stats": core_result.stats,
            "detailedBreakdown": {
                "coreValidations": {
                    "timeOverlaps": len([e for e in core_result.errors if e.error_type == "TIME_OVERLAP"]),
                    "deadheadGaps": len([e for e in core_result.errors if e.error_type == "INSUFFICIENT_DEADHEAD"]),
                    "maxShiftViolations": len([e for e in core_result.errors if e.error_type == "MAX_SHIFT_EXCEEDED"]),
                },
                "advancedValidations": {
                    "mealBreakIssues": len(meal_errors),
                    "restIntegrityIssues": len(rest_errors),
                    "skillMismatches": len(skill_errors),
                    "realDeadheadIssues": len(deadhead_errors),
                },
            },
            "recommendations": self._generate_recommendations(all_errors, all_warnings, uncovered_explanations),
        }

    def _format_issue(self, issue):
        """Format issue for report"""
        if isinstance(issue, dict):
            return issue
        return issue.to_dict()

    def _generate_audit_id(self):
        """Generate unique audit ID"""
        import hashlib
        import time

        data = str(time.time()).encode()
        return "AUD_" + hashlib.md5(data).hexdigest()[:12].upper()

    def _generate_recommendations(self, errors, warnings, uncovered):
        """Generate recommendations based on findings"""
        recommendations = []

        if len(errors) > 5:
            recommendations.append(
                {
                    "priority": "CRITICAL",
                    "message": f"Solution has {len(errors)} errors. Major restructuring needed.",
                    "action": "Review algorithm parameters and retry optimization",
                }
            )

        if any(self._format_issue(e).get("type") == "TIME_OVERLAP" for e in errors):
            recommendations.append(
                {
                    "priority": "CRITICAL",
                    "message": "Time overlaps detected (same vehicle, different trips at same time)",
                    "action": "Check vehicle scheduling algorithm for concurrency issues",
                }
            )

        if len(uncovered) > 0:
            recommendations.append(
                {
                    "priority": "HIGH",
                    "message": f"{len(uncovered)} trips not covered by any vehicle",
                    "action": "Add more vehicles or relax constraints",
                }
            )

        if any(self._format_issue(w).get("type") == "REST_INTERRUPTED" for w in warnings):
            recommendations.append(
                {
                    "priority": "MEDIUM",
                    "message": "Rest periods interrupted by trips",
                    "action": "Ensure break times are respected in scheduling",
                }
            )

        return recommendations


def audit_solution_quick(
    blocks: Sequence[Dict[str, Any]],
    duties: Sequence[Dict[str, Any]],
    trips: Sequence[Dict[str, Any]],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Quick audit without advanced features"""
    auditor = ComprehensiveAuditor()
    return auditor.audit_solution(blocks, duties, trips, params)
