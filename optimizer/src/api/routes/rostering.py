import logging
from fastapi import APIRouter, HTTPException
from ..schemas import (
    NominalRosteringRequest, 
    NominalRosteringResponse, 
    AssignmentOutput
)
from ...services.rostering.solver import NominalRosteringSolver
from ...domain.models import (
    OperatorProfile, 
    RosteringRule, 
    Duty, 
    Trip, 
    DutySegment,
    RuleType
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/", 
    response_model=NominalRosteringResponse, 
    tags=["rostering"],
    summary="Atribuição Nominal de Motoristas a Jornadas (Rostering)",
    description="Maximiza a afinidade e utilidade global usando PuLP."
)
async def run_nominal_rostering(body: NominalRosteringRequest):
    """
    Recebe um conjunto de jornadas (geradas pelo CSP) e uma lista de motoristas 
    com seus metadados para realizar a atribuição matemática ótima.
    """
    logger.info(
        "nominal_rostering_request: operators=%d, duties=%d", 
        len(body.operators), 
        len(body.duties)
    )
    
    try:
        # ── 1. Reconstrução do Domínio ──────────────────────────────────────
        operators = [
            OperatorProfile(
                id=op.id,
                name=op.name,
                cp=op.cp,
                last_shift_end=op.last_shift_end,
                metadata=op.metadata
            ) for op in body.operators
        ]
        
        rules = [
            RosteringRule(
                rule_id=r.rule_id,
                type=RuleType(r.type),
                weight=r.weight,
                meta=r.meta
            ) for r in body.rules
        ]
        
        duties = []
        for d_out in body.duties:
            d = Duty(id=d_out.duty_id)
            
            # Reconstruir trips para o Evaluator saber as linhas/horários
            duty_trips = []
            trips_raw = getattr(d_out, 'trips', []) or []
            
            for t_data in trips_raw:
                # Pydantic model ou dict
                if hasattr(t_data, 'model_dump'):
                    t_dict = t_data.model_dump()
                else:
                    t_dict = t_data
                
                duty_trips.append(Trip(
                    id=t_dict.get("id", 0),
                    line_id=t_dict.get("line_id", 0),
                    start_time=t_dict.get("start_time", 0),
                    end_time=t_dict.get("end_time", 0),
                    origin_id=t_dict.get("origin_id", 0),
                    destination_id=t_dict.get("destination_id", 0)
                ))
            
            # Duty domain model depende de segments para property all_trips
            if duty_trips:
                d.segments = [DutySegment(block_id=0, trips=duty_trips)]
            elif d_out.start_time is not None:
                # Fallback se não houver trips detalhadas, injetamos uma trip fake 
                # para preservar os horários da jornada no evaluator
                fake_trip = Trip(
                    id=-1,
                    line_id=-1,
                    start_time=d_out.start_time,
                    end_time=d_out.end_time or d_out.start_time,
                    origin_id=-1,
                    destination_id=-1
                )
                d.segments = [DutySegment(block_id=0, trips=[fake_trip])]
            
            duties.append(d)

        # ── 2. Execução do Solver ──────────────────────────────────────────
        solver = NominalRosteringSolver()
        solution = solver.solve(
            operators=operators,
            duties=duties,
            rules=rules,
            inter_shift_rest_minutes=body.inter_shift_rest_minutes
        )
        
        # ── 3. Preparação da Resposta ──────────────────────────────────────
        operator_map = {op.id: op.name for op in operators}
        
        return NominalRosteringResponse(
            status="ok",
            assignments=[
                AssignmentOutput(
                    operator_id=a.operator_id,
                    operator_name=operator_map.get(a.operator_id, "Desconhecido"),
                    duty_id=a.duty_id,
                    score=a.score,
                    explanations=a.explanations
                ) for a in solution.assignments
            ],
            unassigned_duties=solution.unassigned_duties,
            total_utility=solution.total_utility,
            elapsed_ms=solution.elapsed_ms,
            logs=solution.logs
        )
        
    except Exception as exc:
        logger.exception("Erro crítico no processamento de Rostering nominal")
        raise HTTPException(
            status_code=500,
            detail=f"Falha interna no motor de Rostering: {str(exc)}"
        )
