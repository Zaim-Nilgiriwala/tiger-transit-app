import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { API_CONFIG } from '../../config/api.config';
import { Route, RouteDetail, RouteShape, Stop, ApiResponse } from '../../types/gtfs.types';

export const transitApi = createApi({
  reducerPath: 'transitApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_CONFIG.BASE_URL }),
  endpoints: (builder) => ({
    // Get all routes
    getRoutes: builder.query<Route[], void>({
      query: () => API_CONFIG.ENDPOINTS.ROUTES,
      transformResponse: (response: ApiResponse<Route[]>) => response.data,
    }),

    // Get route details
    getRouteDetail: builder.query<RouteDetail, string>({
      query: (routeId) => API_CONFIG.ENDPOINTS.ROUTE_DETAIL(routeId),
      transformResponse: (response: ApiResponse<RouteDetail>) => response.data,
    }),

    // Get route shape
    getRouteShape: builder.query<RouteShape, { routeId: string; direction?: number }>({
      query: ({ routeId, direction = 0 }) =>
        API_CONFIG.ENDPOINTS.ROUTE_SHAPE(routeId, direction),
      transformResponse: (response: ApiResponse<RouteShape>) => response.data,
    }),

    // Get all stops
    getStops: builder.query<Stop[], { limit?: number }>({
      query: ({ limit = 200 }) => `${API_CONFIG.ENDPOINTS.STOPS}?limit=${limit}`,
      transformResponse: (response: ApiResponse<Stop[]>) => response.data,
    }),

    // Get stop to route mappings
    getStopRouteMappings: builder.query<Record<string, string[]>, void>({
      query: () => API_CONFIG.ENDPOINTS.STOP_ROUTE_MAPPINGS,
      transformResponse: (response: ApiResponse<Record<string, string[]>>) => response.data,
    }),

    // Get nearby stops
    getNearbyStops: builder.query<Stop[], { lat: number; lon: number; radius?: number }>({
      query: ({ lat, lon, radius = 500 }) =>
        `${API_CONFIG.ENDPOINTS.STOPS_NEARBY}?lat=${lat}&lon=${lon}&radius=${radius}`,
      transformResponse: (response: ApiResponse<Stop[]>) => response.data,
    }),

    // Get stop details
    getStopDetail: builder.query<Stop, string>({
      query: (stopId) => API_CONFIG.ENDPOINTS.STOP_DETAIL(stopId),
      transformResponse: (response: ApiResponse<Stop>) => response.data,
    }),

    // Get routes serving a stop
    getStopRoutes: builder.query<Route[], string>({
      query: (stopId) => API_CONFIG.ENDPOINTS.STOP_ROUTES(stopId),
      transformResponse: (response: ApiResponse<Route[]>) => response.data,
    }),
  }),
});

export const {
  useGetRoutesQuery,
  useGetRouteDetailQuery,
  useGetRouteShapeQuery,
  useGetStopsQuery,
  useGetStopRouteMappingsQuery,
  useGetNearbyStopsQuery,
  useGetStopDetailQuery,
  useGetStopRoutesQuery,
} = transitApi;
