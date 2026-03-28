/**
 * BusCalloutContent - Inner content for bus marker callout bubbles
 *
 * Shows route name, passenger capacity bar, delay status pill,
 * and next 3 stop ETAs from the vehicle's minutesToNextStops data.
 *
 * Wrapped in React.memo for performance since callout content
 * refreshes every poll cycle via Redux re-render.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { VehiclePosition } from '../../types/gtfs.types';
import { STOPS_BY_ID } from '../../data/stops';
import {
  typography,
  textColors,
  statusColors,
  surfaces,
  spacing,
  pillRadius,
} from '../../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BusCalloutContentProps {
  vehicle: VehiclePosition;
  routeColor: string;
  routeLongName: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function BusCalloutContent({ vehicle, routeColor, routeLongName }: BusCalloutContentProps) {
  const loadRatio = Math.min(vehicle.load / 50, 1.0);
  const nextStops = (vehicle.minutesToNextStops ?? []).slice(0, 3);

  return (
    <View style={styles.container}>
      {/* Header: route name with color bar */}
      <View style={styles.headerRow}>
        <View style={[styles.colorBar, { backgroundColor: routeColor }]} />
        <Text style={styles.routeName} numberOfLines={2}>
          {routeLongName}
        </Text>
      </View>

      {/* Passenger capacity bar */}
      <View style={styles.passengerSection}>
        <View style={styles.capacityBarTrack}>
          <View
            style={[
              styles.capacityBarFill,
              {
                backgroundColor: routeColor,
                width: `${Math.max(loadRatio * 100, 0)}%`,
              },
            ]}
          />
        </View>
        <Text style={styles.passengerText}>
          {vehicle.load} passengers
        </Text>
      </View>

      {/* Delay status pill */}
      <View style={styles.delayRow}>
        {vehicle.isDelayed ? (
          <View style={[styles.pill, { backgroundColor: statusColors.delayed }]}>
            <Text style={styles.pillTextWhite}>DELAYED</Text>
          </View>
        ) : (
          <View style={[styles.pill, { backgroundColor: `${statusColors.onTime}26` }]}>
            <Text style={[styles.pillTextGreen]}>On Time</Text>
          </View>
        )}
      </View>

      {/* Next stops section */}
      <View style={styles.nextStopsSection}>
        <Text style={styles.sectionLabel}>NEXT STOPS</Text>
        {nextStops.length > 0 ? (
          nextStops.map((item, index) => {
            const stopName = STOPS_BY_ID[item.stopId]?.stopName ?? 'Unknown';
            return (
              <View key={`${item.stopId}-${index}`} style={styles.stopRow}>
                <Text style={styles.stopName} numberOfLines={1}>
                  {stopName}
                </Text>
                <Text style={styles.stopEta}>
                  {' '}&mdash; {Math.round(item.minutes)} min
                </Text>
              </View>
            );
          })
        ) : (
          <Text style={styles.noStops}>No upcoming stops</Text>
        )}
      </View>
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
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.s1,
  },
  colorBar: {
    width: 4,
    height: 28,
    borderRadius: 2,
    marginRight: spacing.s1,
  },
  routeName: {
    ...typography.titleMD,
    color: textColors.onSurface,
    flex: 1,
  },
  passengerSection: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.s1,
  },
  capacityBarTrack: {
    flex: 1,
    height: 6,
    backgroundColor: surfaces.level1,
    borderRadius: 3,
    overflow: 'hidden',
  },
  capacityBarFill: {
    height: 6,
    borderRadius: 3,
  },
  passengerText: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    marginLeft: spacing.s1,
  },
  delayRow: {
    flexDirection: 'row',
    marginBottom: spacing.s1,
  },
  pill: {
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: pillRadius,
  },
  pillTextWhite: {
    ...typography.labelSM,
    color: '#FFFFFF',
  },
  pillTextGreen: {
    ...typography.labelSM,
    color: statusColors.onTimeText,
  },
  sectionLabel: {
    ...typography.labelSM,
    color: textColors.onSurfaceVariant,
    marginBottom: 4,
  },
  nextStopsSection: {
    marginTop: 2,
  },
  stopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 2,
  },
  stopName: {
    ...typography.bodyMD,
    color: textColors.onSurface,
    flexShrink: 1,
  },
  stopEta: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
  },
  noStops: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    fontStyle: 'italic',
  },
});

export default React.memo(BusCalloutContent);
