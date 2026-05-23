# Sprint 1.5: Load Testing & SLA Validation Plan

**Status:** Planning phase (awaiting approval)  
**Target date:** 2026-05-22 to 2026-06-05 (2 weeks)  
**Priority:** P1 — production readiness gate  

---

## Executive Summary

Sprint 1.5 establishes load testing infrastructure and validates SLA compliance across the OTIMIZ system before staging/production deployment. This sprint will:

- Inventory and extend existing k6 + Playwright load test suite
- Define realistic dataset sizes (1k–50k trips) and concurrent user profiles
- Establish quantified pass/fail thresholds for API, optimizer, and infrastructure
- Validate observability (Prometheus, Sentry, logs, Grafana)
- Identify bottlenecks (CPU, memory, Postgres, Redis, Celery queue depth)
- Document runbook steps for perf monitoring in production

**Key decision:** Use **k6** as primary load tool (already present, JS-native). Extend with **k6-reporter** JSON output for CI/CD integration. **No Locust** — Python stack already heavy; k6 is lighter.

---

## 1. Inventory of Current Load-Testing Assets

### Existing k6 Scripts

| File | Purpose | Current Config | Status |
|------|---------|-----------------|--------|
| `tests/load/api.k6.js` | Auth + read endpoints | 50 VUs, 2m sustained, P95<200ms | ✓ Ready |
| `tests/load/optimize.k6.js` | Optimization endpoint | 5 VUs, 3m sustained, P95<5s submission | ✓ Ready |

### Existing Playwright Tests

| File | Scope | Coverage |
|------|-------|----------|
| `frontend/e2e/auth.setup.ts` | Auth session bootstrap | Session creation |
| `frontend/e2e/smoke.spec.ts` | Pages load, no JS crashes | 7 page smoke tests |
| `frontend/e2e/flows.spec.ts` | CRUD flows, form interactions | Trips, Drivers, Fleet CRUD |

### Backend Performance Instrumentation

- **PerformanceMonitorService** (`backend/src/common/performance/performance-monitor.service.ts`)
  - Tracks: schedule_generation, trip_assignment, scenario_evaluation, vehicle_optimization, constraint_validation
  - Records: duration, heap usage, external memory
  - Current thresholds: 5s–1s targets with warning/critical zones

- **MetricsController** (`backend/src/modules/monitoring/metrics.controller.ts`)
  - Prometheus-compatible endpoint at `/api/v1/metrics`
  - Public + throttle-exempt for scraper access

### Infrastructure Observability

- **Sentry:** Already configured (see `frontend/src/instrumentation.ts`)
- **Prometheus:** Assumed present (MetricsController exists)
- **Grafana:** Likely configured in docker-compose
- **Logs:** Requested context ID tracking (see memory: RLS + Silent Refresh 2026-05-20)

### Missing/To-Be-Created

- ❌ k6 load test for CSV/GTFS upload endpoint
- ❌ k6 load test for custom report generation
- ❌ k6 load test for what-if scenario execution
- ❌ k6 load test for concurrent optimization (multiple jobs in parallel)
- ❌ k6 load test for schedule history retrieval at scale
- ❌ Celery queue depth / worker saturation tracking
- ❌ Frontend-driven load test for Gantt rendering with 5k+ rows
- ❌ Pass/fail threshold documentation (currently only in PerformanceMonitor code)
- ❌ Runbook for production perf troubleshooting

---

## 2. Test Scenarios & Flows

### 2.1 API Health & Smoke (Baseline)

**Purpose:** Verify service is responsive under minimal load.

| Scenario | Flow | Dataset | VUs | Duration | Success Criteria |
|----------|------|---------|-----|----------|------------------|
| **API Smoke** | Login → Profile → History → Refresh | None | 5 | 30s ramp + 1m sustained | P95<100ms, errors <0.1% |
| **Dashboard Load** | Login → Dashboard page render | None | 10 | 30s + 1m | Page <3s, no 500s |
| **Parameters Read** | GET /settings/parameters | None | 5 | 1m | P95<150ms |

### 2.2 Core Flows (Golden Path)

