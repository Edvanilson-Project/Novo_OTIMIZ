# OTIMIZ Operational Runbook

**Last Updated:** 2026-05-22

This runbook provides operational procedures for maintaining, monitoring, and troubleshooting the OTIMIZ platform in staging and production environments.

---

## 1. System Overview

OTIMIZ consists of the following critical services:

- **Backend** (NestJS): REST API, authentication, schedule management
  - Port: 3001
  - Health: `http://localhost:3001/api/v1` (GET)
  - Metrics: `http://localhost:3001/api/v1/metrics` (Prometheus format)

- **Frontend** (Next.js): React SPA, user interface
  - Port: 3000
  - Health: `http://localhost:3000` (HEAD/GET)

- **Optimizer** (Python/FastAPI): Vehicle scheduling optimization
  - Port: 8000
  - Health: `http://localhost:8000/health` (GET)
  - Metrics: `http://localhost:8000/metrics` (Prometheus format)

- **PostgreSQL**: Primary data store
  - Port: 5432
  - Default credentials in `.env`

- **Redis**: Cache, message broker, session store
  - Port: 6379
  - Password required (see `.env`)

- **Celery Workers**: Async optimization task processing
  - Two worker types: `celery-worker` (general) and `celery-worker-depot` (depot-specific)

- **Monitoring Stack:**
  - **Prometheus**: Metrics scraping and alerting rules (port 9090)
  - **Grafana**: Dashboards and visualization (port 3002)
  - **AlertManager**: Alert routing and delivery (port 9093)
  - **postgres-exporter**: PostgreSQL metrics (port 9187)
  - **redis-exporter**: Redis metrics (port 9121)

- **Flower**: Celery monitoring UI (port 5555)

---

## 2. Health Checks

### 2.1 Quick System Health

```bash
# Check all service health in one command
docker-compose ps

# Expected output: all services should show "Up" (green)
```

### 2.2 Individual Service Health

**Backend NestJS:**
```bash
curl -s http://localhost:3001/api/v1 | head -50
# Should respond with 200 and API documentation
```

**Frontend Next.js:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Should respond with 200
```

**Optimizer FastAPI:**
```bash
curl -s http://localhost:8000/health | jq .
# Should respond with: {"status": "healthy"}
```

**PostgreSQL:**
```bash
docker-compose exec postgres pg_isready -U ${DB_USER} -d ${DB_NAME}
# Should respond: accepting connections
```

**Redis:**
```bash
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} ping
# Should respond: PONG
```

**Celery Workers:**
```bash
# Check worker status in Flower UI
curl -s http://localhost:5555/api/workers | jq .
```

### 2.3 Readiness for Deployments

A system is ready for deployment if:
- ✅ All services show "Up" in `docker-compose ps`
- ✅ Backend health check returns 200
- ✅ Frontend responds (200 or redirect to login)
- ✅ Optimizer `/health` responds with `healthy`
- ✅ PostgreSQL accepts connections
- ✅ Redis responds to PING
- ✅ Prometheus scrapes all targets (see section 4.1)
- ✅ No critical alerts are active in AlertManager

---

## 3. Structured Logging & Request Tracing

### 3.1 Accessing Logs

**Backend logs:**
```bash
docker-compose logs -f backend --tail=100
```

**Optimizer logs:**
```bash
docker-compose logs -f optimizer --tail=100
```

**Celery worker logs:**
```bash
docker-compose logs -f celery-worker --tail=100
```

**All services:**
```bash
docker-compose logs -f --tail=200
```

### 3.2 Structured Log Format

All backend requests are logged with the following structure:

```
[TIMESTAMP] [LEVEL] [MODULE] "METHOD /path HTTP/1.1" STATUS_CODE REQUEST_ID DURATION_MS
```

Example:
```
2026-05-22T15:30:45.123Z [INFO] [ScheduleController] "GET /api/v1/schedules?page=0&limit=10 HTTP/1.1" 200 req-uuid-1234 45ms
```

### 3.3 Tracing a Single Request by REQUEST_ID

All backend requests generate a `REQUEST_ID` (UUID) and propagate it via:
- `X-Request-ID` HTTP header
- Structured logs
- Sentry error reports
- Prometheus metrics labels

**To trace a request:**

1. **Find the REQUEST_ID in logs:**
   ```bash
   docker-compose logs backend | grep "specific-pattern" | grep -oE "req-[a-f0-9-]+"
   ```

2. **Grep for all logs with that REQUEST_ID:**
   ```bash
   docker-compose logs | grep "REQUEST_ID_VALUE"
   ```

3. **Check Sentry (if configured):**
   - Go to Sentry project > Issues
   - Search for the REQUEST_ID in the error details

4. **Check metrics in Prometheus (see section 4.2)**

### 3.4 Log Levels

- `DEBUG`: Development only, detailed request/response payloads
- `INFO`: Normal operations, successful requests, state changes
- `WARN`: Recoverable issues, retries, degraded conditions
- `ERROR`: Unhandled exceptions, 5xx responses
- `FATAL`: System-wide failures (unrecoverable)

**To filter logs by level:**
```bash
docker-compose logs backend 2>&1 | grep "ERROR\|FATAL"
```

### 3.5 Sensitive Data Handling

**Never log or expose:**
- Authorization tokens or JWTs
- Passwords or API keys
- PII (email, phone, ID numbers) outside specific audit tables
- Raw request/response bodies for authenticated endpoints

Logs are automatically sanitized by the backend's structured logging middleware.

---

## 4. Prometheus Metrics & Monitoring

### 4.1 Accessing Prometheus

**Web UI:**
```
http://localhost:9090
```

**Query Prometheus directly:**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq .
```

