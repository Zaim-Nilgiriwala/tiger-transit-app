/**
 * RouteList - Sectioned route list for the bottom sheet
 *
 * Reads routes and vehicle positions from Redux, computes per-route
 * bus counts, sorts alphabetically by long name, and renders
 * RouteCard items under an "ACTIVE ROUTES" section header.
 *
 * Design system compliance:
 * - ROUTE-01: "Active Routes" section header in labelSM uppercase
 * - ROUTE-03: Level 1 section background with Level 2 card surfaces
 * - ROUTE-04: Inactive routes stay in alphabetical position, dimmed
 *
 * Data flow:
 * - state.routes.list -> sorted route array
 * - state.vehicles.positions -> busCountMap per routeId
 */
import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAppSelector } from '../../store';
import {
  surfaces,
  textColors,
  typography,
  spacing,
  EDGE_MARGIN,
  listItemGap,
} from '../../theme';
import RouteCard from './RouteCard';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RouteList() {
  // -------------------------------------------------------------------------
  // Read from Redux
  // -------------------------------------------------------------------------
  const routes = useAppSelector((state) => state.routes.list);
  const positions = useAppSelector((state) => state.vehicles.positions);

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

  /** Routes sorted alphabetically by long name */
  const sortedRoutes = useMemo(
    () => [...routes].sort((a, b) => a.longName.localeCompare(b.longName)),
    [routes],
  );

  // -------------------------------------------------------------------------
  // Render
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
          />
        ))}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    backgroundColor: surfaces.level1,
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
});