| Scenario | Flow | Dataset | VUs | Duration | Target |
|----------|------|---------|-----|----------|--------|
| **Trip CRUD** | Create trip → List trips → Update → Delete | 100 trips | 10 | 2m | P95<500ms, zero errors |
| **Driver CRUD** | Create driver → Verify in list → Update profile | 50 drivers | 5 | 1m30s | P95<400ms |
| **Fleet Setup** | Create vehicle type → Create vehicles | 30 vehicles | 3 | 1m | P95<300ms |
| **Schedule History** | GET /operations/history with paging | 100 schedules | 15 | 2m | P95<200ms per page |

### 2.3 Data Import (File Upload)

| Scenario | File Type | Size | VUs | Target | Notes |
|----------|-----------|------|-----|--------|-------|
| **CSV Upload** | trips.csv | 1MB (100 trips) | 3 | P95<5s submission | Form multipart |
| **CSV Upload** | trips.csv | 10MB (1k trips) | 3 | P95<15s submission | Monitor memory |
| **CSV Upload** | trips.csv | 50MB (5k trips) | 1 | P95<45s submission | Check DoS mitigation (xlsx→exceljs) |
| **GTFS Upload** | feed.zip | 20MB | 2 | P95<30s submission | Async parsing |

### 2.4 Optimization Request (Core CPU Load)

| Scenario | Dataset | VUs | Concurrency | Target | Notes |
|----------|---------|-----|-------------|--------|-------|
| **1k trips / 14 vehicles** | 1k trips, 1 line, 1 day | 3 | Sequential | Submit <3s, solve <30s, P95<40s total | Greedy + B&P |
| **5k trips / 40 vehicles** | 5k trips, 2 lines, 1 day | 2 | Sequential | Submit <3s, solve <60s, P95<90s total | CPU-intensive |
| **10k trips / 80 vehicles** | 10k trips, 4 lines, 1 day | 1 | Sequential | Submit <3s, solve <120s | Hardware limit test |
| **Multi-optimize** | 5k trips | 5 | Parallel (3 jobs/user) | Queue depth <100, worker util <80% | Celery saturation |

### 2.5 Reporting & Export

| Scenario | Flow | Dataset | VUs | Target |
|----------|------|---------|-----|--------|
| **Standard Report** | POST /operations/{id}/report with KPIs | 1k trips, 1 schedule | 5 | P95<5s, file <10MB |
| **Custom Report** | POST /custom-reports/run with 10+ metrics | 5k trips, 1 schedule | 3 | P95<15s, file <50MB |
| **CSV Export** | GET /operations/export?format=csv | 5k trips, 100 schedules | 3 | P95<10s, streaming OK |
| **PDF Export** | GET /operations/export?format=pdf | 1k trips, 1 schedule | 2 | P95<20s (pdfkit) |

### 2.6 What-If / Scenario Analysis

| Scenario | Flow | VUs | Target |
|----------|------|-----|--------|
| **Evaluate scenario** | POST /scenarios/{id}/evaluate | 3 | P95<30s (10k trips) |
| **Compare scenarios** | POST /scenarios/compare | 2 | P95<60s (multiple evaluations) |
| **Replay from fingerprint** | POST /operations/replay | 2 | P95<5s (deterministic) |

### 2.7 Frontend Load (Gantt + Interactive)

| Scenario | Component | Data | Target | Tool |
|----------|-----------|------|--------|------|
| **Gantt render** | `/operations/planner` with schedule | 1k trips (50 rows) | TTI <3s | Playwright |
| **Gantt render** | `/operations/planner` with schedule | 5k trips (200 rows) | TTI <8s | Playwright |
| **Gantt drag/drop** | Drag task + re-optimize | 1k trips | P95<500ms response | Playwright |
| **Map render** | `/operations/map` with 500 trips | 500 trips, 200 terminals | TTI <4s | Playwright |

---

## 3. Dataset Sizes & Dimensionality

### Primary Test Matrix

| Size | Trips | Lines | Days | Drivers | Vehicles | Trips/Vehicle | Use Case |
|------|-------|-------|------|---------|----------|-----------------|----------|
| **S** | 1,000 | 1 | 1 | 10 | 14 | ~71 | Smoke, quick regression |
| **M** | 5,000 | 2 | 1 | 30 | 40 | ~125 | Standard load |
| **L** | 10,000 | 4 | 1 | 60 | 80 | ~125 | High-load baseline |
| **XL** | 30,000 | 8 | 1 | 150 | 200 | ~150 | Stress test |
| **XXL** | 50,000 | 10 | 1 | 250 | 350 | ~143 | Hardware limit (optional) |

