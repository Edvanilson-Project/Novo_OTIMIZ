#!/usr/bin/env bash
# Testes de integração do stack Docker rodando
# Uso: bash tests/integration_stack_test.sh
set -euo pipefail

BACKEND="http://localhost:3001/api/v1"
OPTIMIZER="http://localhost:8000"
PASS=0; FAIL=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

check_http() {
  local label="$1"; local url="$2"; local expected="$3"
  local code; code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
  if [ "$code" = "$expected" ]; then ok "$label (HTTP $code)"; else fail "$label (esperado $expected, got $code)"; fi
}

check_json_field() {
  local label="$1"; local url="$2"; local field="$3"
  local val; val=$(curl -s "$url" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field','MISSING'))" 2>/dev/null || echo "ERROR")
  if [ "$val" != "MISSING" ] && [ "$val" != "ERROR" ] && [ "$val" != "None" ]; then
    ok "$label ($field=$val)"
  else
    fail "$label ($field ausente ou inválido: $val)"
  fi
}

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  OTIMIZ — Testes de Integração do Stack"
echo "═══════════════════════════════════════════════════════"

# ─── 1. Infra ───────────────────────────────────────────────
echo ""
echo "1. Infraestrutura"
redis_ok=$(docker exec otimiz-v2-redis redis-cli -p 6379 ping 2>/dev/null || echo "FAIL")
[ "$redis_ok" = "PONG" ] && ok "Redis responde PONG" || fail "Redis não responde (got: $redis_ok)"

pg_ok=$(docker exec otimiz-v2-postgres pg_isready -U otimiz_admin -d otimiz_db 2>/dev/null | grep -c "accepting" || echo "0")
[ "$pg_ok" -gt 0 ] && ok "PostgreSQL aceitando conexões" || fail "PostgreSQL não responde"

# ─── 2. Optimizer API ───────────────────────────────────────
echo ""
echo "2. Optimizer API (localhost:8000)"
check_http "Optimizer health acessível"   "$OPTIMIZER/health/"  "200"
check_json_field "Versão presente"        "$OPTIMIZER/health/"  "version"

# Testar Redis interno do optimizer
redis_status=$(curl -s "$OPTIMIZER/health/" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('redis_status','?'))" 2>/dev/null || echo "ERROR")
[ "$redis_status" = "ok" ] && ok "Optimizer conectado ao Redis (redis_status=ok)" || fail "Optimizer NÃO conectado ao Redis (redis_status=$redis_status)"

celery_status=$(curl -s "$OPTIMIZER/health/" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('celery_status','?'))" 2>/dev/null || echo "ERROR")
[ "$celery_status" = "ok" ] && ok "Optimizer com Celery funcional (celery_status=ok)" || fail "Optimizer sem Celery (celery_status=$celery_status)"

# ─── 3. Backend API ─────────────────────────────────────────
echo ""
echo "3. Backend API (localhost:3001)"
check_http "Backend raiz acessível"       "$BACKEND"            "200"
check_http "Health endpoint"              "$BACKEND/health"     "200"

# ─── 4. Auth Flow ───────────────────────────────────────────
echo ""
echo "4. Autenticação"
LOGIN=$(curl -s -X POST "$BACKEND/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@otimiz.com","password":"admin123"}' 2>/dev/null || echo "{}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || echo "")
[ -n "$TOKEN" ] && ok "Login retorna access_token" || fail "Login falhou (response: $LOGIN)"

if [ -n "$TOKEN" ]; then
  # ─── 5. Endpoints autenticados ────────────────────────────
  echo ""
  echo "5. Endpoints autenticados"

  AUTH="-H \"Authorization: Bearer $TOKEN\""
  for ep in companies vehicles; do
    code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BACKEND/$ep" 2>/dev/null || echo "000")
    [ "$code" = "200" ] && ok "GET /$ep (HTTP $code)" || fail "GET /$ep falhou (HTTP $code)"
  done
  for ep in operations/latest-schedule operations/drivers operations/trips; do
    code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BACKEND/$ep" 2>/dev/null || echo "000")
    [ "$code" = "200" ] && ok "GET /$ep (HTTP $code)" || fail "GET /$ep falhou (HTTP $code)"
  done

  # Testar terminals/depots
  DEPOTS_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$BACKEND/terminals/depots" 2>/dev/null || echo "000")
  [ "$DEPOTS_CODE" = "200" ] && ok "GET /terminals/depots (HTTP 200)" || \
    fail "GET /terminals/depots falhou (HTTP $DEPOTS_CODE)"

  # ─── 6. Otimização end-to-end ─────────────────────────────
  echo ""
  echo "6. Otimização E2E"

  COMPANY_ID=$(curl -s -H "Authorization: Bearer $TOKEN" "$BACKEND/companies" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0].get('id','') if isinstance(d,list) and d else '')" 2>/dev/null || echo "")
  [ -n "$COMPANY_ID" ] && ok "Company ID recuperado ($COMPANY_ID)" || fail "Não conseguiu recuperar Company ID"

  LATEST=$(curl -s -H "Authorization: Bearer $TOKEN" "$BACKEND/operations/latest-schedule" 2>/dev/null || echo "{}")
  LATEST_ID=$(echo "$LATEST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || echo "")
  [ -n "$LATEST_ID" ] && ok "Latest schedule ID recuperado ($LATEST_ID)" || fail "Nenhum schedule disponível"

  OPT_OUT=$(curl -s -w "\n%{http_code}" -X POST "$BACKEND/operations/optimize" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"algorithm":"greedy"}' 2>/dev/null || echo "{}\n000")
  HTTP_OPT=$(echo "$OPT_OUT" | tail -1)
  OPT_BODY=$(echo "$OPT_OUT" | head -1)
  OPT_TASK=$(echo "$OPT_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('taskId',d.get('task_id',d.get('message','?'))))" 2>/dev/null || echo "?")
  echo "  → Optimization response (HTTP $HTTP_OPT): $OPT_TASK"
  # 201=novo job, 409=job já em andamento (ambos são comportamento correto)
  [ "$HTTP_OPT" = "201" ] || [ "$HTTP_OPT" = "409" ] && ok "POST /operations/optimize aceito (HTTP $HTTP_OPT)" || fail "POST /operations/optimize falhou (HTTP $HTTP_OPT)"
fi

# ─── 7. Resumo ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
TOTAL=$((PASS+FAIL))
echo "  Resultado: $PASS/$TOTAL passaram | $FAIL falhos"
echo "═══════════════════════════════════════════════════════"
echo ""
[ $FAIL -eq 0 ] && exit 0 || exit 1
