# Baseline Performance Report — [DATE]

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Test Date | YYYY-MM-DD HH:MM:SS | — |
| Backend Version | [git SHA or tag] | — |
| Test Duration | Xm Ys | — |
| Total Requests | N | — |
| Error Rate | X.XX% | ✅ / ⚠️ / ❌ |
| p95 Latency (all) | Xms | ✅ / ⚠️ |

**Summary:** [1-2 sentence assessment of baseline performance]

---

## Environment

### Hardware

| Component | Value |
|-----------|-------|
| CPU | AMD Ryzen 5 4600H (6 cores, 12 threads) |
| RAM | 19 GB DDR4 |
| GPU | Radeon Vega (integrated, no VRAM) |
| Disk | NVMe SSD |
| OS | Manjaro Linux 6.12.90 |

### Backend

| Component | Value |
|-----------|-------|
| Node.js | [version from `node -v`] |
| NestJS | [version from package.json] |
| TypeORM | [version] |
| PostgreSQL | 15.x |
| Redis | 7.x |

### k6 & Load Parameters

| Parameter | Value |
|-----------|-------|
| k6 Version | [from `k6 version`] |
| Test Duration | [Xm Ys total] |
| Total VUs | ~10 (peak from stages) |
| Ramp-up | Gradual (health → auth → schedule → optimize → status) |
| Rate Limit Hits | [0 / X] |

---

## Scenario Results

### S1: Health Check (10 VUs, 30s)

```
Requests:  Xk
Duration:  p50=Xms, p95=Xms, p99=Xms
Errors:    X
Throughput: X req/s
```

**SLA:** p95 < 100ms ✅

### S2: Auth & Profile (5 VUs, 1m)

```
Requests:  Xk
Duration:  p50=Xms, p95=Xms, p99=Xms
Errors:    X
```

**SLA:** p95 < 500ms ✅

### S3: Schedule History (5 VUs, 1m)

```
Requests:  Xk
Duration:  p50=Xms, p95=Xms, p99=Xms
Errors:    X
```

**SLA:** p95 < 1000ms ✅

### S4: Optimize Submit (1 VU, 30s)

```
Requests:  X
Duration:  p50=Xms, p95=Xms, p99=Xms
Errors:    X
```

**SLA:** p95 < 2000ms ✅

**Note:** Single VU to respect rate limit (5 req/300s per tenant).

### S5: Status Poll (3 VUs, 2m)

```
Requests:  Xk
Duration:  p50=Xms, p95=Xms, p99=Xms
Errors:    X
```

**SLA:** p95 < 500ms ✅

---

## Dataset Upload Performance

### trips_1k.csv (1000 trips)

```
Upload Time: Xms
Throughput: X MB/s
Backend Processing: Xms (response latency)
Trips Imported: 1000
```

### trips_5k.csv (5000 trips)

```
Upload Time: Xms
Throughput: X MB/s
Backend Processing: Xms
Trips Imported: 5000
```

### trips_10k.csv (10000 trips)

```
Upload Time: Xms
Throughput: X MB/s
Backend Processing: Xms
Trips Imported: 10000
```

**Scaling:** Linear / Sublinear / Superlinear

---

## Bottlenecks & Observations

### Database Performance

- **Connection pool:** [status from logs]
- **Slow queries:** [any p99 latencies > 1000ms? which endpoints?]
- **Lock contention:** [any observable?]

### Memory Usage

- **Backend peak:** [X MB from logs]
- **Redis memory:** [X MB]
- **Database:** [X MB]

### Network

- **Packet loss:** [0% expected]
- **Latency to DB:** [X ms, typical for local]

### Rate Limiting

- **Login (10/60s):** [0 hits expected, hits if any]
- **Optimize (5/300s):** [0 hits expected (single VU), hits if any]

---

## Recommendations

### Short-term (No Code Changes)

- [ ] Add read replicas if profile queries dominate p99
- [ ] Increase connection pool if DB connections hit limit
- [ ] Enable query logging for p99 outliers

### Medium-term (Next Sprint)

- [ ] Implement caching for `/operations/schedules` (high frequency, stable data)
- [ ] Index on `tenant_id + created_at` for history queries
- [ ] Async job processing for long optimizations (>10s)

### Long-term (After Baseline)

- [ ] Load test with 50k–100k trips (database stress)
- [ ] Profile optimizer performance separately
- [ ] Measure multi-tenant isolation under load
- [ ] Establish SLA gates for CI (not yet blocking)

---

## Regression Detection

**Baseline SLAs (not yet blocking CI):**

```
http_req_duration.p95: < 2000ms
http_req_duration.p99: < 5000ms
http_req_failed.rate: < 0.05
```

To compare future runs:

```bash
# Extract baseline p95
grep -o '"p95":[0-9]*' docs/performance/results/baseline_*.json

# Compare against new run
k6 run tests/load/baseline.k6.js --out json=new_run.json
grep -o '"p95":[0-9]*' new_run.json

# Flag if delta > 10%
```

---

## Raw Data

All k6 JSON output and logs available in:

```
docs/performance/results/baseline_YYYY-MM-DD_HHMMSS.json
docs/performance/results/baseline_YYYY-MM-DD_HHMMSS.log
docs/performance/results/upload_1k_YYYY-MM-DD_HHMMSS.json
docs/performance/results/upload_5k_YYYY-MM-DD_HHMMSS.json
docs/performance/results/upload_10k_YYYY-MM-DD_HHMMSS.json
```

---

## Approval

| Role | Name | Date | Sign-off |
|------|------|------|----------|
| Performance | [Your Name] | [Date] | ✅ / ❌ |
| QA Lead | — | — | ❌ (pending) |

---

**Next Steps:**
1. [ ] Run ./scripts/run_baseline.sh
2. [ ] Populate metrics above
3. [ ] Review bottlenecks
4. [ ] Get sign-off
5. [ ] Establish CI gates (future sprint)
