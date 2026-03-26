/**
 * BusMarker - Route-colored directional bus marker for MapView
 *
 * Renders a rounded-square marker with 3 rounded corners and 1 sharp corner
 * (the "pointer") that rotates to indicate travel direction. The bus icon
 * inside counter-rotates to stay upright at all times.
 *
 * Visual design:
 * - ~36x36px container filled with the route's specific color
 * - 3 corners heavily rounded (borderRadius ~18px), 1 sharp (0px)
 * - Brighter tint outline (30% toward white) for subtle glow effect
 * - Navy-tinted drop shadow consistent with design system
 * - White Ionicons 'bus' icon, always upright
 *
 * Heading rotation:
 * - Sharp corner is at bottom-right by default (135 degrees from north)
 * - Container rotates by (heading + 135) degrees to point sharp corner
 *   in the travel direction
 * - Icon counter-rotates by -(heading + 135) degrees to stay upright
 */
import React from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { Marker } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';

import type { VehiclePosition } from '../../types/gtfs.types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface BusMarkerProps {
  vehicle: VehiclePosition;
  routeColor: string; // '#RRGGBB' — looked up by parent
  zIndex: number;     // for z-ordering by timestamp
}

// ---------------------------------------------------------------------------
// Helper: brighten a hex color toward white
// ---------------------------------------------------------------------------
/**
 * Parse hex color, increase each RGB channel toward 255 by `amount` fraction
 * (0.3 = 30%), return as hex string.
 */
function brightenColor(hex: string, amount: number): string {
  // Strip leading '#' if present
  const raw = hex.replace(/^#/, '');
  const r = parseInt(raw.substring(0, 2), 16);
  const g = parseInt(raw.substring(2, 4), 16);
  const b = parseInt(raw.substring(4, 6), 16);

  const br = Math.min(255, Math.round(r + (255 - r) * amount));
  const bg = Math.min(255, Math.round(g + (255 - g) * amount));
  const bb = Math.min(255, Math.round(b + (255 - b) * amount));

  const toHex = (n: number) => n.toString(16).padStart(2, '0');
  return `#${toHex(br)}${toHex(bg)}${toHex(bb)}`;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const MARKER_SIZE = 36;
const BORDER_RADIUS = MARKER_SIZE / 2; // 18px — heavily rounded
const BORDER_WIDTH = 3;
const ICON_SIZE = 18;

/**
 * The sharp corner sits at bottom-right, which is 135 degrees clockwise
 * from north (12 o'clock). To point the sharp corner in the heading
 * direction, rotate the container by (heading + 135) degrees.
 */
const SHARP_CORNER_OFFSET = 135;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
function BusMarker({ vehicle, routeColor, zIndex }: BusMarkerProps) {
  const rotation = vehicle.heading + SHARP_CORNER_OFFSET;
  const counterRotation = -rotation;
  const brighterTint = brightenColor(routeColor, 0.3);

  return (
    <Marker
      coordinate={{ latitude: vehicle.lat, longitude: vehicle.lon }}
      anchor={{ x: 0.5, y: 0.5 }}
      tracksViewChanges={false}
      zIndex={zIndex}
    >
      {/* Outer container: rotates to point sharp corner in heading direction */}
      <View
        style={[
          styles.container,
          {
            backgroundColor: routeColor,
            borderColor: brighterTint,
            transform: [{ rotate: `${rotation}deg` }],
          },
        ]}
      >
        {/* Bus icon: counter-rotates to stay upright */}
        <Ionicons
          name="bus"
          size={ICON_SIZE}
          color="#FFFFFF"
          style={{ transform: [{ rotate: `${counterRotation}deg` }] }}
        />
      </View>
    </Marker>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  container: {
    width: MARKER_SIZE,
    height: MARKER_SIZE,
    borderWidth: BORDER_WIDTH,
    // 3 rounded corners, 1 sharp corner (bottom-right)
    borderTopLeftRadius: BORDER_RADIUS,
    borderTopRightRadius: BORDER_RADIUS,
    borderBottomLeftRadius: BORDER_RADIUS,
    borderBottomRightRadius: 0,
    alignItems: 'center',
    justifyContent: 'center',
    // Navy-tinted drop shadow (design system)
    ...Platform.select({
      ios: {
        shadowColor: 'rgba(12, 35, 64, 1)',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.3,
        shadowRadius: 4,
      },
      android: {
        elevation: 5,
      },
    }),
  },
});

export default React.memo(BusMarker);
