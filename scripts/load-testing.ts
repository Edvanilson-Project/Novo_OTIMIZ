import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';

interface LoadTestConfig {
  baseUrl: string;
  concurrency: number;
  duration: number; // seconds
  rampUp: number; // seconds
  endpoints: Array<{
    name: string;
    method: 'GET' | 'POST';
    path: string;
    body?: any;
    weight: number; // probability weight
  }>;
}

interface TestResult {
  endpoint: string;
  totalRequests: number;
  successfulRequests: number;
  failedRequests: number;
  averageResponseTime: number;
  minResponseTime: number;
  maxResponseTime: number;
  p95ResponseTime: number;
  p99ResponseTime: number;
  requestsPerSecond: number;
  errorRate: number;
}

class LoadTestRunner {
  private httpService: HttpService;
  private results: Map<string, number[]> = new Map();
  private errors: Map<string, number> = new Map();
  private startTime: number = 0;
  private totalRequests: number = 0;

  constructor(private config: LoadTestConfig) {
    this.httpService = new HttpService();
  }

  async run(): Promise<TestResult[]> {
    console.log('Starting load test...');
    this.startTime = Date.now();

    // Initialize result maps
    this.config.endpoints.forEach((ep) => {
      this.results.set(ep.name, []);
      this.errors.set(ep.name, 0);
    });

    // Ramp up phase
    await this.rampUp();

    // Sustained phase
    await this.sustained();

    // Generate results
    return this.generateResults();
  }

  private async rampUp(): Promise<void> {
    const rampUpDuration = this.config.rampUp * 1000;
    const startConcurrency = 1;
    const targetConcurrency = this.config.concurrency;
    const step = (targetConcurrency - startConcurrency) / (this.config.rampUp / 1);

    let currentConcurrency = startConcurrency;
    const rampUpStart = Date.now();

    while (Date.now() - rampUpStart < rampUpDuration) {
      currentConcurrency += step;
      const promises = [];

      for (let i = 0; i < Math.floor(currentConcurrency); i++) {
        promises.push(this.executeRandomRequest());
      }

      await Promise.allSettled(promises);
    }

    console.log('Ramp up complete');
  }

  private async sustained(): Promise<void> {
    const sustainedDuration = this.config.duration * 1000;
    const sustainStart = Date.now();

    const promises = [];

    while (Date.now() - sustainStart < sustainedDuration) {
      for (let i = 0; i < this.config.concurrency; i++) {
        promises.push(this.executeRandomRequest());
      }

      await Promise.allSettled(promises);
    }

    console.log('Sustained phase complete');
  }

  private async executeRandomRequest(): Promise<void> {
    const endpoint = this.selectEndpoint();
    const startTime = Date.now();

    try {
      const url = `${this.config.baseUrl}${endpoint.path}`;

      let response;
      if (endpoint.method === 'GET') {
        response = await firstValueFrom(this.httpService.get(url));
      } else {
        response = await firstValueFrom(this.httpService.post(url, endpoint.body));
      }

      const duration = Date.now() - startTime;
      this.recordResult(endpoint.name, duration);
    } catch (error) {
      this.recordError(endpoint.name);
    }

    this.totalRequests++;
  }

  private selectEndpoint() {
    const totalWeight = this.config.endpoints.reduce((sum, ep) => sum + ep.weight, 0);
    let random = Math.random() * totalWeight;

    for (const endpoint of this.config.endpoints) {
      random -= endpoint.weight;
      if (random <= 0) {
        return endpoint;
      }
    }

    return this.config.endpoints[0];
  }

  private recordResult(endpoint: string, duration: number): void {
    const times = this.results.get(endpoint) || [];
    times.push(duration);
    this.results.set(endpoint, times);
  }

  private recordError(endpoint: string): void {
    this.errors.set(endpoint, (this.errors.get(endpoint) || 0) + 1);
  }

