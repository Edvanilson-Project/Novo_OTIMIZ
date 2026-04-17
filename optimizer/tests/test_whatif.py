"""
Testes de integração para o endpoint POST /api/v1/evaluate-delta (What-If).

Cenários cobertos:
1. Mover viagem isolada → custo não-zero, bloco destino cresce.
2. Mover Ida de um par Ida+Volta (trip_group_id) → Volta deve ser arrastada junto.
3. Mover Ida de um par sequencial (sem trip_group_id, mesma linha, terminais espelhados).
4. Frontend pré-aplicou o move (computedBlocks) → Python avalia sem mover de novo.
5. Source block não encontrado → HTTP 404.
"""
from __future__ import annotations

import sys
import os

# Garante que o módulo 'src' seja encontrado ao rodar pytest do diretório optimizer/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from main import app  # type: ignore[import]

client = TestClient(app, raise_server_exceptions=True, headers={"X-Internal-Key": "internal-key-123456"})


def _trip_ids_in(block: dict) -> set:
    """Extrai IDs das trips de um bloco da resposta (trips são objetos, não inteiros)."""
    return {t.get("id") for t in block.get("trips", []) if isinstance(t, dict)}

# ── Helpers de fixture ────────────────────────────────────────────────────────

def _trip(
    id: int,
    line_id: int = 1,
    start_time: int = 480,
    end_time: int = 540,
    origin_id: int = 1,
    destination_id: int = 2,
    direction: str | None = None,
    trip_group_id: int | None = None,
    distance_km: float = 10.0,
    duration: int | None = None,
) -> dict:
    """Cria um dicionário de viagem com os campos mínimos que o endpoint aceita."""
    dur = duration if duration is not None else (end_time - start_time)
    return {
        "id": id,
        "line_id": line_id,
        "start_time": start_time,
        "end_time": end_time,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "direction": direction,
        "trip_group_id": trip_group_id,
        "distance_km": distance_km,
        "duration": dur,
        "deadhead_times": {},
        "idle_before_minutes": 0,
        "idle_after_minutes": 0,
    }


def _block(id: int, trips: list[dict], vehicle_type_id: int | None = None) -> dict:
    return {"id": id, "trips": trips, "vehicle_type_id": vehicle_type_id}


# ── Teste 1: Viagem isolada ───────────────────────────────────────────────────