### 4.2 Key Metrics to Monitor

**Service Availability:**
```promql
# Check if a service is up (1 = up, 0 = down)
up{job="backend"}
up{job="optimizer"}
up{job="postgres"}
up{job="redis"}
```

**Request Latency:**
```promql
# P95 request latency (95th percentile)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

**Error Rate:**
```promql
# Percentage of 5xx errors in last 5 minutes
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])
```

**Database Connections:**
```promql
# Active PostgreSQL connections
pg_stat_activity_count

# Max allowed is 100; warn if > 80
```

**Redis Memory:**
```promql
# Redis memory usage
redis_memory_used_bytes / redis_memory_max_bytes
```

**Celery Queue Depth:**
```promql
# Number of pending tasks
celery_queue_length

# Warn if > 20 for > 10 minutes
```

### 4.3 Tracing a Request in Prometheus

Using the REQUEST_ID from logs:

```promql
# Find all requests with this ID
http_request_duration_seconds{request_id="req-uuid-1234"}

# Check status distribution
increase(http_requests_total{request_id="req-uuid-1234"}[5m])
```

### 4.4 Exporting Metrics for Analysis

```bash
# Export last 24h of data (JSON format)
curl -s 'http://localhost:9090/api/v1/query_range?query=up&start=UNIX_TIMESTAMP_START&end=UNIX_TIMESTAMP_END&step=300' | jq . > metrics.json
```

---

## 5. Grafana Dashboards

### 5.1 Accessing Grafana

**URL:**
```
http://localhost:3002
```

**Default credentials:**
- Username: `admin` (or from `GRAFANA_USER` env var)
- Password: Check `.env` or ask ops team

### 5.2 Available Dashboards

- **System Overview**: CPU, memory, disk usage across all services
- **OTIMIZ Backend**: Request rate, latency, errors, database connections
- **OTIMIZ Optimizer**: Optimization success rate, execution time, queue depth
- **Database (PostgreSQL)**: Connections, cache hit ratio, slow queries
- **Redis**: Memory usage, hit ratio, evictions
- **Celery Workers**: Task count, success/failure rates, worker availability

### 5.3 Creating Custom Dashboards

1. Click **"+" > Dashboard** in Grafana UI
2. Add panels by selecting Prometheus as data source
3. Use PromQL queries (see section 4.2)
4. Set appropriate alert thresholds

### 5.4 Alerting from Dashboards

Thresholds are pre-configured in AlertManager rules (see section 6).

---

## 6. Alert Management

### 6.1 Accessing AlertManager

**Web UI:**
```
http://localhost:9093
```

**Alert endpoints:**
```bash
# List all active alerts
curl -s http://localhost:9093/api/v1/alerts | jq '.data[] | {status, labels, annotations}'

