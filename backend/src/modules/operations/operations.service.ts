import {
  Injectable,
  BadRequestException,
  NotFoundException,
} from '@nestjs/common';
import ExcelJS from 'exceljs';
import { TripRepository } from '../database/repositories/operations.repository';
import { DriverRepository } from '../database/repositories/operations.repository';
import { TenantContext } from '../../common/context/tenant-context';

// ─── Mapa de nomes de coluna aceitos → canônico camelCase ────────────────────
const TRIP_COL_MAP: Record<string, string> = {
  trip_id: 'tripId',
  tripid: 'tripId',
  id_viagem: 'tripId',
  viagem: 'tripId',
  line_id: 'lineCode',
  lineid: 'lineCode',
  linha: 'lineCode',
  id_linha: 'lineCode',
  line_code: 'lineCode',
  linecode: 'lineCode',
  codigo_linha: 'lineCode',
  pair_id: 'pairId',
  pairid: 'pairId',
  id_par: 'pairId',
  par: 'pairId',
  start_time: 'startTime',
  starttime: 'startTime',
  inicio: 'startTime',
  hora_inicio: 'startTime',
  partida: 'startTime',
  saida: 'startTime',
  end_time: 'endTime',
  endtime: 'endTime',
  fim: 'endTime',
  hora_fim: 'endTime',
  chegada: 'endTime',
  termino: 'endTime',
  origin_id: 'originId',
  originid: 'originId',
  origem: 'originId',
  id_origem: 'originId',
  destination_id: 'destinationId',
  destinationid: 'destinationId',
  destino: 'destinationId',
  id_destino: 'destinationId',
  distance_km: 'distanceKm',
  distancekm: 'distanceKm',
  distancia: 'distanceKm',
  duration: 'duration',
  duracao: 'duration',
  direction: 'direction',
  direcao: 'direction',
  sentido: 'direction',
};

const DRIVER_COL_MAP: Record<string, string> = {
  driver_id: 'driverId',
  driverid: 'driverId',
  matricula: 'driverId',
  id_motorista: 'driverId',
  name: 'name',
  nome: 'name',
  role: 'role',
  funcao: 'role',
  cargo: 'role',
  max_hours_per_day: 'maxHoursPerDay',
  maxhoursperday: 'maxHoursPerDay',
  max_horas: 'maxHoursPerDay',
  last_shift_end: 'lastShiftEnd',
  lastshiftend: 'lastShiftEnd',
};

function normalizeRow(
  raw: Record<string, any>,
  colMap: Record<string, string>,
): Record<string, any> {
  const result: Record<string, any> = {};
  for (const [key, val] of Object.entries(raw)) {
    const k = key.trim().toLowerCase().replace(/\s+/g, '_');
    result[colMap[k] ?? key] = typeof val === 'string' ? val.trim() : val;
  }
  return result;
}

function parseMinutes(val: any): number | null {
  if (val === undefined || val === null || val === '') return null;

  // Se o valor for um número (comum em arquivos Excel),
  // ele vem como fração do dia (ex: 0.5 = 12:00) ou minutos totais.
  if (typeof val === 'number') {
    // Excel envia tempo como fração de dia (1.0 = 24h). Aceitamos até 2.5 (~60h)
    // para suportar viagens que atravessam meia-noite ou múltiplos dias.
    if (val > 0 && val < 2.5) {
      return Math.round(val * 1440);
    }
    return Math.round(val);
  }

  const s = String(val).trim();

  // Suporte ao formato HH:MM ou HH:MM:SS
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) {
    const parts = s.split(':').map(Number);
    return (parts[0] || 0) * 60 + (parts[1] || 0);
  }

  // Se for uma string numérica (ex: "480" ou "0.5")
  const n = Number(s.replace(',', '.'));
  if (isNaN(n)) return null;

  // Se for uma fração de dia em formato string
  if (n > 0 && n < 1) {
    return Math.round(n * 1440);
  }

  return Math.round(n);
}

function safeInt(val: any, fallback = 0): number {
  const n = Number(val);
  return isNaN(n) || !isFinite(n) ? fallback : Math.round(n);
}

function safeFloat(val: any, fallback = 0): number {
  const n = Number(String(val ?? '').replace(',', '.'));
  return isNaN(n) || !isFinite(n) ? fallback : n;
}