### Optional High-Dimensionality Test

- **Multi-day**: Same volumes × 5 days → 5k–50k trips over a week
- **Multi-depot**: 3 depots, distributed allocations
- **Mixed metrics**: Real AVG, MIN, MAX trip durations (not uniform)

---

## 4. Metrics to Collect

### 4.1 API Response Metrics

| Metric | Tool | Format | SLA |
|--------|------|--------|-----|
| **Latency (p50/p95/p99)** | k6 | ms | API: <200ms / Optimize: <5s |
| **Throughput** | k6 | req/s | Min 50 req/s (50 VUs) |
| **Error rate** | k6 | % | <1% (API), <2% (Optimize) |
| **Response body size** | k6 | bytes | Log p95 |
| **Request queue time** | k6 | ms | <50ms when healthy |

### 4.2 System Resource Metrics

| Resource | Scraper | Target | Alert Threshold |
|----------|---------|--------|------------------|
| **CPU usage** | Prometheus (cgroup) | <70% avg | >85% |
| **Memory (RSS)** | Prometheus | <80% of limit | >90% |
| **Postgres connections** | `SELECT count(*)` | <50 (max 100) | >75 |
| **Postgres query time** | `pg_stat_statements` | P95<100ms | P95>500ms |
| **Redis memory** | `INFO memory` | <90% of 256MB | >95% |
| **Redis hit ratio** | `INFO stats` | >80% | <50% |

### 4.3 Optimizer Metrics

| Metric | Source | Expected | Alert |
|--------|--------|----------|-------|
| **Celery queue depth** | `celery inspect active_queues` | <10 at rest | >50 |
| **Worker utilization** | Flower UI / Celery inspect | <70% | >85% |
| **Task duration** | Celery result backend | Greedy 10–60s, B&P 30–120s | 2x baseline |
| **Failed task count** | Celery result backend | 0 | >0 |
| **Optimization iterations** | CSP/VSP logs | Matches expected | Divergent behavior |
| **Solution quality** | Optimizer output | Vehicle count = MCNF lower bound (14 for 1k) | <90% of baseline |

### 4.4 Frontend Metrics

| Metric | Tool | Baseline | Alert |
|--------|------|----------|-------|
| **Page load (TTI)** | Lighthouse / Playwright | <3s (small), <8s (5k rows) | >2x baseline |
| **Gantt render time** | Playwright | <500ms DOM paint | >1s |
| **First Contentful Paint (FCP)** | Lighthouse | <1.5s | >3s |
| **Cumulative Layout Shift (CLS)** | Lighthouse | <0.1 | >0.25 |
| **JavaScript errors** | Sentry | 0 | >1 per 100 pageloads |
| **Memory leak** | DevTools | Stable after GC | +20MB/min rise |

### 4.5 Observability Metrics

| System | Check | Expected | Pass |
|--------|-------|----------|------|
| **Prometheus** | Scrape success | All 4 services scraped | Scrape interval = 15s |
| **Grafana** | Dashboard panel | Data visible | P95 latency shows trend |
| **Sentry** | Error capture | 1 controlled error visible | Event logged + alert sent |
| **Logs** | requestId propagation | Every error has requestId | Trace linkable in dashboard |
| **Flower** | Worker health | All N workers online | No "offline" workers |

---

## 5. Pass/Fail Thresholds for Staging

### 5.1 API Thresholds

| Endpoint | p50 | p95 | p99 | Error Rate |
|----------|-----|-----|-----|-----------|
| **Auth (login, refresh)** | <50ms | <150ms | <300ms | <0.5% |
| **GET /users/profile** | <20ms | <80ms | <150ms | <0.5% |
| **GET /operations/history** | <50ms | <150ms | <300ms | <0.5% |
| **POST /operations/optimize** (submit) | <2s | <5s | <10s | <2% |
| **GET /operations/{id}/status** (poll) | <50ms | <200ms | <500ms | <1% |
| **POST /custom-reports/run** | <5s | <15s | <30s | <2% |
| **POST /operations/export** | <10s | <30s | <60s | <2% |
| **Dashboard page load** | <1s | <3s | <5s | <0.5% |

