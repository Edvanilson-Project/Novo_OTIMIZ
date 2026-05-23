import http from 'k6/http';
import { sleep, check, group } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001/api/v1';
const TEST_EMAIL = __ENV.TEST_EMAIL || 'admin@empresa.com';
const TEST_PASS = __ENV.TEST_PASS || 'admin123';

export const options = {
  stages: [
    { duration: '30s', target: 10 },  // S1: health smoke (10 VUs)
    { duration: '1m', target: 5 },    // S2: auth + profile (5 VUs)
    { duration: '1m', target: 5 },    // S3: schedule history (5 VUs)
    { duration: '30s', target: 1 },   // S4: optimize submit (1 VU)
    { duration: '2m', target: 3 },    // S5: status poll (3 VUs)
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000', 'p(99)<5000'],  // informational
    http_req_failed: ['rate<0.05'],                    // informational
  },
};

// Setup: login once per VU to get auth token
export function setup() {
  const loginPayload = JSON.stringify({
    email: TEST_EMAIL,
    password: TEST_PASS,
  });

  const loginParams = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const loginRes = http.post(`${BASE_URL}/auth/login`, loginPayload, loginParams);

  check(loginRes, {
    'login status 200': (r) => r.status === 200,
    'has access_token cookie': (r) => r.cookies && r.cookies.access_token && r.cookies.access_token.length > 0,
  });

  if (loginRes.status !== 200) {
    console.error('Setup login failed:', loginRes.status, loginRes.body);
    return null;
  }

  // Extract token for Bearer auth (optional, k6 manages cookies automatically)
  const token = loginRes.cookies.access_token && loginRes.cookies.access_token[0]
    ? loginRes.cookies.access_token[0].value
    : null;

  return { token };
}

export default function (data) {
  const authParams = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': data.token ? `Bearer ${data.token}` : undefined,
    },
    cookies: {},
  };

  // S1: Health check (all VUs, smoke)
  group('S1: Health Check', () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, {
      'health status 200': (r) => r.status === 200,
      'health is healthy': (r) => r.json('status') === 'ok',
    });
  });

  sleep(1);

  // S2: Auth Profile (subset of VUs)
  group('S2: Auth & Profile', () => {
    const profileRes = http.get(`${BASE_URL}/auth/profile`, authParams);
    check(profileRes, {
      'profile status 200': (r) => r.status === 200,
      'profile has user id': (r) => r.json('id') !== undefined,
    });
  });

  sleep(1);

  // S3: Schedule History (subset of VUs)
  group('S3: Schedule History', () => {
    const scheduleRes = http.get(`${BASE_URL}/operations/schedules`, authParams);
    check(scheduleRes, {
      'schedules status 200': (r) => r.status === 200,
      'schedules is array': (r) => Array.isArray(r.json()),
    });
  });

  sleep(1);

  // S4: Optimize Submit (single VU)
  group('S4: Optimize Submit', () => {
    const optimizePayload = JSON.stringify({
      scheduleId: 1,
      algorithm: 'vcsp_pulp',
    });

    const optimizeRes = http.post(
      `${BASE_URL}/operations/optimize`,
      optimizePayload,
      authParams,
    );

    check(optimizeRes, {
      'optimize status 200 or 202': (r) => r.status === 200 || r.status === 202,
      'optimize has taskId': (r) => r.json('taskId') !== undefined,
    });
  });

  sleep(2); // Brief pause before polling

  // S5: Status Poll (subset of VUs)
  group('S5: Status Poll', () => {
    const statusRes = http.get(`${BASE_URL}/operations/optimize/status`, authParams);
    check(statusRes, {
      'status endpoint 200': (r) => r.status === 200,
    });
  });

  sleep(2);
}
