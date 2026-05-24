import path from 'node:path';
import { test, expect, request as playwrightRequest, type APIRequestContext, type Page } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3005';
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:3001/api/v1/';
const AUTH_FILE = path.join(__dirname, '.auth/user.json');

type TripRow = {
  id: number;
  tripId: number | null;
  lineId: number | null;
  lineCode: string | null;
  pairId: string | null;
};

type DriverRow = {
  id: number;
  driverId: string;
};

type LineRow = {
  id: number;
  lineId: string;
};

type TerminalRow = {
  id: number;
  terminalId: string;
  isDepot: boolean;
};

type ReportRow = {
  id: number;
  name: string;
};

type RegressionArtifacts = {
  outboundTripId: number;
  returnTripId: number;
  pairId: string;
  lineCode: string;
  driverId: string;
  reportName: string;
  gtfsRouteId: string;
  gtfsTripId: string;
  gtfsStopIds: [string, string];
};

type SelectedTerminals = {
  originId: number;
  destinationId: number;
};

const CRC32_TABLE = buildCrc32Table();

function buildCrc32Table(): Uint32Array {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let crc = index;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc & 1) === 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
    table[index] = crc >>> 0;
  }
  return table;
}

function crc32(buffer: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = CRC32_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// Gera um ZIP STORED mínimo, suficiente para o parser GTFS do backend.
function buildStoredZip(files: Record<string, string>): Buffer {
  const localParts: Buffer[] = [];
  const centralParts: Buffer[] = [];
  let offset = 0;

  for (const [name, content] of Object.entries(files)) {
    const fileName = Buffer.from(name, 'utf8');
    const payload = Buffer.from(content, 'utf8');
    const payloadCrc = crc32(payload);

    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0, 6);
    localHeader.writeUInt16LE(0, 8);
    localHeader.writeUInt16LE(0, 10);
    localHeader.writeUInt16LE(0, 12);
    localHeader.writeUInt32LE(payloadCrc, 14);
    localHeader.writeUInt32LE(payload.length, 18);
    localHeader.writeUInt32LE(payload.length, 22);
    localHeader.writeUInt16LE(fileName.length, 26);
    localHeader.writeUInt16LE(0, 28);

    localParts.push(localHeader, fileName, payload);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0, 8);
    centralHeader.writeUInt16LE(0, 10);
    centralHeader.writeUInt16LE(0, 12);
    centralHeader.writeUInt16LE(0, 14);
    centralHeader.writeUInt32LE(payloadCrc, 16);
    centralHeader.writeUInt32LE(payload.length, 20);
    centralHeader.writeUInt32LE(payload.length, 24);
    centralHeader.writeUInt16LE(fileName.length, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(0, 38);
    centralHeader.writeUInt32LE(offset, 42);

    centralParts.push(centralHeader, fileName);
    offset += localHeader.length + fileName.length + payload.length;
  }

  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const endOfCentralDirectory = Buffer.alloc(22);
  endOfCentralDirectory.writeUInt32LE(0x06054b50, 0);
  endOfCentralDirectory.writeUInt16LE(0, 4);
  endOfCentralDirectory.writeUInt16LE(0, 6);
  endOfCentralDirectory.writeUInt16LE(centralParts.length / 2, 8);
  endOfCentralDirectory.writeUInt16LE(centralParts.length / 2, 10);
  endOfCentralDirectory.writeUInt32LE(centralSize, 12);
  endOfCentralDirectory.writeUInt32LE(offset, 16);
  endOfCentralDirectory.writeUInt16LE(0, 20);

  return Buffer.concat([...localParts, ...centralParts, endOfCentralDirectory]);
}

