# 🚀 FASE 1-3: Implementation Roadmap
**Branch:** `feature/fase-1-2-3-product-enhancement`  
**Status:** 🎯 Starting now  
**Target:** 70-90% Optibus competitive (3-5 months)

---

## 📅 Timeline Overview

```
MAY 2026 (Weeks 1-4):
  FASE 1: Multi-depot + Vehicle Types + Dashboard
  ├─ Week 1-2: Backend Foundation
  ├─ Week 3-4: Frontend Dashboard
  └─ Deliverable: MVP+1 (70% Optibus)

JUNE 2026 (Weeks 5-8):
  FASE 2: Performance & Advanced Algorithms
  ├─ Week 5-6: Parallelization & Caching
  ├─ Week 7-8: Advanced GA
  └─ Deliverable: 75-80% Optibus

JULY 2026 (Weeks 9-13):
  FASE 3: Intelligence & Real-time
  ├─ Week 9-10: ML & Forecasting
  ├─ Week 11-12: Real-time Optimization
  ├─ Week 13: Polish & Documentation
  └─ Deliverable: 85-90% Optibus

TOTAL: 13 weeks (3+ months)
```

---

## FASE 1: MVP+1 Edition (Weeks 1-4)

### Week 1-2: Backend Foundation

#### Task 1.1: Multi-Depot Database Schema
```python
# File: backend/src/modules/database/entities/depot.entity.ts

@Entity('depots')
export class Depot {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  name: string;

  @Column('geometry', { spatialFeatureType: 'Point' })
  location: Point;

  @Column()
  city: string;

  @Column({ nullable: true })
  address: string;

  @OneToMany(() => Vehicle, vehicle => vehicle.depot)
  vehicles: Vehicle[];
}
```

**Subtasks:**
- [ ] Create Depot entity
- [ ] Create depot_id in Vehicle entity
- [ ] Create depot_id in Block entity
- [ ] Add migration file
- [ ] Update database schema
- [ ] Seed test data (3 depots for Company 16)

**Estimated:** 8 hours  
**Status:** 🔲 Not started

---

#### Task 1.2: Multi-Depot Python Backend
```python
# File: optimizer/src/algorithms/vsp/multi_depot_scheduler.py

class MultiDepotScheduler:
    def __init__(self, depots: List[Depot], vehicles: List[Vehicle]):
        self.depots = depots
        self.vehicles = {v.id: v for v in vehicles}
        self.distance_matrix = self._load_distance_matrix()
    
    def validate_block(self, block: Block) -> bool:
        """Validate vehicle stays in its depot"""
        vehicle = self.vehicles[block.vehicle_id]
        return block.depot_id == vehicle.depot_id
    
    def calculate_deadhead_to_depot(self, origin: Terminal) -> int:
        """Calculate time to return vehicle to its depot"""
        vehicle = self.vehicles[self.current_vehicle_id]
        depot = self.depots[vehicle.depot_id]
        return self.distance_matrix[(origin.id, depot.location)]
```

**Subtasks:**
- [ ] Load depot locations
- [ ] Modify solver to respect depot constraints
- [ ] Calculate real deadhead between depots
- [ ] Validate vehicle returns to depot
- [ ] Add tests (5+ test cases)

**Estimated:** 20 hours  
**Status:** 🔲 Not started

---

#### Task 1.3: Vehicle Types
```python
# File: backend/src/modules/database/entities/vehicle-type.entity.ts

@Entity('vehicle_types')
export class VehicleType {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  name: string;  // 'BUS', 'MINIBUS', 'COACH'

  @Column()
  capacity: number;

  @Column()
  costPerDay: number;

  @Column()
  accessible: boolean;

  @OneToMany(() => Vehicle, vehicle => vehicle.type)
  vehicles: Vehicle[];
}
```

**Subtasks:**
- [ ] Create VehicleType entity
- [ ] Add type_id to Vehicle
- [ ] Update cost calculation for vehicle types
- [ ] Add capacity validation
- [ ] Seed vehicle types
- [ ] Add tests (5+ test cases)

**Estimated:** 16 hours  
**Status:** 🔲 Not started