def test_move_isolated_trip_returns_nonzero_cost():
    """
    Mover uma viagem isolada de um bloco para outro.
    O custo total deve ser > 0 (ativação de veículo + tempo).
    """
    isolada = _trip(id=1, start_time=480, end_time=540, distance_km=15.0)
    payload = {
        "blocks": [
            _block(id=10, trips=[isolada]),
            _block(id=20, trips=[]),
        ],
        "trip_ids": [1],
        "source_block_id": 10,
        "target_block_id": 20,
        "target_index": 0,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["cost_breakdown"]["total"] > 0, (
        "Custo deve ser maior que zero (pelo menos custo fixo de ativação)"
    )
    # bloco 20 agora deve ter a trip
    target = next((b for b in data["blocks"] if b["block_id"] == 20), None)
    assert target is not None, "Bloco 20 (destino) deve estar na resposta"
    assert 1 in _trip_ids_in(target), "Trip 1 deve estar no bloco 20"


# ── Teste 2: Par Ida+Volta com trip_group_id ──────────────────────────────────

def test_move_ida_with_trip_group_id_drags_volta_junto():
    """
    CENÁRIO CRÍTICO DE NEGÓCIO:
    Bloco 10: [Isolada(id=1)], Bloco 20: [Ida(id=2, group=42), Volta(id=3, group=42)]
    Mover Ida (id=2) de 20 para 10.
    Esperado: Bloco 10 com 3 viagens (Isolada + Ida + Volta).
    Esperado: cost_breakdown.total > 0.
    """
    isolada = _trip(id=1, start_time=360, end_time=420)
    ida     = _trip(id=2, start_time=480, end_time=540, direction="outbound", trip_group_id=42)
    volta   = _trip(id=3, start_time=545, end_time=605, direction="inbound",  trip_group_id=42)

    payload = {
        "blocks": [
            _block(id=10, trips=[isolada]),
            _block(id=20, trips=[ida, volta]),
        ],
        "trip_ids": [2],           # ← só pedimos para mover a Ida
        "source_block_id": 20,
        "target_block_id": 10,
        "target_index": 1,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "ok"

    target = next((b for b in data["blocks"] if b["block_id"] == 10), None)
    assert target is not None, "Bloco 10 (destino) deve estar na resposta"
    assert target["num_trips"] == 3, (
        f"Bloco destino deve ter 3 viagens (Isolada+Ida+Volta), tem {target['num_trips']}"
    )
    assert 2 in _trip_ids_in(target), "Trip Ida (id=2) deve estar no bloco 10"
    assert 3 in _trip_ids_in(target), "Trip Volta (id=3) deve estar no bloco 10 — par deve ser arrastado"

    assert data["cost_breakdown"]["total"] > 0, "Custo deve ser maior que zero"


# ── Teste 3: Par sequencial (sem trip_group_id) ───────────────────────────────

def test_move_ida_sequential_cycle_drags_volta():
    """
    Par Ida+Volta detectado por ciclo sequencial:
    mesma linha, direction outbound→inbound,
    destination_id(Ida) == origin_id(Volta), gap < 45 min.
    Sem trip_group_id.
    """
    isolada = _trip(id=1, start_time=300, end_time=360)
    ida = _trip(
        id=4, line_id=9, start_time=480, end_time=540,
        origin_id=10, destination_id=20, direction="outbound",
        trip_group_id=None,
    )
    volta = _trip(
        id=5, line_id=9, start_time=545, end_time=605,
        origin_id=20, destination_id=10, direction="inbound",
        trip_group_id=None,
    )
    payload = {
        "blocks": [
            _block(id=10, trips=[isolada]),
            _block(id=20, trips=[ida, volta]),
        ],
        "trip_ids": [4],
        "source_block_id": 20,
        "target_block_id": 10,
        "target_index": 1,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    target = next((b for b in data["blocks"] if b["block_id"] == 10), None)
    assert target is not None
    assert target["num_trips"] == 3, (
        f"Ciclo sequencial: bloco destino deve ter 3 viagens, tem {target['num_trips']}"
    )
    assert 4 in _trip_ids_in(target), "Ida (id=4) deve estar no destino"
    assert 5 in _trip_ids_in(target), "Volta (id=5) deve ser arrastada junto (ciclo sequencial)"


# ── Teste 4: Frontend pré-aplicou o move (computedBlocks) ────────────────────

def test_frontend_preapplied_move_evaluates_as_is():
    """
    O frontend enviou computedBlocks: trips já estão no bloco destino.
    Python detecta source_has_trips=False e apenas avalia (não move de novo).
    Resultado: bloco destino tem 2 trips, custo > 0.
    """
    trip_a = _trip(id=10, start_time=480, end_time=540)
    trip_b = _trip(id=11, start_time=600, end_time=660)

    # Estado pós-move: trip_a já está no bloco 20
    payload = {
        "blocks": [
            _block(id=10, trips=[]),       # source vazio (frontend já moveu)
            _block(id=20, trips=[trip_a, trip_b]),  # destino com ambas
        ],
        "trip_ids": [10],
        "source_block_id": 10,
        "target_block_id": 20,
        "target_index": 0,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    # Bloco de origem vazio é filtrado, logo não importa o status 200 vs 404 para
    # o source_block — o que importa é que o destino é avaliado.
    # Note: source_block vazio ainda aparece no payload, Python o encontra (sem trips).
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cost_breakdown"]["total"] > 0

    target = next((b for b in data["blocks"] if b["block_id"] == 20), None)
    assert target is not None
    assert target["num_trips"] == 2


# ── Teste 5: Source block não existe → HTTP 404 ───────────────────────────────

def test_missing_source_block_and_trips_nowhere_returns_404():
    """
    Se source_block_id não existir E as trip_ids pedidas também não existem
    em nenhum bloco do payload, retorna 404 (requisição genuinamente inválida).
    """
    trip = _trip(id=99, start_time=480, end_time=540)
    payload = {
        "blocks": [_block(id=10, trips=[trip])],
        "trip_ids": [7777],             # ← ID que não existe em bloco algum
        "source_block_id": 999,         # ← bloco inexistente
        "target_block_id": 10,
        "target_index": 0,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    assert resp.status_code == 404, f"Esperado 404, recebido {resp.status_code}: {resp.text}"


def test_stale_source_with_trips_already_in_target_succeeds():
    """
    STALE STATE GRACIOSO: usuário re-arrasta uma trip já movida. O frontend
    envia sourceBlockId desatualizado, mas as trips já estão no target.
    Python deve avaliar o estado atual sem quebrar.
    """
    trip = _trip(id=42, start_time=480, end_time=540, distance_km=12.0)
    payload = {
        "blocks": [_block(id=10, trips=[trip])],  # trip já está em block 10
        "trip_ids": [42],
        "source_block_id": 999,   # ← stale: bloco de onde a trip VEIO (já não existe/vazio)
        "target_block_id": 10,
        "target_index": 0,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cost_breakdown"]["total"] > 0
    target = next((b for b in data["blocks"] if b["block_id"] == 10), None)
    assert target is not None
    assert 42 in _trip_ids_in(target)


# ── Teste 6: Source block vazio no payload (único trip movido) ────────────────

def test_source_block_empty_after_move_succeeds():
    """
    Reproduz o bug real: única trip do bloco source é movida para target.
    O frontend agora envia source_block vazio (não omite o bloco do payload).
    Python deve detectar pre-applied (source vazio) e avaliar normalmente.
    Resultado esperado: HTTP 200, bloco destino com 1 trip, custo > 0.
    """
    trip = _trip(id=77, start_time=900, end_time=973, distance_km=15.0)
    payload = {
        "blocks": [
            _block(id=1, trips=[]),        # source vazio — frontend já moveu e manteve no payload
            _block(id=2, trips=[trip]),    # destino já com a trip
        ],
        "trip_ids": [77],
        "source_block_id": 1,
        "target_block_id": 2,
        "target_index": 0,
    }
    resp = client.post("/api/v1/evaluate-delta", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["cost_breakdown"]["total"] > 0

    target = next((b for b in data["blocks"] if b["block_id"] == 2), None)
    assert target is not None, "Bloco 2 (destino) deve estar na resposta"
    assert 77 in _trip_ids_in(target), "Trip 77 deve estar no bloco destino"
