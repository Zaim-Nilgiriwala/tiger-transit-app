/**
 * RouteDetailView - Route detail with sticky header and stop list
 *
 * Displayed inside the bottom sheet when a route is selected.
 * Shows the route name, back/favorite actions, and an ordered
 * stop list with transit-diagram-style indicators and live ETAs.
 *
 * Design system compliance:
 * - ROUTE-05: Ordered stop list in GTFS stop_times sequence order
 * - ROUTE-06: Transit diagram with numbered route-colored indicators
 * - ROUTE-07: Sticky header with back arrow and favorite star
 * - ROUTE-08: ETAs formatted as "3 min", "< 1 min", "No buses en route"
 * - ROUTE-10: ETAs update reactively with 5s GTFS-RT polling cycle
 *
 * Data flow:
 * - state.ui.selectedRouteId -> which route to display
 * - state.routes.list -> Route object lookup
 * - state.routes.stops[routeId] -> ordered Stop[] (from Plan 04-01)
 * - state.vehicles.positions -> live vehicles for ETA derivation
 * - state.ui.selectedStopId -> which stop is highlighted
 */
import React, { useCallback, useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';

import { useAppDispatch, useAppSelector } from '../../store';
import { selectRoute, selectStop } from '../../store/slices/uiSlice';
import type { Stop, VehiclePosition } from '../../types/gtfs.types';
import {
  surfaces,
  textColors,
  typography,
  spacing,
  EDGE_MARGIN,
  MIN_TAP_TARGET,
} from '../../theme';
import { showToast } from '../../utils/toast';
import { hexToRgba } from './RouteCard';
import StopRow from './StopRow';

// ---------------------------------------------------------------------------
// ETA formatting helpers
// ---------------------------------------------------------------------------

/**
 * Format an ETA in seconds to a human-readable string.
 * - < 60s -> "< 1 min"
 * - >= 60s -> "N min" (rounded)
 */
function formatEta(etaSeconds: number): string {
  if (etaSeconds < 60) return '< 1 min';
  return `${Math.round(etaSeconds / 60)} min`;
}

/**
 * Build a map of stopId -> formatted ETA text for all stops on a route.
 * Vehicles are matched by nextStopId. Multiple ETAs are sorted ascending
 * and joined with middle dot separator.
 */
function buildEtaMap(
  stops: Stop[],
  vehicles: VehiclePosition[],
): Record<string, string> {
  const map: Record<string, string> = {};

  for (const stop of stops) {
    const matching = vehicles
      .filter((v) => v.nextStopId === stop.stopId)
      .map((v) => v.etaSeconds)
      .sort((a, b) => a - b);

    if (matching.length === 0) {
      map[stop.stopId] = 'No buses en route';
    } else {
      map[stop.stopId] = matching.map(formatEta).join(' \u00B7 ');
    }
  }

  return map;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RouteDetailView() {
  const dispatch = useAppDispatch();

  // -------------------------------------------------------------------------
  // Read from Redux
  // -------------------------------------------------------------------------
  const selectedRouteId = useAppSelector((s) => s.ui.selectedRouteId);
  const selectedStopId = useAppSelector((s) => s.ui.selectedStopId);
  const routes = useAppSelector((s) => s.routes.list);
  const stopsMap = useAppSelector((s) => s.routes.stops);
  const positions = useAppSelector((s) => s.vehicles.positions);

  // -------------------------------------------------------------------------
  // Derived data
  // -------------------------------------------------------------------------
  const route = useMemo(
    () => routes.find((r) => r.routeId === selectedRouteId) ?? null,
    [routes, selectedRouteId],
  );

  const stops = useMemo(
    () => (selectedRouteId ? stopsMap[selectedRouteId] ?? [] : []),
    [stopsMap, selectedRouteId],
  );

  /** Vehicles on this route */
  const routeVehicles = useMemo(
    () => positions.filter((v) => v.routeId === selectedRouteId),
    [positions, selectedRouteId],
  );

  /** ETA text per stop — recomputed when vehicle positions update (5s cycle) */
  const etaMap = useMemo(
    () => buildEtaMap(stops, routeVehicles),
    [stops, routeVehicles],
  );

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------
  const handleBack = useCallback(() => {
    dispatch(selectRoute(null));
    dispatch(selectStop(null));
  }, [dispatch]);

  const handleFavorite = useCallback(() => {
    showToast('Coming soon');
  }, []);

  const handleStopPress = useCallback(
    (stopId: string) => {
      // Toggle: if same stop tapped again, deselect
      dispatch(selectStop(selectedStopId === stopId ? null : stopId));
    },
    [dispatch, selectedStopId],
  );

  // -------------------------------------------------------------------------
  // Guard: no route selected
  // -------------------------------------------------------------------------
  if (!route) return null;

  const tintColor = hexToRgba(route.routeColor, 0.08);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <View style={styles.container}>
      {/* Sticky header */}
      <View style={[styles.header, { backgroundColor: tintColor }]}>
        {/* Color stripe */}
        <View
          style={[styles.stripe, { backgroundColor: route.routeColor }]}
        />

        {/* Back button */}
        <Pressable
          onPress={handleBack}
          hitSlop={8}
          style={styles.headerButton}
          accessibilityRole="button"
          accessibilityLabel="Go back to route list"
        >
          <Ionicons
            name="chevron-back"
            size={24}
            color={textColors.onSurface}
          />
        </Pressable>

        {/* Route name */}
        <Text style={styles.routeName} numberOfLines={2}>
          {route.longName}
        </Text>

        {/* Favorite button */}
        <Pressable
          onPress={handleFavorite}
          hitSlop={8}
          style={styles.headerButton}
          accessibilityRole="button"
          accessibilityLabel="Add to favorites"
        >
          <MaterialIcons
            name="star-border"
            size={24}
            color={textColors.onSurface}
          />
        </Pressable>
      </View>

      {/* Stop list (plain Views, not FlatList — stop counts are small) */}
      <View style={styles.stopList}>
        {stops.map((stop, index) => (
          <StopRow
            key={`${stop.stopId}-${index}`}
            stop={stop}
            sequenceNumber={index + 1}
            routeColor={route.routeColor}
            isLast={index === stops.length - 1}
            isSelected={stop.stopId === selectedStopId}
            etaText={etaMap[stop.stopId] ?? 'No buses en route'}
            onPress={() => handleStopPress(stop.stopId)}
          />
        ))}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STRIPE_WIDTH = 4;
const HEADER_MIN_HEIGHT = 56;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    backgroundColor: 'transparent',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: HEADER_MIN_HEIGHT,
    paddingHorizontal: EDGE_MARGIN,
    paddingVertical: spacing.s1,
    overflow: 'hidden',
  },
  stripe: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: STRIPE_WIDTH,
  },
  headerButton: {
    width: MIN_TAP_TARGET,
    height: MIN_TAP_TARGET,
    alignItems: 'center',
    justifyContent: 'center',
  },
  routeName: {
    ...typography.headlineLG,
    color: textColors.onSurface,
    flex: 1,
  },
  stopList: {
    paddingBottom: spacing.s2,
  },
});
