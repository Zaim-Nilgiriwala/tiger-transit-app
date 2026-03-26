/**
 * RouteCard - Individual route card for the route list
 *
 * Displays a compact two-line card with:
 * - 4px left color stripe in route color
 * - Subtle tinted background at 6% route color opacity
 * - Line 1: Route long name (Manrope Medium 18pt)
 * - Line 2: (Short name) + bus count text (Inter Regular 14pt)
 *
 * Design system compliance:
 * - ROUTE-02: Color stripe + tinted background for route identity
 * - ROUTE-03: Level 2 surface (white) card with no border lines
 * - ROUTE-04: Inactive routes dimmed at 50% opacity
 * - ERR-02: "No active buses" muted text for inactive routes
 *
 * Wrapped in React.memo to prevent unnecessary re-renders when
 * vehicle positions update every 5 seconds.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Route } from '../../types/gtfs.types';
import {
  surfaces,
  textColors,
  typography,
  cardPadding,
  cardRadius,
  MIN_TAP_TARGET,
} from '../../theme';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RouteCardProps {
  route: Route;
  busCount: number;
  onPress?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Convert a hex color string to rgba with the given alpha.
 * Handles both '#RRGGBB' and 'RRGGBB' formats.
 */
function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Format bus count into human-readable text.
 * - 0: "No active buses"
 * - 1: "1 bus active"
 * - N: "N buses active"
 */
function formatBusCount(count: number): string {
  if (count === 0) return 'No active buses';
  if (count === 1) return '1 bus active';
  return `${count} buses active`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const RouteCard = React.memo(function RouteCard({
  route,
  busCount,
  onPress,
}: RouteCardProps) {
  const isInactive = busCount === 0;
  const tintColor = hexToRgba(route.routeColor, 0.06);

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        isInactive && styles.inactive,
        pressed && { opacity: isInactive ? 0.35 : 0.7 },
      ]}
      accessibilityRole="button"
      accessibilityLabel={`${route.longName}, ${formatBusCount(busCount)}`}
    >
      {/* Tinted background overlay */}
      <View style={[styles.tint, { backgroundColor: tintColor }]} />

      {/* 4px color stripe on left edge */}
      <View
        style={[styles.stripe, { backgroundColor: route.routeColor }]}
      />

      {/* Text content */}
      <View style={styles.content}>
        <Text style={styles.longName} numberOfLines={1}>
          {route.longName}
        </Text>
        <Text style={styles.secondaryLine} numberOfLines={1}>
          ({route.shortName}){' \u00B7 '}
          {formatBusCount(busCount)}
        </Text>
      </View>
    </Pressable>
  );
});

export default RouteCard;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

/** Extra left padding to account for the 4px stripe */
const STRIPE_WIDTH = 4;

const styles = StyleSheet.create({
  card: {
    backgroundColor: surfaces.level2,
    borderRadius: cardRadius,
    minHeight: MIN_TAP_TARGET,
    overflow: 'hidden',
  },
  inactive: {
    opacity: 0.5,
  },
  tint: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: cardRadius,
  },
  stripe: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: STRIPE_WIDTH,
    borderTopLeftRadius: cardRadius,
    borderBottomLeftRadius: cardRadius,
  },
  content: {
    paddingTop: cardPadding,
    paddingBottom: cardPadding,
    paddingRight: cardPadding,
    paddingLeft: cardPadding + STRIPE_WIDTH,
  },
  longName: {
    ...typography.titleMD,
    color: textColors.onSurface,
  },
  secondaryLine: {
    ...typography.bodyMD,
    color: textColors.onSurfaceVariant,
    marginTop: 2,
  },
});
