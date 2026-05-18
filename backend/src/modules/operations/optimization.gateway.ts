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

@WebSocketGateway({
  cors: {
    origin: '*',
  },
  namespace: 'operations',
})
export class OptimizationGateway
  implements OnGatewayConnection, OnGatewayDisconnect
{
  @WebSocketServer()
  server: Server;

  private logger: Logger = new Logger('OptimizationGateway');

  handleConnection(client: Socket) {
    const rawCompanyId = client.handshake.query.companyId;
    const companyId = Array.isArray(rawCompanyId)
      ? rawCompanyId[0]
      : rawCompanyId;
    if (companyId) {
      void client.join(`company_${companyId}`);
      this.logger.log(`Client ${client.id} joined room company_${companyId}`);
    }
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
