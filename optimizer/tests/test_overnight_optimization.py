"""
Teste E2E — Viagens de Madrugada (Overnight Shifts) — Linha Corujão

Prova que o sistema lida corretamente com viagens que cruzam a meia-noite
usando tempo linear (minutos absolutos, sem módulo 1440).

Execute com:
    cd optimizer
    pytest tests/test_overnight_optimization.py -v
    # ou diretamente:
    python tests/test_overnight_optimization.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.algorithms.hybrid.pipeline import HybridPipeline
from src.domain.models import Trip, VehicleType


# ── Fixtures ──────────────────────────────────────────────────────────────────

LINHA_CORUJAO_ID = 99

OVERNIGHT_TRIPS = [
    # T1: 22:00 → 23:00  (ida: terminal A → B)
    Trip(
        id=1, line_id=LINHA_CORUJAO_ID,
        start_time=1320, end_time=1380,
        origin_id=1, destination_id=2,
        duration=60, distance_km=15.0,
    ),
    # T2: 23:30 → 00:30+1  (volta: terminal B → A)  ← cruza meia-noite
    Trip(
        id=2, line_id=LINHA_CORUJAO_ID,
        start_time=1410, end_time=1470,
        origin_id=2, destination_id=1,
        duration=60, distance_km=15.0,
    ),
    # T3: 01:00+1 → 02:00+1  (ida: terminal A → B)
    Trip(
        id=3, line_id=LINHA_CORUJAO_ID,
        start_time=1500, end_time=1560,
        origin_id=1, destination_id=2,
        duration=60, distance_km=15.0,
    ),
]

VEHICLE_TYPES = [
    VehicleType(
        id=1, name="Ônibus Noturno",
        passenger_capacity=40,
        cost_per_km=2.0,
        cost_per_hour=50.0,
        fixed_cost=800.0,
    )
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(minutes: int) -> str:
    """Formata minutos absolutos em HH:MM (+N para dia seguinte)."""
    day = minutes // 1440
    m = minutes % 1440
    hh = m // 60
    mm = m % 60
    suffix = f" +{day}" if day else ""
    return f"{hh:02d}:{mm:02d}{suffix}"


def _run_pipeline() -> object:
    pipeline = HybridPipeline(
        time_budget_s=30.0,
        cct_params={
            "max_shift_minutes": 480,    # 8h de jornada máxima
            "max_work_minutes": 360,     # 6h de condução máxima
            "min_break_minutes": 20,
        },
        vsp_params={
            "min_layover_minutes": 5,    # tempo mínimo entre viagens no mesmo veículo
        },
    )
    return pipeline.solve(OVERNIGHT_TRIPS, VEHICLE_TYPES)


# ── Testes (pytest) ────────────────────────────────────────────────────────────

def test_solver_nao_falha_com_viagens_de_madrugada():
    """O solver não deve lançar exceção ao processar overnight."""
    result = _run_pipeline()
    assert result is not None, "Pipeline retornou None"


def test_todas_as_viagens_sao_cobertas():
    """As 3 viagens da Linha Corujão devem estar alocadas (sem unassigned)."""
    result = _run_pipeline()
    covered_ids = {t.id for b in result.vsp.blocks for t in b.trips}
    expected_ids = {t.id for t in OVERNIGHT_TRIPS}
    unassigned = expected_ids - covered_ids
    assert not unassigned, f"Viagens não alocadas: {unassigned}"


def test_viagens_consolidadas_em_um_unico_veiculo():
    """Com gaps de 30 min entre viagens consecutivas, um veículo é suficiente."""
    result = _run_pipeline()
    num_vehicles = result.vsp.num_vehicles
    assert num_vehicles == 1, (
        f"Esperado 1 veículo para a Linha Corujão, obteve {num_vehicles}. "
        "Gaps de 30 min deveriam permitir consolidação."
    )


def test_gap_entre_viagens_nao_e_negativo():
    """Verifica que nenhum gap entre viagens consecutivas do bloco é negativo."""
    result = _run_pipeline()
    for block in result.vsp.blocks:
        trips = sorted(block.trips, key=lambda t: t.start_time)
        for i in range(len(trips) - 1):
            gap = trips[i + 1].start_time - trips[i].end_time
            assert gap >= 0, (
                f"Gap negativo detectado entre T{trips[i].id} (end={trips[i].end_time}) "
                f"e T{trips[i+1].id} (start={trips[i+1].start_time}): gap={gap}"
            )


def test_custo_total_positivo():
    """O custo total deve ser um número positivo e finito."""
    result = _run_pipeline()
    cost = result.total_cost
    assert isinstance(cost, (int, float)), f"total_cost não é numérico: {type(cost)}"
    assert cost > 0, f"total_cost deve ser positivo, obteve {cost}"
    assert cost < 1_000_000, f"total_cost suspeito (BigM?): {cost}"


def test_sem_violacoes_de_tempo_negativo():
    """Nenhuma jornada deve ter spread_time negativo."""
    result = _run_pipeline()
    for duty in result.csp.duties:
        assert duty.spread_time >= 0, (
            f"spread_time negativo em duty {duty.id}: {duty.spread_time}"
        )


# ── Runner manual (python tests/test_overnight_optimization.py) ───────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  OTIMIZ — Teste E2E: Linha Corujão (Overnight Shifts)")
    print("=" * 60)

    print("\n📋 Carta Horária da Madrugada:")
    for t in OVERNIGHT_TRIPS:
        print(f"   Viagem {t.id}: {_fmt(t.start_time)} → {_fmt(t.end_time)}"
              f"  ({t.duration}min | {t.distance_km}km)")

    print("\n🔧 Executando HybridPipeline...")
    try:
        result = _run_pipeline()
    except Exception as exc:
        print(f"\n❌ FALHA: O solver lançou exceção: {exc}")
        sys.exit(1)

    print("\n✅ Solver concluído sem exceções.")
    print(f"\n📊 Resultado:")
    print(f"   Veículos utilizados : {result.vsp.num_vehicles}")
    print(f"   Jornadas (duties)   : {len(result.csp.duties)}")
    print(f"   Custo total         : R$ {result.total_cost:,.2f}")
    print(f"   Violações CCT       : {result.csp.cct_violations}")
    print(f"   Viagens não alocadas: {len(result.vsp.unassigned_trips)}")

    print(f"\n🚌 Blocos de Veículo:")
    for block in result.vsp.blocks:
        trips_sorted = sorted(block.trips, key=lambda t: t.start_time)
        print(f"   Bloco {block.id} — {len(trips_sorted)} viagens:")
        for i, t in enumerate(trips_sorted):
            gap_str = ""
            if i > 0:
                gap = t.start_time - trips_sorted[i - 1].end_time
                gap_str = f"  [gap: {gap}min]"
            print(f"     T{t.id}: {_fmt(t.start_time)} → {_fmt(t.end_time)}{gap_str}")

    print(f"\n👷 Jornadas de Motorista:")
    for duty in result.csp.duties:
        print(f"   Duty {duty.id}: spread={duty.spread_time}min | "
              f"work={duty.work_time}min | violations={duty.shift_violations}")

    # Assertivas finais do runner manual
    errors = []
    covered = {t.id for b in result.vsp.blocks for t in b.trips}
    missing = {t.id for t in OVERNIGHT_TRIPS} - covered
    if missing:
        errors.append(f"Viagens não alocadas: {missing}")
    if result.vsp.num_vehicles != 1:
        errors.append(f"Esperado 1 veículo, obteve {result.vsp.num_vehicles}")
    if result.total_cost <= 0:
        errors.append(f"Custo inválido: {result.total_cost}")
    for block in result.vsp.blocks:
        trips_sorted = sorted(block.trips, key=lambda t: t.start_time)
        for i in range(len(trips_sorted) - 1):
            gap = trips_sorted[i + 1].start_time - trips_sorted[i].end_time
            if gap < 0:
                errors.append(f"Gap negativo: {gap}min entre T{trips_sorted[i].id} e T{trips_sorted[i+1].id}")

    if errors:
        print("\n❌ ASSERTIVAS FALHARAM:")
        for e in errors:
            print(f"   • {e}")
        sys.exit(1)
    else:
        print("\n🎉 TODOS OS TESTES PASSARAM — Sistema overnight validado!")
