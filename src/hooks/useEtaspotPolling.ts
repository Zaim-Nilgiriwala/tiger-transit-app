/**
 * ETASpot Polling Hook
 *
 * Polls the ETASpot PHP endpoint for live vehicle positions.
 * Temporary replacement for useVehicleSubscription (Supabase).
 *
 * - Polls every 10 seconds (PHP data refreshes every ~10-15s)
 * - Pauses when app goes to background
 * - Resumes with stale clearing on foreground
 * - Silent failure: errors set connected=false but never crash
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { useAppDispatch, store } from '../store';
import { setPositions, setConnected } from '../store/slices/vehiclesSlice';
import { fetchEtaspotVehicles } from '../services/etaspotService';
import { STALE_THRESHOLD_MS } from '../config/feeds';

const POLL_INTERVAL_MS = 10_000; // 10s — matches PHP server refresh cadence

export function useEtaspotPolling(): { isConnected: boolean } {
  const dispatch = useAppDispatch();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef(true);
  const [isConnected, setIsConnected] = useState(false);

  const poll = useCallback(async () => {
    try {
      const vehicles = await fetchEtaspotVehicles();
      if (!isMountedRef.current) return;

      dispatch(setPositions(vehicles));
      dispatch(setConnected(true));
      setIsConnected(true);
    } catch (err) {
      if (!isMountedRef.current) return;
      console.warn('[ETASpot] Poll error:', err);
      dispatch(setConnected(false));
      setIsConnected(false);
    }
  }, [dispatch]);

  const startPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
    }
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
  }, [poll]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;

    // Initial poll + start interval
    poll();
    startPolling();

    const handleAppStateChange = (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        // Clear stale vehicles before fresh poll
        const currentPositions = store.getState().vehicles.positions;
        const now = Date.now();
        const fresh = currentPositions.filter(
          (v) => now - v.timestamp < STALE_THRESHOLD_MS,
        );
        dispatch(setPositions(fresh));
        poll();
        startPolling();
      } else {
        stopPolling();
      }
    };

    const subscription = AppState.addEventListener(
      'change',
      handleAppStateChange,
    );

    return () => {
      isMountedRef.current = false;
      stopPolling();
      subscription.remove();
    };
  }, [dispatch, poll, startPolling, stopPolling]);

  return { isConnected };
}
