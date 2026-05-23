# Load Testing & Performance Baseline

This directory contains baseline performance metrics and load testing infrastructure for OTIMIZ.

## Quick Start

### Prerequisites

**k6 load testing tool** (required)

```bash
# Manjaro / Arch
sudo pacman -S k6

# Or via binary (any OS)
wget https://github.com/grafana/k6/releases/latest/download/k6-linux-amd64.tar.gz
tar xzf k6-linux-amd64.tar.gz
sudo mv k6 /usr/local/bin/
```

Verify: `k6 version`

**Backend running locally**

```bash
# In project root
npm run dev:backend  # starts on http://localhost:3001
```

### Run Baseline (All-in-One)

```bash
./scripts/run_baseline.sh
```

This:
1. Generates trip datasets (1k, 5k, 10k CSVs)
2. Runs API smoke + auth + schedule history + optimize flow
3. Uploads each dataset and measures import performance
4. Outputs JSON + logs to `docs/performance/results/`

**Expected output:**
```
🔄 Starting baseline load test suite...
📊 Step 1: Generating trip datasets...
✅ trips_1k.csv: 1001 lines
...
✅ All tests completed!
📁 Results in: docs/performance/results
```

### Run Individual Tests

**Dataset generation only:**
```bash
python3 tests/load/datasets/gen_trips.py \
  --sizes 1000 5000 10000 \
  --output-dir tests/load/datasets/
```

**API baseline (all VUs, all scenarios):**
```bash
k6 run tests/load/baseline.k6.js \
  -e BASE_URL=http://localhost:3001/api/v1 \
  -e TEST_EMAIL=admin@empresa.com \
  -e TEST_PASS=admin123
```

**Upload test for 5k dataset:**
```bash
k6 run tests/load/upload_import.k6.js \
  -e BASE_URL=http://localhost:3001/api/v1 \
  -e TEST_EMAIL=admin@empresa.com \
  -e TEST_PASS=admin123 \
  -e DATASET=tests/load/datasets/trips_5k.csv \
  -e DATASET_SIZE=5k
```

---

## Metrics Glossary

### HTTP Request Metrics

| Metric | Meaning |
|--------|---------|
| `http_req_duration` | Request time (ms), end-to-end |
| `http_req_duration.p50` | Median latency |
| `http_req_duration.p95` | 95th percentile latency |
| `http_req_duration.p99` | 99th percentile latency |
| `http_req_failed` | Requests with non-2xx/3xx status |
| `http_reqs` | Total requests completed |

### Aggregated Metrics

| Metric | Meaning |
|--------|---------|
| `iteration_duration` | Time to complete one scenario cycle per VU |
| `iterations` | Total scenario iterations completed |
| `vus` | Virtual users active |
| `vus_max` | Peak VU count |

### Performance Thresholds (Baseline)

**Informational only** (not blocking CI):

```
http_req_duration:
  p(95) < 2000ms    # 95% of requests within 2s
  p(99) < 5000ms    # 99% of requests within 5s

http_req_failed:
  rate < 0.05       # < 5% error rate
```

---

## Scenario Breakdown

### S1: Health Check (10 VUs, 30s)
- Endpoint: `GET /health`
- No auth required
- SLA: should be <100ms p95

### S2: Auth & Profile (5 VUs, 1m)
- Endpoints:
  - `POST /auth/login` (setup phase only)
  - `GET /auth/profile` (main test)
- SLA: <500ms p95

### S3: Schedule History (5 VUs, 1m)
- Endpoint: `GET /operations/schedules`
- Lists all schedules for tenant
- SLA: <1000ms p95

### S4: Optimize Submit (1 VU, 30s)
- Endpoint: `POST /operations/optimize`
- Submits optimization job
- Rate limit: 5 req/300s per tenant
- Single VU to avoid throttling
- SLA: <2000ms p95

### S5: Status Poll (3 VUs, 2m)
- Endpoint: `GET /operations/optimize/status`
- Polls optimization run status
- SLA: <500ms p95

---

## Analyzing Results

### View summary from JSON output:

```bash
# Extract key metrics
cat docs/performance/results/baseline_*.json | jq '.metrics' | jq '.http_req_duration'

# Check error rate
cat docs/performance/results/baseline_*.json | jq '.metrics.http_req_failed.values.rate'

# Get all p95 latencies
cat docs/performance/results/*.json | jq -r '.metrics | to_entries[] | "\(.key): p95=\(.value.values.p95 // "N/A")ms"'
```

### Generate baseline report:

After running tests, populate `baseline-YYYY-MM-DD.md` with:
1. Date / environment (backend version, CPU cores, RAM)
2. Summary table (requests, errors, p50/p95/p99)
3. Per-scenario breakdown
4. Upload performance (1k/5k/10k import times)
5. Observed bottlenecks
6. SLA recommendations

Example template at: `baseline-TEMPLATE.md`

---

## Rate Limiting

OTIMIZ enforces request throttling:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /auth/login` | 10 req | 60s |
| `POST /operations/optimize` | 5 req | 300s per tenant |
| Other endpoints | Unlimited | — |

**Load test strategy:**
- Health / profile / schedule history: standard load (high VU count, parallel ok)
- Optimize: single VU, sequential requests with 60s sleep between

---

## Troubleshooting

### k6 not found
```bash
# Check PATH
which k6

# Or install via snap
sudo snap install k6
```

### Backend unreachable
```bash
curl http://localhost:3001/api/v1/health
# Should return: {"status":"ok"}
```

### Auth failures
```
error: login status 200 failed
```
- Check backend is running: `curl http://localhost:3001/api/v1/health`
- Verify credentials in `.env` or script (default: admin@empresa.com / admin123)

### Upload script fails with "file not found"
```bash
# Regenerate datasets
python3 tests/load/datasets/gen_trips.py

# Verify
ls -la tests/load/datasets/trips_*.csv
```

### High error rates (>5%)
- Check backend logs: `docker logs backend` (if containerized)
- Verify no rate limit hits: grep `429` in k6 output
- Reduce VU count temporarily: edit baseline.k6.js stages

---

## CI/CD Integration (Future)

Currently, load tests run manually only. To integrate into CI:

1. Add k6 to runner environment
2. Create baseline thresholds (not yet blocking)
3. Compare new runs against baseline
4. Flag regressions (>10% p95 increase)

⚠️ **Currently out of scope** — perform manual baseline first, then gate on CI.

---

## See Also

- Baseline results: `docs/performance/results/baseline-*.md`
- Test scripts: `tests/load/`
- Generator: `tests/load/datasets/gen_trips.py`
- Monitoring stack: `docker-compose.yml` (Prometheus + Grafana)