@Injectable()
export class OperationsService {
  constructor(
    private readonly tripRepository: TripRepository,
    private readonly driverRepository: DriverRepository,
    private readonly tenantContext: TenantContext,
  ) {}

  private parseCsvBuffer(buffer: Buffer): any[] {
    const text = buffer
      .toString('utf-8')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n');
    const lines = text
      .trim()
      .split('\n')
      .filter((l) => l.trim());
    if (lines.length < 2) return [];

    // Detecta delimitador: ponto-e-vírgula ou vírgula
    const delim = lines[0].includes(';') ? ';' : ',';
    const headers = lines[0]
      .split(delim)
      .map((h) => h.trim().replace(/^"|"$/g, ''));

    return lines
      .slice(1)
      .map((line) => {
        const values = line
          .split(delim)
          .map((v) => v.trim().replace(/^"|"$/g, ''));
        const obj: Record<string, string> = {};
        headers.forEach((h, i) => {
          if (h) obj[h] = values[i] ?? '';
        });
        return obj;
      })
      .filter((row) => Object.values(row).some((v) => v !== ''));
  }

  async processUpload(fileBuffer: Buffer, type: 'trips' | 'drivers') {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Tenant não identificado');

    const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 MB — protege contra ReDoS em arquivos xlsx maliciosos
    if (fileBuffer.length > MAX_FILE_BYTES)
      throw new BadRequestException(
        'Arquivo excede o tamanho máximo permitido (10 MB)',
      );

    let rawData: any[];
    const header4 = fileBuffer.slice(0, 4).toString('hex');
    const isProbablyXlsx = header4 === '504b0304' || header4.startsWith('d0cf');

    if (isProbablyXlsx) {
      const workbook = new ExcelJS.Workbook();
      // @ts-expect-error — exceljs types predate @types/node 22 Buffer<ArrayBufferLike> generic
      await workbook.xlsx.load(fileBuffer);
      const worksheet = workbook.worksheets[0];
      if (!worksheet)
        throw new BadRequestException('Planilha não encontrada no arquivo');

      const headers: string[] = [];
      const data: Record<string, unknown>[] = [];
      worksheet.eachRow((row, rowNum) => {
        if (rowNum === 1) {
          row.eachCell({ includeEmpty: true }, (cell, col) => {
            // eslint-disable-next-line @typescript-eslint/no-base-to-string
            headers[col - 1] = String(cell.value ?? '');
          });
        } else {
          const obj: Record<string, unknown> = {};
          let hasValue = false;
          row.eachCell({ includeEmpty: true }, (cell, col) => {
            const h = headers[col - 1];
            if (!h) return;
            const v = cell.value;
            // Resolve complex ExcelJS cell value types to primitive
            let resolved: unknown = '';
            if (v === null || v === undefined) {
              resolved = '';
            } else if (typeof v === 'object' && 'richText' in (v as object)) {
              resolved = (v as { richText: { text: string }[] }).richText
                .map((rt) => rt.text)
                .join('');
            } else if (typeof v === 'object' && 'result' in (v as object)) {
              // eslint-disable-next-line @typescript-eslint/no-base-to-string
              resolved = String((v as { result: unknown }).result ?? '');
            } else {
              resolved = v;
            }
            obj[h] = resolved;
            if (resolved !== '' && resolved !== null) hasValue = true;
          });
          if (hasValue) data.push(obj);
        }
      });
      rawData = data;
    } else {
      rawData = this.parseCsvBuffer(fileBuffer);
    }

    if (rawData.length === 0)
      throw new BadRequestException('Arquivo vazio ou sem dados válidos');

    if (type === 'trips') return this.processTrips(rawData, companyId);
    return this.processDrivers(rawData, companyId);
  }