### 5.2 Infrastructure Thresholds

| Component | Warning | Critical | Action |
|-----------|---------|----------|--------|
| **Postgres CPU** | >60% | >80% | Scale replicas / optimize queries |
| **Postgres connections** | >60 | >90 | Kill idle / add connection pool |
| **Postgres query p95** | >200ms | >500ms | Index + vacuum + analyze |
| **Redis memory** | >85% | >95% | Eviction policy active / increase limit |
| **Redis hit ratio** | <70% | <50% | Cache key review / increase TTL |
| **Celery queue depth** | >30 | >100 | Scale workers / reduce task payload |
| **Celery worker CPU** | >75% | >90% | Add workers / reduce concurrency |
| **Backend memory** | >75% | >90% | Heap dump / memory leak investigation |
| **Backend response p95** | >500ms | >1s | Profile + optimize code path |

### 5.3 Frontend Thresholds

| Metric | Baseline | Warning | Fail |
|--------|----------|---------|------|
| **Gantt TTI (1k trips)** | <1s | <2s | >3s |
| **Gantt TTI (5k trips)** | <4s | <6s | >8s |
| **Unhandled JS errors** | 0/100 loads | >1 | >3 |
| **Memory growth** | <5MB/min | <10MB/min | >20MB/min |
| **Drag-drop response** | <200ms | <500ms | >1s |

### 5.4 Optimization Quality Thresholds

| Test | Baseline | Pass | Fail |
|------|----------|------|------|
| **1k trips: vehicle count** | 14 | 14 (±0) | >15 |
| **1k trips: total cost** | Baseline | ±5% | >±15% |
| **5k trips: vehicle count** | ~40 | 38–42 | >45 |
| **Algorithm consistency** | All 7 match greedy | Match | Diverge >5% |
| **Solver timeout rate** | 0% | <1% | >5% |

---

## 6. Observability Validation Steps

### 6.1 Prometheus

**Setup check:**
```bash
curl http://localhost:9090/api/v1/targets
# Expected: 4 targets UP (backend, optimizer, postgres_exporter, redis_exporter)

curl 'http://localhost:9090/api/v1/query?query=up'
# Expected: {"result": [{"metric": {"job": "backend"}, "value": [time, "1"]}, ...]}
```

**Load test validation:**
- Run k6 for 2m, then query Prometheus for latency trends
- `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
- Should show smooth upward curve during ramp, flat during sustained, downward during ramp-down

### 6.2 Grafana

**Checks:**
- [ ] Latency p50/p95/p99 panels visible, data flowing
- [ ] CPU/memory panels show system resource usage during load
- [ ] Celery queue depth panel shows job submissions
- [ ] Request count panel shows throughput

**Expected during 50-VU load:**
- p95 latency: ~150–250ms
- CPU: ~40–60%
- Memory: ~1.5–2GB backend, ~3GB optimizer

### 6.3 Sentry

**Controlled error test:**
```bash
# Inject test error via backend
curl -X POST http://localhost:3001/api/v1/admin/test-error \
  -H "Authorization: Bearer <token>"