# Silence an alert (suppress notifications for 4h)
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [
      {"name": "alertname", "value": "BackendDown", "isRegex": false}
    ],
    "duration": "4h",
    "createdBy": "ops-runbook"
  }'
```

### 6.2 Alert Rules

**Critical Alerts (page on-call):**
- `BackendDown`: Backend unreachable for > 1 minute
- `OptimizerDown`: Optimizer unreachable for > 1 minute
- `PostgresDown`: Database unreachable for > 1 minute
- `RedisDown`: Cache unreachable for > 1 minute

**Warning Alerts (email/Slack):**
- `BackendHighErrorRate`: 5xx rate > 2% for > 5 minutes
- `OptimizerHighErrorRate`: 5xx rate > 5% for > 5 minutes
- `OptimizerHighLatency`: P95 latency > 30s for > 5 minutes
- `PostgresHighConnections`: > 80 active connections for > 5 minutes
- `CeleryQueueDepth`: > 20 pending tasks for > 10 minutes
- `DiskSpaceLow`: < 15% free space
- `HighMemoryUsage`: > 90% memory utilization

### 6.3 Responding to Alerts

**Backend Down:**
1. Check service health: `docker-compose ps | grep backend`
2. Check logs: `docker-compose logs backend --tail=50`
3. Restart if needed: `docker-compose restart backend`
4. Verify: `curl http://localhost:3001/api/v1`

**Optimizer Down:**
1. Check service health: `docker-compose ps | grep optimizer`
2. Check logs: `docker-compose logs optimizer --tail=50`
3. Check Celery workers: `curl http://localhost:5555/api/workers | jq .`
4. Restart if needed: `docker-compose restart optimizer`

**Database Down:**
1. Check PostgreSQL: `docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} -c "SELECT 1"`
2. Check disk space: `docker-compose exec postgres df -h /var/lib/postgresql/data`
3. If corrupted, follow recovery procedures (section 9)

**Redis Down:**
1. Check Redis: `docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} ping`
2. Check disk space: `docker-compose exec redis df -h /data`
3. Restart if needed: `docker-compose restart redis`

---

## 7. Optimizer Diagnostics

### 7.1 Check Optimizer Status

```bash
# Check service health
curl -s http://localhost:8000/health | jq .

# Expected response:
# {"status": "healthy", "uptime_seconds": 12345}
```

### 7.2 Monitor Optimization Tasks

**Via Flower (Celery UI):**
```
http://localhost:5555
```

- View active tasks
- See worker status
- Inspect task details (inputs, outputs, runtime)
- Monitor task success/failure rates

**Via logs:**
```bash
docker-compose logs celery-worker | grep "optimizer"
docker-compose logs celery-worker-depot | grep "optimizer"
```

**Via Prometheus:**
```promql
# Optimization success rate
rate(optimizer_tasks_total{status="success"}[5m]) / rate(optimizer_tasks_total[5m])

# Average optimization time
avg(optimizer_task_duration_seconds)

# Current queue depth
celery_queue_length{queue="optimizer"}
```

### 7.3 Troubleshooting Optimizer Failures

**High error rate (> 5%):**
1. Check recent changes to optimization constraints
2. Verify input data validity in PostgreSQL
3. Check Celery worker logs for exceptions
4. Review optimizer parameters in configuration

**Slow optimizations (> 30s P95):**
1. Check if queue is backed up (`celery_queue_length > 20`)
2. Check worker CPU usage (may be underprovisioned)
3. Verify data volume isn't abnormally large
4. Consider scale strategy (add more workers, adjust concurrency)

**Task timeouts:**
1. Check soft/hard limits in `docker-compose.yml` (celery-worker service)
2. Increase timeout if legitimate (large problems take longer)
3. Monitor actual execution time in Flower

---

## 8. Safe Restart Procedures

### 8.1 Restart Strategy

**Never force-kill containers.** Always use graceful shutdown:

```bash
# Graceful restart of a service (waits for in-flight requests)
docker-compose restart SERVICE_NAME

# Graceful restart of all services
docker-compose restart

# Example: restart backend only
docker-compose restart backend
```

