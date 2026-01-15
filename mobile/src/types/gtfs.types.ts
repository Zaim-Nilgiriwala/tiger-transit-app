export interface Route {
  id: string;
  shortName: string | null;
  longName: string;
  color: string | null;
  textColor: string | null;
  routeType: number;
  agency: string;
}

export interface Stop {
  id: string;
  name: string;
  code: string | null;
  lat: number;
  lon: number;
  wheelchairAccessible: boolean;
  isMajorStop?: boolean;
}

export interface RouteDetail extends Omit<Route, 'agency'> {
  agency: {
    name: string;
    timezone: string;
  };
  stops: StopOnRoute[];
}

export interface StopOnRoute {
  id: string;
  name: string;
  code: string | null;
  lat: number;
  lon: number;
  sequence: number;
}

export interface RouteShape {
  routeId: string;
  directionId: number;
  coordinates: Coordinate[];
  encodedPolyline?: string;
  bounds?: LatLngBounds;
  cached?: boolean;
  pointCount?: number;
}

export interface Coordinate {
  lat: number;
  lon: number;
}

export interface LatLngBounds {
  ne: { lat: number; lng: number };
  sw: { lat: number; lng: number };
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  meta: {
    timestamp: string;
    count?: number;
    cached?: boolean;
  };
}