  private async processTrips(rawData: any[], companyId: number) {
    const errors: string[] = [];
    const tripsToSave: any[] = [];

    rawData.forEach((raw, idx) => {
      const item = normalizeRow(raw, TRIP_COL_MAP);
      const row = idx + 2;

      const startTime = parseMinutes(item.startTime);
      const endTime = parseMinutes(item.endTime);

      if (startTime === null || endTime === null) {
        errors.push(
          `Linha ${row}: Horário inválido (Início: "${item.startTime}", Fim: "${item.endTime}")`,
        );
        return;
      }

      // Nota: endTime pode ser < startTime para viagens que atravessam meia-noite ou múltiplos dias
      // Isso é tratado corretamente no banco de dados e frontend

      const duration = item.duration
        ? safeInt(item.duration)
        : endTime - startTime;

      tripsToSave.push(
        this.tripRepository.create({
          companyId,
          tripId: item.tripId ? safeInt(item.tripId) : undefined,
          lineCode: item.lineCode ? String(item.lineCode) : undefined,
          lineId: item.lineId ? safeInt(item.lineId) : undefined,
          pairId: item.pairId ? String(item.pairId) : undefined,
          startTime,
          endTime,
          originId: safeInt(item.originId),
          destinationId: safeInt(item.destinationId),
          distanceKm: safeFloat(item.distanceKm),
          duration,
          direction: item.direction
            ? String(item.direction).toUpperCase()
            : undefined,
        }),
      );
    });

    if (errors.length > 0 && tripsToSave.length === 0) {
      throw new BadRequestException({ message: 'Arquivo inválido', errors });
    }

    const saved = await this.tripRepository.save(tripsToSave);
    return {
      inserted: saved.length,
      skipped: errors.length,
      errors: errors.length > 0 ? errors.slice(0, 10) : undefined,
    };
  }

  private async processDrivers(rawData: any[], companyId: number) {
    const errors: string[] = [];
    const driversToSave: any[] = [];

    rawData.forEach((raw, idx) => {
      const item = normalizeRow(raw, DRIVER_COL_MAP);
      const row = idx + 2;

      if (!item.driverId) {
        errors.push(`Linha ${row}: driverId ausente`);
        return;
      }
      if (!item.name) {
        errors.push(`Linha ${row}: name ausente`);
        return;
      }

      driversToSave.push(
        this.driverRepository.create({
          companyId,
          driverId: String(item.driverId),
          name: String(item.name),
          role: String(item.role || 'Motorista'),
          maxHoursPerDay: safeInt(item.maxHoursPerDay, 480),
          lastShiftEnd: safeInt(item.lastShiftEnd, 0),
          metadata: {},
        }),
      );
    });

    if (errors.length > 0 && driversToSave.length === 0) {
      throw new BadRequestException({ message: 'Arquivo inválido', errors });
    }

    const saved = await this.driverRepository.save(driversToSave);
    return {
      inserted: saved.length,
      skipped: errors.length,
      errors: errors.length > 0 ? errors.slice(0, 10) : undefined,
    };
  }

  async getTrips(page: number = 1, limit: number = 100, companyId?: number) {
    return this.tripRepository.find({
      where: companyId ? { companyId } : undefined,
      skip: (page - 1) * limit,
      take: limit,
      order: { startTime: 'ASC' },
    });
  }

  async getDrivers(companyId?: number) {
    return this.driverRepository.find({
      where: companyId ? { companyId } : undefined,
      order: { name: 'ASC' },
    });
  }

  async createDriver(data: Record<string, any>, companyId: number) {
    if (!data.driverId || !data.name) {
      throw new BadRequestException('driverId e name são obrigatórios');
    }
    const driver = this.driverRepository.create({
      companyId,
      driverId: String(data.driverId),
      name: String(data.name),
      role: String(data.role || 'Motorista'),
      maxHoursPerDay: Number(data.maxHoursPerDay || 480),
      lastShiftEnd: Number(data.lastShiftEnd || 0),
      metadata: data.metadata || {},
    });
    return this.driverRepository.save(driver);
  }

  async updateDriver(id: number, data: Record<string, any>, companyId: number) {
    const driver = await this.driverRepository.findOne({
      where: { id, companyId },
    });
    if (!driver) throw new NotFoundException('Motorista não encontrado');
    Object.assign(driver, {
      driverId:
        data.driverId !== undefined ? String(data.driverId) : driver.driverId,
      name: data.name !== undefined ? String(data.name) : driver.name,
      role: data.role !== undefined ? String(data.role) : driver.role,
      maxHoursPerDay:
        data.maxHoursPerDay !== undefined
          ? Number(data.maxHoursPerDay)
          : driver.maxHoursPerDay,
      lastShiftEnd:
        data.lastShiftEnd !== undefined
          ? Number(data.lastShiftEnd)
          : driver.lastShiftEnd,
    });
    return this.driverRepository.save(driver);
  }

