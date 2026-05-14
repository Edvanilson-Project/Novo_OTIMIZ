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
}

interface OperationsMapProps {
  terminals: MapTerminal[];
  trips?: MapTripLine[];
  height?: number | string;
}

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

export default function OperationsMap({ terminals, trips = [], height = 600 }: OperationsMapProps) {
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

  // Centro padrão: aproximação do Brasil (São Paulo) caso não haja dados
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

        {validTrips.map((trip) => (
          <Polyline
            key={`trip-${trip.id}`}
            positions={[
              [trip.originLatitude as number, trip.originLongitude as number],
              [trip.destinationLatitude as number, trip.destinationLongitude as number],
            ]}
            pathOptions={{ color: '#1976d2', weight: 2, opacity: 0.55 }}
          >
            <Tooltip sticky>
              Viagem #{trip.id}
              {trip.lineCode ? ` · Linha ${trip.lineCode}` : ''}
            </Tooltip>
          </Polyline>
        ))}

        {validTerminals.map((t) => (
          <CircleMarker
            key={`terminal-${t.id}`}
            center={[t.latitude, t.longitude]}
            radius={6}
            pathOptions={{ color: '#e53935', fillColor: '#e53935', fillOpacity: 0.85, weight: 1 }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {t.name}
            </Tooltip>
          </CircleMarker>
        ))}

        <FitBounds points={allPoints} />
      </MapContainer>
    </div>
  );
}
