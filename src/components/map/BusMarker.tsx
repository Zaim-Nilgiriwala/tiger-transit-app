/**
 * BusMarker - Route-colored directional bus marker for MapView
 *
 * Renders a rounded-square marker with 3 rounded corners and 1 sharp corner
 * (the "pointer") that rotates to indicate travel direction. The bus icon
 * inside counter-rotates to stay upright at all times.
 *
 * Visibility is controlled via `visible` prop with a 500ms fade.
 * Markers are never unmounted — react-native-maps handles prop updates
 * reliably but struggles with bulk add/remove.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Animated, Platform, StyleSheet, View } from 'react-native';
import { Marker } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';

import type { Coordinate, VehiclePosition } from '../../types/gtfs.types';
import { useAnimatedPosition } from '../../hooks/useAnimatedPosition';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface BusMarkerProps {
  vehicle: VehiclePosition;
  routeColor: string;          // '#RRGGBB' -- looked up by parent
  zIndex: number;              // for z-ordering
  visible: boolean;            // false = hidden via opacity (stays mounted)
  routeShape?: Coordinate[];   // polyline for this vehicle's route
  onPress?: () => void;        // fires when marker is tapped (callout system)
  isHighlighted?: boolean;     // true = 1.2x scale + glow ring (callout open)
}

// ---------------------------------------------------------------------------
// useFade — drives a 0→1 or 1→0 animation, returns current value as number
// ---------------------------------------------------------------------------
const FADE_MS = 200;

function useFade(visible: boolean): number {
  const anim = useRef(new Animated.Value(visible ? 1 : 0)).current;
  const [value, setValue] = useState(visible ? 1 : 0);

  useEffect(() => {
    const id = anim.addListener(({ value: v }) => setValue(v));

    Animated.timing(anim, {
      toValue: visible ? 1 : 0,
      duration: FADE_MS,
      useNativeDriver: false,
    }).start();

    return () => anim.removeListener(id);
  }, [visible, anim]);

  return value;
}

// ---------------------------------------------------------------------------
// Helper: brighten a hex color toward white
// ---------------------------------------------------------------------------
function brightenColor(hex: string, amount: number): string {
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
 * direction, rotate the container by (heading + 225) degrees.
 */
const SHARP_CORNER_OFFSET = 225;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
function BusMarker({
  vehicle,
  routeColor,
  zIndex,
  visible,
  routeShape,
  onPress,
  isHighlighted = false,
}: BusMarkerProps) {
  const fade = useFade(visible);
  const animated = useAnimatedPosition(vehicle, routeShape, visible);
  const rotation = animated.heading + SHARP_CORNER_OFFSET;
  const counterRotation = -rotation;
  const brighterTint = brightenColor(routeColor, 0.3);

  return (
    <Marker
      coordinate={{ latitude: animated.latitude, longitude: animated.longitude }}
      anchor={{ x: 0.5, y: 0.5 }}
      tracksViewChanges={animated.isAnimating}
      zIndex={zIndex}
      opacity={fade}
      onPress={onPress}
    >
      {/* Outer container: rotates to point sharp corner in heading direction */}
      <View
        style={[
          styles.container,
          {
            backgroundColor: routeColor,
            borderColor: brighterTint,
            transform: [
              { scale: isHighlighted ? 1.2 : 1 },
              { rotate: `${rotation}deg` },
            ],
          },
          isHighlighted && styles.highlighted,
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
  // Glow ring effect when callout is open for this marker
  highlighted: {
    ...Platform.select({
      ios: {
        shadowOpacity: 0.5,
        shadowRadius: 8,
      },
      android: {
        elevation: 10,
      },
    }),
  },
});

export default React.memo(BusMarker);
