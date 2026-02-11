import { EventEmitter } from 'events';
import GtfsRealtimeBindings from 'gtfs-realtime-bindings';

const { transit_realtime } = GtfsRealtimeBindings;

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

interface TripEta {
  nextStopId: string;
  etaSeconds: number;
  delay: number;
}

const POSITION_FEED_URL = 'https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb';
const TRIP_UPDATES_FEED_URL = 'https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb';
const POLL_INTERVAL_MS = 5000;

class ETASpotService extends EventEmitter {
  private vehicles: Map<string, VehiclePosition> = new Map();
  private tripEtas: Map<string, TripEta> = new Map();
  private isConnected: boolean = false;
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  start(): void {
    console.log('Starting GTFS-RT feed polling...');
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), POLL_INTERVAL_MS);
  }

  stop(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.isConnected = false;
    this.emit('disconnected', 'stopped');
  }

  private async poll(): Promise<void> {
    try {
      const [positions, trips] = await Promise.all([
        this.fetchFeed(POSITION_FEED_URL),
        this.fetchFeed(TRIP_UPDATES_FEED_URL),
      ]);

      // Process trip updates first so ETAs are available for position mapping
      if (trips) {
        this.processTripUpdates(trips);
      }

      if (positions) {
        this.processPositionUpdates(positions);
      }

      if (!this.isConnected) {
        this.isConnected = true;
        this.emit('connected');
        console.log('GTFS-RT feeds connected');
      }
    } catch (err) {
      console.error('GTFS-RT poll error:', (err as Error).message);
      if (this.isConnected) {
        this.isConnected = false;
        this.emit('disconnected', (err as Error).message);
      }
      this.emit('error', err);
    }
  }

  private async fetchFeed(url: string): Promise<GtfsRealtimeBindings.transit_realtime.FeedMessage | null> {
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Feed fetch failed: ${res.status} ${res.statusText} for ${url}`);
    }
    const buffer = await res.arrayBuffer();
    return transit_realtime.FeedMessage.decode(new Uint8Array(buffer));
  }

  private processTripUpdates(feed: GtfsRealtimeBindings.transit_realtime.FeedMessage): void {
    for (const entity of feed.entity) {
      const tu = entity.tripUpdate;
      if (!tu) continue;

      const tripId = tu.trip?.tripId;
      if (!tripId) continue;

      // Find the next upcoming stop time update
      const now = Math.floor(Date.now() / 1000);
      let nextStop: { stopId: string; eta: number } | null = null;

      for (const stu of tu.stopTimeUpdate || []) {
        const arrivalTime = stu.arrival?.time;
        const arrivalSec = arrivalTime ? Number(arrivalTime) : 0;
        if (arrivalSec > now && stu.stopId) {
          nextStop = {
            stopId: stu.stopId,
            eta: arrivalSec - now,
          };
          break;
        }
      }

      this.tripEtas.set(tripId, {
        nextStopId: nextStop?.stopId || '',
        etaSeconds: nextStop?.eta || 0,
        delay: Number(tu.delay) || 0,
      });
    }
  }

  private processPositionUpdates(feed: GtfsRealtimeBindings.transit_realtime.FeedMessage): void {
    for (const entity of feed.entity) {
      const vp = entity.vehicle;
      if (!vp?.position) continue;

      const vehicleId = vp.vehicle?.id || entity.id;
      const routeId = vp.trip?.routeId;
      if (!routeId) continue;

      const pos = vp.position;
      if (!pos.latitude || !pos.longitude) continue;

      const tripId = vp.trip?.tripId || '';
      const tripEta = this.tripEtas.get(tripId);

      const vehicle: VehiclePosition = {
        vehicleId,
        routeId,
        lat: pos.latitude,
        lon: pos.longitude,
        heading: pos.bearing || 0,
        speed: pos.speed || 0,
        load: 0,
        capacity: 0,
        nextStopId: vp.stopId || tripEta?.nextStopId || '',
        etaSeconds: tripEta?.etaSeconds || 0,
        onTime: tripEta ? (tripEta.delay <= 0 ? 1 : 0) : 0,
        lastStopId: '',
        isDelayed: (tripEta?.delay || 0) > 300,
        timestamp: vp.timestamp ? Number(vp.timestamp) * 1000 : Date.now(),
      };

      this.vehicles.set(vehicleId, vehicle);
      this.emit('vehicle', vehicle);
    }
  }

  // Keep legacy method name working
  connect(): void {
    this.start();
  }

  disconnect(): void {
    this.stop();
  }

  getVehicles(): VehiclePosition[] {
    const now = Date.now();
    const staleThreshold = 2 * 60 * 1000;

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