---

### Week 3-4: Frontend Dashboard

#### Task 2.1: Next.js Dashboard Setup
```bash
# New project structure
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── dashboard/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── blocks/page.tsx
│   │   ├── analytics/page.tsx
│   │   └── settings/page.tsx
│   └── components/
│       ├── Header.tsx
│       ├── Sidebar.tsx
│       ├── BlockVisualization.tsx
│       └── KPICard.tsx
├── lib/api.ts
└── styles/globals.css
```

**Subtasks:**
- [ ] Create Next.js project with TypeScript
- [ ] Setup Tailwind CSS
- [ ] Setup Chart.js / Recharts
- [ ] Create auth context
- [ ] Setup API client
- [ ] Create routing structure

**Estimated:** 8 hours  
**Status:** 🔲 Not started

---

#### Task 2.2: Core Dashboard Components
```tsx
// File: frontend/app/dashboard/page.tsx

export default function Dashboard() {
  return (
    <div className="grid grid-cols-4 gap-4">
      <KPICard title="Vehicles" value={17} change={-2} />
      <KPICard title="Coverage" value="98%" change={+3} />
      <KPICard title="Cost/Day" value="R$8,872" change={-5} />
      <KPICard title="Errors" value={2} change={-5} status="warning" />
      
      <BlockVisualization blocks={blocks} />
      <UtilizationChart blocks={blocks} />
    </div>
  )
}
```

**Subtasks:**
- [ ] KPI Cards component
- [ ] Block visualization (table view)
- [ ] Utilization charts
- [ ] Cost breakdown chart
- [ ] Error summary display
- [ ] Responsive design

**Estimated:** 20 hours  
**Status:** 🔲 Not started

---

#### Task 2.3: Backend Integration
```ts
// File: frontend/lib/api.ts

export const api = {
  optimization: {
    run: (data) => POST('/api/v1/optimization/run', data),
    getResult: (id) => GET(`/api/v1/optimization/${id}`),
  },
  validation: {
    validate: (data) => POST('/api/v1/audits/validate', data),
  },
  upload: {
    csv: (file) => POST_FORM('/api/v1/upload/csv', file),
  }
}
```

**Subtasks:**
- [ ] API client setup
- [ ] Upload CSV handler
- [ ] Real-time result display
- [ ] Error handling
- [ ] Loading states
- [ ] Tests

**Estimated:** 12 hours  
**Status:** 🔲 Not started

---

#### Task 2.4: Drag & Drop Editing
```tsx
// File: frontend/app/components/DraggableBlock.tsx

import { useDrag, useDrop } from 'react-dnd'

export function DraggableTrip({ trip, onDrop }) {
  const [, drag] = useDrag(() => ({
    type: 'TRIP',
    item: trip,
  }))
  
  return (
    <div ref={drag} className="p-2 bg-blue-100">
      {trip.id}: {trip.start_time} - {trip.end_time}
    </div>
  )
}

export function DroppableVehicle({ vehicle, onDrop }) {
  const [, drop] = useDrop(() => ({
    accept: 'TRIP',
    drop: (trip) => onDrop(vehicle, trip),
  }))
  
  return (
    <div ref={drop} className="border-2 border-dashed p-4">
      Vehicle {vehicle.id}
      {/* trips rendered here */}
    </div>
  )
}
```

**Subtasks:**
- [ ] Install react-dnd
- [ ] Draggable trip component
- [ ] Droppable vehicle container
- [ ] Update on drag handler
- [ ] Validation on drop
- [ ] Real-time cost update
- [ ] Tests

**Estimated:** 16 hours  
**Status:** 🔲 Not started

---

## FASE 2: Performance & Algorithms (Weeks 5-8)

### Week 5-6: Parallelization & Caching

#### Task 3.1: Python Multiprocessing
```python
# File: optimizer/src/algorithms/parallel_optimizer.py

from multiprocessing import Pool, cpu_count

class ParallelOptimizer:
    def optimize_blocks(self, blocks: List[Block]) -> List[Block]:
        """Optimize blocks in parallel"""
        with Pool(cpu_count() - 1) as pool:
            results = pool.map(self._optimize_single_block, blocks)
        return results
    
    def _optimize_single_block(self, block: Block) -> Block:
        """Single block optimization (can run in parallel)"""
        greedy = GreedyVSP()
        return greedy.optimize(block)
```