# Expected: Error appears in Sentry dashboard within 5s
```

**Load test check:**
- Monitor Sentry Events tab during load
- Should see <1% error rate
- No "Unhandled Promise Rejection" or "Maximum call stack exceeded"

### 6.4 Logs & RequestId

**Check propagation:**
```bash
# Grep logs for a specific request ID
grep "req-xxx-yyy-zzz" /var/log/otimiz/backend.log | head -5
# Expected: Multiple log lines from different services with same ID
```

**Validation:**
- [ ] Backend request logs include `requestId`
- [ ] Celery task logs include `requestId` from originating request
- [ ] Postgres slow query log includes `requestId` in comment

### 6.5 Flower (Celery Worker Monitor)

**Access:**
```bash
open http://localhost:5555
# Login: admin / admin123
```

**Checks:**
- [ ] All N worker nodes show "online"
- [ ] Pool size matches config (default 4 concurrent)
- [ ] No "heartbeat missed" warnings
- [ ] Task stats: submitted count matches expected jobs

---

## 7. Risks & Bottlenecks (Expected)

### 7.1 Optimizer CPU Saturation

**Risk:** Large optimization (10k+ trips) consumes 100% of 3.0 CPU limit.

**Symptom:** Solver timeout (>120s), incomplete branch-and-price iterations.

**Mitigation:**
- Single-threaded constraint: keep VU count = 1 for 10k+ tests
- Add `CELERY_TASK_TIME_LIMIT=180` to docker-compose
- Monitor `optimizer` container CPU with `docker stats`

**Validation:**
```bash
docker stats --no-stream | grep otimiz-v2-optimizer
# Expected: CPU <90%, memory <4GB for 1k–5k trips
```

### 7.2 Postgres Connection Pool Exhaustion

**Risk:** 50+ concurrent API VUs → connection limit (default 100).

**Symptom:** "too many connections" error, queue buildup.

**Mitigation:**
- PgBouncer pooling: already in docker-compose (assumed)
- Max connections per VU: ~2 (connection reuse)
- Reduce API test VU count if needed: start at 30, ramp to 50

**Validation:**
```sql
SELECT count(*) FROM pg_stat_activity;
-- Expected: <70 active connections during 50-VU API load
```

### 7.3 Redis Eviction Under Load

**Risk:** Queue buildup + result storage (3600s TTL) → LRU eviction.

**Symptom:** Missing task results, Celery task timeouts.

**Mitigation:**
- Monitor Redis memory: `redis-cli INFO memory | grep used_memory`
- Increase `maxmemory 256mb` if testing >10 concurrent optimizations
- Reduce `CELERY_TASK_RESULT_EXPIRES` in integration tests (300s)

**Validation:**
```bash
redis-cli -a "$REDIS_PASSWORD" INFO stats | grep evicted_keys
# Expected: <10 evictions during 2m load test
```

### 7.4 Frontend Gantt Rendering (Large Schedules)

**Risk:** 5k+ trip rows → browser UI freeze (janky scrolling, slow drag-drop).

**Symptom:** First Contentful Paint >8s, frame drops on drag.

**Mitigation:**
- Virtual scrolling already implemented (likely via react-window)
- Lighthouse throttle to "Slow 4G" to stress-test
- Limit test to 2k rows (1 day, ~140 trips/vehicle) for responsive targets

**Validation:**
```bash
npx playwright test e2e/flows.spec.ts --headed
# Manually scroll Gantt, count frames dropped
# Expected: smooth 60fps, <1 frame drop
```

### 7.5 Celery Worker Saturation

**Risk:** Multiple concurrent long-running optimization jobs → task queue grows faster than workers drain.

**Symptom:** Queue depth >100, new submissions get 429 (rate-limited).

**Mitigation:**
- Add `CELERY_WORKER_PREFETCH_MULTIPLIER=1` (grab one task at a time)
- Scale workers horizontally: `docker-compose up -d --scale optimizer=3`
- Monitor queue with k6: poll `/admin/celery/queue-depth` endpoint

**Validation:**
```bash
celery -A optimizer.celery_app inspect active_queues
# Expected: queue depth <20 at peak 5-job parallel load
```

### 7.6 CSV Upload Memory Spike (xlsx→exceljs)

**Risk:** 50MB XLSX parse → temporary 500MB+ memory usage.

**Symptom:** Backend OOM kill, 502 response mid-upload.

**Mitigation:**
- Streaming parser (likely exceljs default)
- Disk temp file fallback in code
- Limit file size: `MAX_UPLOAD_SIZE_MB=100` config

**Validation:**
```bash
# During upload, monitor backend memory
docker stats otimiz-v2-backend --no-stream | head -20
# Expected: peak <3.5GB (leaving 0.5GB headroom)
```

### 7.7 Postgres Slow Queries (History Paging)

**Risk:** Unindexed sort on large result set (100+ schedules).

**Symptom:** History endpoint p95 >1s when >1000 schedules exist.

**Mitigation:**
- Index on `schedules(created_at DESC NULLS LAST)`
- Limit default page size: `REPORT_DETAIL_LIMIT=10` (already done)
- Add EXPLAIN ANALYZE to slow-query log

**Validation:**
```bash
# Seed 1000 schedules, query with ?limit=10&offset=500
time curl "http://localhost:3001/api/v1/operations/history?limit=10&offset=500" \
  -H "Authorization: Bearer $TOKEN"
