import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.domain.models import Block, CSPSolution, Duty, OptimizationResult, Trip, VSPSolution
from src.services.hard_constraint_validator import HardConstraintValidator
from src.services.operational_time_service import build_duty_operational_time_report


def _trip(
    trip_id: int,
    start: int,
    end: int,
    *,
    origin: int = 1,
    dest: int = 2,
    direction: str | None = None,
    trip_group_id: int | None = None,
) -> Trip:
    return Trip(
        id=trip_id,
        line_id=1,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        direction=direction,
        trip_group_id=trip_group_id,
        duration=end - start,
        distance_km=10.0,
        deadhead_times={origin: 0, dest: 0},
    )


def _block(block_id: int, trip: Trip) -> Block:
    block = Block(id=block_id, trips=[trip])
    block.meta.update(
        {
            "source_block_id": block_id,
            "task_id": block_id,
            "task_drive_minutes": trip.duration,
            "task_start_buffer_minutes": 0,
            "task_end_buffer_minutes": 0,
        }
    )
    return block


def _duty(
    blocks: list[Block],
    *,
    duty_id: int = 1,
    start_buffer: int = 0,
    end_buffer: int = 0,
) -> Duty:
    duty = Duty(id=duty_id)
    for block in blocks:
        duty.add_task(block)
    duty.meta["start_buffer_minutes"] = start_buffer
    duty.meta["end_buffer_minutes"] = end_buffer
    duty.meta["duty_start_minutes"] = blocks[0].start_time - start_buffer
    duty.meta["duty_end_minutes"] = blocks[-1].end_time + end_buffer
    duty.spread_time = duty.meta["duty_end_minutes"] - duty.meta["duty_start_minutes"]
    duty.work_time = sum(trip.duration for block in blocks for trip in block.trips)
    return duty


def test_idle_gap_does_not_become_mandatory_rest():
    block_a = _block(1, _trip(1, 9 * 60, 10 * 60, origin=1, dest=2))
    block_b = _block(2, _trip(2, 10 * 60 + 20, 11 * 60, origin=2, dest=3))
    duty = _duty([block_a, block_b])

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=45,
        mandatory_break_after_minutes=240,
    )

    assert report["idle_time"] == 20
    assert report["normal_break_time"] == 0
    assert report["mandatory_rest_time"] == 0
    assert report["has_valid_mandatory_rest"] is False


def test_normal_break_is_separate_from_mandatory_rest():
    block_a = _block(1, _trip(1, 9 * 60, 10 * 60, origin=1, dest=2))
    block_b = _block(2, _trip(2, 10 * 60 + 40, 11 * 60 + 10, origin=2, dest=3))
    duty = _duty([block_a, block_b])

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=240,
    )

    assert report["idle_time"] == 0
    assert report["normal_break_time"] == 40
    assert report["mandatory_rest_time"] == 0


def test_long_spread_with_low_work_does_not_require_mandatory_rest():
    block_a = _block(1, _trip(1, 6 * 60, 7 * 60 + 40, origin=1, dest=2))
    block_b = _block(2, _trip(2, 11 * 60, 12 * 60 + 40, origin=2, dest=3))
    block_c = _block(3, _trip(3, 13 * 60, 13 * 60 + 20, origin=3, dest=1))
    duty = _duty([block_a, block_b, block_c])

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=30,
        mandatory_break_after_minutes=240,
    )

    assert duty.spread_time > 360
    assert report["work_time"] == 220
    assert report["mandatory_rest_required"] is False
    assert report["has_valid_mandatory_rest"] is False


def test_operational_time_report_respeita_operator_id_em_meta():
    block = _block(1, _trip(1, 9 * 60, 10 * 60, origin=1, dest=2))
    duty = _duty([block])
    duty.meta["operator_id"] = 7

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=45,
        mandatory_break_after_minutes=240,
    )

    assert report["operator_not_assigned"] is False


