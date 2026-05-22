import { Controller, Get } from '@nestjs/common';
import { Public } from '../../common/decorators/roles.decorator';
import { SkipThrottle } from '@nestjs/throttler';
import { MetricsService } from '../../common/telemetry/metrics.service';

/**
 * Prometheus metrics endpoint.
 * Used by Prometheus scraper at /api/v1/metrics
 * Returns metrics in Prometheus text format.
 */
@Controller('metrics')
export class MetricsController {
  @Public()
  @SkipThrottle()
  @Get()
  getMetrics(): string {
    return MetricsService.exportMetrics();
  }
}
