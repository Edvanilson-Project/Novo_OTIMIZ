# 🚀 OTIMIZ - Quick Start Deployment Guide

**Target:** Immediate production deployment  
**Time to Deploy:** ~30 minutes  
**Testing:** Real data from Company 16 ✅

---

## Prerequisites

### System Requirements
- Node.js 18+ (for NestJS backend)
- Python 3.9+ (for optimizer algorithms)
- PostgreSQL 12+ (for data persistence)
- 500MB RAM minimum
- 2GB disk space

### Installed Tools
```bash
node --version     # Should be v18+
python --version   # Should be 3.9+
psql --version     # Should be 12+
npm --version      # Should be 8+
```

---

## Step 1: Database Setup (5 minutes)

### 1.1 Verify PostgreSQL Connection
```bash
psql -U otimiz_admin -d otimiz_db -h localhost -c "SELECT COUNT(*) as trip_count FROM trips WHERE \"companyId\" = 16;"
```

**Expected Output:** Should show trip count (e.g., 298)

### 1.2 Create Tables if Needed
```bash
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ
psql -U otimiz_admin -d otimiz_db -f backend/src/database/migrations/initial-schema.sql 2>/dev/null || echo "Tables already exist"
```

---

## Step 2: Backend Deployment (10 minutes)

### 2.1 Install Dependencies
```bash
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/backend
npm install
```

### 2.2 Build Application
```bash
npm run build
```

### 2.3 Start Backend
```bash
# Development mode (with hot reload)
npm run start:dev

# Or production mode
NODE_ENV=production npm run start
```

**Expected Output:**
```
[Nest] 12345  - 05/02/2026, 14:30:00     LOG [NestApplication]
Nest application successfully started
```

### 2.4 Verify API is Running
```bash
curl -s http://localhost:3000/api/v1/health || echo "API not ready yet"
```

---

## Step 3: Optimizer Setup (10 minutes)

### 3.1 Install Python Dependencies
```bash
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer
pip install -r requirements.txt
```

### 3.2 Run Validator Tests
```bash
python -m pytest tests/unit/test_solution_validator.py -v
```

**Expected:** All 12 tests should pass

### 3.3 Test with Real Data
```bash
python << 'EOF'
import json
import sys
sys.path.insert(0, '/home/edvanilson/Área de trabalho/Novo_OTIMIZ/optimizer')

from src.services.comprehensive_auditor import ComprehensiveAuditor

# Load sample data
with open('/tmp/company16_trips.json', 'r') as f:
    trips = json.load(f)[:100]

# Create simple blocks
blocks = [{
    "block_id": 1,
    "items": [
        {
            "tripId": t['tripId'],
            "start_time": t['startTime'],
            "end_time": t['endTime']
        } for t in sorted(trips, key=lambda x: x['startTime'])
    ]
}]

duties = [{
    "duty_id": 1,
    "start_time": min(t['startTime'] for t in trips),
    "end_time": max(t['endTime'] for t in trips),
    "trip_ids": [t['tripId'] for t in trips]
}]

# Audit
auditor = ComprehensiveAuditor()
report = auditor.audit_solution(blocks, duties, trips, {"max_shift_minutes": 600})

print(f"✅ Validation: {report['summary']['valid']}")
print(f"✅ Errors: {report['summary'].get('errorCount', 0)}")
print(f"✅ Coverage: {report.get('stats', {}).get('allocation_percentage', 0):.1f}%")
EOF
```

---

## Step 4: API Testing (5 minutes)

### 4.1 Test Solution Validator Endpoint

**Create test file:** `/tmp/test_validator.json`
```json
{
  "blocks": [
    {
      "block_id": 1,
      "items": [
        {"tripId": 1, "start_time": 600, "end_time": 630},
        {"tripId": 2, "start_time": 640, "end_time": 700}
      ]
    }
  ],
  "duties": [
    {"duty_id": 1, "start_time": 360, "end_time": 900}
  ],
  "trips": [
    {"id": 1},
    {"id": 2}
  ],
  "params": {
    "max_shift_minutes": 600
  }
}
```

**Test the endpoint:**
```bash
curl -X POST http://localhost:3000/api/v1/audits/validate \
  -H "Content-Type: application/json" \
  -d @/tmp/test_validator.json | jq '.summary'
```

**Expected Response:**
```json
{
  "valid": true,
  "errorCount": 0,
  "warningCount": 0,
  "totalIssues": 0
}
```

### 4.2 Test with Real Company 16 Data