def test_compact_result_expoe_vehicle_id_e_operator_id():
    trip = _trip(1, 9 * 60, 10 * 60, origin=1, dest=2)
    block = _block(11, trip)
    block.meta["vehicle_id"] = 91
    duty = _duty([block], duty_id=21)
    duty.meta["operator_id"] = 7
    duty.meta["operator_name"] = "Motorista 7"

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[duty]),
        total_cost=123.0,
    )

    compact = result.as_compact_dict()

    assert compact["blocks"][0]["vehicle_id"] == 91
    assert compact["duties"][0]["operator_id"] == 7
    assert compact["duties"][0]["operator_name"] == "Motorista 7"


def test_mandatory_rest_requires_mid_duty_gap_and_work_before_it():
    block_a = _block(1, _trip(1, 6 * 60, 9 * 60, origin=1, dest=2))
    block_b = _block(2, _trip(2, 10 * 60, 12 * 60, origin=2, dest=3))
    duty = _duty([block_a, block_b])

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=45,
        mandatory_break_after_minutes=180,
    )

    assert report["mandatory_rest_time"] == 60
    assert report["has_valid_mandatory_rest"] is True
    assert report["mandatory_rest_required"] is True


def test_pullout_and_pullback_do_not_count_as_mandatory_rest():
    block = _block(1, _trip(1, 6 * 60, 8 * 60, origin=1, dest=2))
    duty = _duty([block], start_buffer=60, end_buffer=25)

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=45,
        mandatory_break_after_minutes=180,
    )

    assert report["pullout_time"] == 60
    assert report["pullback_time"] == 25
    assert report["has_valid_mandatory_rest"] is False
    assert report["invalid_rest_position"] is True
    assert "INVALID_REST_POSITION" in report["violations"]


def test_validator_uses_clear_operational_time_violation_codes():
    block = _block(1, _trip(1, 6 * 60, 11 * 60, origin=1, dest=2))
    duty = _duty([block], start_buffer=60)
    duty.meta["max_continuous_drive_minutes"] = 300

    result = OptimizationResult(
        vsp=VSPSolution(blocks=[block]),
        csp=CSPSolution(duties=[duty]),
    )
    report = HardConstraintValidator().audit_result(
        result,
        trips=block.trips,
        cct_params={
            "apply_cct": True,
            "max_shift_minutes": 720,
            "max_driving_minutes": 240,
            "min_break_minutes": 30,
            "meal_break_minutes": 45,
            "mandatory_break_after_minutes": 240,
        },
        vsp_params={},
    )

    assert "MAX_DRIVING_EXCEEDED D1" in report["hard_issues"]
    assert "MANDATORY_REST_MISSING D1" in report["soft_issues"]
    assert "INVALID_REST_POSITION D1" in report["soft_issues"]


# ─────────────────────────────────────────────────────────────────────────────
# Testes de Soltura (pullout) e Recolhimento (pullback) na Jornada
# Especificacao:
#   1. pullout_minutes antecipa o inicio da duty
#   2. pullback_minutes posterga o fim da duty
#   3. spread_time considera pullout + viagens + pullback
#   4. max_shift_minutes usa esse spread completo
#   5. overtime usa work_time (tempo de trabalho), NAO spread
#   6. pullout/pullback nao podem contar como descanso obrigatorio
#   7. operational_time_report expoe: pullout_time, pullback_time,
#      duty_start, duty_end, spread_time (window_time)
# ─────────────────────────────────────────────────────────────────────────────