**Impact:** 6-8x faster for 5000+ trips  
**Estimated:** 20 hours  
**Status:** 🔲 Not started

---

#### Task 3.2: Redis Caching
```python
# File: optimizer/src/services/cache_service.py

import redis
import json

class CacheService:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379)
    
    def get_cached_result(self, company_id: int, date: str) -> Optional[dict]:
        key = f"optimization:{company_id}:{date}"
        cached = self.redis.get(key)
        return json.loads(cached) if cached else None
    
    def cache_result(self, company_id: int, date: str, result: dict):
        key = f"optimization:{company_id}:{date}"
        self.redis.setex(key, 86400, json.dumps(result))  # 24h TTL
```

**Impact:** 50-70% faster re-optimizations  
**Estimated:** 12 hours  
**Status:** 🔲 Not started

---

### Week 7-8: Advanced Genetic Algorithm

#### Task 4.1: NSGA-II Multi-Objective GA
```python
# File: optimizer/src/algorithms/hybrid/nsga2_optimizer.py

from deap import base, creator, tools, algorithms

class NSGA2Optimizer:
    objectives = [
        'minimize_vehicles',
        'minimize_cost',
        'maximize_coverage',
        'minimize_deadhead'
    ]
    
    def optimize(self, population_size=100, generations=50):
        """Find Pareto-optimal solutions"""
        pareto_front = algorithms.eaSimple(
            population, 
            toolbox,
            cxpb=0.7,
            mutpb=0.2,
            ngen=generations
        )
        return pareto_front
```

**Impact:** +20-40% solution quality  
**Estimated:** 30 hours  
**Status:** 🔲 Not started

---

## FASE 3: Intelligence & Real-time (Weeks 9-13)

### Week 9-10: ML & Forecasting

#### Task 5.1: Demand Forecasting
```python
# File: optimizer/src/ml/demand_forecaster.py

from sklearn.ensemble import RandomForestRegressor
import numpy as np

class DemandForecaster:
    def __init__(self):
        self.model = RandomForestRegressor()
    
    def train(self, historical_data):
        """Train on historical trips"""
        X = np.array([
            [row['day_of_week'], row['month'], row['weather']]
            for row in historical_data
        ])
        y = np.array([row['trip_count'] for row in historical_data])
        self.model.fit(X, y)
    
    def forecast(self, day_of_week, month, weather):
        """Predict trips for given day"""
        return self.model.predict([[day_of_week, month, weather]])[0]
```

**Impact:** Plan resources with 48h advance notice  
**Estimated:** 20 hours  
**Status:** 🔲 Not started

---

#### Task 5.2: Anomaly Detection
```python
# File: optimizer/src/ml/anomaly_detector.py

from sklearn.ensemble import IsolationForest

class AnomalyDetector:
    def __init__(self):
        self.model = IsolationForest(contamination=0.05)
    
    def detect_trip_anomalies(self, trips):
        """Detect unusual trips"""
        features = np.array([
            [t['duration'], t['distance'], t['vehicle_type']]
            for t in trips
        ])
        predictions = self.model.predict(features)
        return [trips[i] for i, pred in enumerate(predictions) if pred == -1]
```

**Impact:** Prevent operational crises  
**Estimated:** 16 hours  
**Status:** 🔲 Not started

---

### Week 11-12: Real-time Optimization

#### Task 6.1: Event-driven Reoptimization
```python
# File: optimizer/src/services/realtime_optimizer.py

class RealtimeOptimizer:
    def on_trip_added(self, trip: Trip):
        """When new trip arrives"""
        self.pending_trips.append(trip)
        if len(self.pending_trips) >= 10:
            self.reoptimize()
    
    def on_vehicle_delayed(self, vehicle_id: int, delay: int):
        """When vehicle is delayed"""
        affected_blocks = [b for b in self.blocks if b.vehicle_id == vehicle_id]
        self.reoptimize(affected_blocks)
    
    def reoptimize(self, affected_blocks=None):
        """Re-run optimization on affected blocks only"""
        # Fast reoptimization using cached solutions
        self.optimizer.optimize(affected_blocks, use_cache=True)
```

