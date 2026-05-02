# OTIMIZ vs OPTIBUS - Análise Competitiva & Roadmap
**Data:** 2 de maio de 2026

---

## 📊 Onde Estamos Hoje

### Nível de Maturidade: **MVP/Beta Avançado (40-50%)**

```
Optibus (Referência)     ████████████████████ 100%
OTIMIZ (Hoje)            ████████░░░░░░░░░░░░  40-50%
```

---

## 🎯 Comparação Detalhada

### 1. OTIMIZAÇÃO DE VEÍCULOS (VSP)

| Aspecto | OTIMIZ | Optibus | Gap |
|---------|--------|---------|-----|
| **Greedy Básico** | ✅ Implementado | ✅ Sim | 0 |
| **MCNF (Network Flow)** | ✅ Implementado | ✅ Sim | 0 |
| **Algoritmo Genético** | ✅ Básico | ✅ Avançado | Gap médio |
| **Multi-depot** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Vehicle Types** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Real-time Updates** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Otimização Dinâmica** | ❌ Não | ✅ Sim | **CRÍTICO** |

### 2. OTIMIZAÇÃO DE OPERADORES (CSP)

| Aspecto | OTIMIZ | Optibus | Gap |
|---------|--------|---------|-----|
| **Alocação Básica** | ✅ Implementado | ✅ Sim | 0 |
| **Skill Matching** | ✅ Implementado | ✅ Avançado | Gap pequeno |
| **Preferências** | ❌ Não | ✅ Sim | Gap médio |
| **Rotações (Shifts)** | ✅ Básico | ✅ Avançado | Gap médio |
| **Folgas/Descanso** | ✅ Validação | ✅ Otimização | Gap médio |
| **Repouso Regulatório** | ✅ Sim | ✅ Avançado | Gap pequeno |

### 3. VALIDAÇÃO & COMPLIANCE

| Aspecto | OTIMIZ | Optibus | Gap |
|---------|--------|---------|-----|
| **Sobreposição Horária** | ✅ 8/8 regras | ✅ Sim | 0 |
| **Deadhead Mínimo** | ✅ Sim | ✅ Sim | 0 |
| **Jornada Máxima** | ✅ Sim | ✅ Sim | 0 |
| **Almoço Obrigatório** | ✅ Sim | ✅ Avançado | Gap pequeno |
| **Repouso Interrompido** | ✅ Sim | ✅ Avançado | Gap pequeno |
| **Certificações** | ✅ Auditável | ✅ Certificado | Gap médio |

### 4. INTERFACE & UX

| Aspecto | OTIMIZ | Optibus | Gap |
|---------|--------|---------|-----|
| **API REST** | ✅ Sim | ✅ Sim | 0 |
| **Web Dashboard** | ❌ Não | ✅ Avançado | **CRÍTICO** |
| **Visualização de Mapa** | ❌ Não | ✅ Avançado | **CRÍTICO** |
| **Edição Manual** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Relatórios Customizados** | ⚠️ Básico | ✅ Avançado | Gap grande |
| **Exportação** | ✅ JSON/CSV | ✅ Múltiplos | Gap pequeno |
| **Mobile** | ❌ Não | ✅ Sim | **CRÍTICO** |

### 5. PERFORMANCE & ESCALABILIDADE

| Aspecto | OTIMIZ | Optibus | Gap |
|---------|--------|---------|-----|
| **100 viagens** | < 100ms | < 100ms | 0 |
| **1000 viagens** | < 1s | < 1s | 0 |
| **5000 viagens** | < 10s | < 5s | Gap pequeno |
| **10000+ viagens** | ❌ Não testado | ✅ Sim | **CRÍTICO** |
| **Background Jobs** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Cache** | ❌ Não | ✅ Avançado | Gap médio |
| **Multi-threading** | ❌ Não | ✅ Sim | **CRÍTICO** |

### 6. ANALYTICS & INSIGHTS

| Aspecto | OTIMIZ | Optibus | Gap |
|---------|--------|---------|-----|
| **KPI Básicos** | ✅ Sim | ✅ Avançado | Gap pequeno |
| **Trending** | ❌ Não | ✅ Sim | Gap médio |
| **Comparação vs Manual** | ✅ Básico | ✅ Avançado | Gap médio |
| **Machine Learning** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Previsão** | ❌ Não | ✅ Sim | **CRÍTICO** |
| **Anomaly Detection** | ❌ Não | ✅ Sim | **CRÍTICO** |

---

## 🛣️ Roadmap: De MVP para Optibus Level