def _make_duty_with_buffers(
    first_trip_start: int,
    last_trip_end: int,
    pullout: int,
    pullback: int,
    *,
    duty_id: int = 99,
) -> Duty:
    """Cria Duty com dois blocos e buffers de pullout/pullback."""
    block_first = _block(1, _trip(1, first_trip_start, first_trip_start + 60, origin=1, dest=2))
    block_first.meta["task_start_buffer_minutes"] = pullout
    block_first.meta["task_end_buffer_minutes"] = 0
    block_first.meta["is_source_block_start"] = True
    block_first.meta["is_source_block_end"] = False

    block_last = _block(2, _trip(2, last_trip_end - 60, last_trip_end, origin=2, dest=1))
    block_last.meta["task_start_buffer_minutes"] = 0
    block_last.meta["task_end_buffer_minutes"] = pullback
    block_last.meta["is_source_block_start"] = False
    block_last.meta["is_source_block_end"] = True

    duty = Duty(id=duty_id)
    duty.add_task(block_first)
    duty.add_task(block_last)

    duty.meta["start_buffer_minutes"] = pullout
    duty.meta["end_buffer_minutes"] = pullback
    duty.meta["duty_start_minutes"] = first_trip_start - pullout
    duty.meta["duty_end_minutes"] = last_trip_end + pullback
    duty.spread_time = (last_trip_end + pullback) - (first_trip_start - pullout)
    duty.work_time = sum(trip.duration for b in [block_first, block_last] for trip in b.trips)
    return duty


# -- Regra 1: pullout_minutes antecipa o inicio da duty -----------------------
def test_pullout_antecipa_inicio_da_duty():
    """duty_start deve ser first_trip.start - pullout_minutes."""
    duty = _make_duty_with_buffers(
        first_trip_start=6 * 60,
        last_trip_end=19 * 60,
        pullout=20,
        pullback=25,
    )
    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )
    assert report["duty_start"] == 6 * 60 - 20, (
        f"duty_start esperado {6*60-20} (05:40), obtido {report['duty_start']}"
    )
    assert report["pullout_time"] == 20


# -- Regra 2: pullback_minutes posterga o fim da duty -------------------------
def test_pullback_posterga_fim_da_duty():
    """duty_end deve ser last_trip.end + pullback_minutes."""
    duty = _make_duty_with_buffers(
        first_trip_start=6 * 60,
        last_trip_end=19 * 60,
        pullout=20,
        pullback=25,
    )
    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )
    assert report["duty_end"] == 19 * 60 + 25, (
        f"duty_end esperado {19*60+25} (19:25), obtido {report['duty_end']}"
    )
    assert report["pullback_time"] == 25


# -- Regra 3: spread_time considera pullout + viagens + pullback ---------------
def test_spread_time_inclui_pullout_e_pullback():
    """window_time = duty_end - duty_start = pullout + viagens + pullback."""
    first_trip_start = 6 * 60
    last_trip_end = 19 * 60
    pullout = 20
    pullback = 25
    expected_spread = (last_trip_end + pullback) - (first_trip_start - pullout)  # 825

    duty = _make_duty_with_buffers(
        first_trip_start=first_trip_start,
        last_trip_end=last_trip_end,
        pullout=pullout,
        pullback=pullback,
    )
    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )
    assert report["window_time"] == expected_spread, (
        f"spread esperado {expected_spread}, obtido {report['window_time']}"
    )


# -- Regra 4: max_shift usa o spread completo (_duty_spread_minutes) -----------
def test_max_shift_usa_spread_com_buffers():
    """_duty_spread_minutes inclui pullout + pullback para validacao de max_shift."""
    from src.algorithms.csp.greedy import GreedyCSP as GreedyCSPSolver

    pullout = 20
    pullback = 25
    first_start = 6 * 60
    last_end = 19 * 60
    expected_spread = (last_end + pullback) - (first_start - pullout)  # 825

    trip = Trip(
        id=1, line_id=1,
        start_time=first_start, end_time=last_end,
        origin_id=1, destination_id=2,
        duration=last_end - first_start,
        distance_km=100.0,
        deadhead_times={},
        idle_before_minutes=pullout,
        idle_after_minutes=pullback,
    )
    block = Block(id=1, trips=[trip])
    block.meta["source_block_id"] = 1
    block.meta["task_drive_minutes"] = trip.duration

    solver = GreedyCSPSolver(
        params={"pullout_minutes": pullout, "pullback_minutes": pullback, "apply_cct": False},
        vsp_params={},
    )
    solver._annotate_source_block_boundaries([block])
    computed_spread = solver._duty_spread_minutes([block])

    assert computed_spread == expected_spread, (
        f"_duty_spread_minutes esperado {expected_spread}, obtido {computed_spread}"
    )