# Expected: <200ms p95
```

---

## 8. Implementation Plan

### Phase 1: Extend k6 Load Tests (3 days)

**Tasks:**

1. **Create `tests/load/csv-upload.k6.js`**
   - Upload 1MB, 10MB, 50MB CSV files
   - Measure upload time + backend memory
   - Thresholds: <5s (1MB), <15s (10MB), <45s (50MB)

2. **Create `tests/load/report.k6.js`**
   - Standard report generation (5s target)
   - Custom report with 10 metrics (15s target)
   - CSV export (10s target)

3. **Create `tests/load/scenario.k6.js`**
   - What-if evaluation (30s target)
   - Scenario comparison (60s target)
   - Replay from fingerprint (5s target)

4. **Create `tests/load/optimize-parallel.k6.js`**
   - 3 concurrent optimize jobs
   - Monitor Celery queue depth + worker CPU
   - Measure queue wait time

5. **Extend `tests/load/optimize.k6.js`**
   - Add 5k-trip (M) and 10k-trip (L) test variants
   - Add dataset parameterization
   - Add solution quality validation (vehicle count check)

6. **Enhance k6 base config**
   - Add `--tag scenario:api` for filtering
   - Export JSON results: `--out json=results.json`
   - Add custom metric: `task_solve_time` for optimizer

### Phase 2: Frontend Load Test (Playwright) (2 days)

**Tasks:**

1. **Create `frontend/e2e/performance.spec.ts`**
   - Gantt render time (1k rows, 5k rows)
   - Map render time (500 trips)
   - Drag-drop response latency
   - Memory growth check

2. **Create Lighthouse CI integration**
   - Run Lighthouse on `/operations/planner` with throttling
   - Capture FCP, LCP, CLS
   - Fail CI if CLS >0.25

### Phase 3: Threshold & SLA Documentation (2 days)

**Tasks:**

1. **Create `docs/PERFORMANCE_SLA.md`**
   - Codify all thresholds from this plan
   - Per-endpoint response targets
   - Per-resource alert levels

2. **Update PerformanceMonitorService**
   - Add new thresholds for CSV upload, report generation
   - Align thresholds with documented SLAs
   - Add metrics export (Prometheus format)

3. **Create `docs/LOAD_TEST_RESULTS.md` template**
   - Baseline results (1k, 5k, 10k dataset sizes)
   - p50/p95/p99 snapshots
   - Resource utilization during load
   - Date + operator name for audit trail

### Phase 4: Observability Validation (2 days)

**Tasks:**

1. **Prometheus config validation**
   - Verify all 4 scrape targets in docker-compose
   - Test `curl /metrics` on backend + optimizer
   - Check Prometheus scrape logs for errors

2. **Grafana dashboard verification**
   - Create/update dashboard: "Load Test Results"
   - Panels: p95 latency, CPU %, memory %, queue depth
   - Save JSON export for CI/CD integration

3. **Sentry integration test**
   - Create `/admin/test-error` endpoint
   - Inject error, verify Sentry captures within 5s
   - Document alert routing

4. **Log requestId propagation**
   - Grep test logs for requestId presence
   - Verify requestId in Celery task logs
   - Link example in runbook

5. **Flower (Celery) UI walkthrough**
   - Document how to access (localhost:5555)
   - Screenshot worker pool, task stats
   - Create runbook: "Celery worker troubleshooting"

### Phase 5: Bottleneck Identification & Runbook (1 day)

**Tasks:**

1. **Create `docs/PRODUCTION_PERF_RUNBOOK.md`**
   - Flow: "p95 latency spike detected"
   - Diagnostics: Prometheus queries, log grep patterns
   - Actions: Scale Postgres, kill slow queries, add workers
   - Escalation: who to page

2. **Create baseline comparison script**
   - `tests/scripts/compare-load-results.py`
   - Compare two k6 JSON result files (before/after code change)
   - Alert if p95 >10% regression

### Phase 6: CI/CD Integration (1 day)

**Tasks:**

1. **Create GitHub Actions workflow: `load-test.yml`**
   - Trigger: manual (`workflow_dispatch`)
   - Steps:
     - Start docker-compose (staging)
     - Run k6 tests (api, optimize, csv-upload, report)
     - Collect Prometheus metrics snapshot
     - Compare to baseline, fail if p95 > threshold
     - Archive results to S3 / GitHub releases

2. **Create baseline snapshot**
   - Run load tests on clean staging instance
   - Export Prometheus metrics + k6 results
   - Commit as `tests/load/baseline.json`

---

## 9. Files Likely to Change / New Files

### New Files (To Be Created)

```
tests/load/
├── api.k6.js                      (existing, minor extension)
├── optimize.k6.js                 (existing, extension with dataset variants)
├── csv-upload.k6.js               (NEW)
├── report.k6.js                   (NEW)
├── scenario.k6.js                 (NEW)
├── optimize-parallel.k6.js        (NEW)
├── base-config.js                 (NEW — shared k6 config, thresholds)
└── baseline.json                  (NEW — baseline metrics snapshot)

