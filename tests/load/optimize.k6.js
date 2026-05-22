/**
 * k6 load test — OTIMIZ Optimization endpoint
 *
 * Run:
 *   k6 run tests/load/optimize.k6.js -e BASE_URL=http://localhost:3001/api/v1
 *
 * Targets: P95 < 30s for job submission, error rate < 2%, 5 concurrent VUs.
 * The optimize endpoint is CPU-heavy — use low VU counts intentionally.
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const submitLatency = new Trend('submit_latency', true);
const pollLatency = new Trend('poll_latency', true);

export const options = {
  stages: [
    { duration: '30s', target: 3 },
    { duration: '3m', target: 5 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    submit_latency: ['p(95)<5000'],   // submission < 5s (async queuing)
    poll_latency: ['p(95)<500'],       // status poll < 500ms
    errors: ['rate<0.02'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001/api/v1';
const TEST_EMAIL = __ENV.TEST_EMAIL || 'loadtest@example.com';
const TEST_PASS = __ENV.TEST_PASS || 'LoadTest123!';

const SMALL_PAYLOAD = {
  lineIds: [1],
  date: '2026-06-01',
  algorithm: 'greedy',
  parameters: {
    max_vehicle_shift_minutes: 480,
    depot_id: 1,
  },
};

function login() {
  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: TEST_EMAIL, password: TEST_PASS }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  if (res.status !== 200) return null;
  return res.json('access_token');
}

export default function () {
  const token = login();
  if (!token) {
    errorRate.add(1);
    sleep(5);
    return;
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // ── Submit optimization job ───────────────────────────────────────────────
  const submitRes = http.post(
    `${BASE_URL}/operations/optimize`,
    JSON.stringify(SMALL_PAYLOAD),
    { headers },
  );

  submitLatency.add(submitRes.timings.duration);

  const submitted = check(submitRes, {
    'submit accepted (202/200)': (r) => r.status === 200 || r.status === 202,
  });
  errorRate.add(!submitted);

  if (!submitted) {
    sleep(5);
    return;
  }

  const operationId = submitRes.json('operationId') || submitRes.json('id');
  if (!operationId) {
    sleep(5);
    return;
  }

  // ── Poll status (up to 60s) ───────────────────────────────────────────────
  let done = false;
  for (let i = 0; i < 30 && !done; i++) {
    sleep(2);

    const pollRes = http.get(`${BASE_URL}/operations/${operationId}/status`, { headers });
    pollLatency.add(pollRes.timings.duration);

    check(pollRes, { 'poll 200': (r) => r.status === 200 });

    const status = pollRes.json('status');
    done = status === 'completed' || status === 'failed';
  }

  sleep(3);
}
