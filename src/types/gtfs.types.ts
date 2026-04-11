/**
 * GTFS and Application Data Types
 *
 * TypeScript interfaces matching the PRD Section 7.1 state shape
 * and the VehiclePosition interface from Code/etaspot_reference.ts.
 */

/** Route from GTFS routes.txt */
export interface Route {
  routeId: string;
  shortName: string;
  longName: string;
  routeColor: string;
  routeType: number;
}

/** Stop from GTFS stops.txt */
export interface Stop {
  stopId: string;
  stopName: string;
  lat: number;
  lon: number;
  stopCode: string;
}

/** Geographic coordinate for polylines and positions */
export interface Coordinate {
  latitude: number;
  longitude: number;
}

/**
 * Enriched vehicle position combining GTFS-RT position + trip update data.
 * Matches the VehiclePosition interface from Code/etaspot_reference.ts.
 */
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
  /** Upcoming stops with ETA in minutes from the PHP minutesToNextStops field */
  minutesToNextStops: Array<{ stopId: string; minutes: number }>;
}

/** Model or feed-based arrival prediction for a stop */
export interface ArrivalPrediction {
  vehicleId: string;
  routeId: string;
  stopId: string;
  etaSeconds: number;
  isModelPrediction: boolean;
}

/** GTFS-RT service alert */
export interface ServiceAlert {
  id: string;
  headerText: string;
  descriptionText: string;
  activePeriodStart: number;
  activePeriodEnd: number;
  routeIds: string[];
}

export interface BackendRoute {
  route_id: string;
  route_name: string;
  coordinates: Coordinate[];
}