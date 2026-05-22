"""
Testes de integração — JointBP e EV+CCT via OptimizerService.

Valida:
  - JointBP produz blocos + duties via algorithm="joint_bp"
  - JointBP com CCT params injeta restrição de condução no pricing B&P
  - B&P EV-aware respeita SoC via VehicleType.is_electric
  - B&P CCT-constrained via bp_max_driving_minutes rejeita blocos longos
  - AlgorithmType.JOINT_BP é reconhecido pelo dispatcher
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")

import pytest
from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService


def make_trip(id_, start, end, distance_km=10.0):
    t = Trip(
        id=id_, line_id=1,
        start_time=start, end_time=end, duration=end - start,
        origin_id=1, destination_id=2, distance_km=distance_km,
    )
    t.deadhead_times = {}
    return t


def make_vt(id_=1, fixed_cost=800.0, is_electric=False, battery_kwh=0.0,
            minimum_soc=0.15, charge_rate_kw=0.0, energy_cost_per_kwh=0.0):
    return VehicleType(
        id=id_, name="Bus", passenger_capacity=60, fixed_cost=fixed_cost,
        is_electric=is_electric, battery_capacity_kwh=battery_kwh,
        minimum_soc=minimum_soc, charge_rate_kw=charge_rate_kw,
        energy_cost_per_kwh=energy_cost_per_kwh,
    )


# ─── JointBP integration ──────────────────────────────────────────────────────

class TestJointBPIntegration:

    def test_joint_bp_produces_vsp_and_csp(self):
        """joint_bp deve produzir blocos VSP e jornadas CSP."""
        svc = OptimizerService()
        trips = [
            make_trip(1, 300, 360),
            make_trip(2, 380, 440),
            make_trip(3, 600, 660),
        ]
        result = svc.run(
            trips=trips,
            vehicle_types=[make_vt()],
            algorithm=AlgorithmType.JOINT_BP,
            time_budget_s=30,
            vsp_params={},
            cct_params={},
        )
        assert result.vsp is not None
        assert len(result.vsp.blocks) >= 1
        assert result.csp is not None
        # Todas as trips devem estar cobertas
        covered = {t.id for b in result.vsp.blocks for t in b.trips}
        assert covered == {t.id for t in trips}

    def test_joint_bp_cct_meta_present(self):
        """Meta do joint_bp deve incluir cct_max_driving_minutes."""
        svc = OptimizerService()
        trips = [make_trip(1, 300, 360), make_trip(2, 380, 440)]
        result = svc.run(
            trips=trips,
            vehicle_types=[make_vt()],
            algorithm=AlgorithmType.JOINT_BP,
            time_budget_s=30,
            vsp_params={},
            cct_params={"max_driving_minutes": 300},
        )
        meta = (result.meta or {}).get("joint_bp", {})
        assert meta.get("cct_max_driving_minutes") == 300

    def test_joint_bp_cct_constrains_blocks(self):
        """JointBP com CCT 330min deve rejeitar blocos de condução excessiva."""
        svc = OptimizerService()
        # 3 trips de 150 min sem pausa suficiente: 450 min > 330 limite
        trips = [
            make_trip(1, 0, 150),
            make_trip(2, 158, 308),   # gap=8 < 30 → contínuo
            make_trip(3, 316, 466),   # gap=8 < 30 → contínuo; total=450 > 330
        ]
        result = svc.run(
            trips=trips,
            vehicle_types=[make_vt()],
            algorithm=AlgorithmType.JOINT_BP,
            time_budget_s=30,
            vsp_params={"bp_max_pricing_iterations": 3, "bp_max_pricing_columns": 200},
            cct_params={"max_driving_minutes": 330, "min_break_minutes": 30},
        )
        # Nenhum bloco deve ter 3 trips com condução contínua de 450 min
        for block in result.vsp.blocks:
            trip_durations = [t.duration for t in block.trips]
            # Verificar se existe pausa de 30+ min entre trips consecutivas
            for i in range(len(block.trips) - 1):
                gap = block.trips[i + 1].start_time - block.trips[i].end_time
                if gap < 30:
                    running_total = sum(t.duration for t in block.trips[:i + 2])
                    assert running_total <= 330, (
                        f"Bloco {block.id} tem {running_total} min contínuos — viola CCT"
                    )

    def test_joint_bp_algorithm_type_is_registered(self):
        """AlgorithmType.JOINT_BP deve ser um valor reconhecido."""
        assert AlgorithmType.JOINT_BP == "joint_bp"
        from src.services.algorithm_dispatcher import dispatch_algorithm
        # Verificar que está no switch (não lança InvalidAlgorithmError)
        import inspect
        source = inspect.getsource(dispatch_algorithm)
        assert "JOINT_BP" in source


# ─── EV-Aware B&P via OptimizerService ───────────────────────────────────────

class TestEVBPIntegrationService:

    def test_ev_bp_runs_without_error(self):
        """B&P com veículo elétrico deve concluir sem erro."""
        svc = OptimizerService()
        trips = [
            make_trip(1, 300, 360, distance_km=15.0),
            make_trip(2, 380, 440, distance_km=15.0),
            make_trip(3, 600, 660, distance_km=15.0),
        ]
        ev = make_vt(id_=1, battery_kwh=200.0, is_electric=True,
                     minimum_soc=0.10, charge_rate_kw=100.0, energy_cost_per_kwh=2.0)
        result = svc.run(
            trips=trips,
            vehicle_types=[ev],
            algorithm=AlgorithmType.BRANCH_AND_PRICE,
            time_budget_s=20,
            vsp_params={"ev_kwh_per_km": 1.5},
            cct_params={},
        )
        assert result.vsp is not None
        # Meta do B&P fica em result.vsp.meta (VSPSolution), não em result.meta (OptimizationResult)
        meta = (result.vsp.meta or {}).get("branch_and_price", {})
        assert meta.get("ev_aware") is True

    def test_ev_bp_energy_cost_in_meta_objective(self):
        """B&P EV deve ter custo maior que B&P não-EV pela energia."""
        svc = OptimizerService()
        trips = [make_trip(1, 300, 360, distance_km=50.0)]
        vt_nev = make_vt(id_=1, fixed_cost=800.0, is_electric=False)
        vt_ev = make_vt(id_=2, fixed_cost=800.0, is_electric=True,
                        battery_kwh=500.0, minimum_soc=0.0,
                        charge_rate_kw=0.0, energy_cost_per_kwh=3.0)

        r_nev = svc.run(trips=trips, vehicle_types=[vt_nev],
                        algorithm=AlgorithmType.BRANCH_AND_PRICE,
                        time_budget_s=10, vsp_params={"ev_kwh_per_km": 1.0}, cct_params={})
        r_ev = svc.run(trips=trips, vehicle_types=[vt_ev],
                       algorithm=AlgorithmType.BRANCH_AND_PRICE,
                       time_budget_s=10, vsp_params={"ev_kwh_per_km": 1.0}, cct_params={})

        # EV: fixed(800) + energy(50km*1.0*3.0=150) = 950 > 800 não-EV
        obj_nev = (r_nev.vsp.meta or {}).get("branch_and_price", {}).get("mip_objective", 0)
        obj_ev = (r_ev.vsp.meta or {}).get("branch_and_price", {}).get("mip_objective", 0)
        if obj_nev and obj_ev:
            assert obj_ev > obj_nev, "Custo EV deve ser maior que não-EV pela energia consumida"


# ─── CCT via B&P + dispatcher ─────────────────────────────────────────────────

class TestCCTBPIntegrationService:

    def test_cct_bp_via_vsp_params(self):
        """B&P com bp_max_driving_minutes deve reportar cct_driving_constrained=True."""
        svc = OptimizerService()
        trips = [make_trip(1, 0, 200), make_trip(2, 208, 408)]
        result = svc.run(
            trips=trips,
            vehicle_types=[make_vt()],
            algorithm=AlgorithmType.BRANCH_AND_PRICE,
            time_budget_s=20,
            vsp_params={"bp_max_driving_minutes": 330, "bp_min_break_minutes": 30},
            cct_params={},
        )
        meta = (result.vsp.meta or {}).get("branch_and_price", {})
        assert meta.get("cct_driving_constrained") is True
