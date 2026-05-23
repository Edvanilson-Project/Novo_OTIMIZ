import path from 'node:path';
import { test, expect, request as playwrightRequest, type APIRequestContext, type Page } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3005';
const API_BASE = process.env.E2E_API_URL ?? 'http://127.0.0.1:3001/api/v1/';
const AUTH_FILE = path.join(__dirname, '.auth/user.json');

type TripRow = {
  id: number;
  tripId: number | null;
  lineCode?: string | null;
  pairId: string | null;
};

type DriverRow = {
  id: number;
  driverId: string;
};

type TerminalRow = {
  id: number;
  isDepot: boolean;
};

type SelectedTerminals = {
  originId: number;
  destinationId: number;
};

type FlowArtifacts = {
  outboundTripId: number;
  returnTripId: number;
  pairId: string;
  lineCode: string;
  driverIds: [string, string];
};

function buildArtifacts(runDigits: string): FlowArtifacts {
  const tripBase = 910000 + Number(runDigits.slice(-4)) * 10;
  return {
    outboundTripId: tripBase,
    returnTripId: tripBase + 1,
    pairId: `QA-PAIR-${runDigits}`,
    lineCode: `QA-L-${runDigits}`,
    driverIds: [`DRV-QA-${runDigits}-A`, `DRV-QA-${runDigits}-B`],
  };
}

function pickOperationalTerminals(terminals: TerminalRow[]): SelectedTerminals {
  const nonDepots = terminals.filter((terminal) => !terminal.isDepot);
  const source = nonDepots.length >= 2 ? nonDepots : terminals;
  if (source.length < 2) {
    throw new Error('Teste requer ao menos dois terminais cadastrados.');
  }

  return {
    originId: source[0].id,
    destinationId: source[1].id,
  };
}

function buildTripsCsvBuffer(artifacts: FlowArtifacts, terminals: SelectedTerminals): Buffer {
  return Buffer.from(
    [
      'trip_id,line_code,pair_id,direction,start_time,end_time,origin_id,destination_id,distance_km,duration',
      `${artifacts.outboundTripId},${artifacts.lineCode},,IDA,05:10,05:55,${terminals.originId},${terminals.destinationId},11.8,45`,
      `${artifacts.returnTripId},${artifacts.lineCode},,VOLTA,06:30,07:15,${terminals.destinationId},${terminals.originId},11.8,45`,
    ].join('\n'),
    'utf8',
  );
}

function buildDriversCsvBuffer(artifacts: FlowArtifacts): Buffer {
  return Buffer.from(
    [
      'driver_id,name,role,max_hours_per_day,last_shift_end',
      `${artifacts.driverIds[0]},Motorista QA ${artifacts.driverIds[0]},Motorista,540,0`,
      `${artifacts.driverIds[1]},Motorista QA ${artifacts.driverIds[1]},Motorista,540,0`,
    ].join('\n'),
    'utf8',
  );
}

async function getJson<T>(api: APIRequestContext, url: string): Promise<T> {
  const response = await api.get(url);
  expect(response.ok(), `GET ${url} should succeed`).toBeTruthy();
  return (await response.json()) as T;
}

async function postJson<T>(api: APIRequestContext, url: string, data?: unknown): Promise<T> {
  const response = await api.post(url, data !== undefined ? { data } : undefined);
  expect(response.ok(), `POST ${url} should succeed`).toBeTruthy();
  return (await response.json()) as T;
}

function isResidualTestTrip(trip: TripRow): boolean {
  const pairId = trip.pairId ?? '';
  const lineCode = trip.lineCode ?? '';

  return (
    trip.tripId === null ||
    !lineCode ||
    (typeof trip.tripId === 'number' && trip.tripId >= 900000) ||
    pairId.startsWith('E2E-PAIR-') ||
    pairId.startsWith('QA-PAIR-') ||
    /^pair-\d{10,}$/.test(pairId) ||
    lineCode.startsWith('E2E-L-') ||
    lineCode.startsWith('QA-L-') ||
    /^L-\d{10,}$/.test(lineCode) ||
    lineCode.includes('GTFS')
  );
}

function isResidualTestDriver(driver: DriverRow): boolean {
  return driver.driverId.startsWith('DRV-E2E-') || driver.driverId.startsWith('DRV-QA-');
}

async function cleanupResidualTestArtifacts(api: APIRequestContext): Promise<void> {
  const [trips, drivers] = await Promise.all([
    getJson<TripRow[]>(api, 'operations/trips?limit=1000'),
    getJson<DriverRow[]>(api, 'operations/drivers'),
  ]);

  for (const trip of trips.filter(isResidualTestTrip)) {
    await api.delete(`operations/trips/${trip.id}`);
  }

  for (const driver of drivers.filter(isResidualTestDriver)) {
    await api.delete(`operations/drivers/${driver.id}`);
  }
}

async function cleanupArtifacts(api: APIRequestContext, artifacts: FlowArtifacts): Promise<void> {
  const [trips, drivers] = await Promise.all([
    getJson<TripRow[]>(api, 'operations/trips?limit=1000'),
    getJson<DriverRow[]>(api, 'operations/drivers'),
  ]);

  for (const trip of trips.filter((row) => row.tripId === artifacts.outboundTripId || row.tripId === artifacts.returnTripId || row.pairId === artifacts.pairId)) {
    await api.delete(`operations/trips/${trip.id}`);
  }

  for (const driver of drivers.filter((row) => artifacts.driverIds.includes(row.driverId as (typeof artifacts.driverIds)[number]))) {
    await api.delete(`operations/drivers/${driver.id}`);
  }
}

