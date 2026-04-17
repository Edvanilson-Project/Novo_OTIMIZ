import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  ConnectedSocket,
  MessageBody,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger } from '@nestjs/common';

@WebSocketGateway({
  cors: {
    origin: '*',
  },
  namespace: 'operations',
})
export class OptimizationGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  private logger: Logger = new Logger('OptimizationGateway');

  handleConnection(client: Socket) {
    const companyId = client.handshake.query.companyId;
    if (companyId) {
      client.join(`company_${companyId}`);
      this.logger.log(`Client ${client.id} joined room company_${companyId}`);
    }
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Client ${client.id} disconnected`);
  }

  @SubscribeMessage('ping')
  handlePing(@ConnectedSocket() client: Socket): string {
    return 'pong';
  }

  notifyOptimizationFinished(companyId: number, scheduleId: number, result: any) {
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
}
