import axios from 'axios';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3002/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Injeta JWT em todas as requisições
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('otimiz_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Redireciona para login em 401 (exceto na própria página de login)
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      if (!window.location.pathname.includes('/auth/')) {
        localStorage.removeItem('otimiz_token');
        window.location.href = '/auth/login';
      }
    }
    return Promise.reject(error);
  },
);

// ─── Tipos ───────────────────────────────────────────────────────────────────
type ID = number | string;

export interface SessionUser {
  id: number;
  name: string;
  email: string;
  role: string;
  companyId: number;
  avatarUrl?: string | null;
}

// ─── Sessão ──────────────────────────────────────────────────────────────────
export function saveSession(accessToken: string, user: SessionUser) {
  if (typeof window === 'undefined') return;
  localStorage.setItem('otimiz_token', accessToken);
  localStorage.setItem('otimiz_user', JSON.stringify(user));
}

export function getSessionUser(): SessionUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem('otimiz_user');
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch { return null; }
}

export function clearSession() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('otimiz_token');
  localStorage.removeItem('otimiz_user');
}

// ─── Auth ────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post('/auth/login', { email, password }),
  getProfile: () => apiClient.get('/auth/profile'),
};

// ─── Lines ───────────────────────────────────────────────────────────────────
export const linesApi = {
  getAll: (params?: object) => apiClient.get('/lines', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/lines/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/lines', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/lines/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/lines/${id}`).then((r) => r.data),
};

// ─── Terminals ───────────────────────────────────────────────────────────────
export const terminalsApi = {
  getAll: (params?: object) => apiClient.get('/terminals', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/terminals/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/terminals', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/terminals/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/terminals/${id}`).then((r) => r.data),
};

// ─── Companies ───────────────────────────────────────────────────────────────
export const companiesApi = {
  getAll: () => apiClient.get('/companies').then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/companies/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/companies', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/companies/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/companies/${id}`).then((r) => r.data),
};

// ─── Users ───────────────────────────────────────────────────────────────────
export const usersApi = {
  getAll: () => apiClient.get('/users').then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/users/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/users', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/users/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/users/${id}`).then((r) => r.data),
};

// ─── Operations (Trips + Drivers + Optimization) ─────────────────────────────
export const operationsApi = {
  // Viagens
  getTrips: (params?: object) => apiClient.get('/operations/trips', { params }).then((r) => r.data),
  createTrip: (data: object) => apiClient.post('/operations/trips', data).then((r) => r.data),
  updateTrip: (id: ID, data: object) => apiClient.patch(`/operations/trips/${id}`, data).then((r) => r.data),
  deleteTrip: (id: ID) => apiClient.delete(`/operations/trips/${id}`).then((r) => r.data),
  clearTrips: () => apiClient.delete('/operations/trips').then((r) => r.data),
  // Motoristas
  getDrivers: (params?: object) => apiClient.get('/operations/drivers', { params }).then((r) => r.data),
  createDriver: (data: object) => apiClient.post('/operations/drivers', data).then((r) => r.data),
  updateDriver: (id: ID, data: object) => apiClient.patch(`/operations/drivers/${id}`, data).then((r) => r.data),
  deleteDriver: (id: ID) => apiClient.delete(`/operations/drivers/${id}`).then((r) => r.data),
  // Upload / Otimização
  upload: (formData: FormData) =>
    apiClient.post('/operations/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
  getLatestSchedule: () => apiClient.get('/operations/latest-schedule').then((r) => r.data),
  optimize: (data?: object) => apiClient.post('/operations/optimize', data ?? {}).then((r) => r.data),
  reassignTrip: (data: object) => apiClient.patch('/operations/reassign-trip', data).then((r) => r.data),
  evaluateDelta: (data: object) => apiClient.post('/operations/evaluate-delta', data).then((r) => r.data),
  evaluateBaseline: (data: object) => apiClient.post('/operations/evaluate-baseline', data).then((r) => r.data),
  aiChat: (data: { metrics: any; question: string }) => apiClient.post('/operations/chat', data).then((r) => r.data),
};

// ─── Parameters (CCT) ────────────────────────────────────────────────────────
export const parametersApi = {
  get: () => apiClient.get('/parameters').then((r) => r.data),
  update: (data: object) => apiClient.put('/parameters', data).then((r) => r.data),
};

// ─── Reports ─────────────────────────────────────────────────────────────────
export const reportsApi = {
  getKpis: () => apiClient.get('/reports/kpis').then((r) => r.data),
  getHistory: (days?: number) =>
    apiClient.get('/reports/history', { params: { days } }).then((r) => r.data),
  compare: (run1: ID, run2: ID) =>
    apiClient.get('/reports/compare', { params: { run1, run2 } }).then((r) => r.data),
};

// ─── Audit Log ───────────────────────────────────────────────────────────────
export const auditApi = {
  find: (params?: { entity?: string; days?: number; page?: number; limit?: number }) =>
    apiClient.get('/audit', { params }).then((r) => r.data),
};

// ─── What-if (avaliação de cenários) ─────────────────────────────────────────
export const whatIfApi = {
  evaluateDelta: (body: object) =>
    apiClient.post('/operations/evaluate-delta', body).then((r) => r.data),
  evaluateBaseline: (body: object) =>
    apiClient.post('/operations/evaluate-baseline', body).then((r) => r.data),
};