### 8.2 Zero-Downtime Restart (with load balancing)

If using a load balancer (recommended for production):

```bash
# 1. Remove service from load balancer
# (depends on your load balancer configuration)

# 2. Graceful shutdown (waits for in-flight requests to complete)
docker-compose restart BACKEND

# 3. Verify health check passes
curl http://localhost:3001/api/v1

# 4. Add service back to load balancer
```

### 8.3 Restart Order (if restarting multiple)

1. Optimizer (no dependencies on other app services)
2. Celery workers (depends on Redis and PostgreSQL)
3. Backend (depends on Optimizer, Celery, PostgreSQL, Redis)
4. Frontend (depends on Backend)

```bash
docker-compose restart optimizer celery-worker celery-worker-depot backend frontend
```

### 8.4 Emergency Stop & Cleanup

```bash
# Stop all services gracefully
docker-compose stop

# Full cleanup (removes containers, keeps data volumes)
docker-compose down

# Restart after cleanup
docker-compose up -d
```

---

## 9. Database Verification & Recovery

### 9.1 PostgreSQL Health Checks

```bash
# Check database size
docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} \
  -c "SELECT pg_size_pretty(pg_database_size(current_database()));"

# Check active connections
docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} \
  -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"

# Check table sizes
docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} \
  -c "SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"

# Check for missing indexes
docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} \
  -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema') AND tablename NOT LIKE 'pg_%' ORDER BY tablename;"
```

### 9.2 Redis Health Checks

```bash
# Check memory usage
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} \
  --stat

# Check key count by database
for db in {0..5}; do
  echo "DB $db: $(docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} -n $db DBSIZE | awk '{print $NF}')"
done

# Check for memory pressure (evictions)
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} \
  INFO stats | grep evicted
```

### 9.3 Database Backup Verification

A backup service (`pgbackup`) runs daily:

```bash
# Check latest backup
docker-compose exec pgbackup ls -lh /backups | tail -5

# Verify backup integrity (if possible)
# Note: full restore test is disruptive; only do in staging
docker-compose exec pgbackup pg_restore --version
```

### 9.4 PostgreSQL Recovery Procedures

**If PostgreSQL won't start:**

1. **Check disk space:**
   ```bash
   docker-compose exec postgres df -h /var/lib/postgresql/data
   ```
   If full, free space and restart.

2. **Check logs:**
   ```bash
   docker-compose logs postgres | tail -100
   ```
   Look for corruption or lock messages.

3. **Recover from WAL logs:**
   ```bash
   # This is complex; only attempt with DBA guidance
   docker-compose exec postgres pg_ctl recover
   ```

4. **Last resort: restore from backup:**
   - Shut down backend and optimizer
   - Restore latest backup (contact ops team)
   - Restart services

---

## 10. Common Incidents & Resolution

### 10.1 "BackendDown" Alert

**Symptom:** Backend service unreachable

**Diagnosis:**
```bash
curl -v http://localhost:3001/api/v1
docker-compose logs backend --tail=50
docker-compose ps | grep backend
```

**Resolution:**
1. Check logs for error messages (section 3)
2. Check resource limits (CPU, memory): `docker-compose stats backend`
3. Restart: `docker-compose restart backend`
4. If restart doesn't help, check PostgreSQL and Redis connectivity

### 10.2 "High Error Rate" Alert

**Symptom:** Many 5xx responses

**Diagnosis:**
```bash
# Find errors in logs
docker-compose logs backend 2>&1 | grep "ERROR\|FATAL"

# Check current error rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])' | jq .
```

**Resolution:**
1. Identify the error pattern (all endpoints or specific?)
2. Check recent code deployments
3. Check data integrity in database
4. Restart if needed

### 10.3 "Optimizer Queue Backed Up" Alert

**Symptom:** Celery queue has > 20 pending tasks for > 10 minutes

**Diagnosis:**
```bash
curl -s http://localhost:5555/api/workers | jq '.[] | {name, pool}'
docker-compose logs celery-worker --tail=50
```

**Resolution:**
1. Check if workers are healthy (Flower UI)
2. Check optimizer logs for failures
3. Add more workers if queue is too deep for normal load
4. Restart workers: `docker-compose restart celery-worker celery-worker-depot`

