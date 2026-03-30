/**
 * RouteList - Sectioned route list for the bottom sheet
 *
 * Reads routes and vehicle positions from Redux, computes per-route
 * bus counts, sorts active-first then alphabetical within each group,
 * and renders RouteCard items under three section headers:
 * ACTIVE ROUTES, FAVORITES, and ALERTS.
 *
 * Favorites and Alerts sections are placeholder stubs for Phase 6,
 * which will implement FAV-01 through FAV-04 and ALERT-01/ALERT-02.
 *
 * Design system compliance:
 * - ROUTE-01: Three section headers (Active Routes, Favorites, Alerts) in labelSM uppercase
 * - ROUTE-03: Level 1 section background with Level 2 card surfaces
 * - ROUTE-04: Inactive routes (0 active buses) dimmed and sorted to bottom
 *
 * Data flow:
 * - state.routes.list -> sorted route array (active-first, then alphabetical)
 * - state.vehicles.positions -> busCountMap per routeId (used in sort + card display)
 */
import React, { useCallback, useContext, useEffect, useMemo, useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAppDispatch, useAppSelector } from '../../store';
import { selectRoute } from '../../store/slices/uiSlice';
import { SheetScrollContext } from './BottomSheet';
import {
  surfaces,
  textColors,
  typography,
  spacing,
  EDGE_MARGIN,
  listItemGap,
} from '../../theme';
import RouteCard from './RouteCard';
import RouteDetailView from './RouteDetailView';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RouteList() {
  const dispatch = useAppDispatch();
  const sheetScroll = useContext(SheetScrollContext);
  const prevSelectedRef = useRef<string | null>(null);

  // -------------------------------------------------------------------------
  // Read from Redux
  // -------------------------------------------------------------------------
  const routes = useAppSelector((state) => state.routes.list);
  const positions = useAppSelector((state) => state.vehicles.positions);
  const selectedRouteId = useAppSelector((state) => state.ui.selectedRouteId);

  // Restore scroll position when returning from route detail to route list
  useEffect(() => {
    if (prevSelectedRef.current !== null && selectedRouteId === null) {
      sheetScroll?.restoreScrollPosition();
    }
    prevSelectedRef.current = selectedRouteId;
  }, [selectedRouteId, sheetScroll]);

  // -------------------------------------------------------------------------
  // Derived data (memoized)
  // -------------------------------------------------------------------------

  /** Count vehicles per routeId */
  const busCountMap = useMemo(() => {
    const map = new Map<string, number>();
    positions.forEach((v) =>
      map.set(v.routeId, (map.get(v.routeId) || 0) + 1),
    );
    return map;
  }, [positions]);

  /** Routes sorted active-first, then alphabetical within each group */
  const sortedRoutes = useMemo(() => {
    return [...routes].sort((a, b) => {
      const aActive = (busCountMap.get(a.routeId) || 0) > 0 ? 0 : 1;
      const bActive = (busCountMap.get(b.routeId) || 0) > 0 ? 0 : 1;
      if (aActive !== bActive) return aActive - bActive;
      return a.longName.localeCompare(b.longName);
    });
  }, [routes, busCountMap]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------
  const handleRoutePress = useCallback(
    (routeId: string) => {
      sheetScroll?.saveScrollPosition();
      dispatch(selectRoute(routeId));
    },
    [dispatch, sheetScroll],
  );

  // -------------------------------------------------------------------------
  // Render: Route Detail View (when a route is selected)
  // -------------------------------------------------------------------------
  if (selectedRouteId !== null) {
    return <RouteDetailView />;
  }

  // -------------------------------------------------------------------------
  // Render: Route List (default)
  // -------------------------------------------------------------------------
  return (
    <View style={styles.container}>
      {/* Section header */}
      <Text style={styles.sectionHeader}>ACTIVE ROUTES</Text>

      {/* Route cards */}
      <View style={styles.cardList}>
        {sortedRoutes.map((route) => (
          <RouteCard
            key={route.routeId}
            route={route}
            busCount={busCountMap.get(route.routeId) || 0}
            onPress={() => handleRoutePress(route.routeId)}
          />
        ))}
      </View>

      {/* Favorites section (placeholder - Phase 6: FAV-01 through FAV-04) */}
      <Text style={[styles.sectionHeader, styles.sectionDivider]}>
        FAVORITES
      </Text>
      <Text style={styles.placeholderText}>No favorites yet</Text>

      {/* Alerts section (placeholder - Phase 6: ALERT-01, ALERT-02) */}
      <Text style={[styles.sectionHeader, styles.sectionDivider]}>ALERTS</Text>
      <Text style={styles.placeholderText}>No active alerts</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    backgroundColor: 'transparent',
  },
  sectionHeader: {
    ...typography.labelSM,
    color: textColors.onSurfaceVariant,
    paddingHorizontal: EDGE_MARGIN,
    paddingVertical: spacing.s1,
  },
  cardList: {
    paddingHorizontal: EDGE_MARGIN,
    gap: listItemGap,
    paddingBottom: spacing.s2,
  },
  sectionDivider: {
    marginTop: spacing.s2,
  },
  placeholderText: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    textAlign: 'center' as const,
    paddingVertical: spacing.s2,
    paddingHorizontal: EDGE_MARGIN,
  },
});
