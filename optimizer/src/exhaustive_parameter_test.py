import logging
from typing import List, Dict, Any, Tuple
import traceback

# Configurar imports para rodar como módulo de src
from .domain.models import Trip, VehicleType, AlgorithmType
from .services.optimizer_service import OptimizerService
from .api.schemas import OptimizationParametersDTO

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ExhaustiveTester")


def create_mock_data() -> Tuple[List[Trip], List[VehicleType]]:
    trips = []
    # Viagem 1 e 2: Grupo de Viagens (Ida e Volta) - Noturnas
    t1 = Trip(
        id=1,
        line_id=101,
        start_time=1380,
        end_time=1480,
        origin_id=1,
        destination_id=2,
        distance_km=25.0,
        trip_group_id=1001,
    )
    t2 = Trip(
        id=2,
        line_id=101,
        start_time=1500,
        end_time=1600,
        origin_id=2,
        destination_id=1,
        distance_km=25.0,
        trip_group_id=1001,
    )

    # Viagem 3 e 4: Diurnas
    t3 = Trip(id=3, line_id=101, start_time=480, end_time=580, origin_id=1, destination_id=2, distance_km=25.0)
    t4 = Trip(id=4, line_id=101, start_time=600, end_time=700, origin_id=2, destination_id=1, distance_km=25.0)

    trips = [t1, t2, t3, t4]
    for t in trips:
        t.deadhead_times = {1: 10, 2: 10}
        if t.id == 3:
            t.is_holiday = True

    vt = [VehicleType(id=1, name="Standard", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    return trips, vt


def run_test(
    service: OptimizerService, name: str, trips: List[Trip], v_types: List[VehicleType], params: Dict[str, Any]
) -> Dict[str, Any]:
    logger.info(f"--- Testing Parameter: {name} ---")

    full_params = {
        "driver_cost_per_minute": 0.5,
        "collector_cost_per_minute": 0.4,
        "vehicle_fixed_cost": 800.0,
        "cost_vehicle": 1000.0,
        "cost_km": 1.0,
        "cost_duty": 500.0,
        "waiting_time_pay_pct": 0.3,
        "idle_time_is_paid": True,
        "nocturnal_start_hour": 22,
        "nocturnal_end_hour": 5,
        "nocturnal_factor": 1.0,
        "nocturnal_extra_pct": 0.2,
        "holiday_extra_pct": 1.0,
        "max_shift_minutes": 1000,
        "max_work_minutes": 800,
        "max_driving_minutes": 500,
        "overtime_limit_minutes": 120,
        "min_break_minutes": 15,
        "mandatory_break_after_minutes": 500,
        "meal_break_minutes": 0,
        "min_layover_minutes": 8,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
        "apply_cct": True,
        "strict_hard_validation": True,
        "dynamic_rules": [],
    }
    full_params.update(params)

    try:
        dto = OptimizationParametersDTO(**full_params)
        result = service.run(
            trips=trips,
            vehicle_types=v_types,
            algorithm=AlgorithmType.GREEDY,
            optimization_params=dto,
            cct_params={},
            vsp_params={},
        )

        if not result:
            return {"error": "Solver returned None result"}

        cost_bd = result.meta.get("cost_breakdown", {})
        csp_bd = cost_bd.get("csp", {})

        return {
            "total_cost": float(result.total_cost or 0),
            "nocturnal_extra": float(csp_bd.get("nocturnal_extra") or 0),
            "holiday_extra": float(csp_bd.get("holiday_extra") or 0),
            "work_cost": float(csp_bd.get("work_cost") or 0),
            "duties": len(result.csp.duties),
            "spread": sum(d.spread_time for d in result.csp.duties),
            "error": None,
        }
    except Exception as e:
        logger.warning(f"Exception in run_test({name}): {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}


def verify_all():
    service = OptimizerService()
    trips, v_types = create_mock_data()

    baseline_params = {
        "nocturnal_extra_pct": 0.20,
        "holiday_extra_pct": 1.0,
        "pullout_minutes": 10,
        "nocturnal_start_hour": 22,
    }

    baseline = run_test(service, "Baseline", trips, v_types, baseline_params)
    if baseline.get("error"):
        logger.error(f"Baseline failed completely: {baseline['error']}")
        return

    test_cases = [
        (
            "dynamic_rules",
            [
                {
                    "condition": {"field": "is_holiday", "op": "==", "value": True},
                    "action": {"target": "work_cost", "type": "multiply", "value": 5.0},
                }
            ],
            "Dynamic Rule: Holiday multiplier",
        ),
        ("nocturnal_start_hour", 18, "Expanding night window"),
        ("pullout_minutes", 60, "Increasing pull-out time"),
        ("holiday_extra_pct", 5.0, "Increasing holiday_extra_pct"),
        ("nocturnal_extra_pct", 1.0, "Increasing nocturnal_extra_pct"),
    ]

    results = []
    for param, value, rationale in test_cases:
        test_params = baseline_params.copy()
        test_params[param] = value
        res = run_test(service, param, trips, v_types, test_params)

        if res.get("error"):
            status = f"ERROR: {res['error']}"
        else:
            diff = False
            if param == "dynamic_rules" and res["work_cost"] > baseline["work_cost"]:
                diff = True
            elif param == "nocturnal_start_hour" and res["nocturnal_extra"] > baseline["nocturnal_extra"]:
                diff = True
            elif param == "pullout_minutes" and res["spread"] > baseline["spread"]:
                diff = True
            elif param == "holiday_extra_pct" and res["holiday_extra"] > baseline["holiday_extra"]:
                diff = True
            elif param == "nocturnal_extra_pct" and res["nocturnal_extra"] > baseline["nocturnal_extra"]:
                diff = True

            status = "SUCCESS" if diff else "FAILURE (No Effect)"

        logger.info(f"RESULT: {param} -> {status}")
        results.append((param, status, rationale))

    print("\n" + "=" * 80)
    print(f"{'PARAMETER':<30} | {'STATUS':<20} | {'RATIONALE'}")
    print("-" * 80)
    for p, s, r in results:
        print(f"{p:<30} | {s:<20} | {r}")
    print("=" * 80)


if __name__ == "__main__":
    verify_all()