### 10.4 "Database Connection Limit Reached"

**Symptom:** Alert "PostgresHighConnections" or error "remaining connection slots reserved"

**Diagnosis:**
```bash
docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} \
  -c "SELECT pid, usename, application_name, state FROM pg_stat_activity;"
```

**Resolution:**
1. Identify idle connections (state = 'idle in transaction')
2. Kill idle connections (if safe):
   ```bash
   docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} \
     -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction' AND query_start < now() - interval '5 minutes';"
   ```
3. Increase max connections in PostgreSQL config (requires restart)
4. Check backend connection pool settings (see backend config)

### 10.5 "Redis Memory Limit Exceeded"

**Symptom:** Redis errors, high eviction rate

**Diagnosis:**
```bash
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} \
  INFO memory
```

**Resolution:**
1. Check what keys are consuming memory:
   ```bash
   docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} --bigkeys
   ```
2. Clear old session data (if applicable):
   ```bash
   docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} \
     FLUSHDB  # Clear entire DB 0 (DANGEROUS - clears all sessions)
   ```
3. Increase Redis memory limit in `docker-compose.yml` (maxmemory)
4. Review cache strategy (TTL, eviction policy)

---

## 11. Staging Post-Deployment Validation

After deploying to staging, run this checklist:

### 11.1 Service Health

- [ ] `docker-compose ps` shows all services "Up"
- [ ] Backend health check returns 200
- [ ] Optimizer health returns `healthy`
- [ ] PostgreSQL accepts connections
- [ ] Redis responds to PING

### 11.2 Functional Tests

- [ ] Frontend loads at http://localhost:3000
- [ ] Login works (with test account)
- [ ] Can create a schedule
- [ ] Can optimize a schedule
- [ ] Results display correctly

### 11.3 Monitoring

- [ ] Prometheus scrapes all 4 targets (backend, optimizer, postgres, redis)
- [ ] No gaps in Prometheus data (all targets up)
- [ ] Grafana dashboards load
- [ ] No critical alerts are active
- [ ] Error rate is normal (< 1% 5xx)

### 11.4 Observability

- [ ] Structured logs appear in backend logs
- [ ] REQUEST_ID is present in logs
- [ ] Sentry receives errors (if SENTRY_DSN is set)
- [ ] Prometheus metrics are being recorded

### 11.5 Data Integrity

- [ ] Database backup job completes
- [ ] No missing migrations
- [ ] Foreign key constraints are valid

### 11.6 Production-Readiness Check

Before promoting to production:

- [ ] All staging validation checks pass
- [ ] Load test results are acceptable (if applicable)
- [ ] Security scan shows no critical vulnerabilities
- [ ] Documentation is up-to-date
- [ ] Incident response team is trained
- [ ] Rollback procedure is tested

---

## 12. Escalation & Support

### 12.1 On-Call Rotation

Critical incidents (service down, data loss risk):
1. Page on-call engineer immediately
2. Follow incident severity guidelines
3. Document incident in post-mortem

### 12.2 Emergency Contacts

- Engineering Lead: (add contact)
- DevOps: (add contact)
- Database Admin: (add contact)

### 12.3 Useful Resources

- **Sentry Dashboard:** `https://sentry.io/organizations/...` (if configured)
- **Status Page:** Internal status page URL
- **Architecture Docs:** `docs/ARCHITECTURE.md`
- **Configuration Guide:** `docs/CONFIGURATION.md`

---

## 13. Appendix: Useful Commands

```bash
# Quick health check all services
docker-compose exec backend curl -s http://localhost:3001/api/v1 > /dev/null && echo "✅ Backend" || echo "❌ Backend"

# Tail all logs
docker-compose logs -f

# Export metrics to file
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq . > metrics_dump.json

# Generate database report
docker-compose exec postgres pg_dump -U ${DB_USER} -d ${DB_NAME} --schema-only > schema_backup.sql

# Check service resource usage
docker-compose stats

# Prune unused Docker resources
docker system prune -a --volumes

# Update and restart all services
docker-compose pull && docker-compose up -d
```

---

## 14. Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-05-22 | Engineering | Initial runbook creation with P1 observability features |