**Impact:** Adapt to delays in real-time  
**Estimated:** 25 hours  
**Status:** 🔲 Not started

---

### Week 13: Polish & Documentation

#### Task 7.1: Testing & QA
- [ ] Integration tests for all features
- [ ] Performance testing (5000+ trips)
- [ ] Load testing (concurrent optimizations)
- [ ] Real data testing (Company 16 + 2-3 customers)
- [ ] UAT with pilot customers

**Estimated:** 30 hours  
**Status:** 🔲 Not started

---

#### Task 7.2: Documentation
- [ ] API documentation (Swagger/OpenAPI)
- [ ] Architecture documentation
- [ ] Deployment guide (production)
- [ ] User guide (for customers)
- [ ] Developer guide (for team)

**Estimated:** 15 hours  
**Status:** 🔲 Not started

---

## Implementation Priorities

### FASE 1 (Week 1-4): Must Have
- [x] Database schemas (depots, vehicle types)
- [x] Backend solver modifications
- [x] Frontend dashboard
- [x] Drag & drop editing

### FASE 2 (Week 5-8): Should Have
- [ ] Parallelization
- [ ] Caching
- [ ] Advanced GA

### FASE 3 (Week 9-13): Nice to Have
- [ ] ML forecasting
- [ ] Anomaly detection
- [ ] Real-time optimization

---

## Success Metrics by Phase

### FASE 1 Success (Week 4):
```
✅ Dashboard visible with real data
✅ Multi-depot working with Company 16
✅ Vehicle types reducing costs by 5-10%
✅ Drag & drop functional
✅ 1 pilot customer live
✅ 70% Optibus feature parity
```

### FASE 2 Success (Week 8):
```
✅ Parallelization: 6-8x faster
✅ Cache hit rate: >60%
✅ GA improving solutions by 20%
✅ 3-4 customers using FASE 1
✅ 75% Optibus feature parity
```

### FASE 3 Success (Week 13):
```
✅ ML forecasting accuracy: >85%
✅ Anomaly detection: 95%+ precision
✅ Real-time reoptimization: <2s response
✅ 5-8 customers using platform
✅ 85-90% Optibus feature parity
✅ Ready for Series A pitch
```

---

## Team Assignment

### Recommended Team Structure:
```
Backend Engineer (Full-time)
├─ FASE 1: Multi-depot + Vehicle Types + API integration
├─ FASE 2: Parallelization + Caching
└─ FASE 3: Real-time optimization

Frontend Engineer (Full-time)
├─ FASE 1: Dashboard + Components
├─ FASE 2: Analytics & visualizations
└─ FASE 3: Advanced UX features

ML/Data Engineer (Part-time → Full-time week 9)
├─ FASE 2: Caching optimization
├─ FASE 3: ML models + Real-time
└─ Ongoing: Model training & tuning

DevOps/QA Engineer (50% all phases)
├─ Testing
├─ Deployment
└─ Performance monitoring
```

---

## Weekly Checkpoint Template

```
WEEK N CHECKPOINT:
└─ Completed:
   ├─ [ ] Task 1
   ├─ [ ] Task 2
   └─ [ ] Tests passing
   
├─ In Progress:
│  ├─ [ ] Task 3
│  └─ [ ] Task 4
│
├─ Blockers:
│  └─ [ ] None / [ ] List issues
│
├─ Metrics:
│  ├─ Tests passing: X/Y
│  ├─ Performance: Xms for 300 trips
│  └─ Coverage: XX%
│
└─ Next Week Plan:
   ├─ [ ] Task 5
   └─ [ ] Task 6
```

---

**Status:** 🎯 Ready to start  
**Branch:** `feature/fase-1-2-3-product-enhancement`  
**Next:** Start Week 1 tasks (Multi-depot schema + Vehicle Types)

Let's go! 🚀
