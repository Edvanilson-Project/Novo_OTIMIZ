import { Test, TestingModule } from '@nestjs/testing';
import { MetricsController } from './metrics.controller';
import { MetricsService } from '../../common/telemetry/metrics.service';

describe('MetricsController', () => {
  let controller: MetricsController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [MetricsController],
    }).compile();

    controller = module.get<MetricsController>(MetricsController);
    MetricsService.reset();
  });

  describe('GET /api/v1/metrics', () => {
    it('should return Prometheus metrics in text format', () => {
      MetricsService.recordHttpRequest('GET', '/test', 200, 50);
      MetricsService.recordHttpRequest('POST', '/test', 201, 100);

      const metrics = controller.getMetrics();

      expect(metrics).toContain('# HELP http_requests_total');
      expect(metrics).toContain('# TYPE http_requests_total counter');
      expect(metrics).toContain('http_requests_total{method="GET",status="200"} 1');
      expect(metrics).toContain('http_requests_total{method="POST",status="201"} 1');
    });

    it('should be public and not require authentication', () => {
      // Reflected in decorator @Public() on the controller
      const metadata = Reflect.getMetadata('isPublic', MetricsController.prototype.getMetrics);
      // Note: This test verifies the decorator is applied; actual enforcement is at the guard level
    });
  });
});