async function openOperationsData(page: Page): Promise<void> {
  await page.goto(`${BASE}/operations/data`, { waitUntil: 'networkidle' });
  await expect(page.locator('body')).toContainText('Gestão de Dados Operacionais');
}

async function goToDriversTab(page: Page): Promise<void> {
  await page.locator('[role="tab"]').filter({ hasText: 'Motoristas' }).first().click();
  await expect(page.locator('body')).toContainText('Base de Motoristas');
}

async function expectSnackbarMessage(page: Page, message: string | RegExp): Promise<void> {
  await expect(page.locator('.MuiSnackbar-root [role="alert"]').last()).toContainText(message);
}

test.describe('Operations real user flow', () => {
  test('imports operational data, runs planner optimization, validates the schedule and confirms reporting metrics', async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    test.slow();

    const runDigits = `${Date.now()}${testInfo.workerIndex}${testInfo.retry}`.slice(-8);
    const artifacts = buildArtifacts(runDigits);
    const api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      storageState: AUTH_FILE,
    });

    try {
      await cleanupResidualTestArtifacts(api);
      await cleanupArtifacts(api, artifacts);

      const terminals = await getJson<TerminalRow[]>(api, 'terminals');
      const selectedTerminals = pickOperationalTerminals(terminals);

      await openOperationsData(page);
      await page.locator('input[type="file"][accept=".xlsx,.csv"]').first().setInputFiles({
        name: `qa-trips-${runDigits}.csv`,
        mimeType: 'text/csv',
        buffer: buildTripsCsvBuffer(artifacts, selectedTerminals),
      });
      await expectSnackbarMessage(page, 'Importados: 2 registros');
      await expect(page.locator('body')).toContainText(String(artifacts.outboundTripId));
      await expect(page.locator('body')).toContainText(String(artifacts.returnTripId));

      await goToDriversTab(page);
      await page.locator('input[type="file"][accept=".xlsx,.csv"]').first().setInputFiles({
        name: `qa-drivers-${runDigits}.csv`,
        mimeType: 'text/csv',
        buffer: buildDriversCsvBuffer(artifacts),
      });
      await expectSnackbarMessage(page, 'Importados: 2 registros');
      await expect(page.locator('body')).toContainText(artifacts.driverIds[0]);
      await expect(page.locator('body')).toContainText(artifacts.driverIds[1]);

      const previousLatestSchedule = await getJson<{ id?: number } | null>(api, 'operations/latest-schedule');
      const previousLatestScheduleId = previousLatestSchedule?.id ?? 0;

      await page.goto(`${BASE}/operations/planner`, { waitUntil: 'networkidle' });
      const optimizeButton = page.getByRole('button', { name: /Executar Otimização/i });
      await expect(optimizeButton).toBeVisible({ timeout: 12_000 });

      const optimizeResponse = await api.post('operations/optimize', {
        data: {
          algorithm: 'hybrid_pipeline',
          operational_quality_mode: 'strict',
        },
      });
      expect(optimizeResponse.ok()).toBeTruthy();

      await expect.poll(async () => {
        const status = await getJson<{ status: string }>(api, 'operations/optimize/status');
        return status.status;
      }, { timeout: 180_000, intervals: [1000, 2000, 5000] }).toBe('completed');

      await expect.poll(async () => {
        const latest = await getJson<{ id?: number } | null>(api, 'operations/latest-schedule');
        return latest?.id ?? 0;
      }, { timeout: 180_000, intervals: [1000, 2000, 5000] }).toBeGreaterThan(previousLatestScheduleId);

      await page.reload({ waitUntil: 'networkidle' });
      await expect(page.locator('body')).toContainText('Cenário escolhido');

      const latestSchedule = await getJson<{ id: number; blocks?: unknown[]; duties?: unknown[] } | null>(api, 'operations/latest-schedule');
      expect(latestSchedule?.id).toBeTruthy();
      expect(latestSchedule?.blocks?.length ?? 0).toBeGreaterThan(0);
      expect(latestSchedule?.duties?.length ?? 0).toBeGreaterThan(0);

      await page.getByRole('button', { name: /Validar Escala/i }).click();
      const validationDialog = page.getByRole('dialog');
      await expect(validationDialog).toContainText('Validação da Escala');
      await expect(validationDialog).toContainText(/Válida|erro\(s\)/i);
      await page.keyboard.press('Escape');

      await page.goto(`${BASE}/operations/reporting`, { waitUntil: 'networkidle' });
      await expect(page.locator('body')).toContainText('Analytics & Relatórios');
      const reportingPageText = await page.locator('body').textContent();
      expect(reportingPageText ?? '').toMatch(/Dados reais|Métricas Atuais|Relatório com dados incompletos/i);

      const report = await postJson<{
        metrics: {
          totalTrips: number;
          assignedTrips: number;
          unassignedTrips: number;
          vehiclesUsed: number;
        };
      }>(api, `operations/reporting/generate/${latestSchedule!.id}`);

      expect(report.metrics.totalTrips).toBeGreaterThanOrEqual(2);
      expect(report.metrics.assignedTrips).toBeGreaterThan(0);
      expect(report.metrics.unassignedTrips).toBeGreaterThanOrEqual(0);
      expect(report.metrics.vehiclesUsed).toBeGreaterThan(0);
    } finally {
      await cleanupArtifacts(api, artifacts);
      await api.dispose();
    }
  });
});