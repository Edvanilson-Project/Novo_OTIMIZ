import { io, Socket } from 'socket.io-client';

let socket: Socket | null = null;

export const getSocket = (companyId: number): Socket => {
  if (!socket) {
    const baseUrl = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:3002';
    socket = io(`${baseUrl}/operations`, {
      query: { companyId: companyId.toString() },
      transports: ['websocket'],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
    });
  }
  return socket;
};

export const disconnectSocket = () => {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
};

export const isSocketConnected = (): boolean => Boolean(socket?.connected);

export const reconnectSocket = () => {
  socket?.connect();
};

export const getSocketDiagnostics = () => ({
  connected: Boolean(socket?.connected),
  id: socket?.id ?? null,
});