frontend/e2e/
├── performance.spec.ts            (NEW — Gantt render, memory, map load)
└── playwright.config.ts           (existing, may add throttling)

docs/
├── SPRINT_1.5_LOAD_TEST_PLAN.md  (THIS FILE)
├── PERFORMANCE_SLA.md             (NEW — threshold reference)
├── LOAD_TEST_RESULTS.md           (NEW — template + historical results)
└── PRODUCTION_PERF_RUNBOOK.md    (NEW — debugging guide)

.github/workflows/
└── load-test.yml                  (NEW — CI/CD automation)

backend/src/
├── common/performance/
│   └── performance-monitor.service.ts  (existing, update thresholds)
├── modules/admin/
│   └── perf.controller.ts         (NEW — /admin/test-error, /admin/celery/queue-depth)
└── app.module.ts                  (existing, register perf.controller)

optimizer/
├── celery_config.py               (existing, add TASK_TIME_LIMIT)
└── Dockerfile                     (existing, may increase memory if tests require)

docker-compose.yml                 (existing, may adjust resource limits)

tests/scripts/
├── compare-load-results.py        (NEW — regression detection)
└── seed-load-test-data.ts         (NEW — create 1k/5k/10k trip datasets)
```

### Modified Files

| File | Change | Reason |
|------|--------|--------|
| `backend/src/common/performance/performance-monitor.service.ts` | Add CSV upload, report, scenario thresholds | Align with new k6 tests |
| `backend/src/main.ts` | Register `/admin/*` routes | Add test-error + queue-depth endpoints |
| `docker-compose.yml` | Optional: increase `optimizer` memory to 4.5G if 10k test required | Stress testing |
| `frontend/e2e/playwright.config.ts` | Add `Slow 4G` throttle profile | Performance baseline |
| `package.json` (backend) | Add `@nestjs/throttler` if missing | Rate limiting (already done per memory) |

---

## 10. Validation Strategy

### Milestone 1: Load Test Suite Ready (Day 5)
- [ ] All 5 k6 scripts execute without errors
- [ ] k6 thresholds defined and documented
- [ ] Baseline results collected (1k, 5k datasets)
- [ ] **Gate:** All tests pass, no hard errors

### Milestone 2: Observability Validated (Day 8)
- [ ] Prometheus scrapes all targets
- [ ] Grafana dashboard shows load test metrics
- [ ] Sentry captures 1 test error
- [ ] Logs contain requestId in every entry
- [ ] Flower shows workers online
- [ ] **Gate:** All observability systems respond during load

### Milestone 3: Bottlenecks Identified (Day 11)
- [ ] Load test data collected for 1k, 5k, 10k datasets
- [ ] Postgres slow queries logged and indexed
- [ ] Celery queue depth peaks recorded
- [ ] Frontend Gantt render times baselined
- [ ] **Gate:** No unexpected system failures

### Milestone 4: Documentation & Runbook Complete (Day 14)
- [ ] PERFORMANCE_SLA.md linked in README
- [ ] PRODUCTION_PERF_RUNBOOK.md includes 5 common scenarios
- [ ] CI/CD workflow `load-test.yml` executes and archives results
- [ ] Baseline snapshot committed to repo
- [ ] **Gate:** Operations team can run perf tests independently

### Final Gate: SLA Compliance
- [ ] p95 latency: API <200ms, optimize submit <5s, optimize solve <120s (for 10k)
- [ ] Error rate <2%
- [ ] Postgres CPU <70%, memory <80%
- [ ] Redis hit ratio >80%
- [ ] Celery queue depth <50 at sustained load
- [ ] No unhandled JS errors on Gantt (1k + 5k rows)
- [ ] **PASS → Ready for staging**

---

## 11. Tool Choice Justification

### k6 (Selected) vs Locust

| Criterion | k6 | Locust | Winner |
|-----------|-----|--------|--------|
| **Language** | JavaScript | Python | k6 (JS-native, lighter) |
| **Setup overhead** | npm install | Python venv + pip | k6 |
| **Existing scripts** | ✓ (2 present) | ✗ | k6 |
| **Threshold support** | Built-in | Manual | k6 |
| **JSON result export** | `--out json` | Manual | k6 |
| **Monitoring integration** | Prometheus-native | Requires plugin | k6 |
| **CI/CD ease** | Simple CLI | Container overhead | k6 |
| **Team familiarity** | Frontend team knows JS | None | k6 |

**Decision:** **k6 only**. Locust adds Python dependency overhead and duplicates what k6 already covers.

### Playwright (Selected) for Frontend Load

| Criterion | Playwright | Selenium | Winner |
|-----------|-----------|----------|--------|
| **Existing setup** | ✓ (e2e/auth.setup.ts exists) | ✗ | Playwright |
| **Headless speed** | Fast | Slower | Playwright |
| **Browser automation** | Chromium, Firefox, WebKit | Limited | Playwright |
| **Memory profiling** | Built-in CDP | Requires DevTools Protocol | Playwright |

**Decision:** Extend existing Playwright suite for frontend load tests.

---

## 12. Success Criteria Summary

| Criterion | Metric | Pass |
|-----------|--------|------|
| **Load test coverage** | Endpoints tested | 15+ scenarios |
| **Dataset coverage** | Trip counts | 1k, 5k, 10k tested |
| **Threshold definition** | Documented SLAs | 20+ metrics with p50/p95/p99 |
| **Observability** | Systems validated | Prometheus, Grafana, Sentry, logs, Flower |
| **Bottleneck identification** | Issues found & mitigated | 5+ documented bottlenecks with solutions |
| **Runbook completeness** | Pages written | PERF_RUNBOOK covers 5 scenarios |
| **CI/CD automation** | Workflow created | Runs load tests, compares baseline, archives results |
| **Team readiness** | Knowledge transfer | Docs reviewed, runbook walkthrough completed |

---

## Timeline & Effort Estimate

| Phase | Duration | Effort | Owner | Dependencies |
|-------|----------|--------|-------|--------------|
| **Phase 1:** k6 tests (3 days) | 2026-05-23 to 2026-05-25 | 24h | Backend + Perf | API endpoints stable |
| **Phase 2:** Playwright (2 days) | 2026-05-26 to 2026-05-27 | 16h | Frontend | Component stable |
| **Phase 3:** Thresholds (2 days) | 2026-05-28 to 2026-05-29 | 16h | Team lead | Baseline data collected |
| **Phase 4:** Observability (2 days) | 2026-05-30 to 2026-05-31 | 16h | DevOps + Backend | Prometheus, Grafana running |
| **Phase 5:** Runbook (1 day) | 2026-06-01 | 8h | Team lead | All tests passing |
| **Phase 6:** CI/CD (1 day) | 2026-06-02 | 8h | DevOps | Baseline snapshot ready |
| **Integration & Review** | 2026-06-03 to 2026-06-05 | 24h | Team | All phases complete |

**Total:** ~2 weeks, ~112h (4 FTE)

---

## Approval Checklist

Before implementation begins:

- [ ] Scope approved by PM/Tech Lead
- [ ] Resource availability confirmed (backend, frontend, DevOps)
- [ ] Docker-compose environment validated (all 5 services start)
- [ ] Test data generation script ready (seed 1k/5k/10k trips)
- [ ] Baseline metrics collection plan approved
- [ ] SLA thresholds negotiated with stakeholders
- [ ] CI/CD infrastructure (GitHub Actions) available

---

## Next Steps

1. **Review this plan** with the team (1h)
2. **Negotiate SLA thresholds** with operations team (1h)
3. **Prepare test data** generation script (4h, parallel)
4. **Begin Phase 1** (k6 script development)

---

**Document Status:** Draft — Awaiting approval  
**Last Updated:** 2026-05-22  
**Owner:** Edvanilson (Project Lead)