  private generateResults(): TestResult[] {
    const totalDuration = (Date.now() - this.startTime) / 1000;

    return this.config.endpoints.map((endpoint) => {
      const times = this.results.get(endpoint.name) || [];
      const errorCount = this.errors.get(endpoint.name) || 0;
      const totalCount = times.length + errorCount;

      const sorted = times.sort((a, b) => a - b);
      const p95Index = Math.floor(sorted.length * 0.95);
      const p99Index = Math.floor(sorted.length * 0.99);

      return {
        endpoint: endpoint.name,
        totalRequests: totalCount,
        successfulRequests: times.length,
        failedRequests: errorCount,
        averageResponseTime: times.length > 0 ? Math.round(times.reduce((a, b) => a + b) / times.length) : 0,
        minResponseTime: times.length > 0 ? sorted[0] : 0,
        maxResponseTime: times.length > 0 ? sorted[sorted.length - 1] : 0,
        p95ResponseTime: sorted.length > 0 ? sorted[p95Index] : 0,
        p99ResponseTime: sorted.length > 0 ? sorted[p99Index] : 0,
        requestsPerSecond: Math.round((totalCount / totalDuration) * 100) / 100,
        errorRate: totalCount > 0 ? Math.round((errorCount / totalCount) * 10000) / 100 : 0,
      };
    });
  }
}

async function runLoadTests() {
  const config: LoadTestConfig = {
    baseUrl: 'http://localhost:3000',
    concurrency: 50,
    duration: 60, // 1 minute
    rampUp: 10, // 10 seconds
    endpoints: [
      {
        name: 'scenario_generation',
        method: 'POST',
        path: '/api/operations/optimization-advanced/scenarios/1',
        weight: 30,
      },
      {
        name: 'scenario_comparison',
        method: 'POST',
        path: '/api/operations/optimization-advanced/scenarios/1/compare',
        body: { scenario1Id: 'current', scenario2Id: 'cost-optimized' },
        weight: 20,
      },
      {
        name: 'what_if_simulation',
        method: 'POST',
        path: '/api/operations/optimization-advanced/whatif/vehicle-type-change',
        body: {
          originalCost: 50000,
          fromTypeId: 1,
          toTypeId: 2,
          fromTypeCost: 800,
          toTypeCost: 1200,
          tripCount: 5,
        },
        weight: 25,
      },
      {
        name: 'report_generation',
        method: 'POST',
        path: '/api/operations/reporting/generate/1',
        weight: 15,
      },
      {
        name: 'historical_data',
        method: 'GET',
        path: '/api/operations/reporting/historical/1?days=30',
        weight: 10,
      },
    ],
  };

  const runner = new LoadTestRunner(config);

  try {
    const results = await runner.run();

    console.log('\n=== Load Test Results ===\n');

    results.forEach((result) => {
      console.log(`Endpoint: ${result.endpoint}`);
      console.log(`  Total Requests: ${result.totalRequests}`);
      console.log(`  Successful: ${result.successfulRequests}`);
      console.log(`  Failed: ${result.failedRequests}`);
      console.log(`  Error Rate: ${result.errorRate}%`);
      console.log(`  RPS: ${result.requestsPerSecond}`);
      console.log(`  Response Times (ms):`);
      console.log(`    Average: ${result.averageResponseTime}`);
      console.log(`    Min: ${result.minResponseTime}`);
      console.log(`    Max: ${result.maxResponseTime}`);
      console.log(`    P95: ${result.p95ResponseTime}`);
      console.log(`    P99: ${result.p99ResponseTime}`);
      console.log();
    });

    // Check against targets
    const violations = results.filter((r) => r.averageResponseTime > 5000);
    if (violations.length > 0) {
      console.log('⚠️  Performance targets exceeded:');
      violations.forEach((v) => {
        console.log(`  ${v.endpoint}: ${v.averageResponseTime}ms (target: 5000ms)`);
      });
    } else {
      console.log('✅ All endpoints within performance targets (<5s)');
    }
  } catch (error) {
    console.error('Load test failed:', error);
  }
}

// Run the load test
runLoadTests();
