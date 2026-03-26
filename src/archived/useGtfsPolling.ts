// ARCHIVED: Replaced by Supabase Realtime pipeline (Phase 2 rework, 2026-03-26)
/**
 * GTFS-RT Polling Hook
 *
 * Manages the 5-second polling lifecycle for real-time vehicle positions:
 * - Starts polling immediately on mount
 * - Pauses when app goes to background/inactive
 * - Resumes immediately when app returns to foreground
 * - On resume, clears stale vehicles (>2 min) before first fresh poll
 * - Returns connection status and error for optional consumer display
 *
 * Silent failure pattern: failed polls set connected=false but never crash.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { useAppDispatch } from '../store';
import { store } from '../store';
import { setPositions, setConnected } from '../store/slices/vehiclesSlice';
import { fetchAndDecodeFeeds } from '../services/gtfsRealtimeService';
import { POLL_INTERVAL_MS, STALE_THRESHOLD_MS } from '../config/feeds';

interface PollingState {
  isConnected: boolean;
  error: string | null;
}

export function useGtfsPolling(): PollingState {
  const dispatch = useAppDispatch();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef(true);

  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // -----------------------------------------------------------------------
  // Poll function: fetch, decode, dispatch
  // -----------------------------------------------------------------------
  const poll = useCallback(async () => {
    try {
      const vehicles = await fetchAndDecodeFeeds();
      if (!isMountedRef.current) return;

      dispatch(setPositions(vehicles));
      dispatch(setConnected(true));
      setIsConnected(true);
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;

      dispatch(setConnected(false));
      setIsConnected(false);
      setError(
        err instanceof Error ? err.message : 'Feed fetch failed',
      );
      // Do NOT clear positions -- keep last known data
    }
  }, [dispatch]);

  // -----------------------------------------------------------------------
  // Start polling interval
  // -----------------------------------------------------------------------
  const startPolling = useCallback(() => {
    // Clear any existing interval to prevent duplicates
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
    }
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
  }, [poll]);

  // -----------------------------------------------------------------------
  // Stop polling interval
  // -----------------------------------------------------------------------
  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // AppState handler: pause on background, resume on foreground
  // -----------------------------------------------------------------------
  useEffect(() => {
    isMountedRef.current = true;

    // Initial poll + start interval
    poll();
    startPolling();

    const handleAppStateChange = (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        // Foreground resume: immediately clear stale vehicles before first fresh poll
        const currentPositions = store.getState().vehicles.positions;
        const now = Date.now();
        const freshPositions = currentPositions.filter(
          (v) => now - v.timestamp < STALE_THRESHOLD_MS,
        );
        dispatch(setPositions(freshPositions));

        // Immediately poll and restart interval
        poll();
        startPolling();
      } else {
        // Background or inactive: stop polling to save battery
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

  return { isConnected, error };
}
