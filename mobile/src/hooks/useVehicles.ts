import { useEffect, useState, useCallback, useRef } from 'react';

export interface Vehicle {
  vehicleId: string;
  routeId: string;
  lat: number;
  lon: number;
  heading: number;
  speed: number;
  load: number;
  capacity: number;
  nextStopId: string;
  etaSeconds: number;
  onTime: number;
  lastStopId: string;
  isDelayed: boolean;
  timestamp: number;
}

interface UseVehiclesOptions {
  routeId?: string;
  stopId?: string;
  enabled?: boolean;
}

interface ETASpotVehicle {
  equipmentID: string;
  routeID: number;
  lat: number;
  lng: number;
  h: number;
  load: number;
  capacity: number;
  nextStopID: number;
  nextStopETA: number;
  onSchedule: number;
  lastStopID: number;
  inService: number;
  receiveTime: number;
}

const ETASPOT_API = 'https://auburn.etaspot.net/service.php';
const POLL_INTERVAL_MS = 8000;

function mapVehicle(v: ETASpotVehicle): Vehicle {
  return {
    vehicleId: v.equipmentID,
    routeId: String(v.routeID),
    lat: v.lat,
    lon: v.lng,
    heading: v.h || 0,
    speed: 0,
    load: v.load || 0,
    capacity: v.capacity || 0,
    nextStopId: String(v.nextStopID || ''),
    etaSeconds: v.nextStopETA || 0,
    onTime: v.onSchedule || 0,
    lastStopId: String(v.lastStopID || ''),
    isDelayed: (v.onSchedule || 0) > 300,
    timestamp: v.receiveTime || Date.now(),
  };
}

export const useVehicles = (options: UseVehiclesOptions = {}) => {
  const { routeId, stopId, enabled = true } = options;
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchVehicles = useCallback(async () => {
    try {
      const url = `${ETASPOT_API}?service=get_vehicles&includeETAData=1&inService=1&orderedETAArray=1&token=TESTING`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const etaVehicles: ETASpotVehicle[] = data.get_vehicles || [];
      const mapped = etaVehicles
        .filter((v) => v.inService === 1)
        .map(mapVehicle);

      setVehicles(mapped);
      setConnected(true);
      setError(null);
    } catch (err) {
      console.error('Vehicle fetch error:', (err as Error).message);
      setError((err as Error).message);
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    fetchVehicles();
    timerRef.current = setInterval(fetchVehicles, POLL_INTERVAL_MS);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [enabled, fetchVehicles]);

  // Filter vehicles by route or stop
  const filteredVehicles = routeId
    ? vehicles.filter((v) => v.routeId === routeId)
    : stopId
    ? vehicles.filter((v) => v.nextStopId === stopId)
    : vehicles;

  return {
    vehicles: filteredVehicles,
    allVehicles: vehicles,
    connected,
    error,
    refresh: fetchVehicles,
  };
};

// Hook for getting vehicles approaching a specific stop
export const useStopArrivals = (stopId: string, enabled = true) => {
  const { vehicles, connected, error } = useVehicles({ stopId, enabled });

  // Sort by ETA
  const sortedArrivals = [...vehicles].sort((a, b) => a.etaSeconds - b.etaSeconds);

  return {
    arrivals: sortedArrivals,
    connected,
    error,
  };
};