# -- Regra 5: overtime usa work_time, NAO spread --------------------------------
def test_overtime_usa_work_time_nao_spread():
    """_regular_overtime_minutes so conta excesso sobre max_work, nao sobre spread."""
    from src.algorithms.csp.greedy import GreedyCSP as GreedyCSPSolver

    solver = GreedyCSPSolver(
        params={"max_work_minutes": 480, "apply_cct": True},
        vsp_params={},
    )
    assert solver._regular_overtime_minutes(460) == 0
    assert solver._regular_overtime_minutes(500) == 20
    # work_time=340 com spread=825 (pullout+pullback) -> zero overtime
    assert solver._regular_overtime_minutes(340) == 0


# -- Regra 6: pullout/pullback nao contam como descanso obrigatorio ------------
def test_pullout_pullback_nao_contam_como_descanso_obrigatorio():
    """Buffers >= required_rest -> invalid_rest_position=True, mandatory_rest_time=0."""
    block = _block(1, _trip(1, 6 * 60, 8 * 60, origin=1, dest=2))
    duty = _duty([block], start_buffer=60, end_buffer=25)

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )
    assert report["mandatory_rest_time"] == 0, "Pullout NAO deve contar como descanso obrigatorio"
    assert report["has_valid_mandatory_rest"] is False
    assert report["invalid_rest_position"] is True
    assert "INVALID_REST_POSITION" in report["violations"]

    block2 = _block(1, _trip(1, 6 * 60, 8 * 60, origin=1, dest=2))
    duty2 = _duty([block2], start_buffer=0, end_buffer=60)
    report2 = build_duty_operational_time_report(
        duty2,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )
    assert report2["mandatory_rest_time"] == 0, "Pullback NAO deve contar como descanso obrigatorio"
    assert report2["invalid_rest_position"] is True


# -- Regra 7: operational_time_report expoe os campos corretos ----------------
def test_operational_time_report_expoe_campos_de_pullout_pullback():
    """Report deve conter: pullout_time, pullback_time, duty_start, duty_end, window_time."""
    duty = _make_duty_with_buffers(
        first_trip_start=6 * 60,
        last_trip_end=19 * 60,
        pullout=20,
        pullback=25,
    )
    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )

    for field in ["pullout_time", "pullback_time", "duty_start", "duty_end", "window_time"]:
        assert field in report, f"Campo '{field}' ausente no operational_time_report"
        assert report[field] is not None, f"Campo '{field}' e None"

    pullout_segs = [s for s in report["duty_time_segments"] if s["type"] == "pullout"]
    pullback_segs = [s for s in report["duty_time_segments"] if s["type"] == "pullback"]
    assert len(pullout_segs) == 1, "Deve existir exatamente 1 segmento pullout"
    assert len(pullback_segs) == 1, "Deve existir exatamente 1 segmento pullback"
    assert pullout_segs[0]["duration"] == 20
    assert pullback_segs[0]["duration"] == 25