### 🔴 FASE 1: FEATURES CRÍTICAS (4-6 semanas)
**Objetivo:** Passar de MVP para "Produto Vendável"

#### 1.1 Multi-Depot Support (1-2 semanas)
```python
# Hoje: Uma garagem
blocks = [{block_id: 1, depot: 1, ...}]

# Necessário: Múltiplas garagens
blocks = [
  {block_id: 1, depot: 1, ...},
  {block_id: 2, depot: 2, ...},
  {block_id: 3, depot: 3, ...}
]
```

**Impacto:**
- ✅ Aumenta casos de uso em 300%
- ✅ Necessário para redes de transporte reais
- ✅ Aumenta ROI potencial

**Esforço:** 40-60 horas

**Como fazer:**
1. Adicionar `depot_id` a blocks e vehicles
2. Validar que viagens usam veículo do mesmo depot
3. Calcular deadhead entre depots
4. Testar com dados de múltiplos depots

#### 1.2 Vehicle Types (1 semana)
```python
# Mapear tipo de veículo a capacidades
VEHICLE_TYPES = {
    'BUS': {'capacity': 60, 'accessible': True, 'cost': 150/day},
    'MINI_BUS': {'capacity': 20, 'accessible': False, 'cost': 100/day},
    'COACH': {'capacity': 50, 'accessible': False, 'cost': 180/day}
}
```

**Impacto:**
- ✅ Aumenta realismo da otimização
- ✅ Reduz custos ao usar veículo certo para viagem

**Esforço:** 20-30 horas

#### 1.3 Web Dashboard Básico (2-3 semanas)
```
┌─────────────────────────────────────┐
│ OTIMIZ Dashboard                    │
├─────────────────────────────────────┤
│                                     │
│  Blocos:    [17]  Jornadas: [19]   │
│  Cobertura: 98%   Erro: 2 viagens  │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ Visualização de Blocos      │   │
│  │ (Cada linha = veículo)      │   │
│  │ ────────────────────────    │   │
│  │ V1: [T1:600-630][T2:640]   │   │
│  │ V2: [T3:700-750][T4:800]   │   │
│  └─────────────────────────────┘   │
│                                     │
│ [Editar] [Exportar] [Validar]      │
└─────────────────────────────────────┘
```

**Impacto:**
- ✅ Sem dashboard, produto não é vendável
- ✅ Usuários precisam visualizar soluções

**Esforço:** 60-80 horas (React component)

**Stack:** React + Next.js + Tailwind + Chart.js

#### 1.4 Edição Manual (1-2 semanas)
Permitir que usuários:
- Arraste trips entre veículos
- Reordene trips
- Deletar e re-alocar
- Visualize impacto em tempo real

**Esforço:** 40-60 horas

---

### 🟡 FASE 2: OTIMIZAÇÃO & PERFORMANCE (3-4 semanas)
**Objetivo:** De "rápido" para "muito rápido" (Optibus level)

#### 2.1 Paralelização (1 semana)
```python
# De serial para parallel
from multiprocessing import Pool

def optimize_block(block_data):
    return greedy_vsp(block_data)

with Pool(8) as p:
    results = p.map(optimize_block, blocks)
```

**Impacto:**
- ✅ 6-8x mais rápido
- ✅ Pode otimizar 10000+ viagens em < 5s

**Esforço:** 30-40 horas

#### 2.2 Caching & Memoization (1 semana)
```python
from functools import lru_cache
import redis

@lru_cache(maxsize=10000)
def get_distance(origin, dest):
    return distance_matrix[origin][dest]

# Cache de resultados já otimizados
redis_client.setex(
    f"optimization:{company_id}:{date}",
    86400,  # 24h
    json.dumps(result)
)
```

**Impacto:**
- ✅ Reduz tempo de re-otimização em 50-70%
- ✅ Essencial para ajustes iterativos

**Esforço:** 20-30 horas

#### 2.3 Algoritmo GA Avançado (2 semanas)
```python
# De GA básico para GA multi-objetivo
class AdvancedGA:
    objectives = [
        'minimize_vehicles',
        'minimize_cost',
        'maximize_coverage',
        'minimize_deadhead'
    ]
    
    # Usar Pareto Front
    pareto_solutions = nsga2(population, objectives)
```

**Impacto:**
- ✅ Qualidade de solução +20-40%
- ✅ Mais soluções alternativas para escolher

**Esforço:** 40-60 horas

---

### 🟠 FASE 3: INTELIGÊNCIA & INSIGHTS (4-6 semanas)
**Objetivo:** Ir além de otimização para inteligência

