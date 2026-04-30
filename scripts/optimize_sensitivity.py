import json
import psycopg2
import random
from datetime import datetime
import sys
import os
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("SuperOptimizer")

# Adiciona o diretorio do optimizer ao path
sys.path.append(os.path.abspath("optimizer"))

from src.services.optimizer_service import OptimizerService
from src.domain.models import Trip, VehicleType, AlgorithmType
from src.api.schemas import OptimizationParametersDTO

def fetch_data(company_id):
    conn = psycopg2.connect("host=localhost port=5444 dbname=otimiz_db user=otimiz_admin password=otimiz_password")
    cur = conn.cursor()
    
    # Fetch trips (usando lineCode como line_id)
    cur.execute('SELECT id, "lineCode", "tripGroupId", direction, "startTime", "endTime", "originId", "destinationId", duration, "distanceKm" FROM trips WHERE "companyId" = %s', (company_id,))
    trips = []
    for row in cur.fetchall():
        try: line_val = int(row[1]) if row[1] else 0
        except: line_val = 0
            
        trips.append(Trip(
            id=row[0], line_id=line_val, trip_group_id=row[2], direction=row[3],
            start_time=row[4], end_time=row[5], origin_id=row[6], destination_id=row[7],
            duration=row[8], distance_km=float(row[9])
        ))
        
    # Fetch current parameters
    cur.execute("SELECT * FROM company_parameters WHERE \"companyId\" = %s", (company_id,))
    columns = [desc[0] for desc in cur.description]
    params_row = cur.fetchone()
    base_params = dict(zip(columns, params_row))
    base_params = {k: v for k, v in base_params.items() if not isinstance(v, (datetime,))}
    
    conn.close()
    return trips, base_params

def run_simulation(service, trips, v_types, base_params, overrides):
    merged = {**base_params, **overrides}
    
    # Limpeza e Tipagem
    dto_params = {}
    for k, v in merged.items():
        if v is not None:
            if any(x in k for x in ["minutes", "hour", "limit", "seed", "count", "vehicles"]):
                dto_params[k] = int(v)
            elif any(x in k for x in ["cost", "factor", "pct", "weight", "target", "tolerance", "km", "budget", "penalty"]):
                dto_params[k] = float(v)
            elif any(x in k for x in ["allow", "enforce", "strict", "apply", "enabled", "is_"]):
                dto_params[k] = bool(v)
            else:
                dto_params[k] = v
    
    try:
        result = service.run(
            trips=trips,
            vehicle_types=v_types,
            optimization_params=dto_params,
            algorithm=AlgorithmType.GREEDY
        )
        
        # Extrair metricas reais
        duties_count = len(result.csp.duties) if result.csp else 0
        vehicles_count = len(result.vsp.blocks) if result.vsp else 0
        roster_count = result.csp.meta.get("roster_count", 0) if result.csp else 0
        
        # Validacao de sobreposicao basica
        has_overlap = False
        if result.csp:
            for duty in result.csp.duties:
                all_duty_trips = []
                for segment in duty.segments:
                    all_duty_trips.extend(segment.trips)
                
                sorted_trips = sorted(all_duty_trips, key=lambda x: x.start_time)
                for i in range(len(sorted_trips) - 1):
                    if sorted_trips[i].end_time > sorted_trips[i+1].start_time:
                        has_overlap = True
                        break
        
        return {
            "cost": result.total_cost,
            "duties": duties_count,
            "vehicles": vehicles_count,
            "rosters": roster_count,
            "violations": result.csp.meta.get("cct_violations", 0) if result.csp else 0,
            "overlap": has_overlap,
            "config": overrides
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    company_id = 16
    N_ITERATIONS = 300
    
    print(f"\n⚡ INICIANDO SUPER OTIMIZADOR OTIMIZ ⚡")
    print(f"Empresa: {company_id} | Iterações: {N_ITERATIONS}")
    
    trips, base_params = fetch_data(company_id)
    v_types = [VehicleType(id=1, name="Standard", passenger_capacity=80, cost_per_km=1.0, fixed_cost=1000.0)]
    service = OptimizerService()
    
    results = []
    start_time = time.time()
    
    for i in range(N_ITERATIONS):
        # Gerar configuracao aleatoria inteligente focada em ECONOMIA DE FROTA
        overrides = {
            "cost_duty": random.uniform(400, 800),
            "cost_vehicle": random.uniform(5000, 15000), # Aumentado drasticamente (era 2000)
            "max_shift_minutes": random.choice([600, 660, 720, 780, 840]),
            "max_work_minutes": random.choice([480, 510, 540]),
            "min_break_minutes": random.choice([30, 45, 60]),
            "enforce_single_line_duty": random.choice([True, False]),
            "operator_single_vehicle_only": False, # DESATIVADO para permitir troca de carro
            "allow_vehicle_swap": True,            # ATIVADO para economia de frota
            "enforce_same_depot_start_end": True
        }
        
        res = run_simulation(service, trips, v_types, base_params, overrides)
        if res and not res["overlap"]:
            results.append(res)
            
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            print(f"  Progress: {i+1}/{N_ITERATIONS} | Tempo: {elapsed:.1f}s | Melhor Custo: R$ {min([r['cost'] for r in results]) if results else 0:,.2f}")

    if not results:
        print("❌ Nenhuma simulação válida encontrada.")
        return

    # Selecao do "Ponto de Ouro" (Foco em Frota)
    # Prioridade: 1. Zero Violacoes, 2. Menos Veiculos, 3. Menor Custo, 4. Menos Motoristas
    clean_results = [r for r in results if r["violations"] == 0]
    candidate_list = clean_results if clean_results else results
    
    # Ordenar por numero de veiculos primeiro, entao custo
    candidate_list.sort(key=lambda x: (x["vehicles"], x["cost"], x["duties"]))
    best = candidate_list[0]

    print("\n" + "═"*60)
    print(f"🏆 RESULTADO DA BUSCA EXAUSTIVA (TOP 1 de {len(results)})")
    print(f"💰 Custo Total: R$ {best['cost']:,.2f}")
    print(f"👤 Motoristas: {best['duties']} | 👥 Escala: {best['rosters']}")
    print(f"🚌 Veículos: {best['vehicles']}")
    print(f"⚠️ Violações CCT: {best['violations']}")
    print("═"*60)
    
    # Atualizar o banco de dados com a melhor config
    print(f"\nSalvando configuração otimizada no banco de dados...")
    conn = psycopg2.connect("host=localhost port=5444 dbname=otimiz_db user=otimiz_admin password=otimiz_password")
    cur = conn.cursor()
    
    set_clauses = []
    values = []
    for k, v in best['config'].items():
        set_clauses.append(f"\"{k}\" = %s")
        values.append(v)
    
    values.append(company_id)
    query = f"UPDATE company_parameters SET {', '.join(set_clauses)} WHERE \"companyId\" = %s"
    cur.execute(query, tuple(values))
    conn.commit()
    conn.close()
    print("✅ Banco de dados atualizado com os parâmetros de performance máxima!")

if __name__ == "__main__":
    main()
