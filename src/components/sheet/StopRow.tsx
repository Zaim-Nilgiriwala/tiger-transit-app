/**
 * StopRow - Individual stop row in the transit diagram
 *
 * Displays a single stop with:
 * - Route-colored circular sequence indicator with connecting line
 * - Stop name and ETA text
 * - Selected state with tinted background
 *
 * Design system compliance:
 * - ROUTE-05: Ordered stop list with numbered indicators
 * - ROUTE-06: Vertical connecting line creating transit diagram
 * - ROUTE-08: ETAs formatted as "3 min", "< 1 min", or "No buses en route"
 *
 * Wrapped in React.memo to prevent unnecessary re-renders during polling.
 */
import React, { useCallback } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Stop } from '../../types/gtfs.types';
import {
  textColors,
  typography,
  MIN_TAP_TARGET,
  EDGE_MARGIN,
  spacing,
} from '../../theme';
import { hexToRgba } from './RouteCard';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StopRowProps {
  stop: Stop;
  sequenceNumber: number;
  routeColor: string;
  isLast: boolean;
  isSelected: boolean;
  etaText: string;
  onPress: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const INDICATOR_SIZE = 24;
const INDICATOR_COLUMN_WIDTH = 40;
const LINE_WIDTH = 2;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const StopRow = React.memo(function StopRow({
  stop,
  sequenceNumber,
  routeColor,
  isLast,
  isSelected,
  etaText,
  onPress,
}: StopRowProps) {
  const isNoService = etaText === 'No buses en route';
  const selectedBg = isSelected ? hexToRgba(routeColor, 0.08) : 'transparent';

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: selectedBg },
        pressed && { opacity: 0.7 },
      ]}
      accessibilityRole="button"
      accessibilityLabel={`Stop ${sequenceNumber}: ${stop.stopName}, ${etaText}`}
    >
      {/* Indicator column with circle and connecting line */}
      <View style={styles.indicatorColumn}>
        {/* Connecting line above the circle */}
        {sequenceNumber > 1 && (
          <View
            style={[
              styles.lineAbove,
              { backgroundColor: routeColor },
            ]}
          />
        )}

        {/* Sequence indicator circle */}
        <View
          style={[
            styles.circle,
            { backgroundColor: routeColor },
          ]}
        >
          <Text style={styles.circleText}>{sequenceNumber}</Text>
        </View>

        {/* Connecting line below the circle */}
        {!isLast && (
          <View
            style={[
              styles.lineBelow,
              { backgroundColor: routeColor },
            ]}
          />
        )}
      </View>

      {/* Text column */}
      <View style={styles.textColumn}>
        <Text style={styles.stopName} numberOfLines={1}>
          {stop.stopName}
        </Text>
        <Text
          style={[
            styles.etaText,
            isNoService && styles.etaTextMuted,
          ]}
          numberOfLines={1}
        >
          {etaText}
        </Text>
      </View>
    </Pressable>
  );
});

export default StopRow;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: MIN_TAP_TARGET,
    paddingRight: EDGE_MARGIN,
  },
  indicatorColumn: {
    width: INDICATOR_COLUMN_WIDTH,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
  circle: {
    width: INDICATOR_SIZE,
    height: INDICATOR_SIZE,
    borderRadius: INDICATOR_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  circleText: {
    ...typography.labelSM,
    color: '#FFFFFF',
    fontSize: 10,
    lineHeight: 14,
    textTransform: 'none' as const,
    letterSpacing: 0,
  },
  lineAbove: {
    position: 'absolute',
    top: 0,
    width: LINE_WIDTH,
    height: '50%',
  },
  lineBelow: {
    position: 'absolute',
    bottom: 0,
    width: LINE_WIDTH,
    height: '50%',
  },
  textColumn: {
    flex: 1,
    paddingVertical: spacing.s1,
    paddingLeft: spacing.s1,
  },
  stopName: {
    ...typography.titleMD,
    color: textColors.onSurface,
  },
  etaText: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    marginTop: 2,
  },
  etaTextMuted: {
    opacity: 0.6,
  },
});
