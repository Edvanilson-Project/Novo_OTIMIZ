/**
 * k6 load test — OTIMIZ API (auth + read endpoints)
 *
 * Run:
 *   k6 run tests/load/api.k6.js -e BASE_URL=http://localhost:3001/api/v1
 *
 * Targets: P95 < 200ms, error rate < 1%, sustained 50 VUs for 2 minutes.
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const loginLatency = new Trend('login_latency', true);
const profileLatency = new Trend('profile_latency', true);

export const options = {
  stages: [
    { duration: '30s', target: 20 },   // ramp up
    { duration: '2m', target: 50 },    // sustained load
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'],
    errors: ['rate<0.01'],
    login_latency: ['p(95)<300'],
    profile_latency: ['p(95)<150'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001/api/v1';
const TEST_EMAIL = __ENV.TEST_EMAIL || 'loadtest@example.com';
const TEST_PASS = __ENV.TEST_PASS || 'LoadTest123!';

export default function () {
  // ── Login ──────────────────────────────────────────────────────────────────
  const loginRes = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: TEST_EMAIL, password: TEST_PASS }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  loginLatency.add(loginRes.timings.duration);

  const loginOk = check(loginRes, {
    'login 200': (r) => r.status === 200,
    'has access_token': (r) => !!r.json('access_token'),
  });

  errorRate.add(!loginOk);

  if (!loginOk) {
    sleep(1);
    return;
  }

  const token = loginRes.json('access_token');
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  sleep(0.5);

  // ── GET /users/profile ────────────────────────────────────────────────────
  const profileRes = http.get(`${BASE_URL}/users/profile`, { headers });
  profileLatency.add(profileRes.timings.duration);
  const profileOk = check(profileRes, { 'profile 200': (r) => r.status === 200 });
  errorRate.add(!profileOk);

  sleep(0.5);

  // ── GET /operations/history ────────────────────────────────────────────────
  const historyRes = http.get(`${BASE_URL}/operations/history?limit=10`, { headers });
  check(historyRes, { 'history 200': (r) => r.status === 200 });
  errorRate.add(historyRes.status !== 200);

  sleep(1);

  // ── POST /auth/refresh ────────────────────────────────────────────────────
  const refreshCookie = loginRes.cookies['refresh_token'];
  if (refreshCookie && refreshCookie.length > 0) {
    const refreshRes = http.post(`${BASE_URL}/auth/refresh`, null, {
      headers: { Cookie: `refresh_token=${refreshCookie[0].value}` },
    });
    check(refreshRes, { 'refresh 200': (r) => r.status === 200 });
    errorRate.add(refreshRes.status !== 200);
  }

  sleep(1);
}