# -- Teste Canonico de Aceitacao ----------------------------------------------
def test_pullout_pullback_canonical_acceptance():
    """
    Teste canonico de aceitacao:
      - primeira viagem: 06:00 (360 min)
      - ultima viagem termina: 19:00 (1140 min)
      - pullout: 20 min
      - pullback: 25 min

    Resultados esperados:
      - duty_start = 340  (05:40)
      - duty_end   = 1165 (19:25)
      - window_time = 825
      - Segmento pullout: start=340, end=360, duration=20
      - Segmento pullback: start=1140, end=1165, duration=25
      - has_valid_mandatory_rest = False
      - mandatory_rest_time = 0
    """
    FIRST_TRIP_START = 6 * 60    # 360
    LAST_TRIP_END    = 19 * 60   # 1140
    PULLOUT          = 20
    PULLBACK         = 25

    EXPECTED_DUTY_START = FIRST_TRIP_START - PULLOUT   # 340
    EXPECTED_DUTY_END   = LAST_TRIP_END + PULLBACK      # 1165
    EXPECTED_SPREAD     = EXPECTED_DUTY_END - EXPECTED_DUTY_START  # 825

    duty = _make_duty_with_buffers(
        first_trip_start=FIRST_TRIP_START,
        last_trip_end=LAST_TRIP_END,
        pullout=PULLOUT,
        pullback=PULLBACK,
    )

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )

    assert report["duty_start"] == EXPECTED_DUTY_START, (
        f"[FAIL] duty_start: esperado {EXPECTED_DUTY_START} (05:40), obtido {report['duty_start']}"
    )
    assert report["duty_end"] == EXPECTED_DUTY_END, (
        f"[FAIL] duty_end: esperado {EXPECTED_DUTY_END} (19:25), obtido {report['duty_end']}"
    )
    assert report["window_time"] == EXPECTED_SPREAD, (
        f"[FAIL] window_time: esperado {EXPECTED_SPREAD}, obtido {report['window_time']}"
    )
    assert report["pullout_time"] == PULLOUT
    assert report["pullback_time"] == PULLBACK

    pullout_seg = next((s for s in report["duty_time_segments"] if s["type"] == "pullout"), None)
    assert pullout_seg is not None, "[FAIL] Segmento 'pullout' nao encontrado"
    assert pullout_seg["start"] == EXPECTED_DUTY_START
    assert pullout_seg["end"] == FIRST_TRIP_START
    assert pullout_seg["duration"] == PULLOUT

    pullback_seg = next((s for s in report["duty_time_segments"] if s["type"] == "pullback"), None)
    assert pullback_seg is not None, "[FAIL] Segmento 'pullback' nao encontrado"
    assert pullback_seg["start"] == LAST_TRIP_END
    assert pullback_seg["end"] == EXPECTED_DUTY_END
    assert pullback_seg["duration"] == PULLBACK

    assert report["has_valid_mandatory_rest"] is False, (
        "[FAIL] Pullout/pullback nao devem gerar has_valid_mandatory_rest=True"
    )
    assert report["mandatory_rest_time"] == 0


def test_bundle_metadata_and_vehicle_change_segment_are_exposed():
    trip_a = _trip(1, 6 * 60, 6 * 60 + 20, origin=1, dest=2, direction="IDA", trip_group_id=700)
    trip_b = _trip(2, 6 * 60 + 20, 6 * 60 + 40, origin=2, dest=1, direction="VOLTA", trip_group_id=700)
    block_a = Block(id=1, trips=[trip_a, trip_b])
    block_a.meta.update(
        {
            "source_block_id": 1,
            "task_id": 1,
            "task_drive_minutes": trip_a.duration + trip_b.duration,
            "task_start_buffer_minutes": 0,
            "task_end_buffer_minutes": 0,
        }
    )

    trip_c = _trip(3, 7 * 60, 8 * 60, origin=1, dest=2, direction="IDA", trip_group_id=701)
    block_b = _block(2, trip_c)

    duty = _duty([block_a, block_b])
    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=15,
        meal_break_minutes=15,
        mandatory_break_after_minutes=240,
    )

    commercial_segments = [segment for segment in report["duty_time_segments"] if segment["type"] == "commercial_trip"]
    assert commercial_segments[0]["trip_count"] == 2
    assert commercial_segments[0]["bundle_event_type"] == "commercial_trip_bundle"
    assert commercial_segments[0]["event_scope"] == "driver_vehicle"
    assert commercial_segments[0]["trip_group_ids"] == [700]
    assert commercial_segments[0]["trip_directions"] == ["IDA", "VOLTA"]

    vehicle_changes = [segment for segment in report["duty_time_segments"] if segment["type"] == "driver_vehicle_change"]
    assert len(vehicle_changes) == 1
    assert vehicle_changes[0]["from_block_id"] == 1
    assert vehicle_changes[0]["to_block_id"] == 2
    assert vehicle_changes[0]["event_scope"] == "driver"


