import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  ConnectedSocket,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';

/**
 * Lê allowlist da env CORS_ALLOWED_ORIGINS (mesma usada em main.ts).
 * Sem allowlist em produção = bloqueio. Em dev cobre localhost/127.0.0.1 nas portas da UI.
 */
function resolveAllowedOrigins(): string[] {
  const devDefaultOrigins = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:3005',
    'http://127.0.0.1:3005',
  ].join(',');
  const raw =
    process.env.CORS_ALLOWED_ORIGINS ||
    process.env.FRONTEND_URL ||
    (process.env.NODE_ENV === 'production' ? '' : devDefaultOrigins);
  return raw
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean);
}

@WebSocketGateway({
  cors: {
    origin: resolveAllowedOrigins(),
    credentials: true,
  },
  namespace: 'operations',
})
export class OptimizationGateway
  implements OnGatewayConnection, OnGatewayDisconnect
{
  private static readonly ANONYMOUS_SOCKET_WARN_THROTTLE_MS = 60_000;

  @WebSocketServer()
  server: Server;

  private logger: Logger = new Logger('OptimizationGateway');
  private lastAnonymousSocketWarningAt: number | null = null;

  constructor(private readonly jwtService: JwtService) {}

  /**
   * Autenticação do socket:
   *   1. Lê access_token do cookie (preferido) ou do auth handshake.
   *   2. Valida assinatura JWT com JWT_SECRET.
   *   3. Coloca o socket SOMENTE na sala do companyId do token.
   *
   * Por que não usar query string?
   *   - query.companyId é controlada pelo cliente; permite escutar outro tenant.
   *   - JWT verificado é a única fonte de autoridade de tenant.
   */
  handleConnection(client: Socket) {
    const secret = process.env.JWT_SECRET;
    if (!secret) {
      this.logger.error(
        'JWT_SECRET ausente — desconectando socket por segurança.',
      );
      client.disconnect(true);
      return;
    }

    const token = this.extractToken(client);
    if (!token) {
      this.logAnonymousConnection(client);
      client.disconnect(true);
      return;
    }

    try {
      const payload = this.jwtService.verify(token, { secret }) as {
        companyId?: number;
        sub?: number;
      };
      const companyId = payload?.companyId;
      if (!companyId) {
        this.logger.warn(
          `Socket ${client.id} token sem companyId — desconectando.`,
        );
        client.disconnect(true);
        return;
      }
      // Sala derivada do TOKEN, nunca da query do cliente
      void client.join(`company_${companyId}`);
      (client.data as Record<string, unknown>).companyId = companyId;
      this.logger.log(
        `Socket ${client.id} autenticado em company_${companyId}`,
      );
    } catch (err) {
      this.logger.warn(
        `Socket ${client.id} token inválido (${(err as Error).message}) — desconectando.`,
      );
      client.disconnect(true);
    }
  }

  private extractToken(client: Socket): string | undefined {
    // 1) Cookie httpOnly (preferido) — vem em handshake.headers.cookie
    const cookieHeader = client.handshake.headers?.cookie;
    if (cookieHeader) {
      const match = /(?:^|;\s*)access_token=([^;]+)/.exec(cookieHeader);
      if (match && match[1]) return decodeURIComponent(match[1]);
    }
    // 2) Auth handshake { auth: { token } } — fallback para clients sem cookie
    const auth = client.handshake.auth as { token?: string } | undefined;
    if (auth?.token) return auth.token;
    return undefined;
  }

  private logAnonymousConnection(client: Socket) {
    const origin = client.handshake.headers?.origin ?? 'origin-desconhecida';
    const address = client.handshake.address ?? 'ip-desconhecido';
    const now = Date.now();
    const details = `origem=${origin} ip=${address}`;

    if (
      this.lastAnonymousSocketWarningAt === null ||
      now - this.lastAnonymousSocketWarningAt >=
        OptimizationGateway.ANONYMOUS_SOCKET_WARN_THROTTLE_MS
    ) {
      this.lastAnonymousSocketWarningAt = now;
      this.logger.warn(
        `Socket ${client.id} sem token — desconectando (${details}). Novas ocorrências em 60s seguirão em debug.`,
      );
      return;
    }

    this.logger.debug(
      `Socket ${client.id} sem token — desconectando (${details}).`,
    );
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Client ${client.id} disconnected`);
  }

  @SubscribeMessage('ping')
  handlePing(@ConnectedSocket() _client: Socket): string {
    return 'pong';
  }

  notifyOptimizationProgress(
    companyId: number,
    payload: {
      scheduleId: number;
      taskId: string;
      progressPct?: number | null;
      phase?: string | null;
      phaseLabel?: string | null;
    },
  ) {
    this.server
      .to(`company_${companyId}`)
      .emit('optimization_progress', payload);
  }

  notifyOptimizationFinished(
    companyId: number,
    scheduleId: number,
    result: any,
  ) {
    this.server.to(`company_${companyId}`).emit('optimization_finished', {
      scheduleId,
      result,
    });
  }

  notifyOptimizationFailed(companyId: number, error: string) {
    this.server.to(`company_${companyId}`).emit('optimization_failed', {
      error,
    });
  }

  notifyOptimizationQueued(
    companyId: number,
    payload: { scheduleId: number; taskId: string },
  ) {
    this.server.to(`company_${companyId}`).emit('optimization_queued', payload);
  }

  notifyOptimizationStale(
    companyId: number,
    payload: { scheduleId: number; taskId: string },
  ) {
    this.server.to(`company_${companyId}`).emit('optimization_stale', payload);
  }
}
