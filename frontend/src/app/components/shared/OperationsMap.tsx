'use client';

import React, { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Tooltip, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface MapTerminal {
  id: number;
  name: string;
  latitude: number | null;
  longitude: number | null;
}

export interface MapTripLine {
  id: number;
  originLatitude: number | null;
  originLongitude: number | null;
  destinationLatitude: number | null;
  destinationLongitude: number | null;
  lineCode?: string | null;
  originId?: number | null;
  destinationId?: number | null;
  startTime?: number | null;
  endTime?: number | null;
  duration?: number | null;
  distanceKm?: number | null;
}

interface OperationsMapProps {
  terminals: MapTerminal[];
  trips?: MapTripLine[];
  height?: number | string;
  selectedTerminalId?: number | null;
  selectedTripId?: number | null;
  onSelectTerminal?: (terminal: MapTerminal) => void;
  onSelectTrip?: (trip: MapTripLine) => void;
  /** Mapa de lineCode → cor (hex). Quando ausente, todas as polylines usam azul padrão. */
  lineColors?: Record<string, string>;
}

const DEFAULT_TRIP_COLOR = '#1976d2';
const SELECTED_COLOR = '#ff9800';

function FitBounds({ points }: { points: Array<[number, number]> }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    const bounds = L.latLngBounds(points.map(([lat, lng]) => L.latLng(lat, lng)));
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }
  }, [map, points]);
  return null;
}

export default function OperationsMap({
  terminals,
  trips = [],
  height = 600,
  selectedTerminalId = null,
  selectedTripId = null,
  onSelectTerminal,
  onSelectTrip,
  lineColors,
}: OperationsMapProps) {
  const validTerminals = useMemo(
    () =>
      terminals.filter(
        (t): t is MapTerminal & { latitude: number; longitude: number } =>
          typeof t.latitude === 'number' && typeof t.longitude === 'number',
      ),
    [terminals],
  );

  const validTrips = useMemo(
    () =>
      trips.filter(
        (t) =>
          typeof t.originLatitude === 'number' &&
          typeof t.originLongitude === 'number' &&
          typeof t.destinationLatitude === 'number' &&
          typeof t.destinationLongitude === 'number',
      ),
    [trips],
  );

  const allPoints = useMemo<Array<[number, number]>>(() => {
    const pts: Array<[number, number]> = validTerminals.map((t) => [t.latitude, t.longitude]);
    for (const trip of validTrips) {
      pts.push([trip.originLatitude as number, trip.originLongitude as number]);
      pts.push([trip.destinationLatitude as number, trip.destinationLongitude as number]);
    }
    return pts;
  }, [validTerminals, validTrips]);

  const defaultCenter: [number, number] = [-23.55, -46.63];

  return (
    <div style={{ height, width: '100%', position: 'relative' }}>
      <MapContainer
        center={allPoints[0] ?? defaultCenter}
        zoom={11}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {validTrips.map((trip) => {
          const isSelected = selectedTripId === trip.id;
          const lineColor = lineColors && trip.lineCode ? lineColors[trip.lineCode] : undefined;
          return (
            <Polyline
              key={`trip-${trip.id}`}
              positions={[
                [trip.originLatitude as number, trip.originLongitude as number],
                [trip.destinationLatitude as number, trip.destinationLongitude as number],
              ]}
              pathOptions={{
                color: isSelected ? SELECTED_COLOR : lineColor ?? DEFAULT_TRIP_COLOR,
                weight: isSelected ? 4 : 2,
                opacity: isSelected ? 0.95 : 0.65,
              }}
              eventHandlers={onSelectTrip ? { click: () => onSelectTrip(trip) } : undefined}
            >
              <Tooltip sticky>
                Viagem #{trip.id}
                {trip.lineCode ? ` · Linha ${trip.lineCode}` : ''}
              </Tooltip>
            </Polyline>
          );
        })}

        {validTerminals.map((t) => {
          const isSelected = selectedTerminalId === t.id;
          return (
            <CircleMarker
              key={`terminal-${t.id}`}
              center={[t.latitude, t.longitude]}
              radius={isSelected ? 10 : 6}
              pathOptions={{
                color: isSelected ? '#ff9800' : '#e53935',
                fillColor: isSelected ? '#ff9800' : '#e53935',
                fillOpacity: 0.85,
                weight: isSelected ? 2 : 1,
              }}
              eventHandlers={onSelectTerminal ? { click: () => onSelectTerminal(t) } : undefined}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {t.name}
              </Tooltip>
            </CircleMarker>
          );
        })}

        <FitBounds points={allPoints} />
      </MapContainer>
    </div>
  );
}
