/**
 * ETASpot PHP Polling Service
 *
 * Fetches live vehicle data from the ETASpot PHP endpoint.
 * This is a temporary replacement for the Supabase Realtime pipeline,
 * polling the PHP API directly from the client.
 *
 * The PHP endpoint updates server-side every ~10-15 seconds.
 * Each vehicle has a `receiveTime` timestamp (ms epoch).
 */
import { VehiclePosition } from '../types/gtfs.types';
import { STALE_THRESHOLD_MS } from '../config/feeds';

const ETASPOT_URL =
  'https://auburn.etaspot.net/service.php?service=get_vehicles&includeETAData=1&inService=1&orderedETAArray=1&token=TESTING';

/**
 * PHP routeIDs that don't match the app's composite routeId strings.
 * The app uses underscore-joined IDs for multi-pattern routes.
 */
const ROUTE_ID_MAP: Record<string, string> = {
  '215': '215_202_201_156',
  '226': '226_32',
};

/* eslint-disable @typescript-eslint/no-explicit-any */
function mapPhpVehicle(v: any): VehiclePosition {
  const rawRouteId = String(v.routeID ?? '');
  const routeId = ROUTE_ID_MAP[rawRouteId] ?? rawRouteId;

  // Map minutesToNextStops array (PHP returns [{stopID, minutes}, ...])
  const minutesToNextStops: Array<{ stopId: string; minutes: number }> =
    Array.isArray(v.minutesToNextStops)
      ? v.minutesToNextStops.map((item: any) => ({
          stopId: String(item.stopID ?? ''),
          minutes: item.minutes ?? 0,
        }))
      : [];

  return {
    vehicleId: v.equipmentID ?? '',
    routeId,
    lat: v.lat ?? 0,
    lon: v.lng ?? 0,
    heading: v.h ?? 0,
    speed: 0, // PHP endpoint doesn't provide speed
    load: v.load ?? 0,
    capacity: v.capacity ?? 0,
    nextStopId: String(v.nextStopID ?? ''),
    etaSeconds: v.nextStopETA ?? 0,
    onTime: (v.onSchedule ?? 0) <= 0 ? 1 : 0,
    lastStopId: String(v.lastStopID ?? ''),
    isDelayed: (v.onSchedule ?? 0) > 300,
    timestamp: v.receiveTime ?? 0,
    minutesToNextStops,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/**
 * Fetch live vehicles from the ETASpot PHP endpoint.
 * Filters out stale vehicles (receiveTime > 2 minutes old).
 */
export async function fetchEtaspotVehicles(): Promise<VehiclePosition[]> {
  const res = await fetch(ETASPOT_URL);
  if (!res.ok) {
    throw new Error(`ETASpot fetch failed: ${res.status} ${res.statusText}`);
  }

  const json = await res.json();
  const raw = json.get_vehicles ?? json;

  if (!Array.isArray(raw)) {
    throw new Error('ETASpot response missing get_vehicles array');
  }

  const now = Date.now();
  return raw
    .map(mapPhpVehicle)
    .filter((v) => v.routeId !== '' && now - v.timestamp < STALE_THRESHOLD_MS);
}
