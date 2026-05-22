import { MetricsService } from './metrics.service';

describe('MetricsService', () => {
  beforeEach(() => {
    MetricsService.reset();
  });

  describe('recordHttpRequest', () => {
    it('should track HTTP request counters', () => {
      MetricsService.recordHttpRequest('GET', '/api/v1/users', 200, 50);
      MetricsService.recordHttpRequest('GET', '/api/v1/users', 200, 60);
      MetricsService.recordHttpRequest('POST', '/api/v1/users', 201, 100);
      MetricsService.recordHttpRequest('POST', '/api/v1/users', 500, 200);

      const metrics = MetricsService.exportMetrics();
      expect(metrics).toContain('http_requests_total{method="GET",status="200"} 2');
      expect(metrics).toContain('http_requests_total{method="POST",status="201"} 1');
      expect(metrics).toContain('http_requests_total{method="POST",status="500"} 1');
    });

    it('should track HTTP request duration histograms', () => {
      MetricsService.recordHttpRequest('GET', '/api/v1/users', 200, 100); // 0.1s
      MetricsService.recordHttpRequest('GET', '/api/v1/users', 200, 200); // 0.2s

      const metrics = MetricsService.exportMetrics();
      expect(metrics).toContain('http_request_duration_seconds{method="GET",quantile="0.5"}');
      expect(metrics).toContain('http_request_duration_seconds{method="GET",quantile="0.95"}');
      expect(metrics).toContain('http_request_duration_seconds_sum{method="GET"}');
      expect(metrics).toContain('http_request_duration_seconds_count{method="GET"} 2');
    });

    it('should calculate percentiles correctly', () => {
      // Create 100 requests with durations 10ms, 20ms, ..., 1000ms
      for (let i = 10; i <= 1000; i += 10) {
        MetricsService.recordHttpRequest('GET', '/test', 200, i);
      }

      const metrics = MetricsService.exportMetrics();
      const lines = metrics.split('\n');

      // P50 should be around 505ms
      const p50Line = lines.find((l) => l.includes('quantile="0.5"') && l.includes('method="GET"'));
      expect(p50Line).toBeDefined();
      const p50Value = parseFloat(p50Line!.split(' ')[1]);
      expect(p50Value).toBeGreaterThan(0.5);
      expect(p50Value).toBeLessThan(0.6);

      // P95 should be around 950ms
      const p95Line = lines.find((l) => l.includes('quantile="0.95"') && l.includes('method="GET"'));
      expect(p95Line).toBeDefined();
      const p95Value = parseFloat(p95Line!.split(' ')[1]);
      expect(p95Value).toBeGreaterThan(0.9);
      expect(p95Value).toBeLessThan(1.0);
    });
  });

  describe('exportMetrics', () => {
    it('should return Prometheus text format', () => {
      MetricsService.recordHttpRequest('GET', '/api/v1/test', 200, 50);

      const metrics = MetricsService.exportMetrics();
      expect(metrics).toContain('# HELP http_requests_total');
      expect(metrics).toContain('# TYPE http_requests_total counter');
      expect(metrics).toContain('# HELP http_request_duration_seconds');
      expect(metrics).toContain('# TYPE http_request_duration_seconds summary');
    });

    it('should return empty metrics when nothing recorded', () => {
      const metrics = MetricsService.exportMetrics();
      expect(metrics).toContain('# HELP http_requests_total');
      expect(metrics).not.toContain('{method=');
    });

    it('should include method and status labels', () => {
      MetricsService.recordHttpRequest('GET', '/test', 200, 50);
      MetricsService.recordHttpRequest('POST', '/test', 201, 100);
      MetricsService.recordHttpRequest('DELETE', '/test', 500, 200);

      const metrics = MetricsService.exportMetrics();
      expect(metrics).toContain('method="GET"');
      expect(metrics).toContain('method="POST"');
      expect(metrics).toContain('method="DELETE"');
      expect(metrics).toContain('status="200"');
      expect(metrics).toContain('status="201"');
      expect(metrics).toContain('status="500"');
    });
  });

  describe('reset', () => {
    it('should clear all metrics', () => {
      MetricsService.recordHttpRequest('GET', '/test', 200, 50);
      let metrics = MetricsService.exportMetrics();
      expect(metrics).toContain('http_requests_total');

      MetricsService.reset();
      metrics = MetricsService.exportMetrics();
      expect(metrics).not.toContain('method=');
    });
  });
});
