import { Injectable, BadRequestException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
// eslint-disable-next-line @typescript-eslint/no-require-imports
const AdmZip = require('adm-zip');
import { Terminal } from '../database/entities/terminal.entity';
import { Line } from '../database/entities/line.entity';
import { Trip } from '../database/entities/trip.entity';
import { TenantContext } from '../../common/context/tenant-context';

export interface GtfsImportResult {
  imported: { terminals: number; lines: number; trips: number };
  skipped: number;
  errors: string[];
}

// Raw GTFS row types
interface GtfsStop { stop_id: string; stop_name: string; stop_lat?: string; stop_lon?: string; }
interface GtfsRoute { route_id: string; route_short_name?: string; route_long_name?: string; }
interface GtfsTrip { trip_id: string; route_id: string; direction_id?: string; }
interface GtfsStopTime { trip_id: string; stop_id: string; departure_time: string; arrival_time: string; stop_sequence: string; }

@Injectable()
export class GtfsImportService {
  constructor(
    @InjectRepository(Terminal) private terminalRepo: Repository<Terminal>,
    @InjectRepository(Line) private lineRepo: Repository<Line>,
    @InjectRepository(Trip) private tripRepo: Repository<Trip>,
    private readonly tenantContext: TenantContext,
  ) {}

  async importFromBuffer(buffer: Buffer): Promise<GtfsImportResult> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) throw new BadRequestException('Empresa não identificada.');

    let zip: AdmZip;
    try {
      zip = new AdmZip(buffer);
    } catch {
      throw new BadRequestException('Arquivo inválido — esperado ZIP com dados GTFS.');
    }

    const errors: string[] = [];

    const stopsRaw = this._readEntry(zip, 'stops.txt');
    const routesRaw = this._readEntry(zip, 'routes.txt');
    const tripsRaw = this._readEntry(zip, 'trips.txt');
    const stopTimesRaw = this._readEntry(zip, 'stop_times.txt');

    if (!stopsRaw) throw new BadRequestException('stops.txt não encontrado no ZIP.');
    if (!routesRaw) throw new BadRequestException('routes.txt não encontrado no ZIP.');
    if (!tripsRaw) throw new BadRequestException('trips.txt não encontrado no ZIP.');
    if (!stopTimesRaw) throw new BadRequestException('stop_times.txt não encontrado no ZIP.');

    const stops = this._parseCsv<GtfsStop>(stopsRaw);
    const routes = this._parseCsv<GtfsRoute>(routesRaw);
    const gtfsTrips = this._parseCsv<GtfsTrip>(tripsRaw);
    const stopTimes = this._parseCsv<GtfsStopTime>(stopTimesRaw);

    // ── 1. Terminals ───────────────────────────────────────────────────────
    const stopIdToDbId = new Map<string, number>();
    let terminalCount = 0;
    let skipped = 0;

    for (const stop of stops) {
      if (!stop.stop_id || !stop.stop_name) { skipped++; continue; }
      const existing = await this.terminalRepo.findOne({
        where: { terminalId: stop.stop_id, companyId },
      });
      if (existing) {
        stopIdToDbId.set(stop.stop_id, existing.id);
        skipped++;
        continue;
      }
      const terminal = this.terminalRepo.create({
        companyId,
        terminalId: stop.stop_id,
        name: stop.stop_name.trim(),
        latitude: stop.stop_lat ? parseFloat(stop.stop_lat) : undefined,
        longitude: stop.stop_lon ? parseFloat(stop.stop_lon) : undefined,
      });
      const saved = await this.terminalRepo.save(terminal);
      stopIdToDbId.set(stop.stop_id, saved.id);
      terminalCount++;
    }

    // ── 2. Lines ───────────────────────────────────────────────────────────
    const routeIdToDbId = new Map<string, number>();
    let lineCount = 0;

    for (const route of routes) {
      if (!route.route_id) { skipped++; continue; }
      const existing = await this.lineRepo.findOne({
        where: { lineId: route.route_id, companyId },
      });
      if (existing) {
        routeIdToDbId.set(route.route_id, existing.id);
        skipped++;
        continue;
      }
      const name = (route.route_short_name || route.route_long_name || route.route_id).trim();
      const line = this.lineRepo.create({
        companyId,
        lineId: route.route_id,
        name,
        isActive: true,
      });
      const saved = await this.lineRepo.save(line);
      routeIdToDbId.set(route.route_id, saved.id);
      lineCount++;
    }

    // ── 3. Trips ───────────────────────────────────────────────────────────
    // Group stop_times by trip_id and sort by stop_sequence
    const stopTimesByTrip = new Map<string, GtfsStopTime[]>();
    for (const st of stopTimes) {
      if (!st.trip_id) continue;
      if (!stopTimesByTrip.has(st.trip_id)) stopTimesByTrip.set(st.trip_id, []);
      stopTimesByTrip.get(st.trip_id)!.push(st);
    }
    for (const arr of stopTimesByTrip.values()) {
      arr.sort((a, b) => parseInt(a.stop_sequence) - parseInt(b.stop_sequence));
    }

    // Build a map: gtfs trip_id → route_id
    const gtfsTripRouteMap = new Map<string, string>();
    const gtfsTripDirectionMap = new Map<string, string>();
    for (const t of gtfsTrips) {
      if (t.trip_id) {
        gtfsTripRouteMap.set(t.trip_id, t.route_id);
        if (t.direction_id) gtfsTripDirectionMap.set(t.trip_id, t.direction_id);
      }
    }

    let tripCount = 0;
    for (const [tripId, times] of stopTimesByTrip) {
      if (times.length < 2) { skipped++; continue; }
      const first = times[0];
      const last = times[times.length - 1];
      const routeId = gtfsTripRouteMap.get(tripId);
      if (!routeId) { errors.push(`trip_id=${tripId}: route_id não encontrado`); continue; }

      const originDbId = stopIdToDbId.get(first.stop_id);
      const destDbId = stopIdToDbId.get(last.stop_id);
      if (!originDbId || !destDbId) {
        errors.push(`trip_id=${tripId}: terminal origin/destino não mapeado`);
        continue;
      }
      if (originDbId === destDbId) { skipped++; continue; }

      const lineDbId = routeIdToDbId.get(routeId);
      const startTime = this._hhmmssToMinutes(first.departure_time);
      const endTime = this._hhmmssToMinutes(last.arrival_time);
      if (endTime <= startTime) { skipped++; continue; }

      const existing = await this.tripRepo.findOne({
        where: { lineId: lineDbId, startTime, originId: originDbId, destinationId: destDbId, companyId },
      });
      if (existing) { skipped++; continue; }

      const trip = this.tripRepo.create({
        companyId,
        lineId: lineDbId,
        startTime,
        endTime,
        duration: endTime - startTime,
        originId: originDbId,
        destinationId: destDbId,
        direction: gtfsTripDirectionMap.get(tripId) === '1' ? 'VOLTA' : 'IDA',
      });
      await this.tripRepo.save(trip);
      tripCount++;
    }

    return {
      imported: { terminals: terminalCount, lines: lineCount, trips: tripCount },
      skipped,
      errors: errors.slice(0, 20),
    };
  }

  private _readEntry(zip: AdmZip, filename: string): string | null {
    const entry = zip.getEntry(filename) ?? zip.getEntries().find(e => e.entryName.endsWith('/' + filename));
    return entry ? entry.getData().toString('utf8') : null;
  }

  private _parseCsv<T>(content: string): T[] {
    const lines = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    if (lines.length < 2) return [];
    const headers = lines[0].split(',').map(h => h.trim().replace(/^﻿/, ''));
    const result: T[] = [];
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      const values = this._splitCsvLine(line);
      const row: Record<string, string> = {};
      for (let j = 0; j < headers.length; j++) {
        row[headers[j]] = (values[j] ?? '').trim().replace(/^"|"$/g, '');
      }
      result.push(row as unknown as T);
    }
    return result;
  }

  private _splitCsvLine(line: string): string[] {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;
    for (const ch of line) {
      if (ch === '"') { inQuotes = !inQuotes; continue; }
      if (ch === ',' && !inQuotes) { result.push(current); current = ''; continue; }
      current += ch;
    }
    result.push(current);
    return result;
  }

  private _hhmmssToMinutes(time: string): number {
    const parts = time.split(':');
    return parseInt(parts[0] ?? '0') * 60 + parseInt(parts[1] ?? '0');
  }
}
