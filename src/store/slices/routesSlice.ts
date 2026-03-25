/**
 * Routes Slice
 *
 * Manages GTFS static route data: route list, stops per route,
 * and shape polylines per route.
 *
 * PRD Section 7.1: AppState.routes
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Route, Stop, Coordinate } from '../../types/gtfs.types';

interface RoutesState {
  list: Route[];
  stops: Record<string, Stop[]>;
  shapes: Record<string, Coordinate[]>;
  loading: boolean;
  error: string | null;
}

const initialState: RoutesState = {
  list: [],
  stops: {},
  shapes: {},
  loading: false,
  error: null,
};

export const routesSlice = createSlice({
  name: 'routes',
  initialState,
  reducers: {
    setRoutes(state, action: PayloadAction<Route[]>) {
      state.list = action.payload;
    },
    setRouteStops(
      state,
      action: PayloadAction<{ routeId: string; stops: Stop[] }>
    ) {
      state.stops[action.payload.routeId] = action.payload.stops;
    },
    setRouteShape(
      state,
      action: PayloadAction<{ routeId: string; shape: Coordinate[] }>
    ) {
      state.shapes[action.payload.routeId] = action.payload.shape;
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload;
    },
    setError(state, action: PayloadAction<string | null>) {
      state.error = action.payload;
    },
  },
});

export const {
  setRoutes,
  setRouteStops,
  setRouteShape,
  setLoading,
  setError,
} = routesSlice.actions;

export default routesSlice.reducer;
