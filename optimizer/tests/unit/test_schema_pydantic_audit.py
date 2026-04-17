"""
Auditoria: Validações Pydantic dos schemas de entrada e saída do optimizer.

Cobre os contratos entre o backend NestJS e o FastAPI Python.
Grupo 1 do PLANO_COPILOT_WEB_OPT.md — Auditor de Schema.
"""
import pytest
from pydantic import ValidationError

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.api.schemas import (
    TripInput,
    OptimizeRequest,
    BlockOutput,
    DutyOutput,
    CctParamsInput,
    VspParamsInput,
)


# ─── Fixtures ───────────────────────────────────────────────

def make_trip_dict(**overrides):
    base = {
        "id": 1,
        "line_id": 16,
        "start_time": 360,
        "end_time": 420,
        "origin_id": 1,
        "destination_id": 2,
        "duration": 60,
        "deadhead_times": {"2": 10},
    }
    base.update(overrides)
    return base


# ─── TripInput Validation ─────────────────────────────────

class TestTripInputSchema:
    def test_valid_trip_accepted(self):
        trip = TripInput(**make_trip_dict())
        assert trip.id == 1
        assert trip.start_time == 360

    def test_trip_dict_object_rejects_raw_int_via_list(self):
        """Reproduz o bug histórico: trips=[int] passado para List[TripInput] causa ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            OptimizeRequest(
                trips=[1, 2, 3],  # tipo errado: int ao invés de TripInput dict
                algorithm="greedy",
            )
        errors = exc_info.value.errors()
        # Pydantic v2 usa 'model_type' quando o tipo esperado é um modelo e recebe um primitivo
        assert any("model_type" in str(e.get("type", "")) or "TripInput" in str(e.get("msg", "")) for e in errors)

    def test_trip_requires_start_time(self):
        data = make_trip_dict()
        del data["start_time"]
        with pytest.raises(ValidationError) as exc_info:
            TripInput(**data)
        assert any(e["loc"] == ("start_time",) for e in exc_info.value.errors())

    def test_trip_requires_origin_id(self):
        data = make_trip_dict()
        del data["origin_id"]
        with pytest.raises(ValidationError):
            TripInput(**data)

    def test_trip_end_time_before_start_time_is_accepted_by_schema(self):
        """Schema Pydantic não valida lógica de negócio (end > start), apenas tipos.
        Isso é intencionalmente delegado ao algoritmo."""
        trip = TripInput(**make_trip_dict(start_time=500, end_time=400))
        assert trip.start_time == 500
        assert trip.end_time == 400

    def test_deadhead_times_keys_coerced_to_int(self):
        trip = TripInput(**make_trip_dict(deadhead_times={"2": 15, "5": 20}))
        assert trip.deadhead_times == {2: 15, 5: 20}

    def test_trip_optional_fields_default(self):
        trip = TripInput(**make_trip_dict())
        assert trip.is_pull_out is False
        assert trip.is_pull_back is False
        assert trip.distance_km == 0.0
        assert trip.is_relief_point is False

    def test_mid_trip_relief_requires_point_and_offset_together(self):
        with pytest.raises(ValidationError):
            TripInput(**make_trip_dict(mid_trip_relief_point_id=99))

    def test_mid_trip_relief_rejects_endpoint_as_relief_point(self):
        with pytest.raises(ValidationError):
            TripInput(
                **make_trip_dict(
                    mid_trip_relief_point_id=1,
                    mid_trip_relief_offset_minutes=20,
                )
            )

    def test_mid_trip_relief_distance_ratio_must_be_inside_open_interval(self):
        with pytest.raises(ValidationError):
            TripInput(
                **make_trip_dict(
                    mid_trip_relief_point_id=9,
                    mid_trip_relief_offset_minutes=20,
                    mid_trip_relief_distance_ratio=1.0,
                )
            )


# ─── OptimizeRequest ──────────────────────────────────────

class TestOptimizeRequestSchema:
    def test_minimal_valid_request(self):
        req = OptimizeRequest(
            trips=[TripInput(**make_trip_dict())],
            algorithm="greedy",
        )
        assert req.algorithm.value == "greedy"
        assert len(req.trips) == 1

    def test_empty_trips_accepted_by_schema(self):
        """Schema aceita trips=[]; a rejeição de lista vazia é feita na rota /optimize."""
        req = OptimizeRequest(trips=[], algorithm="greedy")
        assert req.trips == []

    def test_invalid_algorithm_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            OptimizeRequest(
                trips=[TripInput(**make_trip_dict())],
                algorithm="magic_solver",
            )
        assert any("algorithm" in str(e) for e in exc_info.value.errors())

    def test_cct_params_connection_tolerance(self):
        req = OptimizeRequest(
            trips=[TripInput(**make_trip_dict())],
            algorithm="hybrid_pipeline",
            cct_params=CctParamsInput(connection_tolerance_minutes=5),
        )
        assert req.cct_params.connection_tolerance_minutes == 5

    def test_vsp_params_allow_multi_line(self):
        req = OptimizeRequest(
            trips=[TripInput(**make_trip_dict())],
            algorithm="greedy",
            vsp_params=VspParamsInput(allow_multi_line_block=False),
        )
        assert req.vsp_params.allow_multi_line_block is False

    def test_time_budget_s_accepts_float(self):
        req = OptimizeRequest(
            trips=[TripInput(**make_trip_dict())],
            algorithm="greedy",
            time_budget_s=15.5,
        )
        assert req.time_budget_s == 15.5


# ─── BlockOutput ─────────────────────────────────────────

class TestBlockOutputSchema:
    def test_trips_must_be_int_list(self):
        """BlockOutput.trips: List[int] — objetos dict devem ser normalizados ANTES."""
        with pytest.raises(ValidationError) as exc_info:
            BlockOutput(
                block_id=1,
                trips=[{"id": 1, "start_time": 360}],  # deve ser [1], não [dict]
                num_trips=1,
                start_time=360,
                end_time=420,
            )
        assert any("int_type" in str(e) for e in exc_info.value.errors())

    def test_trips_as_int_list_accepted(self):
        b = BlockOutput(
            block_id=1,
            trips=[1, 2, 3],
            num_trips=3,
            start_time=360,
            end_time=480,
        )
        assert b.trips == [1, 2, 3]


# ─── DutyOutput ──────────────────────────────────────────

class TestDutyOutputSchema:
    def test_duty_with_start_end_time(self):
        d = DutyOutput(
            duty_id=10,
            blocks=[1, 2],
            work_time=480,
            spread_time=560,
            rest_violations=0,
            start_time=360,
            end_time=920,
        )
        assert d.start_time == 360
        assert d.end_time == 920

    def test_duty_start_end_time_nullable(self):
        d = DutyOutput(
            duty_id=11,
            blocks=[1],
            work_time=300,
            spread_time=360,
            rest_violations=0,
        )
        assert d.start_time is None
        assert d.end_time is None

    def test_duty_trips_any_list_accepted(self):
        d = DutyOutput(
            duty_id=12,
            blocks=[1],
            work_time=300,
            spread_time=360,
            rest_violations=0,
            trips=[{"id": 1, "start_time": 360, "end_time": 420}],
        )
        assert len(d.trips) == 1


# ─── CctParamsInput ───────────────────────────────────────

class TestCctParamsInput:
    def test_all_optional(self):
        p = CctParamsInput()
        assert p.max_work_minutes is None
        assert p.connection_tolerance_minutes is None

    def test_negative_max_work_minutes_accepted_by_schema(self):
        """Schema não impede negativos — validação de negócio é no serviço."""
        p = CctParamsInput(max_work_minutes=-10)
        assert p.max_work_minutes == -10


# ─── VspParamsInput ───────────────────────────────────────

class TestVspParamsInput:
    def test_allow_multi_line_defaults_none(self):
        p = VspParamsInput()
        assert p.allow_multi_line_block is None

    def test_connection_tolerance_not_in_vsp_schema(self):
        """VspParamsInput não tem connection_tolerance_minutes — é propagado via pipeline."""
        assert not hasattr(VspParamsInput, "connection_tolerance_minutes")
