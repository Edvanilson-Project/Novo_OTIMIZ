from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..domain.models import Block, Duty


def _sorted_tasks(duty: Duty) -> List[Block]:
    return sorted((task for task in duty.tasks if task.trips), key=lambda item: (item.start_time, item.id))


def build_duty_operational_time_report(
    duty: Duty,
    *,
    min_break_minutes: int,
    meal_break_minutes: int,
    mandatory_break_after_minutes: int,
    pullout_counts_in_driver_shift: bool = True,
    pullback_counts_in_driver_shift: bool = True,
) -> Dict[str, Any]:
    tasks = _sorted_tasks(duty)
    if not tasks:
        return {
            "duty_id": int(duty.id),
            "work_time": 0,
            "driving_time": 0,
            "idle_time": 0,
            "normal_break_time": 0,
            "mandatory_rest_time": 0,
            "pullout_time": 0,
            "pullback_time": 0,
            "has_valid_mandatory_rest": False,
            "mandatory_rest_required": False,
            "invalid_rest_position": False,
            "violations": [],
            "duty_time_segments": [],
            "user_explanation": "Jornada sem tarefas operacionais.",
            "suggestion": "Revisar a geração da duty.",
        }

    required_rest = max(0, int(max(min_break_minutes, meal_break_minutes)))
    mandatory_break_after = max(0, int(mandatory_break_after_minutes))
    start_buffer = max(0, int(duty.meta.get("start_buffer_minutes", 0) or 0))
    end_buffer = max(0, int(duty.meta.get("end_buffer_minutes", 0) or 0))
    duty_start = int(
        duty.meta.get(
            "duty_start_minutes", tasks[0].start_time - (start_buffer if pullout_counts_in_driver_shift else 0)
        )
    )
    duty_end = int(
        duty.meta.get("duty_end_minutes", tasks[-1].end_time + (end_buffer if pullback_counts_in_driver_shift else 0))
    )

    total_drive = 0
    cumulative_work_before_gap = 0
    work_after_by_index: List[int] = []
    task_work: List[int] = []
    for task in tasks:
        minutes = int(task.meta.get("task_drive_minutes", sum(trip.duration for trip in task.trips)) or 0)
        task_work.append(minutes)
        total_drive += minutes
    remaining = total_drive
    for minutes in task_work:
        remaining -= minutes
        work_after_by_index.append(max(0, remaining))

    segments: List[Dict[str, Any]] = []
    idle_time = 0
    normal_break_time = 0
    mandatory_rest_time = 0

    segments.append(
        {
            "type": "duty_start",
            "event_scope": "driver",
            "start": duty_start,
            "end": duty_start,
            "duration": 0,
            "location": tasks[0].trips[0].origin_id,
        }
    )

    is_block_start = bool(tasks[0].meta.get("is_source_block_start", False))
    is_block_end = bool(tasks[-1].meta.get("is_source_block_end", False))

    if is_block_start and start_buffer > 0 and pullout_counts_in_driver_shift:
        segments.append(
            {
                "type": "pullout",
                "event_scope": "driver",
                "start": tasks[0].start_time - start_buffer,
                "end": tasks[0].start_time,
                "duration": start_buffer,
                "location": tasks[0].trips[0].origin_id,
            }
        )
    elif not is_block_start:
        first_block_id = int(tasks[0].meta.get("source_block_id", tasks[0].id))
        segments.append(
            {
                "type": "driver_change",
                "event_scope": "driver",
                "start": int(tasks[0].start_time),
                "end": int(tasks[0].start_time),
                "duration": 0,
                "location": tasks[0].trips[0].origin_id,
                "from_block_id": first_block_id,
                "to_block_id": first_block_id,
                "from_vehicle_id": first_block_id,
                "to_vehicle_id": first_block_id,
                "explanation": "Motorista assume veículo em operação (rendição no início da jornada).",
                "relief_role": "incoming",
            }
        )

    for index, task in enumerate(tasks):
        trip_ids = list(dict.fromkeys(int(getattr(trip, "public_id", trip.id)) for trip in task.trips))
        trip_group_ids = sorted({int(trip.trip_group_id) for trip in task.trips if trip.trip_group_id is not None})
        trip_directions = sorted({str(trip.direction) for trip in task.trips if trip.direction})
        block_id = int(task.meta.get("source_block_id", task.id))
        trip_count = len(trip_ids)
        segments.append(
            {
                "type": "commercial_trip",
                "event_scope": "driver_vehicle",
                "start": int(task.start_time),
                "end": int(task.end_time),
                "duration": int(task.end_time) - int(task.start_time),
                "trip_ids": trip_ids,
                "trip_count": trip_count,
                "block_id": block_id,
                "vehicle_id": block_id,
                "location_start": task.trips[0].origin_id,
                "location_end": task.trips[-1].destination_id,
                "driving_time": int(task_work[index]),
                "trip_group_ids": trip_group_ids,
                "trip_directions": trip_directions,
                **({"bundle_event_type": "commercial_trip_bundle"} if trip_count > 1 else {}),
                **(
                    {"explanation": f"Segmento operacional agrupado com {trip_count} viagens reais."}
                    if trip_count > 1
                    else {}
                ),
            }
        )
        cumulative_work_before_gap += int(task_work[index])

        if index == len(tasks) - 1:
            continue

        current = task
        nxt = tasks[index + 1]
        current_block_id = int(current.meta.get("source_block_id", current.id))
        next_block_id = int(nxt.meta.get("source_block_id", nxt.id))
        if current_block_id != next_block_id:
            segments.append(
                {
                    "type": "driver_vehicle_change",
                    "event_scope": "driver",
                    "start": int(current.end_time),
                    "end": int(current.end_time),
                    "duration": 0,
                    "location": current.trips[-1].destination_id,
                    "from_block_id": current_block_id,
                    "to_block_id": next_block_id,
                    "from_vehicle_id": current_block_id,
                    "to_vehicle_id": next_block_id,
                    "explanation": "Motorista troca de veículo entre blocos distintos da mesma jornada.",
                }
            )

        gap = max(0, int(nxt.start_time) - int(current.end_time))
        if gap <= 0:
            continue

        work_after_gap = work_after_by_index[index]
        qualifies_as_mandatory_rest = (
            required_rest > 0
            and gap >= required_rest
            and cumulative_work_before_gap >= mandatory_break_after
            and work_after_gap > 0
        )
        # BUG-OTS-07 fix: salvar work_before ANTES do reset do contador.
        # Antes, o reset ocorria na linha 186 e work_before_minutes recebia 0 (já zerado).
        work_before_this_gap = cumulative_work_before_gap
        if qualifies_as_mandatory_rest:
            segment_type = "mandatory_rest"
            mandatory_rest_time += gap
            cumulative_work_before_gap = 0  # Motorista reinicia o contador após descanso obrigatório
        elif gap >= max(0, int(min_break_minutes)):
            segment_type = "normal_break"
            normal_break_time += gap
        else:
            segment_type = "driver_idle"
            idle_time += gap

        segments.append(
            {
                "type": segment_type,
                "event_scope": "driver",
                "start": int(current.end_time),
                "end": int(nxt.start_time),
                "duration": gap,
                "location": current.trips[-1].destination_id,
                "from_block_id": current_block_id,
                "to_block_id": next_block_id,
                "work_before_minutes": work_before_this_gap,
                "work_after_minutes": work_after_gap,
            }
        )

    if is_block_end and end_buffer > 0 and pullback_counts_in_driver_shift:
        segments.append(
            {
                "type": "pullback",
                "event_scope": "driver",
                "start": tasks[-1].end_time,
                "end": tasks[-1].end_time + end_buffer,
                "duration": end_buffer,
                "location": tasks[-1].trips[-1].destination_id,
            }
        )
    elif not is_block_end:
        last_block_id = int(tasks[-1].meta.get("source_block_id", tasks[-1].id))
        segments.append(
            {
                "type": "driver_change",
                "event_scope": "driver",
                "start": int(tasks[-1].end_time),
                "end": int(tasks[-1].end_time),
                "duration": 0,
                "location": tasks[-1].trips[-1].destination_id,
                "from_block_id": last_block_id,
                "to_block_id": last_block_id,
                "from_vehicle_id": last_block_id,
                "to_vehicle_id": last_block_id,
                "explanation": "Motorista entrega veículo para rendição (rendição no fim da jornada).",
                "relief_role": "outgoing",
            }
        )

    segments.append(
        {
            "type": "duty_end",
            "event_scope": "driver",
            "start": duty_end,
            "end": duty_end,
            "duration": 0,
            "location": tasks[-1].trips[-1].destination_id,
        }
    )

    has_valid_mandatory_rest = mandatory_rest_time > 0
    invalid_rest_position = bool(required_rest > 0 and (start_buffer >= required_rest or end_buffer >= required_rest))
    # BUG-OTS-06 fix: expressão morta `int(duty.work_time or total_drive)` sem atribuição removida.
    max_continuous_drive = int(duty.meta.get("max_continuous_drive_minutes", 0) or 0)
    # CCT BR transporte urbano (CLT art. 235-D): pausa obrigatória de 30min é exigida
    # quando há CONDUÇÃO CONTÍNUA acima do limite (mandatory_break_after, ex: 4h).
    # Trabalho TOTAL fragmentado em pedaços menores com pausas válidas entre não exige
    # pausa adicional só por causa do total. (A regra de meal break para jornada > 6h
    # é separada e tratada via meal_break_minutes na classificação dos gaps.)
    # A condição antiga `productive_minutes > mandatory_break_after` produzia falso-positivo
    # em duties como D27/D32/D43 (work 316min com max_continuous 110min).
    mandatory_rest_required = bool(
        required_rest > 0 and (has_valid_mandatory_rest or max_continuous_drive > mandatory_break_after)
    )

    violations: List[str] = []
    if invalid_rest_position:
        violations.append("INVALID_REST_POSITION")
    if mandatory_rest_required and not has_valid_mandatory_rest:
        violations.append("MANDATORY_REST_MISSING")

    window_total = max(0, duty_end - duty_start)
    productive = int(duty.work_time or total_drive)
    non_productive = max(0, window_total - productive)
    if has_valid_mandatory_rest:
        user_explanation = (
            f"Esta jornada possui {window_total} minutos de janela total, {productive} minutos de trabalho produtivo e "
            f"{mandatory_rest_time} minutos de descanso obrigatorio valido no meio da jornada."
        )
    elif invalid_rest_position:
        user_explanation = (
            f"Esta jornada possui {window_total} minutos de janela total, {productive} minutos de trabalho produtivo e "
            f"{non_productive} minutos sem producao. Uma pausa longa no inicio/fim da jornada nao foi aceita como descanso obrigatorio."  # noqa: E501
        )
    else:
        user_explanation = (
            f"Esta jornada possui {window_total} minutos de janela total, mas apenas {productive} minutos de trabalho produtivo. "  # noqa: E501
            f"Os {non_productive} minutos restantes ficaram classificados como espera operacional, pausa normal ou buffers de soltura/recolhimento."  # noqa: E501
        )

    if mandatory_rest_required and not has_valid_mandatory_rest:
        suggestion = "Adicionar uma duty, revisar o pairing ou ajustar a regra configuravel de mandatory_rest da CCT."
    elif idle_time > productive:
        suggestion = "Aceitar com warning apenas se a ociosidade longa fizer sentido operacional; caso contrario, revisar o pairing."  # noqa: E501
    else:
        suggestion = "Aceitar com warning se os tempos estiverem aderentes a operacao real."

    operator_id = duty.meta.get("operator_id") if isinstance(duty.meta, dict) else None

    return {
        "duty_id": int(duty.id),
        "operator_not_assigned": operator_id is None,
        "duty_start": duty_start,
        "duty_end": duty_end,
        "window_time": window_total,
        "work_time": int(duty.work_time or total_drive),
        "driving_time": int(total_drive),
        "idle_time": int(idle_time),
        "normal_break_time": int(normal_break_time),
        "mandatory_rest_time": int(mandatory_rest_time),
        "pullout_time": int(start_buffer),
        "pullback_time": int(end_buffer),
        "has_valid_mandatory_rest": has_valid_mandatory_rest,
        "mandatory_rest_required": mandatory_rest_required,
        "invalid_rest_position": invalid_rest_position,
        "violations": violations,
        "duty_time_segments": segments,
        "user_explanation": user_explanation,
        "suggestion": suggestion,
    }


def summarize_operational_time_reports(duties: Sequence[Duty]) -> Dict[str, Any]:
    reports = [
        dict(duty.meta.get("operational_time_report") or {})
        for duty in duties
        if duty.meta.get("operational_time_report")
    ]
    return {
        "duties": reports,
        "summary": {
            "duties_with_valid_mandatory_rest": sum(1 for report in reports if report.get("has_valid_mandatory_rest")),
            "duties_missing_mandatory_rest": sum(
                1 for report in reports if "MANDATORY_REST_MISSING" in (report.get("violations") or [])
            ),
            "duties_with_invalid_rest_position": sum(1 for report in reports if report.get("invalid_rest_position")),
            "total_idle_time": sum(int(report.get("idle_time", 0) or 0) for report in reports),
            "total_normal_break_time": sum(int(report.get("normal_break_time", 0) or 0) for report in reports),
            "total_mandatory_rest_time": sum(int(report.get("mandatory_rest_time", 0) or 0) for report in reports),
            "total_pullout_time": sum(int(report.get("pullout_time", 0) or 0) for report in reports),
            "total_pullback_time": sum(int(report.get("pullback_time", 0) or 0) for report in reports),
        },
    }
