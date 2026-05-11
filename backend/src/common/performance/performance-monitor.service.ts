import { Injectable, Logger } from '@nestjs/common';

export interface PerformanceMetric {
  name: string;
  duration: number; // milliseconds
  memory: {
    heapUsed: number; // MB
    heapTotal: number; // MB
    external: number; // MB
  };
  timestamp: Date;
}

export interface PerformanceThreshold {
  metric: string;
  targetDuration: number; // ms
  warning: number; // ms
  critical: number; // ms
}

@Injectable()
export class PerformanceMonitorService {
  private logger = new Logger('PerformanceMonitor');
  private metrics: PerformanceMetric[] = [];

  private thresholds: PerformanceThreshold[] = [
    { metric: 'schedule_generation', targetDuration: 5000, warning: 4000, critical: 6000 },
    { metric: 'trip_assignment', targetDuration: 2000, warning: 1500, critical: 3000 },
    { metric: 'scenario_evaluation', targetDuration: 3000, warning: 2500, critical: 4000 },
    { metric: 'vehicle_optimization', targetDuration: 4000, warning: 3000, critical: 5000 },
    { metric: 'constraint_validation', targetDuration: 1000, warning: 800, critical: 1500 },
  ];

  recordMetric(name: string, duration: number): void {
    const memUsage = process.memoryUsage();
    const metric: PerformanceMetric = {
      name,
      duration,
      memory: {
        heapUsed: Math.round((memUsage.heapUsed / 1024 / 1024) * 100) / 100,
        heapTotal: Math.round((memUsage.heapTotal / 1024 / 1024) * 100) / 100,
        external: Math.round((memUsage.external / 1024 / 1024) * 100) / 100,
      },
      timestamp: new Date(),
    };

    this.metrics.push(metric);

    // Check threshold
    const threshold = this.thresholds.find((t) => t.metric === name);
    if (threshold) {
      if (duration > threshold.critical) {
        this.logger.error(
          `CRITICAL: ${name} took ${duration}ms (threshold: ${threshold.critical}ms)`,
        );
      } else if (duration > threshold.warning) {
        this.logger.warn(
          `WARNING: ${name} took ${duration}ms (threshold: ${threshold.warning}ms)`,
        );
      }
    }

    this.logger.debug(
      `${name}: ${duration}ms | Heap: ${metric.memory.heapUsed}MB/${metric.memory.heapTotal}MB`,
    );
  }

  recordAsyncMetric(name: string): () => void {
    const startTime = Date.now();
    const startMemory = process.memoryUsage();

    return () => {
      const endTime = Date.now();
      const duration = endTime - startTime;
      this.recordMetric(name, duration);
    };
  }

  async trackAsync<T>(name: string, fn: () => Promise<T>): Promise<T> {
    const startTime = Date.now();

    try {
      const result = await fn();
      const duration = Date.now() - startTime;
      this.recordMetric(name, duration);
      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      this.logger.error(`${name} failed after ${duration}ms: ${error}`);
      throw error;
    }
  }

  trackSync<T>(name: string, fn: () => T): T {
    const startTime = Date.now();

    try {
      const result = fn();
      const duration = Date.now() - startTime;
      this.recordMetric(name, duration);
      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      this.logger.error(`${name} failed after ${duration}ms: ${error}`);
      throw error;
    }
  }

  getMetrics(name?: string): PerformanceMetric[] {
    if (name) {
      return this.metrics.filter((m) => m.name === name);
    }
    return this.metrics;
  }

  getAverageMetric(name: string): number {
    const metrics = this.getMetrics(name);
    if (metrics.length === 0) return 0;
    const total = metrics.reduce((sum, m) => sum + m.duration, 0);
    return Math.round(total / metrics.length);
  }

  getMetricStats(name: string) {
    const metrics = this.getMetrics(name);
    if (metrics.length === 0) {
      return {
        count: 0,
        average: 0,
        min: 0,
        max: 0,
        p95: 0,
        p99: 0,
      };
    }

    const durations = metrics.map((m) => m.duration).sort((a, b) => a - b);
    const count = durations.length;
    const average = durations.reduce((a, b) => a + b, 0) / count;
    const min = durations[0];
    const max = durations[count - 1];
    const p95Index = Math.floor(count * 0.95);
    const p99Index = Math.floor(count * 0.99);

    return {
      count,
      average: Math.round(average),
      min,
      max,
      p95: durations[p95Index],
      p99: durations[p99Index],
    };
  }

  getAverageMemory(name?: string): {
    heapUsed: number;
    heapTotal: number;
    external: number;
  } {
    const metrics = name ? this.getMetrics(name) : this.metrics;

    if (metrics.length === 0) {
      return { heapUsed: 0, heapTotal: 0, external: 0 };
    }

    const avgHeapUsed =
      metrics.reduce((sum, m) => sum + m.memory.heapUsed, 0) / metrics.length;
    const avgHeapTotal =
      metrics.reduce((sum, m) => sum + m.memory.heapTotal, 0) / metrics.length;
    const avgExternal =
      metrics.reduce((sum, m) => sum + m.memory.external, 0) / metrics.length;

    return {
      heapUsed: Math.round(avgHeapUsed * 100) / 100,
      heapTotal: Math.round(avgHeapTotal * 100) / 100,
      external: Math.round(avgExternal * 100) / 100,
    };
  }

  generateReport(): {
    totalMetrics: number;
    metricsPerOperation: Record<string, any>;
    averageMemory: any;
    thresholdViolations: any[];
  } {
    const operations = [...new Set(this.metrics.map((m) => m.name))];
    const metricsPerOperation: Record<string, any> = {};
    const violations: any[] = [];

    for (const op of operations) {
      const stats = this.getMetricStats(op);
      metricsPerOperation[op] = stats;

      const threshold = this.thresholds.find((t) => t.metric === op);
      if (threshold && stats.average > threshold.warning) {
        violations.push({
          operation: op,
          average: stats.average,
          threshold: threshold.warning,
          status: stats.average > threshold.critical ? 'CRITICAL' : 'WARNING',
        });
      }
    }

    return {
      totalMetrics: this.metrics.length,
      metricsPerOperation,
      averageMemory: this.getAverageMemory(),
      thresholdViolations: violations,
    };
  }

  clear(): void {
    this.metrics = [];
  }

  setThreshold(metric: string, targetDuration: number, warning: number, critical: number): void {
    const existing = this.thresholds.find((t) => t.metric === metric);
    if (existing) {
      existing.targetDuration = targetDuration;
      existing.warning = warning;
      existing.critical = critical;
    } else {
      this.thresholds.push({
        metric,
        targetDuration,
        warning,
        critical,
      });
    }
  }
}