#### 3.1 Machine Learning - Previsão de Demanda (2 semanas)
```python
from sklearn.ensemble import RandomForestRegressor

# Prever quantas viagens haverá amanhã
model = RandomForestRegressor()
model.fit(X_historical, y_trips_count)

forecast = model.predict([[day_of_week, month, weather]])
print(f"Esperado: {forecast} viagens")
```

**Impacto:**
- ✅ Planejar recursos com antecedência
- ✅ Reduz custos de contingência

**Esforço:** 40-60 horas

#### 3.2 Anomaly Detection (1-2 semanas)
Detectar:
- Viagens com padrão anormal
- Operadores com performance anormal
- Veículos com consumo anormal
- Picos inesperados de demanda

**Impacto:**
- ✅ Alertar sobre problemas antes de acontecer
- ✅ Evitar crises operacionais

**Esforço:** 30-40 horas

#### 3.3 Real-time Optimization (2 semanas)
```python
# Ao invés de otimizar 1x ao dia:
# Otimizar continuamente conforme eventos chegam

class RealtimeOptimizer:
    def on_trip_added(self, trip):
        self.pending_trips.append(trip)
        if len(self.pending_trips) >= 10:
            self.reoptimize()
    
    def on_vehicle_delayed(self, vehicle_id, delay_minutes):
        self.reoptimize(affected_vehicle=vehicle_id)
```

**Impacto:**
- ✅ Adaptar a atrasos em tempo real
- ✅ Aumenta confiabilidade operacional

**Esforço:** 50-80 horas

---

### 🟢 FASE 4: VISÃO & EXPERIÊNCIA (3-4 semanas)
**Objetivo:** Experiência do usuário Optibus-like

#### 4.1 Mapa Interativo (2 semanas)
```javascript
// Usando Mapbox ou Google Maps
<Map
  blocks={blocks}
  onDragTrip={handleTripDrag}
  onVehicleClick={showVehicleDetails}
  colorBy="utilization"
/>
```

**Impacto:**
- ✅ Visualizar onde estão viagens
- ✅ Entender problemas espaciais

**Esforço:** 40-60 horas

#### 4.2 Relatórios Customizados (1-2 semanas)
Permitir usuários criar:
- Relatórios de utilização
- Relatórios de custos
- Relatórios de cobertura
- Relatórios de compliance

**Esforço:** 30-40 horas

#### 4.3 Mobile App (Opcional, 3-4 semanas)
App para operadores:
- Ver seu turno do dia
- Receber atualizações
- Reportar problemas

**Esforço:** 60-80 horas

---

## 📈 Timeline Proposto: De MVP para "Optibus Competitor"

```
Mai 2026:
  [####] Semana 1-2: Multi-depot, Vehicle Types, Dashboard Básico
  
Junho 2026:
  [####] Semana 3-4: Dashboard avançado, Edição Manual
  [####] Semana 5-6: Paralelização, Cache, GA Avançado
  
Julho 2026:
  [####] Semana 7-8: ML Previsão, Anomaly Detection
  [####] Semana 9-10: Real-time Optimization
  
Agosto 2026:
  [####] Semana 11-12: Mapa, Relatórios, Polish
```

**Total:** 12 semanas (~3 meses)

---

## 💰 Impacto de cada Feature

| Feature | Criticalidade | Impacto em ROI | Esforço | ROI/Esforço |
|---------|---------------|----------------|--------|------------|
| **Multi-depot** | 🔴 Crítica | +50% | Alto | ⭐⭐⭐⭐⭐ |
| **Vehicle Types** | 🔴 Crítica | +30% | Médio | ⭐⭐⭐⭐⭐ |
| **Dashboard** | 🔴 Crítica | +20% | Alto | ⭐⭐⭐⭐ |
| **Edição Manual** | 🟠 Alta | +15% | Alto | ⭐⭐⭐⭐ |
| **Paralelização** | 🟠 Alta | +10% | Médio | ⭐⭐⭐⭐⭐ |
| **GA Avançado** | 🟡 Média | +20% | Alto | ⭐⭐⭐⭐ |
| **ML/Previsão** | 🟡 Média | +25% | Alto | ⭐⭐⭐⭐ |
| **Real-time** | 🟡 Média | +15% | Muito Alto | ⭐⭐⭐ |
| **Mapa** | 🟢 Baixa | +10% | Alto | ⭐⭐⭐ |
| **Mobile** | 🟢 Baixa | +5% | Muito Alto | ⭐⭐ |

