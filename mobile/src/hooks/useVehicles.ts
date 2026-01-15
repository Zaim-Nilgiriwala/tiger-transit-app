import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { API_CONFIG } from '../config/api.config';

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

export const useVehicles = (options: UseVehiclesOptions = {}) => {
  const { routeId, stopId, enabled = true } = options;
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const socket = io(API_CONFIG.BASE_URL, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('WebSocket connected:', socket.id);
      setConnected(true);
      setError(null);

      // Subscribe based on options
      if (routeId) {
        socket.emit('subscribe:route', routeId);
      } else if (stopId) {
        socket.emit('subscribe:stop', stopId);
      } else {
        socket.emit('subscribe:all');
      }
    });

    socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      setConnected(false);
    });

    socket.on('connect_error', (err) => {
      console.error('WebSocket connection error:', err.message);
      setError(err.message);
      setConnected(false);
    });

    // Receive batch of vehicles
    socket.on('vehicles', (data: Vehicle[]) => {
      setVehicles(data);
    });

    // Receive individual vehicle update
    socket.on('vehicle', (vehicle: Vehicle) => {
      setVehicles((prev) => {
        const index = prev.findIndex((v) => v.vehicleId === vehicle.vehicleId);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = vehicle;
          return updated;
        }
        return [...prev, vehicle];
      });
    });

    // Handle vehicle removal (vehicle went offline)
    socket.on('vehicle:removed', (vehicleId: string) => {
      setVehicles((prev) => prev.filter((v) => v.vehicleId !== vehicleId));
    });

    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [enabled, routeId, stopId]);

  // Function to manually refresh vehicles
  const refresh = useCallback(() => {
    if (socketRef.current?.connected) {
      if (routeId) {
        socketRef.current.emit('subscribe:route', routeId);
      } else if (stopId) {
        socketRef.current.emit('subscribe:stop', stopId);
      } else {
        socketRef.current.emit('subscribe:all');
      }
    }
  }, [routeId, stopId]);

  // Filter vehicles by route if routeId is specified
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
    refresh,
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
