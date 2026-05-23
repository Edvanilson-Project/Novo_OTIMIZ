import { io, Socket } from 'socket.io-client';

let socket: Socket | null = null;

function resolveSocketBaseUrl(): string {
  const explicitSocketUrl = process.env.NEXT_PUBLIC_SOCKET_URL?.trim();
  if (explicitSocketUrl) {
    return explicitSocketUrl.replace(/\/$/, '');
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (apiUrl) {
    return apiUrl.replace(/\/api\/v1\/?$/, '').replace(/\/$/, '');
  }

  return 'http://localhost:3001';
}

/**
 * Cria/retorna socket autenticado.
 *
 * Auth: o JWT vai automaticamente via cookie httpOnly (`withCredentials: true`).
 * Backend valida assinatura e deriva o companyId do token — query param `companyId`
 * NÃO é mais usado para autorização (era um vetor de tenant impersonation).
 *
 * Assinatura mantida com parâmetro opcional para compatibilidade com chamadas
 * existentes; o valor é IGNORADO server-side.
 */
export const getSocket = (_companyIdLegacy?: number): Socket => {
  if (!socket) {
    const baseUrl = resolveSocketBaseUrl();
    socket = io(`${baseUrl}/operations`, {
      withCredentials: true,
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