def test_cumulative_work_resets_after_mandatory_rest():
    """
    Após um descanso obrigatório, o contador de trabalho acumulado deve zerar.
    Sem o reset, o segundo intervalo (gap2) seria classificado como mandatory_rest
    porque cumulative continua crescendo além de mandatory_break_after.
    Com o reset, gap2 < mandatory_break_after → normal_break.

    Cenário:
      A(150min) → gap1(45min, mandatory_rest) → B(90min) → gap2(45min, normal_break)
      mandatory_break_after=120min, required_rest=45min
    """
    block_a = _block(1, _trip(1, 0, 150, origin=1, dest=2))
    block_b = _block(2, _trip(2, 195, 285, origin=2, dest=3))
    block_c = _block(3, _trip(3, 330, 390, origin=3, dest=1))
    duty = _duty([block_a, block_b, block_c])

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=45,
        meal_break_minutes=45,
        mandatory_break_after_minutes=120,
    )

    # gap1=45 min, cumulative=150≥120, work_after>0 → mandatory_rest ✅
    # gap2=45 min, cumulative_after_reset=90<120 → normal_break ✅
    assert report["mandatory_rest_time"] == 45, "Apenas o primeiro gap deve ser mandatory_rest"
    assert report["normal_break_time"] == 45, "O segundo gap deve ser normal_break após o reset"
    assert report["has_valid_mandatory_rest"] is True

    seg_types = [s["type"] for s in report["duty_time_segments"]]
    assert seg_types.count("mandatory_rest") == 1
    assert seg_types.count("normal_break") == 1


# -- Regra 9: rendição (driver_change) em duties que pegam veículo no meio do block ---
def test_driver_change_emitted_when_duty_starts_mid_block():
    """Duty cujo primeiro task NÃO é o início do source block deve emitir driver_change no início (rendição) e não pullout."""
    block = _block(1, _trip(1, 8 * 60, 9 * 60, origin=1, dest=2))
    block.meta["task_start_buffer_minutes"] = 0
    block.meta["task_end_buffer_minutes"] = 10
    block.meta["is_source_block_start"] = False
    block.meta["is_source_block_end"] = True
    block.meta["source_block_id"] = 42

    duty = Duty(id=77)
    duty.add_task(block)
    duty.meta["start_buffer_minutes"] = 0
    duty.meta["end_buffer_minutes"] = 10

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )

    seg_types = [s["type"] for s in report["duty_time_segments"]]
    assert "pullout" not in seg_types, "Não deve emitir pullout quando duty pega veículo em operação"
    driver_change = [s for s in report["duty_time_segments"] if s["type"] == "driver_change"]
    assert len(driver_change) == 1, "Deve emitir 1 driver_change no início"
    assert driver_change[0]["relief_role"] == "incoming"
    assert driver_change[0]["start"] == 8 * 60


def test_driver_change_emitted_when_duty_ends_mid_block():
    """Duty cujo último task NÃO é o fim do source block deve emitir driver_change no fim (rendição) e não pullback."""
    block = _block(1, _trip(1, 6 * 60, 7 * 60, origin=1, dest=2))
    block.meta["task_start_buffer_minutes"] = 10
    block.meta["task_end_buffer_minutes"] = 0
    block.meta["is_source_block_start"] = True
    block.meta["is_source_block_end"] = False
    block.meta["source_block_id"] = 42

    duty = Duty(id=78)
    duty.add_task(block)
    duty.meta["start_buffer_minutes"] = 10
    duty.meta["end_buffer_minutes"] = 0

    report = build_duty_operational_time_report(
        duty,
        min_break_minutes=30,
        meal_break_minutes=60,
        mandatory_break_after_minutes=270,
    )

    seg_types = [s["type"] for s in report["duty_time_segments"]]
    assert "pullback" not in seg_types, "Não deve emitir pullback quando duty entrega veículo em operação"
    driver_change = [s for s in report["duty_time_segments"] if s["type"] == "driver_change"]
    assert len(driver_change) == 1, "Deve emitir 1 driver_change no fim"
    assert driver_change[0]["relief_role"] == "outgoing"
    assert driver_change[0]["start"] == 7 * 60
