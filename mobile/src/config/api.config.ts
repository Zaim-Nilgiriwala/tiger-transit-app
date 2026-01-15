export const API_CONFIG = {
  BASE_URL: 'http://10.2.1.96:3001',
  TIMEOUT: 10000,
  ENDPOINTS: {
    HEALTH: '/health',
    ROUTES: '/routes',
    ROUTE_DETAIL: (id: string) => `/routes/${id}`,
    ROUTE_SHAPE: (id: string, direction: number = 0) =>
      `/routes/${id}/shape?direction=${direction}`,
    STOPS: '/stops',
    STOPS_NEARBY: '/stops/nearby',
    STOP_ROUTE_MAPPINGS: '/stops/route-mappings',
    STOP_DETAIL: (id: string) => `/stops/${id}`,
    STOP_ROUTES: (id: string) => `/stops/${id}/routes`,
    VEHICLES: '/vehicles',
    VEHICLES_BY_ROUTE: (routeId: string) => `/vehicles/route/${routeId}`,
    VEHICLES_BY_STOP: (stopId: string) => `/vehicles/stop/${stopId}`,
  }
};

// Auburn University coordinates
export const AUBURN_COORDS = {
  latitude: 32.6024,
  longitude: -85.4876,
  latitudeDelta: 0.05,
  longitudeDelta: 0.05,
};
