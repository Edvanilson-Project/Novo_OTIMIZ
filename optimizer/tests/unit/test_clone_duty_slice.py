"""Regressão: _clone_duty_slice deve recomputar boundaries da duty após o split.

Bug: D7 (left half) e D24 (right half) de um duty original 329→884 herdavam a
janela completa via copy.deepcopy(source.meta) — a operational_time_service
lia duty_start/end_minutes stale e produzia window_time=555 para uma duty que
opera apenas 329→429 (D7) ou 863→884 (D24).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.domain.models import Block, Duty, Trip
from src.services.optimizer_service import OptimizerService


def _trip(trip_id, start, end, origin=1, dest=2):
    return Trip(
        id=trip_id,
        line_id=1,
        start_time=start,
        end_time=end,
        origin_id=origin,
        destination_id=dest,
        duration=end - start,
        distance_km=10.0,
        deadhead_times={origin: 0, dest: 0},
    )


def _task(task_id, trips, *, is_block_start=False, is_block_end=False, start_buffer=0, end_buffer=0):
    block = Block(id=task_id, trips=list(trips), vehicle_type_id=1)
    block.meta.update(
        {
            "source_block_id": task_id,
            "task_id": task_id,
            "is_source_block_start": is_block_start,
            "is_source_block_end": is_block_end,
            "task_start_buffer_minutes": start_buffer,
            "task_end_buffer_minutes": end_buffer,
            "task_drive_minutes": sum(t.duration for t in trips),
        }
    )
    return block


def test_clone_duty_slice_recomputes_boundaries_after_split():
    """Source duty cobre 329→884; left slice deve ter duty_end=429, right slice deve ter duty_start=863."""
    # Tarefa 1: 329→429 (esquerda)
    task_left = _task(1, [_trip(1, 329, 347), _trip(2, 360, 387), _trip(3, 402, 429)],
                      is_block_start=True, is_block_end=False, start_buffer=10)
    # Tarefa 2: 863→884 (direita)
    task_right = _task(2, [_trip(4, 863, 884)], is_block_start=False, is_block_end=True, end_buffer=10)

    source = Duty(id=99)
    source.add_task(task_left)
    source.add_task(task_right)
    source.work_time = 21 + 71  # soma das durações
    source.spread_time = 884 - 329 + 10  # com end_buffer
    source.meta["duty_start_minutes"] = 329 - 10  # source full range com buffers
    source.meta["duty_end_minutes"] = 884 + 10
    source.meta["start_buffer_minutes"] = 10
    source.meta["end_buffer_minutes"] = 10

    service = OptimizerService()

    # Slice esquerda: só task_left
    left = service._clone_duty_slice(source, [task_left], duty_id=7)
    assert left.meta["duty_start_minutes"] == 319, f"left start esperado 319 (329-10 buffer), got {left.meta['duty_start_minutes']}"
    assert left.meta["duty_end_minutes"] == 429, f"left end esperado 429 (último trip), got {left.meta['duty_end_minutes']}"
    assert left.meta["end_buffer_minutes"] == 0, "left não deve ter end buffer (não é fim do block)"
    assert left.spread_time == 110, f"spread esperado 110 (429-319), got {left.spread_time}"

    # Slice direita: só task_right
    right = service._clone_duty_slice(source, [task_right], duty_id=24)
    assert right.meta["duty_start_minutes"] == 863, f"right start esperado 863, got {right.meta['duty_start_minutes']}"
    assert right.meta["duty_end_minutes"] == 894, f"right end esperado 894 (884+10 buffer), got {right.meta['duty_end_minutes']}"
    assert right.meta["start_buffer_minutes"] == 0, "right não deve ter start buffer (não é início do block)"
    assert right.spread_time == 31, f"spread esperado 31, got {right.spread_time}"

    # Crítico: as duas metades NÃO podem compartilhar window
    assert left.meta["duty_end_minutes"] != right.meta["duty_end_minutes"]
    assert left.meta["duty_start_minutes"] != right.meta["duty_start_minutes"]
