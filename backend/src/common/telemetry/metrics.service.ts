import { Injectable } from '@nestjs/common';

/**
 * Minimal Prometheus metrics using prom-client.
 * Tracks HTTP requests, duration, and status codes.
 * Optimization metrics can be added when optimization events are visible.
 */
@Injectable()
export class MetricsService {
  private static counter: Map<string, number> = new Map();
  private static histogram: Map<string, number[]> = new Map();

  private constructor() {}

  /**
   * Track an HTTP request.
   * @param method GET, POST, etc.
   * @param path /api/v1/some-endpoint
   * @param statusCode HTTP status
   * @param durationMs Request duration in milliseconds
   */
  static recordHttpRequest(
    method: string,
    path: string,
    statusCode: number,
    durationMs: number,
  ): void {
    // Count total requests
    const countKey = `http_requests_total:${method}:${statusCode}`;
    this.counter.set(countKey, (this.counter.get(countKey) ?? 0) + 1);

    // Record duration histogram (buckets: 10, 50, 100, 250, 500, 1000, 2500, 5000+ ms)
    const histKey = `http_request_duration_seconds:${method}`;
    if (!this.histogram.has(histKey)) {
      this.histogram.set(histKey, []);
    }
    this.histogram.get(histKey)!.push(durationMs / 1000); // convert to seconds
  }

  /**
   * Export metrics in Prometheus text format.
   * @returns Prometheus-format metrics string
   */
  static exportMetrics(): string {
    const lines: string[] = [];

    // HTTP request total
    lines.push(
      '# HELP http_requests_total Total HTTP requests',
    );
    lines.push(
      '# TYPE http_requests_total counter',
    );
    for (const [key, value] of this.counter.entries()) {
      const [, method, status] = key.split(':');
      lines.push(
        `http_requests_total{method="${method}",status="${status}"} ${value}`,
      );
    }

    // HTTP request duration (P50, P95, P99)
    lines.push(
      '# HELP http_request_duration_seconds HTTP request duration histogram',
    );
    lines.push(
      '# TYPE http_request_duration_seconds summary',
    );
    for (const [key, durations] of this.histogram.entries()) {
      const [, method] = key.split(':');
      if (durations.length > 0) {
        const sorted = durations.slice().sort((a, b) => a - b);
        const p50 = sorted[Math.floor(sorted.length * 0.5)];
        const p95 = sorted[Math.floor(sorted.length * 0.95)];
        const p99 = sorted[Math.floor(sorted.length * 0.99)];
        const sum = sorted.reduce((a, b) => a + b, 0);
        lines.push(
          `http_request_duration_seconds{method="${method}",quantile="0.5"} ${p50.toFixed(4)}`,
        );
        lines.push(
          `http_request_duration_seconds{method="${method}",quantile="0.95"} ${p95.toFixed(4)}`,
        );
        lines.push(
          `http_request_duration_seconds{method="${method}",quantile="0.99"} ${p99.toFixed(4)}`,
        );
        lines.push(
          `http_request_duration_seconds_sum{method="${method}"} ${sum.toFixed(4)}`,
        );
        lines.push(
          `http_request_duration_seconds_count{method="${method}"} ${durations.length}`,
        );
      }
    }

    return lines.join('\n');
  }

  /**
   * Reset metrics (for testing).
   */
  static reset(): void {
    this.counter.clear();
    this.histogram.clear();
  }
}
