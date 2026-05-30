"""Validação ponta a ponta pela STACK REAL (FastAPI + Celery), carta real Salvador.

Para cada algoritmo: POST /optimize/ -> poll status -> coleta e valida:
  VSP: frota (vehicles), cobertura (unassigned), overlaps por bloco, custo.
  CSP: motoristas (crew), spread das jornadas, violações CCT (cct_violations).

Uso: python scratch/e2e_validate_real.py <routes> <time_budget> [algos_csv]
Requer INTERNAL_OPTIMIZER_KEY no ambiente e optimizer em 127.0.0.1:8000.
"""
import sys, os, json, time, math, urllib.request, urllib.error

BASE = os.environ.get("OPTIMIZER_URL", "http://127.0.0.1:8000")
KEY = os.environ.get("INTERNAL_OPTIMIZER_KEY", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
from tests.test_gtfs_real_salvador import build_real_salvador_trips


def http(method, path, payload=None, timeout=60):
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if "/optimize" in path:
        headers["X-Internal-Key"] = KEY
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() or "{}"
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}


def build_payload(routes):
    trips, stops, _ = build_real_salvador_trips(max_routes=routes)
    # deadhead Haversine real
    stop_ids = [s["stop_id"] for s in stops if s.get("stop_id")]
    coord = {}
    for idx, sid in enumerate(stop_ids):
        srow = next((s for s in stops if s.get("stop_id") == sid), None)
        if srow and srow.get("stop_lat") and srow.get("stop_lon"):
            try:
                coord[idx + 1] = (float(srow["stop_lat"]), float(srow["stop_lon"]))
            except ValueError:
                pass

    def hav(a, b):
        R = 6371.0; p1, p2 = math.radians(a[0]), math.radians(b[0])
        dphi = math.radians(b[0]-a[0]); dl = math.radians(b[1]-a[1])
        h = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*R*math.asin(math.sqrt(h))

    terms = sorted({t.origin_id for t in trips} | {t.destination_id for t in trips})
    dh = {a: {str(b): (int(round(hav(coord[a], coord[b])/25.0*60)) if a in coord and b in coord else 0)
              for b in terms} for a in terms}
    tdicts, tmap = [], {}
    for t in trips:
        tmap[t.id] = (t.start_time, t.end_time)
        tdicts.append({
            "id": t.id, "line_id": t.line_id, "start_time": t.start_time, "end_time": t.end_time,
            "origin_id": t.origin_id, "destination_id": t.destination_id, "duration": t.duration,
            "distance_km": getattr(t, "distance_km", 10.0) or 10.0,
            "deadhead_times": dh.get(t.destination_id, {}),
        })
    return tdicts, tmap


def overlaps_in_blocks(blocks, tmap):
    n = 0
    for b in blocks:
        ts = sorted((tmap[i] for i in b.get("trips", []) if i in tmap), key=lambda x: x[0])
        n += sum(1 for a, c in zip(ts, ts[1:]) if c[0] < a[1])
    return n


def run(algo, tdicts, tmap, budget):
    payload = {
        "algorithm": algo, "time_budget_s": budget, "trips": tdicts,
        "vehicle_types": [{"id": 1, "name": "BUS", "passenger_capacity": 60, "fixed_cost": 800,
                           "cost_per_km": 2.5, "cost_per_hour": 30}],
        "vsp_params": {"min_break_minutes": 30, "min_layover_minutes": 10, "deadhead_cost_per_minute": 1.0},
    }
    st, resp = http("POST", "/optimize/", payload, timeout=budget + 60)
    if st != 200:
        return {"algo": algo, "err": f"POST {st}: {str(resp)[:120]}"}
    # síncrono?
    if "vehicles" in resp:
        result = resp
    else:
        task_id = resp.get("task_id")
        if not task_id:
            return {"algo": algo, "err": f"sem task_id: {str(resp)[:120]}"}
        deadline = time.time() + budget + 120
        result = None
        while time.time() < deadline:
            time.sleep(3)
            st2, r2 = http("GET", f"/optimize/status/{task_id}", timeout=30)
            status = r2.get("status")
            if status in ("completed", "success", "SUCCESS"):
                result = r2.get("result", r2)
                break
            if status in ("failed", "FAILURE", "error"):
                return {"algo": algo, "err": f"task {status}: {str(r2)[:160]}"}
        if result is None:
            return {"algo": algo, "err": "timeout poll"}
    blocks = result.get("blocks", [])
    duties = result.get("duties", [])
    spreads = [d.get("spread_time", 0) for d in duties]
    return {
        "algo": algo,
        "vehicles": result.get("vehicles"),
        "crew": result.get("crew"),
        "total_trips": result.get("total_trips"),
        "unassigned": result.get("unassigned_trips"),
        "uncovered_blocks": result.get("uncovered_blocks"),
        "overlaps": overlaps_in_blocks(blocks, tmap),
        "cct_violations": result.get("cct_violations"),
        "max_spread": max(spreads) if spreads else 0,
        "cost": result.get("total_cost"),
    }


def main():
    routes = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    algos = (sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3].strip()
             else ["greedy", "mcnf", "assignment_vsp", "simulated_annealing", "tabu_search",
                   "genetic", "alns", "branch_and_price", "set_partitioning", "hybrid_pipeline",
                   "joint_solver", "vcsp_pulp", "joint_bp", "regional", "joint_timetable"])
    if not KEY:
        print("ERRO: INTERNAL_OPTIMIZER_KEY ausente no ambiente"); sys.exit(1)
    st, health = http("GET", "/health/", timeout=10)
    print(f"health: {st} {health.get('status') if isinstance(health, dict) else ''}")
    tdicts, tmap = build_payload(routes)
    print(f"carta real: {len(tdicts)} viagens, {routes} rotas, budget={budget}s\n")
    hdr = f"{'algo':<20}{'veic':>5}{'crew':>5}{'cobertura':>11}{'ovl':>5}{'cct':>5}{'spread_max':>11}{'custo':>13}"
    print(hdr); print("-" * len(hdr))
    for algo in algos:
        r = run(algo, tdicts, tmap, budget)
        if r.get("err"):
            print(f"{algo:<20} ERRO: {r['err']}")
            continue
        cov = f"{(r['total_trips'] or 0) - (r['unassigned'] or 0)}/{len(tdicts)}"
        print(f"{r['algo']:<20}{r['vehicles']!s:>5}{r['crew']!s:>5}{cov:>11}{r['overlaps']!s:>5}"
              f"{r['cct_violations']!s:>5}{r['max_spread']!s:>11}{(r['cost'] or 0):>13,.0f}")


if __name__ == "__main__":
    main()
