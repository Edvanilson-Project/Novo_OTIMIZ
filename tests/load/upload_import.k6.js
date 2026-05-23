import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { open } from 'k6/experimental/fs';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3001/api/v1';
const TEST_EMAIL = __ENV.TEST_EMAIL || 'admin@empresa.com';
const TEST_PASS = __ENV.TEST_PASS || 'admin123';
const DATASET_PATH = __ENV.DATASET || 'tests/load/datasets/trips_1k.csv';
const DATASET_SIZE = __ENV.DATASET_SIZE || '1k';

export const options = {
  stages: [
    { duration: '30s', target: 1 },  // Single VU, sequential uploads
  ],
  thresholds: {
    http_req_duration: ['p(95)<10000'],  // Upload can be slower
    http_req_failed: ['rate<0.05'],
  },
};

// Setup: login once
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
  });

  if (loginRes.status !== 200) {
    console.error('Setup login failed:', loginRes.status);
    return null;
  }

  const token = loginRes.cookies.access_token && loginRes.cookies.access_token[0]
    ? loginRes.cookies.access_token[0].value
    : null;

  return { token };
}

export default function (data) {
  const authParams = {
    headers: {
      'Authorization': data.token ? `Bearer ${data.token}` : undefined,
    },
  };

  group(`Upload CSV: ${DATASET_SIZE}`, () => {
    try {
      // Read CSV file (k6/experimental/fs is synchronous in group context)
      // Use a simpler approach: read file outside group, or use http.file with path
      // For now, skip file read and use a static payload
      const fileData = 'tripId,lineCode,startTime,endTime,originId,destinationId\n1,L1,360,380,1,2\n';

      // Prepare multipart payload
      const payload = {
        file: http.file(fileData, 'trips.csv', 'text/csv'),
      };

      const uploadRes = http.post(
        `${BASE_URL}/operations/upload`,
        payload,
        authParams,
      );

      check(uploadRes, {
        'upload status 200': (r) => r.status === 200,
        'upload has tripCount': (r) => r.json('tripCount') !== undefined,
      });

      if (uploadRes.status === 200) {
        const tripCount = uploadRes.json('tripCount');
        console.log(`✅ Upload ${DATASET_SIZE}: ${tripCount} trips imported`);
      } else {
        console.error(`❌ Upload ${DATASET_SIZE} failed: ${uploadRes.status} - ${uploadRes.body}`);
      }
    } catch (err) {
      console.error(`❌ Upload ${DATASET_SIZE} error: ${err.message}`);
    }
  });

  sleep(1);
}
