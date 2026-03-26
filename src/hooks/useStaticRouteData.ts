/**
 * Static Route Data Hook
 *
 * Dispatches bundled GTFS stop-sequences and shape polylines into Redux on mount.
 * For each route with GTFS data, hydrates routesSlice.stops and routesSlice.shapes
 * so downstream screens (Route Detail, Map overlays) can consume them synchronously.
 *
 * Follows the same pattern as useStaticData (runs once via useEffect).
 */
import { useEffect } from 'react';
import { useAppDispatch } from '../store';
import { setRouteStops, setRouteShape } from '../store/slices/routesSlice';
import { STOPS_BY_ID } from '../data/stops';
import { SHAPES } from '../data/shapes';
import { ROUTE_STOP_SEQUENCE, ROUTE_SHAPE_ID } from '../data/routeStops';
import { Stop } from '../types/gtfs.types';

export function useStaticRouteData(): void {
  const dispatch = useAppDispatch();

  useEffect(() => {
    const routeIds = Object.keys(ROUTE_STOP_SEQUENCE);

    for (const routeId of routeIds) {
      // 1. Map ordered stopIds to Stop objects
      const stopIds = ROUTE_STOP_SEQUENCE[routeId];
      const orderedStops: Stop[] = [];
      for (const stopId of stopIds) {
        const stop = STOPS_BY_ID[stopId];
        if (stop) {
          orderedStops.push(stop);
        }
      }

      // 2. Dispatch stops into Redux
      if (orderedStops.length > 0) {
        dispatch(setRouteStops({ routeId, stops: orderedStops }));
      }

      // 3. Look up shape and dispatch into Redux
      const shapeId = ROUTE_SHAPE_ID[routeId];
      if (shapeId) {
        const shape = SHAPES[shapeId];
        if (shape) {
          dispatch(setRouteShape({ routeId, shape }));
        }
      }
    }
  }, [dispatch]);
}
