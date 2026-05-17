import axios from 'axios';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  // withCredentials envia o cookie HttpOnly definido pelo backend em /auth/login.
  // O token não é lido via JS — fica protegido contra XSS.
  withCredentials: true,
});

// Redireciona para login em 401 (exceto na própria página de login)
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      if (!window.location.pathname.includes('/auth/')) {
        clearSession();
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
// O token JWT não é armazenado em JS — viaja exclusivamente via cookie HttpOnly
// definido pelo backend. Aqui guardamos apenas metadados não-sensíveis do usuário.
export function saveSession(_accessToken: string, user: SessionUser) {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem('otimiz_user', JSON.stringify(user));
}

export function getSessionUser(): SessionUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem('otimiz_user');
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch { return null; }
}

export function clearSession() {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem('otimiz_user');
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
  getDepots: () => apiClient.get('/terminals/depots').then((r) => r.data),
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
  getOptimizeStatus: () => apiClient.get('/operations/optimize/status').then((r) => r.data) as Promise<{
    status: 'idle' | 'processing' | 'completed' | 'failed';
    scheduleId: number | null;
    startedAt: string | null;
    totalCost: number | null;
    cctViolations: number;
  }>,
  optimize: (data?: { algorithm?: string; operational_quality_mode?: string; depot_ids?: number[] }) =>
    apiClient.post('/operations/optimize', data ?? {}).then((r) => r.data),
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

// ─── Custom Reports (FASE 4.2) ────────────────────────────────────────────────
export interface CustomReportTemplate {
  id: number;
  name: string;
  description: string | null;
  metrics: string[];
  filters: Record<string, any>;
  format: 'json' | 'csv' | 'pdf';
  ownerUserId: number | null;
  createdAt: string;
  updatedAt: string;
}

export const customReportsApi = {
  listMetrics: () => apiClient.get<{ metrics: string[] }>('/custom-reports/metrics').then((r) => r.data),
  list: () => apiClient.get<CustomReportTemplate[]>('/custom-reports').then((r) => r.data),
  get: (id: ID) => apiClient.get<CustomReportTemplate>(`/custom-reports/${id}`).then((r) => r.data),
  create: (data: { name: string; description?: string; metrics: string[]; filters?: Record<string, any>; format?: string }) =>
    apiClient.post<CustomReportTemplate>('/custom-reports', data).then((r) => r.data),
  update: (id: ID, data: Partial<{ name: string; description: string; metrics: string[]; filters: Record<string, any>; format: string }>) =>
    apiClient.patch<CustomReportTemplate>(`/custom-reports/${id}`, data).then((r) => r.data),
  remove: (id: ID) => apiClient.delete(`/custom-reports/${id}`).then((r) => r.data),
  run: (id: ID) => apiClient.get<Record<string, any>>(`/custom-reports/${id}/run`).then((r) => r.data),
  preview: (metrics: string[], filters: Record<string, any> = {}) =>
    apiClient.post<Record<string, any>>('/custom-reports/preview', { metrics, filters }).then((r) => r.data),
  exportCsvUrl: (id: ID) => `${API_BASE_URL}/custom-reports/${id}/export.csv`,
  exportPdfUrl: (id: ID) => `${API_BASE_URL}/custom-reports/${id}/export.pdf`,
};

// ─── Audit Log ───────────────────────────────────────────────────────────────
export const auditApi = {
  find: (params?: { entity?: string; days?: number; page?: number; limit?: number }) =>
    apiClient.get('/audit', { params }).then((r) => r.data),
  validateSchedule: (scheduleId: number) =>
    apiClient.post(`/audits/${scheduleId}/validate`).then((r) => r.data as {
      valid: boolean;
      errorCount: number;
      warningCount: number;
      errors: Array<{ type: string; severity: string; detail: string; dutyId?: number; vehicleId?: number; suggestedFix?: string }>;
      warnings: Array<{ type: string; severity: string; detail: string; dutyId?: number; suggestedFix?: string }>;
      stats: { totalTrips: number; allocatedTrips: number; unallocatedTrips: number; allocationPercentage: number; totalVehicles: number; totalDuties: number; totalOperatorHours: number; avgDutyHours: number };
    }),
};

// ─── What-if (avaliação de cenários) ─────────────────────────────────────────
export const whatIfApi = {
  evaluateDelta: (body: object) =>
    apiClient.post('/operations/evaluate-delta', body).then((r) => r.data),
  evaluateBaseline: (body: object) =>
    apiClient.post('/operations/evaluate-baseline', body).then((r) => r.data),
};

// ─── Vehicles & Fleet ─────────────────────────────────────────────────────────
export const vehiclesApi = {
  getTypes: () => apiClient.get('/vehicles/types').then((r) => r.data),
  getTypeById: (id: ID) => apiClient.get(`/vehicles/types/${id}`).then((r) => r.data),
  createType: (data: object) => apiClient.post('/vehicles/types', data).then((r) => r.data),
  getAll: () => apiClient.get('/vehicles').then((r) => r.data),
  getActive: () => apiClient.get('/vehicles/active').then((r) => r.data),
  getByType: (typeId: ID) => apiClient.get(`/vehicles/by-type/${typeId}`).then((r) => r.data),
  getById: (id: ID) => apiClient.get(`/vehicles/${id}`).then((r) => r.data),
  create: (data: object) => apiClient.post('/vehicles', data).then((r) => r.data),
  getMetricsAll: () => apiClient.get('/vehicles/metrics/all').then((r) => r.data),
  getMetrics: (id: ID) => apiClient.get(`/vehicles/metrics/${id}`).then((r) => r.data),
  getMaintenance: (vehicleId: ID) => apiClient.get(`/vehicles/${vehicleId}/maintenance`).then((r) => r.data),
  createMaintenance: (vehicleId: ID, data: object) => apiClient.post(`/vehicles/${vehicleId}/maintenance`, data).then((r) => r.data),
  updateMaintenance: (vehicleId: ID, maintenanceId: ID, data: object) =>
    apiClient.patch(`/vehicles/${vehicleId}/maintenance/${maintenanceId}`, data).then((r) => r.data),
  checkAvailability: (vehicleId: ID, params?: object) =>
    apiClient.get(`/vehicles/${vehicleId}/maintenance/availability/check`, { params }).then((r) => r.data),
  getAvailabilityWindows: (vehicleId: ID) =>
    apiClient.get(`/vehicles/${vehicleId}/maintenance/availability/periods`).then((r) => r.data),
  createAvailabilityWindow: (vehicleId: ID, data: object) =>
    apiClient.post(`/vehicles/${vehicleId}/maintenance/availability-windows`, data).then((r) => r.data),
};

// ─── Operation Reporting ──────────────────────────────────────────────────────
export const operationReportingApi = {
  generate: (scheduleId: ID) => apiClient.post(`/operations/reporting/generate/${scheduleId}`).then((r) => r.data),
  getHistorical: (scheduleId: ID, days?: number) =>
    apiClient.get(`/operations/reporting/historical/${scheduleId}`, { params: { days } }).then((r) => r.data),
  compare: (scheduleId: ID, compareWith?: ID) =>
    apiClient.get(`/operations/reporting/compare/${scheduleId}`, { params: { compareWith } }).then((r) => r.data),
  getDutyStats: (scheduleId: ID) =>
    apiClient.get(`/operations/reporting/duties/${scheduleId}`).then((r) => r.data),
  exportPdfUrl: (scheduleId: ID) => `/api/operations/reporting/export-pdf/${scheduleId}`,
  exportExcelUrl: (scheduleId: ID) => `/api/operations/reporting/export-excel/${scheduleId}`,
};

// ─── Scenarios & Advanced Optimization ───────────────────────────────────────
export const scenariosApi = {
  // POST = trigger inicial (pode enfileirar runs); GET = polling idempotente (não cria, só lê).
  generate: (scheduleId: ID) => apiClient.post(`/operations/optimization-advanced/scenarios/${scheduleId}`).then((r) => r.data),
  list: (scheduleId: ID) => apiClient.get(`/operations/optimization-advanced/scenarios/${scheduleId}`).then((r) => r.data),
  getScenarioRun: (scheduleId: ID, scenarioId: string) =>
    apiClient.get(`/operations/optimization-advanced/scenarios/${scheduleId}/run/${scenarioId}`).then((r) => r.data),
  compare: (scheduleId: ID, scenario1Id: string, scenario2Id: string) =>
    apiClient.post(`/operations/optimization-advanced/scenarios/${scheduleId}/compare`, { scenario1Id, scenario2Id }).then((r) => r.data),
  whatIfVehicleType: (body: object) => apiClient.post('/operations/optimization-advanced/whatif/vehicle-type-change', body).then((r) => r.data),
  whatIfTimeShift: (body: object) => apiClient.post('/operations/optimization-advanced/whatif/time-shift', body).then((r) => r.data),
  whatIfTripRemoval: (body: object) => apiClient.post('/operations/optimization-advanced/whatif/trip-removal', body).then((r) => r.data),
  whatIfTripAddition: (body: object) => apiClient.post('/operations/optimization-advanced/whatif/trip-addition', body).then((r) => r.data),
  whatIfParameterChange: (body: object) => apiClient.post('/operations/optimization-advanced/whatif/parameter-change', body).then((r) => r.data),
  // Reotimização REAL — enfileira nova run via solver Python com paramsOverride.
  // Frontend deve pollear getScenarioRun(scheduleId, scenarioId) até status=completed.
  whatIfRunReal: (
    scheduleId: ID,
    body: { paramsOverride: Record<string, any>; label?: string; algorithm?: string },
  ) => apiClient.post(`/operations/optimization-advanced/whatif/run-real/${scheduleId}`, body).then((r) => r.data),
  replayByFingerprint: (fingerprint: string) =>
    apiClient.post(`/operations/optimization-advanced/replay/${fingerprint}`).then((r) => r.data),
};

// ─── Weekly Rostering ─────────────────────────────────────────────────────────
export const weeklyRosteringApi = {
  solve: (body: object) =>
    apiClient.post('/optimizer/rostering/weekly', body).then((r) => r.data),
};

export const gtfsApi = {
  import: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiClient.post('/gtfs/import', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data as { imported: { terminals: number; lines: number; trips: number }; skipped: number; errors: string[] });
  },
};