function buildArtifacts(runDigits: string): RegressionArtifacts {
  const tripBase = 900000 + Number(runDigits.slice(-4)) * 10;
  return {
    outboundTripId: tripBase,
    returnTripId: tripBase + 1,
    pairId: `E2E-PAIR-${runDigits}`,
    lineCode: `E2E-L-${runDigits}`,
    driverId: `DRV-E2E-${runDigits}`,
    reportName: `E2E Report ${runDigits}`,
    gtfsRouteId: `GTFS-R-${runDigits}`,
    gtfsTripId: `GTFS-TRIP-${runDigits}`,
    gtfsStopIds: [`GTFS-S1-${runDigits}`, `GTFS-S2-${runDigits}`],
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

function buildTripsCsvBuffer(artifacts: RegressionArtifacts, terminals: SelectedTerminals): Buffer {
  return Buffer.from(
    [
      'trip_id,line_code,pair_id,direction,start_time,end_time,origin_id,destination_id,distance_km,duration',
      `${artifacts.outboundTripId},${artifacts.lineCode},${artifacts.pairId},IDA,05:10,05:55,${terminals.originId},${terminals.destinationId},11.8,45`,
      `${artifacts.returnTripId},${artifacts.lineCode},${artifacts.pairId},VOLTA,06:05,06:50,${terminals.destinationId},${terminals.originId},11.8,45`,
    ].join('\n'),
    'utf8',
  );
}

function buildDriversCsvBuffer(artifacts: RegressionArtifacts): Buffer {
  return Buffer.from(
    [
      'driver_id,name,role,max_hours_per_day,last_shift_end',
      `${artifacts.driverId},Motorista E2E ${artifacts.driverId},Motorista,510,300`,
    ].join('\n'),
    'utf8',
  );
}

function buildGtfsZipBuffer(artifacts: RegressionArtifacts): Buffer {
  return buildStoredZip({
    'stops.txt': [
      'stop_id,stop_name,stop_lat,stop_lon',
      `${artifacts.gtfsStopIds[0]},Terminal GTFS Alpha ${artifacts.gtfsStopIds[0]},-12.9401,-38.4301`,
      `${artifacts.gtfsStopIds[1]},Terminal GTFS Beta ${artifacts.gtfsStopIds[1]},-12.9502,-38.4402`,
    ].join('\n'),
    'routes.txt': [
      'route_id,route_short_name,route_long_name',
      `${artifacts.gtfsRouteId},GTFS ${artifacts.gtfsRouteId.slice(-4)},Linha GTFS ${artifacts.gtfsRouteId}`,
    ].join('\n'),
    'trips.txt': [
      'trip_id,route_id,direction_id',
      `${artifacts.gtfsTripId},${artifacts.gtfsRouteId},0`,
    ].join('\n'),
    'stop_times.txt': [
      'trip_id,stop_id,departure_time,arrival_time,stop_sequence',
      `${artifacts.gtfsTripId},${artifacts.gtfsStopIds[0]},08:00:00,08:00:00,1`,
      `${artifacts.gtfsTripId},${artifacts.gtfsStopIds[1]},08:35:00,08:35:00,2`,
    ].join('\n'),
  });
}

async function getJson<T>(api: APIRequestContext, url: string): Promise<T> {
  const response = await api.get(url);
  expect(response.ok(), `GET ${url} should succeed`).toBeTruthy();
  return (await response.json()) as T;
}

async function createEphemeralReport(api: APIRequestContext, reportName: string): Promise<number> {
  const response = await api.post('custom-reports', {
    data: {
      name: reportName,
      description: 'Relatório efêmero criado pelo spec de regressão E2E.',
      metrics: ['completedRuns', 'totalTrips'],
      filters: { dateRangeDays: 30 },
    },
  });
  expect(response.ok(), 'custom report creation should succeed').toBeTruthy();
  const report = (await response.json()) as { id: number };
  return report.id;
}

async function cleanupArtifacts(api: APIRequestContext, artifacts: RegressionArtifacts): Promise<void> {
  const [trips, drivers, lines, terminals, reports] = await Promise.all([
    getJson<TripRow[]>(api, 'operations/trips?limit=1000'),
    getJson<DriverRow[]>(api, 'operations/drivers'),
    getJson<LineRow[]>(api, 'lines'),
    getJson<TerminalRow[]>(api, 'terminals'),
    getJson<ReportRow[]>(api, 'custom-reports'),
  ]);

  const gtfsLine = lines.find((line) => line.lineId === artifacts.gtfsRouteId) ?? null;
  const tripDeletes = trips.filter((trip) => {
    if (trip.tripId === artifacts.outboundTripId || trip.tripId === artifacts.returnTripId) {
      return true;
    }
    if (trip.pairId === artifacts.pairId) {
      return true;
    }
    return gtfsLine !== null && trip.lineId === gtfsLine.id;
  });

  for (const trip of tripDeletes) {
    await api.delete(`operations/trips/${trip.id}`);
  }

  for (const driver of drivers.filter((row) => row.driverId === artifacts.driverId)) {
    await api.delete(`operations/drivers/${driver.id}`);
  }

  for (const report of reports.filter((row) => row.name === artifacts.reportName)) {
    await api.delete(`custom-reports/${report.id}`);
  }

  if (gtfsLine !== null) {
    await api.delete(`lines/${gtfsLine.id}`);
  }

  for (const terminal of terminals.filter((row) => artifacts.gtfsStopIds.includes(row.terminalId as (typeof artifacts.gtfsStopIds)[number]))) {
    await api.delete(`terminals/${terminal.id}`);
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

async function expectSnackbarMessage(page: Page, message: string): Promise<void> {
  await expect(page.locator('.MuiSnackbar-root [role="alert"]').last()).toContainText(message);
}

test.describe('Operations import/export/edit/delete regression', () => {
  test('covers CSV import, GTFS import, exports, edit/delete and automatic cleanup', async ({ page }, testInfo) => {
    test.setTimeout(180_000);
    test.slow();

    const runDigits = `${Date.now()}${testInfo.workerIndex}${testInfo.retry}`.slice(-8);
    const artifacts = buildArtifacts(runDigits);
    const api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      storageState: AUTH_FILE,
    });

    try {
      await cleanupArtifacts(api, artifacts);

      const terminals = await getJson<TerminalRow[]>(api, 'terminals');
      const selectedTerminals = pickOperationalTerminals(terminals);

      const tripsCsvBuffer = buildTripsCsvBuffer(artifacts, selectedTerminals);
      const driversCsvBuffer = buildDriversCsvBuffer(artifacts);
      const gtfsZipBuffer = buildGtfsZipBuffer(artifacts);

      await openOperationsData(page);

      await page.locator('button').filter({ hasText: /^Exportar Layout$/ }).first().click();
      await expectSnackbarMessage(page, 'Layout exportado com sucesso!');

      await page.locator('input[type="file"][accept=".xlsx,.csv"]').first().setInputFiles({
        name: `trips-${runDigits}.csv`,
        mimeType: 'text/csv',
        buffer: tripsCsvBuffer,
      });
      await expectSnackbarMessage(page, 'Importados: 2 registros');
      await expect(page.locator('body')).toContainText(String(artifacts.outboundTripId));
      await expect(page.locator('body')).toContainText(String(artifacts.returnTripId));

      await goToDriversTab(page);
      await page.locator('input[type="file"][accept=".xlsx,.csv"]').first().setInputFiles({
        name: `drivers-${runDigits}.csv`,
        mimeType: 'text/csv',
        buffer: driversCsvBuffer,
      });
      await expectSnackbarMessage(page, 'Importados: 1 registros');
      await expect(page.locator('body')).toContainText(artifacts.driverId);

      await page.locator('[role="tab"]').filter({ hasText: 'Viagens' }).first().click();
      await expect(page.locator('body')).toContainText('Viagens Carregadas');
      await page.locator('input[type="file"][accept=".zip"]').setInputFiles({
        name: `gtfs-${runDigits}.zip`,
        mimeType: 'application/zip',
        buffer: gtfsZipBuffer,
      });
      await expectSnackbarMessage(page, 'GTFS importado: 2 terminais, 1 linhas, 1 viagens');

      await expect.poll(async () => {
        const lines = await getJson<LineRow[]>(api, 'lines');
        return lines.some((line) => line.lineId === artifacts.gtfsRouteId);
      }).toBe(true);

      const updatedTripRow = page.locator('[role="row"]').filter({ hasText: String(artifacts.outboundTripId) }).first();
      await updatedTripRow.getByRole('button', { name: 'Editar' }).click();
      const tripDialog = page.getByRole('dialog');
      await expect(tripDialog).toContainText('Editar Viagem');
      const timeInputs = tripDialog.locator('input[placeholder="HH:MM"]');
      await timeInputs.nth(1).fill('06:02');
      await timeInputs.nth(3).fill('07:12');
      await tripDialog.getByRole('button', { name: /^Salvar$/ }).click();
      await expectSnackbarMessage(page, 'Viagem e par atualizados!');
      await expect(page.locator('[role="row"]').filter({ hasText: String(artifacts.outboundTripId) }).first()).toContainText('06:02');
      await expect(page.locator('[role="row"]').filter({ hasText: String(artifacts.returnTripId) }).first()).toContainText('07:12');

      await goToDriversTab(page);
      const driverRow = page.locator('[role="row"]').filter({ hasText: artifacts.driverId }).first();
      await driverRow.getByRole('button', { name: 'Editar' }).click();
      const driverDialog = page.getByRole('dialog');
      await expect(driverDialog).toContainText('Editar Motorista');
      const numericInputs = driverDialog.locator('input[type="number"]');
      await numericInputs.nth(0).fill('525');
      await numericInputs.nth(1).fill('330');
      await driverDialog.getByRole('button', { name: /^Salvar$/ }).click();
      await expectSnackbarMessage(page, 'Motorista atualizado!');
      await expect(page.locator('[role="row"]').filter({ hasText: artifacts.driverId }).first()).toContainText('05:30');

      const reportId = await createEphemeralReport(api, artifacts.reportName);
      await page.goto(`${BASE}/operations/reporting/custom`, { waitUntil: 'networkidle' });
      const reportCard = page.locator('.MuiCard-root').filter({ hasText: artifacts.reportName }).first();
      await expect(reportCard).toBeVisible();

      const csvResponsePromise = page.waitForResponse(
        (response) => response.url().includes(`/api/v1/custom-reports/${reportId}/export.csv`) && response.status() === 200,
      );
      await reportCard.getByRole('button', { name: /^CSV$/ }).click();
      const csvResponse = await csvResponsePromise;
      expect(csvResponse.headers()['content-type']).toContain('text/csv');
      expect((await csvResponse.body()).length).toBeGreaterThan(0);

      const pdfResponsePromise = page.waitForResponse(
        (response) => response.url().includes(`/api/v1/custom-reports/${reportId}/export.pdf`) && response.status() === 200,
      );
      await reportCard.getByRole('button', { name: /^PDF$/ }).click();
      const pdfResponse = await pdfResponsePromise;
      expect(pdfResponse.headers()['content-type']).toContain('application/pdf');
      expect((await pdfResponse.body()).length).toBeGreaterThan(0);

      await openOperationsData(page);

      page.once('dialog', async (dialog) => {
        await dialog.accept();
      });
      await page.locator('[role="row"]').filter({ hasText: String(artifacts.outboundTripId) }).first().getByRole('button', { name: 'Excluir' }).click();
      await expectSnackbarMessage(page, 'Viagem e par excluídos.');
      await expect(page.locator('body')).not.toContainText(String(artifacts.outboundTripId));
      await expect(page.locator('body')).not.toContainText(String(artifacts.returnTripId));

      const freshTrips = await getJson<TripRow[]>(api, 'operations/trips?limit=1000');
      const gtfsLine = (await getJson<LineRow[]>(api, 'lines')).find((line) => line.lineId === artifacts.gtfsRouteId);
      const gtfsTrip = freshTrips.find((trip) => gtfsLine !== undefined && trip.lineId === gtfsLine.id);
      expect(gtfsTrip, 'GTFS trip should exist before UI deletion').toBeTruthy();

      const gtfsTripRow = page
        .locator('[role="row"]')
        .filter({ hasText: 'IDA' })
        .filter({ hasText: '08:00' })
        .filter({ hasText: '08:35' });

      await expect(gtfsTripRow).toHaveCount(1);

      page.once('dialog', async (dialog) => {
        await dialog.accept();
      });
      await gtfsTripRow.first().getByRole('button', { name: 'Excluir' }).click();
      await expectSnackbarMessage(page, 'Viagem excluída.');

      await goToDriversTab(page);
      page.once('dialog', async (dialog) => {
        await dialog.accept();
      });
      await page.locator('[role="row"]').filter({ hasText: artifacts.driverId }).first().getByRole('button', { name: 'Excluir' }).click();
      await expectSnackbarMessage(page, 'Motorista excluído.');
      await expect(page.locator('body')).not.toContainText(artifacts.driverId);
    } finally {
      await cleanupArtifacts(api, artifacts);

      const [remainingTrips, remainingDrivers, remainingLines, remainingTerminals, remainingReports] = await Promise.all([
        getJson<TripRow[]>(api, 'operations/trips?limit=1000'),
        getJson<DriverRow[]>(api, 'operations/drivers'),
        getJson<LineRow[]>(api, 'lines'),
        getJson<TerminalRow[]>(api, 'terminals'),
        getJson<ReportRow[]>(api, 'custom-reports'),
      ]);

      expect(remainingTrips.some((trip) => trip.tripId === artifacts.outboundTripId || trip.tripId === artifacts.returnTripId || trip.pairId === artifacts.pairId)).toBeFalsy();
      expect(remainingDrivers.some((driver) => driver.driverId === artifacts.driverId)).toBeFalsy();
      expect(remainingLines.some((line) => line.lineId === artifacts.gtfsRouteId)).toBeFalsy();
      expect(remainingTerminals.some((terminal) => artifacts.gtfsStopIds.includes(terminal.terminalId as (typeof artifacts.gtfsStopIds)[number]))).toBeFalsy();
      expect(remainingReports.some((report) => report.name === artifacts.reportName)).toBeFalsy();

      await api.dispose();
    }
  });
});