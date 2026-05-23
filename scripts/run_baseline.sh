#!/usr/bin/env bash
# Load testing baseline runner
# Prerequisites: k6 installed, backend running on 3001
# Usage: ./scripts/run_baseline.sh

set -e

BASE_URL="${BASE_URL:-http://localhost:3001/api/v1}"
TEST_EMAIL="${TEST_EMAIL:-admin@empresa.com}"
TEST_PASS="${TEST_PASS:-admin123}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="docs/performance/results"

echo "🔄 Starting baseline load test suite..."
echo "Timestamp: $TIMESTAMP"
echo "Base URL: $BASE_URL"
echo ""

# Ensure results directory
mkdir -p "$RESULTS_DIR"

# Step 1: Generate datasets
echo "📊 Step 1: Generating trip datasets..."
python3 tests/load/datasets/gen_trips.py --output-dir tests/load/datasets/
echo ""

# Verify datasets exist
for SIZE in 1k 5k 10k; do
  FILE="tests/load/datasets/trips_${SIZE}.csv"
  if [ -f "$FILE" ]; then
    COUNT=$(wc -l < "$FILE")
    echo "✅ $FILE: $COUNT lines"
  else
    echo "❌ $FILE: NOT FOUND"
    exit 1
  fi
done
echo ""

# Step 2: Baseline API smoke test + auth + schedule + optimize flow
echo "🚀 Step 2: Running baseline k6 test (all scenarios)..."
k6 run tests/load/baseline.k6.js \
  -e BASE_URL="$BASE_URL" \
  -e TEST_EMAIL="$TEST_EMAIL" \
  -e TEST_PASS="$TEST_PASS" \
  --out json="$RESULTS_DIR/baseline_${TIMESTAMP}.json" \
  2>&1 | tee "$RESULTS_DIR/baseline_${TIMESTAMP}.log"

echo ""
echo "✅ Baseline test completed. Results: $RESULTS_DIR/baseline_${TIMESTAMP}.json"
echo ""

# Step 3: Upload tests per dataset size
echo "📤 Step 3: Running dataset upload tests..."
for SIZE in 1k 5k 10k; do
  echo "  → Testing upload_${SIZE}.csv..."
  k6 run tests/load/upload_import.k6.js \
    -e BASE_URL="$BASE_URL" \
    -e TEST_EMAIL="$TEST_EMAIL" \
    -e TEST_PASS="$TEST_PASS" \
    -e DATASET="tests/load/datasets/trips_${SIZE}.csv" \
    -e DATASET_SIZE="$SIZE" \
    --out json="$RESULTS_DIR/upload_${SIZE}_${TIMESTAMP}.json" \
    2>&1 | tee "$RESULTS_DIR/upload_${SIZE}_${TIMESTAMP}.log"
  echo ""
done

echo "✅ All tests completed!"
echo ""
echo "📁 Results in: $RESULTS_DIR"
echo "📄 Next: Review metrics and populate docs/performance/baseline-${TIMESTAMP}.md"
echo ""
echo "Sample analysis commands:"
echo "  cat $RESULTS_DIR/baseline_${TIMESTAMP}.json | jq '.metrics'"
echo "  grep -h 'http_req_duration' $RESULTS_DIR/*.json | jq '.values.p95'"