  async deleteDriver(id: number, companyId: number) {
    const driver = await this.driverRepository.findOne({
      where: { id, companyId },
    });
    if (!driver) throw new NotFoundException('Motorista não encontrado');
    await this.driverRepository.remove(driver);
    return { deleted: true, id };
  }

  private async nextTripId(companyId: number): Promise<number> {
    const last = await this.tripRepository.findOne({
      where: { companyId },
      order: { tripId: 'DESC' },
    });
    return (last?.tripId ?? 0) + 1;
  }

  async createTrip(data: Record<string, any>, companyId: number) {
    if (data.startTime === undefined || data.endTime === undefined) {
      throw new BadRequestException('startTime e endTime são obrigatórios');
    }

    const startTime = parseMinutes(data.startTime) ?? safeInt(data.startTime);
    const endTime = parseMinutes(data.endTime) ?? safeInt(data.endTime);

    if (endTime < startTime) {
      throw new BadRequestException(
        `Hora de fim não pode ser anterior à hora de início (início: ${data.startTime}, fim: ${data.endTime})`,
      );
    }

    const calcDuration = endTime - startTime;
    const duration = data.duration ? safeInt(data.duration) : calcDuration;

    const roundTrip = data.roundTrip === true || data.roundTrip === 'true';
    const pairId = roundTrip ? `pair-${Date.now()}` : (data.pairId ?? null);

    const baseId = await this.nextTripId(companyId);
    const trip = this.tripRepository.create({
      companyId,
      tripId: baseId,
      lineId: data.lineId ? safeInt(data.lineId) : undefined,
      lineCode: data.lineCode ?? null,
      pairId,
      startTime,
      endTime,
      originId: safeInt(data.originId),
      destinationId: safeInt(data.destinationId),
      distanceKm: safeFloat(data.distanceKm),
      duration,
      direction: data.direction || 'IDA',
      // Relief points (rendição) — opcional. Marca terminal como ponto de troca de motorista
      // (`isReliefPoint`) e/ou define ponto intermediário no meio da viagem para split em 2.
      isReliefPoint:
        data.isReliefPoint === true || data.isReliefPoint === 'true',
      reliefPointId:
        data.reliefPointId !== undefined &&
        data.reliefPointId !== null &&
        data.reliefPointId !== ''
          ? safeInt(data.reliefPointId)
          : null,
      midTripReliefPointId:
        data.midTripReliefPointId !== undefined &&
        data.midTripReliefPointId !== null &&
        data.midTripReliefPointId !== ''
          ? safeInt(data.midTripReliefPointId)
          : null,
      midTripReliefOffsetMinutes:
        data.midTripReliefOffsetMinutes !== undefined &&
        data.midTripReliefOffsetMinutes !== null &&
        data.midTripReliefOffsetMinutes !== ''
          ? safeInt(data.midTripReliefOffsetMinutes)
          : null,
      midTripReliefDistanceRatio:
        data.midTripReliefDistanceRatio !== undefined &&
        data.midTripReliefDistanceRatio !== null &&
        data.midTripReliefDistanceRatio !== ''
          ? safeFloat(data.midTripReliefDistanceRatio)
          : null,
      midTripReliefElevationRatio:
        data.midTripReliefElevationRatio !== undefined &&
        data.midTripReliefElevationRatio !== null &&
        data.midTripReliefElevationRatio !== ''
          ? safeFloat(data.midTripReliefElevationRatio)
          : null,
      depotId:
        data.depotId !== undefined &&
        data.depotId !== null &&
        data.depotId !== ''
          ? safeInt(data.depotId)
          : null,
    });
    const saved = await this.tripRepository.save(trip);

    if (roundTrip) {
      // Support explicit return-trip fields from frontend
      const retStart =
        data.returnStartTime !== undefined
          ? (parseMinutes(data.returnStartTime) ??
            safeInt(data.returnStartTime))
          : endTime;
      const retEnd =
        data.returnEndTime !== undefined
          ? (parseMinutes(data.returnEndTime) ?? safeInt(data.returnEndTime))
          : endTime + duration;
      const retCalcDuration =
        retEnd >= retStart ? retEnd - retStart : 1440 + retEnd - retStart;
      const retDuration = data.returnDuration
        ? safeInt(data.returnDuration)
        : retCalcDuration;

      const returnId = await this.nextTripId(companyId);
      const returnTrip = this.tripRepository.create({
        companyId,
        tripId: returnId,
        lineId: trip.lineId,
        lineCode: trip.lineCode,
        pairId,
        startTime: retStart,
        endTime: retEnd,
        originId: data.returnOriginId
          ? safeInt(data.returnOriginId)
          : safeInt(data.destinationId),
        destinationId: data.returnDestinationId
          ? safeInt(data.returnDestinationId)
          : safeInt(data.originId),
        distanceKm: data.returnDistanceKm
          ? safeFloat(data.returnDistanceKm)
          : trip.distanceKm,
        duration: retDuration,
        direction: 'VOLTA',
      });
      const returnSaved = await this.tripRepository.save(returnTrip);
      return { trips: [saved, returnSaved], pairId };
    }

    return saved;
  }

