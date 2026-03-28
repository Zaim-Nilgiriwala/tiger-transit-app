/**
 * StopCalloutContent - Inner content for stop marker callout bubbles
 *
 * Shows stop name, ETAs for all routes serving this stop,
 * horizontal route badge pills, and a "View More" link (coming soon).
 *
 * Wrapped in React.memo for performance since callout content
 * refreshes every poll cycle via Redux re-render.
 */
import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { Route, Stop, VehiclePosition } from '../../types/gtfs.types';
import { ROUTE_STOP_SEQUENCE } from '../../data/routeStops';
import {
  typography,
  textColors,
  spacing,
  pillRadius,
} from '../../theme';
import { showToast } from '../../utils/toast';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface StopCalloutContentProps {
  stop: Stop;
  vehicles: VehiclePosition[];
  routes: Route[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function StopCalloutContent({ stop, vehicles, routes }: StopCalloutContentProps) {
  // Build lookup maps from routes prop
  const routeColorMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => {
      const color = r.routeColor
        ? `#${r.routeColor.replace(/^#/, '')}`
        : '#FF8934';
      map.set(r.routeId, color);
    });
    return map;
  }, [routes]);

  const routeShortNameMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => map.set(r.routeId, r.shortName));
    return map;
  }, [routes]);

  const routeLongNameMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => map.set(r.routeId, r.longName));
    return map;
  }, [routes]);

  // Find all routes serving this stop
  const servingRouteIds = useMemo(() => {
    const ids: string[] = [];
    for (const [routeId, stopSequence] of Object.entries(ROUTE_STOP_SEQUENCE)) {
      if (stopSequence.includes(stop.stopId)) {
        ids.push(routeId);
      }
    }
    return ids;
  }, [stop.stopId]);

  // Compute ETAs for each serving route
  const routeEtas = useMemo(() => {
    return servingRouteIds.map((routeId) => {
      // Find vehicles on this route heading to this stop
      const matchingVehicles = vehicles.filter(
        (v) => v.routeId === routeId && v.nextStopId === stop.stopId
      );

      let etaText: string;
      let hasEta = false;

      if (matchingVehicles.length > 0) {
        // Pick the one with smallest etaSeconds
        const closest = matchingVehicles.reduce((a, b) =>
          a.etaSeconds < b.etaSeconds ? a : b
        );
        const minutes = Math.round(closest.etaSeconds / 60);
        etaText = minutes < 1 ? '< 1 min' : `${minutes} min`;
        hasEta = true;
      } else {
        etaText = 'No buses';
      }

      return {
        routeId,
        color: routeColorMap.get(routeId) || '#FF8934',
        shortName: routeShortNameMap.get(routeId) || routeId,
        longName: routeLongNameMap.get(routeId) || '',
        etaText,
        hasEta,
      };
    });
  }, [servingRouteIds, vehicles, stop.stopId, routeColorMap, routeShortNameMap, routeLongNameMap]);

  return (
    <View style={styles.container}>
      {/* Stop name */}
      <Text style={styles.stopName} numberOfLines={2}>
        {stop.stopName}
      </Text>

      {/* Route ETAs section */}
      {routeEtas.length > 0 ? (
        <View style={styles.etaSection}>
          {routeEtas.map((item) => (
            <View key={item.routeId} style={styles.etaRow}>
              <View style={[styles.routeDot, { backgroundColor: item.color }]} />
              <Text style={styles.routeLabel}>{item.shortName}</Text>
              <Text
                style={[
                  styles.etaText,
                  !item.hasEta && styles.etaTextDim,
                ]}
              >
                {item.etaText}
              </Text>
            </View>
          ))}
        </View>
      ) : (
        <Text style={styles.noRoutes}>No routes at this stop</Text>
      )}

      {/* Route badges (horizontal scrollable) */}
      {routeEtas.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.badgeScroll}
          contentContainerStyle={styles.badgeContainer}
        >
          {routeEtas.map((item) => (
            <View
              key={`badge-${item.routeId}`}
              style={[styles.badge, { backgroundColor: item.color }]}
            >
              <Text style={styles.badgeText}>{item.shortName}</Text>
            </View>
          ))}
        </ScrollView>
      )}

      {/* View More link */}
      <Pressable
        onPress={() => showToast('Coming soon')}
        style={styles.viewMoreButton}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <Text style={styles.viewMoreText}>View More</Text>
      </Pressable>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    paddingVertical: spacing.s1,
    paddingHorizontal: 12,
  },
  stopName: {
    ...typography.titleMD,
    color: textColors.onSurface,
    marginBottom: spacing.s1,
  },
  etaSection: {
    marginBottom: spacing.s1,
  },
  etaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  routeDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  routeLabel: {
    ...typography.labelSM,
    fontWeight: '700',
    marginRight: 6,
    color: textColors.onSurface,
  },
  etaText: {
    ...typography.bodyMD,
    color: textColors.onSurface,
  },
  etaTextDim: {
    color: textColors.onSurfaceVariant,
  },
  noRoutes: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    fontStyle: 'italic',
    marginBottom: spacing.s1,
  },
  badgeScroll: {
    marginBottom: spacing.s1,
  },
  badgeContainer: {
    flexDirection: 'row',
    gap: 6,
  },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: pillRadius,
  },
  badgeText: {
    ...typography.labelSM,
    color: '#FFFFFF',
  },
  viewMoreButton: {
    paddingVertical: 4,
  },
  viewMoreText: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
  },
});

export default React.memo(StopCalloutContent);
