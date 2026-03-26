/**
 * Static Data Hook
 *
 * Dispatches bundled GTFS static route data into Redux on mount.
 * Routes are a const import -- synchronous, no async loading.
 * Runs once per mount (idempotent).
 */
import { useEffect } from 'react';
import { useAppDispatch } from '../store';
import { setRoutes } from '../store/slices/routesSlice';
import { ROUTES } from '../data/routes';

export function useStaticData(): void {
  const dispatch = useAppDispatch();

  useEffect(() => {
    dispatch(setRoutes(ROUTES));
  }, [dispatch]);
}
