import { io, Socket } from 'socket.io-client';
import { EventEmitter } from 'events';

export interface VehiclePosition {
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

interface SysRptMessage {
  vid: string;
  lt: number;
  ln: number;
  h: number;
  v: number;
  load: number;
  capacity: number;
  isDelayed: boolean;
  ts: number;
  serviceState?: {
    rID: number;
    status: number;
    patternID: number;
    tripID: string;
    nextStopPercentProgress: number;
  };
  lastStop?: {
    stopID: number;
    time: number;
    onTime: number;
  };
  eta?: {
    stopID: number;
    eta: number;
    onTime: number;
  };
}

class ETASpotService extends EventEmitter {
  private socket: Socket | null = null;
  private vehicles: Map<string, VehiclePosition> = new Map();
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;

  connect(): void {
    const cookie = process.env.ETASPOT_COOKIE || '';

    if (!cookie) {
      console.warn('ETASPOT_COOKIE not set - live vehicle tracking will not work');
      return;
    }

    console.log('Connecting to ETA SPOT...');

    this.socket = io('https://auburn.etaspot.com', {
      transports: ['websocket'],
      extraHeaders: {
        Cookie: cookie
      },
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    this.socket.on('connect', () => {
      console.log('Connected to ETA SPOT WebSocket');
      this.isConnected = true;
      this.reconnectAttempts = 0;
      this.emit('connected');
    });

    this.socket.on('disconnect', (reason) => {
      console.log('Disconnected from ETA SPOT:', reason);
      this.isConnected = false;
      this.emit('disconnected', reason);
    });

    this.socket.on('connect_error', (error) => {
      console.error('ETA SPOT connection error:', error.message);
      this.reconnectAttempts++;
      this.emit('error', error);
    });

    this.socket.on('sysRpt', (msg: SysRptMessage) => {
      const vehicle = this.transformVehicle(msg);
      if (vehicle) {
        this.vehicles.set(vehicle.vehicleId, vehicle);
        this.emit('vehicle', vehicle);
      }
    });
  }

  private transformVehicle(msg: SysRptMessage): VehiclePosition | null {
    // Skip vehicles not on a route
    if (!msg.serviceState?.rID) {
      return null;
    }

    // Skip invalid coordinates
    if (!msg.lt || !msg.ln || msg.lt === 0 || msg.ln === 0) {
      return null;
    }

    return {
      vehicleId: msg.vid,
      routeId: String(msg.serviceState.rID),
      lat: msg.lt,
      lon: msg.ln,
      heading: msg.h || 0,
      speed: msg.v || 0,
      load: msg.load || 0,
      capacity: msg.capacity || 25,
      nextStopId: msg.eta?.stopID ? String(msg.eta.stopID) : '',
      etaSeconds: msg.eta?.eta || 0,
      onTime: msg.eta?.onTime || 0,
      lastStopId: msg.lastStop?.stopID ? String(msg.lastStop.stopID) : '',
      isDelayed: msg.isDelayed || false,
      timestamp: msg.ts || Date.now()
    };
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.isConnected = false;
    }
  }

  getVehicles(): VehiclePosition[] {
    // Filter out stale vehicles (older than 2 minutes)
    const now = Date.now();
    const staleThreshold = 2 * 60 * 1000; // 2 minutes

    return Array.from(this.vehicles.values()).filter(v => {
      return (now - v.timestamp) < staleThreshold;
    });
  }

  getVehiclesByRoute(routeId: string): VehiclePosition[] {
    return this.getVehicles().filter(v => v.routeId === routeId);
  }

  getVehiclesByStop(stopId: string): VehiclePosition[] {
    return this.getVehicles().filter(v => v.nextStopId === stopId);
  }

  getVehicle(vehicleId: string): VehiclePosition | undefined {
    return this.vehicles.get(vehicleId);
  }

  isServiceConnected(): boolean {
    return this.isConnected;
  }

  getVehicleCount(): number {
    return this.getVehicles().length;
  }
}

// Export singleton instance
export const etaSpotService = new ETASpotService();
