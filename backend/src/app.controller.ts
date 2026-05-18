import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { SkipThrottle } from '@nestjs/throttler';
import { DataSource } from 'typeorm';
import { AppService } from './app.service';
import { Public } from './common/decorators/roles.decorator';

@Controller()
export class AppController {
  constructor(
    private readonly appService: AppService,
    private readonly dataSource: DataSource,
  ) {}

  @Public()
  @Get()
  getHello(): string {
    return this.appService.getHello();
  }

  /**
   * Liveness probe: o processo Node está vivo? Não bate em DB para evitar derrubar
   * o container quando DB tem hiccup transitório (k8s reiniciaria desnecessariamente).
   */
  @Public()
  @SkipThrottle()
  @Get('health')
  getHealth() {
    return {
      status: 'ok',
      service: 'otimiz-backend',
      uptime_s: Math.floor(process.uptime()),
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Readiness probe: backend está pronto para servir requests? Verifica DB.
   * k8s/Docker swarm usam para parar de mandar tráfego quando dependência cai.
   */
  @Public()
  @SkipThrottle()
  @Get('ready')
  async getReady() {
    try {
      await this.dataSource.query('SELECT 1');
      return {
        status: 'ready',
        db: 'ok',
        timestamp: new Date().toISOString(),
      };
    } catch (err) {
      throw new ServiceUnavailableException({
        status: 'unready',
        db: 'error',
        message: (err as Error).message,
      });
    }
  }
}
