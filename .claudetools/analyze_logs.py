import os
import re
from typing import Dict

def analyze_solver_logs(log_path: str):
    """
    Skill: analyze-solver-logs
    Extracts key performance indicators from solver logs.
    """
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return

    # Padrões específicos do seu HybridPipeline
    patterns = {
        "mcnf_baseline": r"mcnf baseline: (\d+) veículos, cost=([\d.]+), issues=(\d+)",
        "sa_result": r"SA: (\d+) veículos, cost=([\d.]+), issues=(\d+), iters=(\d+)",
        "tabu_result": r"Tabu: (\d+) veículos, cost=([\d.]+), issues=(\d+), iters=(\d+)",
        "final_selection": r"Selecionado: (\w+) com (\d+) veículos"
    }

    results = {}

    with open(log_path, 'r') as f:
        content = f.read()
        for key, pattern in patterns.items():
            # Pegar a última ocorrência de cada fase
            matches = re.findall(pattern, content)
            if matches:
                results[key] = matches[-1]

    print("--- Diagnóstico Profundo do Pipeline OTIMIZ ---")
    if not results:
        print("⚠️ Nenhuma execução de otimização encontrada em 'optimizer/celery.log'.")
        print("Verifique se o worker está rodando e se houve requisições recentes.")
    else:
        for phase, data in results.items():
            if phase == "final_selection":
                 print(f"✅ FINAL: Algoritmo {data[0]} selecionado com {data[1]} veículos.")
            else:
                 print(f"📊 {phase.replace('_', ' ').upper()}: {data[0]} veículos | Custo: {data[1]} | Issues: {data[2]}")

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "solver.log"
    analyze_solver_logs(path)
