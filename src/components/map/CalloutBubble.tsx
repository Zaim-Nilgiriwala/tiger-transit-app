/**
 * CalloutBubble - Glassmorphic callout overlay positioned above map markers
 *
 * Rendered as a sibling OUTSIDE MapView in MapScreen, absolutely positioned
 * using marker screen coordinates from pointForCoordinate().
 *
 * Features:
 * - Glassmorphic panel with backdrop blur (expo-blur)
 * - Downward-pointing triangle connecting callout to marker
 * - Auto-repositioning: flips below marker if insufficient space above
 * - Horizontal clamping to keep callout within screen bounds
 * - Scale + fade entrance/exit animation (200ms in, 150ms out)
 * - pointerEvents="box-none" so map touches pass through
 *
 * Dismiss behavior is handled by the parent (MapScreen) -- this component
 * does not handle outside-tap dismissal.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  Platform,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { BlurView } from 'expo-blur';

import { glass, createGlassStyle, surfaces } from '../../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CalloutBubbleProps {
  type: 'bus' | 'stop';
  markerScreenX: number;
  markerScreenY: number;
  children: React.ReactNode;
  onDismiss: () => void;
  visible: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_WIDTH = 280;
const TRIANGLE_HEIGHT = 10;
const TRIANGLE_HALF_WIDTH = 10;
const GAP_ABOVE_MARKER = 8;
const EDGE_PADDING = 16;
const SAFE_AREA_TOP = 50; // hardcoded safe area top inset

const APPEAR_DURATION = 200;
const DISMISS_DURATION = 150;

const glassStyle = createGlassStyle('callout');

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function CalloutBubble({
  markerScreenX,
  markerScreenY,
  children,
  onDismiss,
  visible,
}: CalloutBubbleProps) {
  const { width: screenWidth } = useWindowDimensions();

  // Animation values
  const scaleAnim = useRef(new Animated.Value(0.9)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;
  const [shouldRender, setShouldRender] = useState(false);

  // Callout measured size
  const [calloutHeight, setCalloutHeight] = useState(0);
  const [calloutWidth, setCalloutWidth] = useState(MAX_WIDTH);

  // Appear animation
  useEffect(() => {
    if (visible) {
      setShouldRender(true);
      scaleAnim.setValue(0.9);
      opacityAnim.setValue(0);
      Animated.parallel([
        Animated.timing(scaleAnim, {
          toValue: 1,
          duration: APPEAR_DURATION,
          useNativeDriver: true,
        }),
        Animated.timing(opacityAnim, {
          toValue: 1,
          duration: APPEAR_DURATION,
          useNativeDriver: true,
        }),
      ]).start();
    } else if (shouldRender) {
      Animated.parallel([
        Animated.timing(scaleAnim, {
          toValue: 0.9,
          duration: DISMISS_DURATION,
          useNativeDriver: true,
        }),
        Animated.timing(opacityAnim, {
          toValue: 0,
          duration: DISMISS_DURATION,
          useNativeDriver: true,
        }),
      ]).start(() => {
        setShouldRender(false);
        onDismiss();
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // Measure callout dimensions
  const handleLayout = useCallback(
    (e: { nativeEvent: { layout: { height: number; width: number } } }) => {
      setCalloutHeight(e.nativeEvent.layout.height);
      setCalloutWidth(e.nativeEvent.layout.width);
    },
    []
  );

  if (!shouldRender) return null;

  // -------------------------------------------------------------------------
  // Positioning calculations
  // -------------------------------------------------------------------------

  const totalCalloutWithTriangle = calloutHeight + TRIANGLE_HEIGHT + GAP_ABOVE_MARKER;

  // Decide above vs below marker
  const fitsAbove = markerScreenY - totalCalloutWithTriangle >= SAFE_AREA_TOP + 8;
  const isAbove = fitsAbove;

  // Vertical position
  let top: number;
  if (isAbove) {
    top = markerScreenY - totalCalloutWithTriangle;
  } else {
    // Below the marker: triangle points up, callout body below
    top = markerScreenY + GAP_ABOVE_MARKER + TRIANGLE_HEIGHT;
  }

  // Horizontal position: centered on marker, clamped to screen bounds
  let left = markerScreenX - calloutWidth / 2;
  left = Math.max(EDGE_PADDING, Math.min(left, screenWidth - calloutWidth - EDGE_PADDING));

  // Triangle offset: should always point at the marker x position
  const triangleLeft = markerScreenX - left - TRIANGLE_HALF_WIDTH;
  const clampedTriangleLeft = Math.max(
    8,
    Math.min(triangleLeft, calloutWidth - TRIANGLE_HALF_WIDTH * 2 - 8)
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <View style={styles.overlay} pointerEvents="box-none">
      <Animated.View
        style={[
          styles.calloutContainer,
          {
            top,
            left,
            maxWidth: MAX_WIDTH,
            opacity: opacityAnim,
            transform: [{ scale: scaleAnim }],
          },
        ]}
        pointerEvents="auto"
      >
        {/* Triangle pointing down (above marker) or up (below marker) */}
        {isAbove ? (
          <>
            {/* Callout body */}
            <View onLayout={handleLayout}>
              <BlurView
                intensity={glass.callout.backdropBlur}
                tint="light"
                style={[glassStyle, styles.calloutBody]}
              >
                {children}
              </BlurView>
            </View>
            {/* Downward triangle */}
            <View style={[styles.triangleDown, { left: clampedTriangleLeft }]} />
          </>
        ) : (
          <>
            {/* Upward triangle */}
            <View style={[styles.triangleUp, { left: clampedTriangleLeft }]} />
            {/* Callout body */}
            <View onLayout={handleLayout}>
              <BlurView
                intensity={glass.callout.backdropBlur}
                tint="light"
                style={[glassStyle, styles.calloutBody]}
              >
                {children}
              </BlurView>
            </View>
          </>
        )}
      </Animated.View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 9999,
  },
  calloutContainer: {
    position: 'absolute',
  },
  calloutBody: {
    ...Platform.select({
      ios: {
        shadowColor: 'rgba(12, 35, 64, 1)',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 12,
      },
      android: {
        elevation: 8,
      },
    }),
  },
  triangleDown: {
    position: 'absolute',
    bottom: -TRIANGLE_HEIGHT,
    width: 0,
    height: 0,
    borderLeftWidth: TRIANGLE_HALF_WIDTH,
    borderRightWidth: TRIANGLE_HALF_WIDTH,
    borderTopWidth: TRIANGLE_HEIGHT,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderTopColor: surfaces.level2,
  },
  triangleUp: {
    width: 0,
    height: 0,
    borderLeftWidth: TRIANGLE_HALF_WIDTH,
    borderRightWidth: TRIANGLE_HALF_WIDTH,
    borderBottomWidth: TRIANGLE_HEIGHT,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderBottomColor: surfaces.level2,
  },
});

export default React.memo(CalloutBubble);
