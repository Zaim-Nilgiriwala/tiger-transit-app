/**
 * Vehicle Subscription Hook (Supabase Realtime)
 *
 * Replaces useGtfsPolling with push-based Supabase Realtime subscription:
 * - Fetches initial snapshot from vehicles table on mount
 * - Subscribes to postgres_changes for live updates
 * - Pauses subscription when app goes to background
 * - Resumes with stale clearing when app returns to foreground
 * - Dispatches to the same vehiclesSlice used by all UI components
 *
 * Silent failure pattern: errors set connected=false but never crash.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { RealtimeChannel } from '@supabase/supabase-js';

import { supabase } from '../config/supabase';
import { useAppDispatch, store } from '../store';
import { setPositions, setConnected } from '../store/slices/vehiclesSlice';
import { VehiclePosition } from '../types/gtfs.types';
import { STALE_THRESHOLD_MS } from '../config/feeds';

// ---------------------------------------------------------------------------
// Row-to-VehiclePosition mapper (snake_case DB -> camelCase TS)
// ---------------------------------------------------------------------------

/* eslint-disable @typescript-eslint/no-explicit-any */
function mapRowToVehiclePosition(row: any): VehiclePosition {
  return {
    vehicleId: row.vehicle_id ?? '',
    routeId: row.route_id ?? '',
    lat: row.lat ?? 0,
    lon: row.lon ?? 0,
    heading: row.heading ?? 0,
    speed: row.speed ?? 0,
    load: row.load ?? 0,
    capacity: row.capacity ?? 0,
    nextStopId: row.next_stop_id ?? '',
    etaSeconds: row.eta_seconds ?? 0,
    onTime: row.on_time ?? 0,
    lastStopId: row.last_stop_id ?? '',
    isDelayed: row.is_delayed ?? false,
    timestamp: row.timestamp ?? 0,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useVehicleSubscription(): { isConnected: boolean } {
  const dispatch = useAppDispatch();
  const channelRef = useRef<RealtimeChannel | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // -----------------------------------------------------------------------
  // Fetch full snapshot from vehicles table
  // -----------------------------------------------------------------------
  const fetchSnapshot = useCallback(async () => {
    try {
      const { data, error } = await supabase.from('vehicles').select('*');

      if (error) {
        console.warn('[VehicleSubscription] Snapshot fetch error:', error.message);
        dispatch(setConnected(false));
        setIsConnected(false);
        // Do NOT clear positions -- keep last known data
        return;
      }

      const now = Date.now();
      const positions: VehiclePosition[] = (data ?? [])
        .map(mapRowToVehiclePosition)
        .filter((v) => now - v.timestamp < STALE_THRESHOLD_MS);

      dispatch(setPositions(positions));
      dispatch(setConnected(true));
      setIsConnected(true);
    } catch (err) {
      console.warn('[VehicleSubscription] Snapshot fetch exception:', err);
      dispatch(setConnected(false));
      setIsConnected(false);
    }
  }, [dispatch]);

  // -----------------------------------------------------------------------
  // Subscribe to Realtime postgres_changes
  // -----------------------------------------------------------------------
  const subscribe = useCallback(() => {
    // Fetch snapshot immediately (covers any missed updates)
    fetchSnapshot();

    // Create Realtime channel
    const channel = supabase
      .channel('vehicles-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'vehicles' },
        () => {
          // On any change, re-fetch the full snapshot
          // This is simpler and more reliable than incremental updates
          fetchSnapshot();
        },
      )
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          dispatch(setConnected(true));
          setIsConnected(true);
        } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          dispatch(setConnected(false));
          setIsConnected(false);
        }
      });

    channelRef.current = channel;
  }, [dispatch, fetchSnapshot]);

  // -----------------------------------------------------------------------
  // Unsubscribe from Realtime channel
  // -----------------------------------------------------------------------
  const unsubscribe = useCallback(() => {
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
      channelRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Lifecycle: subscribe on mount, AppState-aware pause/resume
  // -----------------------------------------------------------------------
  useEffect(() => {
    subscribe();

    const handleAppStateChange = (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        // Foreground resume: clear stale positions before resubscribing
        const currentPositions = store.getState().vehicles.positions;
        const now = Date.now();
        const freshPositions = currentPositions.filter(
          (v) => now - v.timestamp < STALE_THRESHOLD_MS,
        );
        dispatch(setPositions(freshPositions));

        // Resubscribe (which fetches fresh snapshot)
        subscribe();
      } else {
        // Background or inactive: unsubscribe to save battery/bandwidth
        unsubscribe();
      }
    };

    const subscription = AppState.addEventListener(
      'change',
      handleAppStateChange,
    );

    return () => {
      unsubscribe();
      subscription.remove();
    };
  }, [dispatch, subscribe, unsubscribe]);

  return { isConnected };
}