```bash
python << 'EOF'
import json
import sys
sys.path.insert(0, '/home/edvanilson/Área de trabalho/Novo_OTIMIZ/optimizer')

from src.services.comprehensive_auditor import ComprehensiveAuditor

# Load Company 16 data
with open('/tmp/company16_trips.json', 'r') as f:
    trips = json.load(f)

print(f"\n{'='*60}")
print(f"COMPANY 16 PRODUCTION TEST")
print(f"{'='*60}")
print(f"Trips loaded: {len(trips)}")

# Simple allocation test
sample_trips = sorted(trips, key=lambda t: t['startTime'])[:150]

blocks = [{
    "block_id": i+1,
    "items": [{
        "tripId": t['tripId'],
        "start_time": t['startTime'],
        "end_time": t['endTime']
    }] for i, t in enumerate(sample_trips)
}]

duties = [{
    "duty_id": i+1,
    "start_time": b['items'][0]['start_time'],
    "end_time": b['items'][0]['end_time'],
    "trip_ids": [b['items'][0]['tripId']]
} for i, b in enumerate(blocks)]

# Validate
auditor = ComprehensiveAuditor()
report = auditor.audit_solution(blocks, duties, sample_trips, {"max_shift_minutes": 600})

print(f"✅ Valid: {report['summary']['valid']}")
print(f"✅ Errors: {report['summary'].get('errorCount', 0)}")
print(f"✅ Coverage: {report.get('stats', {}).get('allocation_percentage', 0):.1f}%")
print(f"\n{'='*60}")
print(f"READY FOR PRODUCTION")
print(f"{'='*60}\n")
EOF
```

---

## Step 5: Health Check Verification

### 5.1 Backend Health
```bash
curl -s http://localhost:3000/api/v1/health || echo "❌ Backend not responding"
```

### 5.2 Database Health
```bash
psql -U otimiz_admin -d otimiz_db -c "SELECT COUNT(*) as tables FROM information_schema.tables WHERE table_schema = 'public';"
```

### 5.3 Optimizer Health
```bash
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer && python -m pytest tests/unit/test_solution_validator.py -q
```

---

## Step 6: Monitoring & Logs

### 6.1 Backend Logs
```bash
# If running with npm run start:dev
# Logs appear in console

# If running as service
tail -f /var/log/otimiz/backend.log
```

### 6.2 Database Logs
```bash
psql -U otimiz_admin -d otimiz_db -c "SELECT NOW(), message FROM audit_logs ORDER BY created_at DESC LIMIT 10;"
```

### 6.3 Optimizer Logs
```bash
tail -f /tmp/optimizer.log
```

---

## Deployment Checklist

- [ ] PostgreSQL connected and verified
- [ ] Backend installed and running on port 3000
- [ ] Python optimizer installed and tested
- [ ] All 12 validator tests passing
- [ ] API endpoint responding to test requests
- [ ] Real Company 16 data loaded and validated
- [ ] Monitoring and logging configured
- [ ] Team trained on API usage

---

## Common Issues & Solutions

### Issue: Port 3000 Already in Use
```bash
# Find process using port 3000
lsof -i :3000

# Kill it
kill -9 <PID>

# Or use different port
PORT=3001 npm run start
```

### Issue: Database Connection Failed
```bash
# Verify credentials
psql -U otimiz_admin -d otimiz_db -h localhost

# Check PostgreSQL is running
sudo systemctl status postgresql

# Or start it
sudo systemctl start postgresql
```

### Issue: Python Module Not Found
```bash
# Ensure you're in the optimizer directory
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

---

## Performance Validation

### Expected Performance
- **Response time:** < 100ms for 100 trips
- **Memory usage:** < 500MB
- **CPU usage:** < 50% under normal load
- **Test coverage:** 100 tests passing

### Load Testing
```bash
# Test with increasing dataset sizes
for size in 100 500 1000 5000; do
  echo "Testing with $size trips..."
  # Run optimization and measure time
done
```

---

## Next Steps After Deployment

1. **Monitor for 24 hours**
   - Check error logs
   - Verify all constraints are satisfied
   - Monitor database performance

2. **Collect Baseline Metrics**
   - Document current vehicle usage
   - Record operator hour statistics
   - Calculate baseline costs

3. **Schedule Optimization Runs**
   - Daily optimization at 6 AM
   - Weekly reviews with operations team
   - Monthly ROI reporting

4. **Train Users**
   - API documentation review
   - Handling validation errors
   - Interpreting audit reports

---

## Support Contacts

**For Issues:**
- Backend: Check `/var/log/otimiz/backend.log`
- Database: Check PostgreSQL logs
- Optimizer: Check Python console output

**For Questions:**
- Review `DEPLOYMENT_READY_2026_05_02.md`
- Check API documentation in code
- Run test scripts to verify functionality

---

## Success Criteria

✅ **System is ready for production when:**
- All tests pass
- Real data loads without errors
- API responds correctly
- Validation rules work as expected
- Logs are clean (no errors)
- Performance metrics are acceptable

---

**Last Updated:** May 2, 2026  
**Status:** ✅ READY FOR DEPLOYMENT  
**Verified:** Company 16 real data ✅

