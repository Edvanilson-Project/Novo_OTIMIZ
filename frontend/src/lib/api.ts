import axios from 'axios';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Interceptor para adicionar JWT
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('otimiz_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor de resposta para erros 401
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      const isLoginPage = window.location.pathname.includes('/auth/');
      if (!isLoginPage) {
        localStorage.removeItem('otimiz_token');
        window.location.href = '/auth/auth1/login';
      }
    }
    return Promise.reject(error);
  },
);

// ─── Auth ────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post('/auth/login', { email, password }),
  getProfile: () => apiClient.get('/auth/profile'),
};

type ID = number | string;

// ─── Helpers de sessão ───────────────────────────────────────────────────────
export interface SessionUser {
  id: number;
  name: string;
  email: string;
  role: string;
  companyId: number;
  avatarUrl?: string | null;
}

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

// ─── Companies ───────────────────────────────────────────────────────────────
export const companiesApi = {
  getAll: () => apiClient.get('/companies').then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/companies/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/companies', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/companies/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/companies/${id}`).then((r) => r.data),
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

// ─── Trips ───────────────────────────────────────────────────────────────────
export const tripsApi = {
  getAll: (params?: object) => apiClient.get('/trips', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/trips/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/trips', data).then((r) => r.data),
  createBulk: (data: object[]) => apiClient.post('/trips/bulk', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/trips/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/trips/${id}`).then((r) => r.data),
};

// ─── Optimization ────────────────────────────────────────────────────────────
export const optimizationSettingsApi = {
  getAll: (companyId?: number) => apiClient.get('/optimization-settings', { params: companyId ? { companyId } : {} }).then((r) => r.data),
  getActive: (companyId?: number) => apiClient.get('/optimization-settings/active', { params: companyId ? { companyId } : {} }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/optimization-settings/${id}`).then((r) => r.data),
  create: (data: object, companyId?: number) => apiClient.post('/optimization-settings', data, { params: companyId ? { companyId } : {} }).then((r) => r.data),
  update: (id: ID, data: object, companyId?: number) => apiClient.patch(`/optimization-settings/${id}`, data, { params: companyId ? { companyId } : {} }).then((r) => r.data),
  activate: (id: ID, companyId?: number) => apiClient.patch(`/optimization-settings/${id}/activate`, {}, { params: companyId ? { companyId } : {} }).then((r) => r.data),
  delete: (id: ID, companyId?: number) => apiClient.delete(`/optimization-settings/${id}`, { params: companyId ? { companyId } : {} }).then((r) => r.data),
};

export const optimizationApi = {
  run: (data: object) => apiClient.post('/optimization/run', data).then((r) => r.data),
  getAll: (params?: object) => apiClient.get('/optimization', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/optimization/${id}`).then((r) => r.data),
  getAudit: (id: ID) => apiClient.get(`/optimization/${id}/audit`).then((r) => r.data),
  compare: (id: ID, otherId: ID) => apiClient.get(`/optimization/${id}/compare/${otherId}`).then((r) => r.data),
  cancel: (id: ID) => apiClient.patch(`/optimization/${id}/cancel`, {}).then((r) => r.data),
  getDashboard: (companyId: ID) =>
    apiClient.get(`/optimization/dashboard/${companyId}`).then((r) => r.data),
  evaluateDelta: (data: object) =>
    apiClient.post('/optimization/evaluate-delta', data).then((r) => r.data),
  evaluateBaseline: (data: object) =>
    apiClient.post('/optimization/evaluate-baseline', data).then((r) => r.data),
};

// ─── Reports ─────────────────────────────────────────────────────────────────
export const reportsApi = {
  getKpis: (companyId: ID) =>
    apiClient.get(`/reports/kpis/${companyId}`).then((r) => r.data),
  getHistory: (companyId: ID, days?: number) =>
    apiClient.get(`/reports/history/${companyId}`, { params: { days } }).then((r) => r.data),
  compare: (run1: ID, run2: ID) =>
    apiClient.get('/reports/compare', { params: { run1, run2 } }).then((r) => r.data),
};

export const vehicleTypesApi = {
  getAll: () => apiClient.get('/vehicle-types').then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/vehicle-types/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/vehicle-types', data).then((r) => r.data),
  update: (id: ID, data: object) =>
    apiClient.patch(`/vehicle-types/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/vehicle-types/${id}`).then((r) => r.data),
};

export const usersApi = {
  getAll: () => apiClient.get('/users').then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/users/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/users', data).then((r) => r.data),
  update: (id: ID, data: object) =>
    apiClient.patch(`/users/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/users/${id}`).then((r) => r.data),
};

// ─── Operations ──────────────────────────────────────────────────────────────
export const operationsApi = {
  getTrips: (params?: object) => apiClient.get('/operations/trips', { params }).then((r) => r.data),
  getDrivers: () => apiClient.get('/operations/drivers').then((r) => r.data),
  upload: (formData: FormData) =>
    apiClient.post('/operations/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
  getLatestSchedule: () => apiClient.get('/operations/latest-schedule').then((r) => r.data),
  optimize: (data: object) => apiClient.post('/operations/optimize', data).then((r) => r.data),
  reassignTrip: (data: object) => apiClient.patch('/operations/reassign-trip', data).then((r) => r.data),
  evaluateDelta: (data: object) => apiClient.post('/operations/evaluate-delta', data).then((r) => r.data),
};

// ─── Parameters ──────────────────────────────────────────────────────────────
export const parametersApi = {
  get: () => apiClient.get('/parameters').then((r) => r.data),
  update: (data: object) => apiClient.put('/parameters', data).then((r) => r.data),
};

// ─── Time Bands (Faixas Horárias) ────────────────────────────────────────────
export const timeBandsApi = {
  getAll: (params?: object) => apiClient.get('/time-bands', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/time-bands/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/time-bands', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/time-bands/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/time-bands/${id}`).then((r) => r.data),
};

// ─── Line Trip Profiles (Perfil por Sentido/Faixa) ───────────────────────────
export const lineTripProfilesApi = {
  getAll: (params?: object) => apiClient.get('/line-trip-profiles', { params }).then((r) => r.data),
  getByLine: (lineId: ID) => apiClient.get('/line-trip-profiles', { params: { lineId } }).then((r) => r.data),
  createBulk: (data: object[]) => apiClient.post('/line-trip-profiles/bulk', data).then((r) => r.data),
  create: (data: object) => apiClient.post('/line-trip-profiles', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/line-trip-profiles/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/line-trip-profiles/${id}`).then((r) => r.data),
};

// ─── Schedules (Quadros Horários) ────────────────────────────────────────────
export const schedulesApi = {
  getAll: (params?: object) => apiClient.get('/schedules', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/schedules/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/schedules', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/schedules/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/schedules/${id}`).then((r) => r.data),
};

// ─── Timetable Rules (Regras de Quadro) ──────────────────────────────────────
export const timetableRulesApi = {
  getAll: (params?: object) => apiClient.get('/timetable-rules', { params }).then((r) => r.data),
  getBySchedule: (scheduleId: ID) => apiClient.get('/timetable-rules', { params: { scheduleId } }).then((r) => r.data),
  createBulk: (data: object[]) => apiClient.post('/timetable-rules/bulk', data).then((r) => r.data),
  create: (data: object) => apiClient.post('/timetable-rules', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/timetable-rules/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/timetable-rules/${id}`).then((r) => r.data),
};

// ─── Schedule Groups (Grupos de Programação) ─────────────────────────────────
export const scheduleGroupsApi = {
  getAll: (params?: object) => apiClient.get('/schedule-groups', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/schedule-groups/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/schedule-groups', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/schedule-groups/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/schedule-groups/${id}`).then((r) => r.data),
  generateTrips: (id: ID) => apiClient.post(`/schedule-groups/${id}/generate-trips`).then((r) => r.data),
  getTrips: (id: ID) => apiClient.get(`/schedule-groups/${id}/trips`).then((r) => r.data),
};

// ─── Trip Time Configs (Tempo de Viagem) ─────────────────────────────────────
export const tripTimeConfigsApi = {
  getAll: (params?: object) => apiClient.get('/trip-time-configs', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/trip-time-configs/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/trip-time-configs', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/trip-time-configs/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/trip-time-configs/${id}`).then((r) => r.data),
  getBands: (id: ID) => apiClient.get(`/trip-time-configs/${id}/bands`).then((r) => r.data),
  saveBands: (id: ID, data: object[]) => apiClient.post(`/trip-time-configs/${id}/bands`, data).then((r) => r.data),
};

// ─── Passenger Configs (Passageiros por Faixa) ──────────────────────────────
export const passengerConfigsApi = {
  getAll: (params?: object) => apiClient.get('/passenger-configs', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/passenger-configs/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/passenger-configs', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/passenger-configs/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/passenger-configs/${id}`).then((r) => r.data),
  getBands: (id: ID) => apiClient.get(`/passenger-configs/${id}/bands`).then((r) => r.data),
  saveBands: (id: ID, data: object[]) => apiClient.post(`/passenger-configs/${id}/bands`, data).then((r) => r.data),
};

// ─── Timetables (Carta Horária) ─────────────────────────────────────────────
export const timetablesApi = {
  getAll: (params?: object) => apiClient.get('/timetables', { params }).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/timetables/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/timetables', data).then((r) => r.data),
  update: (id: ID, data: object) => apiClient.patch(`/timetables/${id}`, data).then((r) => r.data),
  delete: (id: ID) => apiClient.delete(`/timetables/${id}`).then((r) => r.data),
  generateTrips: (id: ID) => apiClient.post(`/timetables/${id}/generate-trips`).then((r) => r.data),
  getTrips: (id: ID) => apiClient.get(`/timetables/${id}/trips`).then((r) => r.data),
};