  async updateTrip(id: number, data: Record<string, any>, companyId: number) {
    const trip = await this.tripRepository.findOne({
      where: { id, companyId },
    });
    if (!trip) throw new NotFoundException('Viagem não encontrada');

    const newStartTime =
      data.startTime !== undefined
        ? (parseMinutes(data.startTime) ?? safeInt(data.startTime))
        : trip.startTime;
    const newEndTime =
      data.endTime !== undefined
        ? (parseMinutes(data.endTime) ?? safeInt(data.endTime))
        : trip.endTime;

    if (newEndTime < newStartTime) {
      throw new BadRequestException(
        `Hora de fim não pode ser anterior à hora de início`,
      );
    }

    const numOrNull = (v: any): number | null =>
      v === undefined || v === null || v === '' ? null : safeInt(v);
    const floatOrNull = (v: any): number | null =>
      v === undefined || v === null || v === '' ? null : safeFloat(v);

    Object.assign(trip, {
      lineId:
        data.lineId !== undefined
          ? data.lineId
            ? safeInt(data.lineId)
            : null
          : trip.lineId,
      lineCode: data.lineCode !== undefined ? data.lineCode : trip.lineCode,
      startTime: newStartTime,
      endTime: newEndTime,
      originId:
        data.originId !== undefined ? safeInt(data.originId) : trip.originId,
      destinationId:
        data.destinationId !== undefined
          ? safeInt(data.destinationId)
          : trip.destinationId,
      distanceKm:
        data.distanceKm !== undefined
          ? safeFloat(data.distanceKm)
          : trip.distanceKm,
      duration:
        data.duration !== undefined ? safeInt(data.duration) : trip.duration,
      direction: data.direction !== undefined ? data.direction : trip.direction,
      isReliefPoint:
        data.isReliefPoint !== undefined
          ? data.isReliefPoint === true || data.isReliefPoint === 'true'
          : trip.isReliefPoint,
      reliefPointId:
        data.reliefPointId !== undefined
          ? numOrNull(data.reliefPointId)
          : trip.reliefPointId,
      midTripReliefPointId:
        data.midTripReliefPointId !== undefined
          ? numOrNull(data.midTripReliefPointId)
          : trip.midTripReliefPointId,
      midTripReliefOffsetMinutes:
        data.midTripReliefOffsetMinutes !== undefined
          ? numOrNull(data.midTripReliefOffsetMinutes)
          : trip.midTripReliefOffsetMinutes,
      midTripReliefDistanceRatio:
        data.midTripReliefDistanceRatio !== undefined
          ? floatOrNull(data.midTripReliefDistanceRatio)
          : trip.midTripReliefDistanceRatio,
      midTripReliefElevationRatio:
        data.midTripReliefElevationRatio !== undefined
          ? floatOrNull(data.midTripReliefElevationRatio)
          : trip.midTripReliefElevationRatio,
      depotId:
        data.depotId !== undefined ? numOrNull(data.depotId) : trip.depotId,
    });
    return this.tripRepository.save(trip);
  }

  async deleteTrip(id: number, companyId: number) {
    const trip = await this.tripRepository.findOne({
      where: { id, companyId },
    });
    if (!trip) throw new NotFoundException('Viagem não encontrada');
    await this.tripRepository.remove(trip);
    return { deleted: true, id };
  }

  async clearAllTrips(companyId: number) {
    const trips = await this.tripRepository.find({ where: { companyId } });
    await this.tripRepository.remove(trips);
    return { deleted: trips.length };
  }
}