---

## 🎯 Seleção Estratégica: "MVP+1"

Se você tem apenas **4-6 semanas**, implemente SÓ:

```
SEMANA 1-2: Multi-depot + Vehicle Types
SEMANA 3-4: Dashboard Básico
SEMANA 5-6: Edição Manual + Paralelização

Resultado: Um produto 60-70% do Optibus
           Vendável em 80%+ dos casos
           ROI +40%
```

---

## 📊 Comparação Competitiva Esperada

### OTIMIZ Hoje (MVP)
```
Funcionalidade:  ████░░░░░░ 40%
Performance:     ████████░░ 80%
UX/Dashboard:    ██░░░░░░░░ 20%
Confiabilidade:  ███████░░░ 70%
Documentação:    ████████░░ 80%
─────────────────────────────────
TOTAL:           ███░░░░░░░ 45%
```

### OTIMIZ + Fase 1 (4-6 semanas)
```
Funcionalidade:  ██████░░░░ 60%
Performance:     █████████░ 90%
UX/Dashboard:    ██████░░░░ 60%
Confiabilidade:  ████████░░ 80%
Documentação:    █████████░ 90%
─────────────────────────────────
TOTAL:           ██████░░░░ 68%
```

### OTIMIZ + Fase 1-2 (10-12 semanas)
```
Funcionalidade:  █████████░ 90%
Performance:     ██████████ 95%
UX/Dashboard:    ████████░░ 80%
Confiabilidade:  █████████░ 90%
Documentação:    █████████░ 95%
─────────────────────────────────
TOTAL:           █████████░ 90%
```

### Optibus (Referência)
```
Funcionalidade:  ██████████ 100%
Performance:     ██████████ 100%
UX/Dashboard:    ██████████ 100%
Confiabilidade:  ██████████ 100%
Documentação:    ██████████ 100%
─────────────────────────────────
TOTAL:           ██████████ 100%
```

---

## 🚀 Próximas Ações Imediatas

### Hoje (maio 2):
- [ ] Revisar este documento com time
- [ ] Escolher entre "MVP" vs "MVP+1" (Fase 1)
- [ ] Alocar recursos

### Semana 1:
- [ ] Começar Multi-depot (critério de sucesso é rígido)
- [ ] Começar Vehicle Types em paralelo
- [ ] Começar wireframes do Dashboard

### Semana 2-3:
- [ ] Terminar Multi-depot + testes reais
- [ ] Terminar Vehicle Types + testes
- [ ] Implementar Dashboard básico

### Semana 4:
- [ ] Integração: Dashboard + dados reais
- [ ] QA/testes com Company 16
- [ ] Se viável: começar Edição Manual

---

## 💡 Decisão Crítica

### Você tem 3 opções:

**Opção A: Vender MVP Hoje (40-50%)**
- ✅ Tempo: Agora mesmo
- ✅ Risco: Baixo
- ✅ Receita: Imediata
- ❌ Competitividade: 40%
- ❌ Retenção: Baixa (faltam features)

**Opção B: 6 semanas p/ "MVP+1" (65-70%)**
- ✅ Competitivo o suficiente
- ✅ Vendável para 80% dos casos
- ✅ Multi-depot = +50% potencial de mercado
- ✅ Tempo razoável
- ⏱️ Tempo: 6 semanas
- 💰 ROI: +40% vs hoje

**Opção C: 12 semanas p/ "Enterprise" (90%+)**
- ✅ Quase Optibus level
- ✅ Altamente competitivo
- ✅ Pode competir diretamente
- ❌ Tempo: 3 meses
- ❌ Risco: Maior (mais features = mais bugs)

---

## 📌 Recomendação Final

**Escolha: Opção B + Opção A**

1. **Imediato (semana que vem):**
   - Venda o MVP atual para pequenos clientes (50-200 viagens)
   - Gere receita e feedback
   - Comece pipeline de vendas

2. **Paralelo (próximas 6 semanas):**
   - Implemente Fase 1 (Multi-depot + Vehicle Types + Dashboard)
   - Teste com dados reais de 2-3 clientes
   - Refine baseado em feedback

3. **Resultado (em 6 semanas):**
   - Upgrade clientes existentes para versão "MVP+1"
   - Venda para clientes maiores
   - Receita + Features = Vencer Optibus

---

**Status Atual:** MVP 40-50% ✅  
**Próximo Target:** MVP+1 65-70% (6 semanas)  
**Ultimate Target:** Enterprise 90% (12 semanas)  

Qual opção você escolhe? 🚀
