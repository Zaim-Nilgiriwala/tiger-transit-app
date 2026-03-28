/**
 * RouteOverlay - Route polylines and stop markers on the map
 *
 * Renders polylines and stop dot markers for ALL routes at all times.
 * Visibility is controlled via props (transparent colors / zero opacity),
 * never via mount/unmount — react-native-maps handles prop updates on
 * existing native overlays reliably, but struggles with bulk add/remove.
 *
 * Visibility transitions use a 500ms fade driven by Animated.Value.
 * Polyline strokeColor is computed from the animated opacity each frame.
 *
 * Visibility rule:
 * - No route selected: all routes visible
 * - Route selected: only that route visible, others fade out
 *
 * State is read from Redux; onStopPress is passed as a prop from MapScreen.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Platform, StyleSheet, View } from 'react-native';
import { Marker, Polyline } from 'react-native-maps';

import { useAppSelector } from '../../store';
import type { Coordinate, Stop } from '../../types/gtfs.types';

/** Fallback route color when route is not found in list */
const FALLBACK_COLOR = '#FF8934';

/** Default stop marker size (diameter in px) */
const DOT_SIZE = 12;

/** Focused stop marker size (diameter in px) */
const FOCUSED_DOT_SIZE = 20;

/** Fade duration in ms */
const FADE_MS = 200;

// ---------------------------------------------------------------------------
// useFade — drives a 0→1 or 1→0 animation, returns current value as number
// ---------------------------------------------------------------------------

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
// SingleRouteOverlay — memoized per-route rendering
// ---------------------------------------------------------------------------

interface SingleRouteOverlayProps {
  routeId: string;
  color: string;
  coords: Coordinate[];
  routeStops: Stop[] | undefined;
  selectedStopId: string | null;
  visible: boolean;
  zBase: number; // unique per route, static at mount — never changes
  onStopPress?: (stopId: string) => void;
}

function SingleRouteOverlay({
  routeId,
  color,
  coords,
  routeStops,
  selectedStopId,
  visible,
  zBase,
  onStopPress,
}: SingleRouteOverlayProps) {
  const fade = useFade(visible);

  // Polylines snap on/off — react-native-maps can't handle strokeColor updates
  // on many polylines per frame without flickering. Only markers animate smoothly.
  const shadowColor = visible ? applyOpacity(color, 0.25) : 'rgba(0,0,0,0)';
  const mainColor = visible ? color : 'rgba(0,0,0,0)';
  const markerOpacity = fade;

  return (
    <>
      {/* Polylines — always mounted, faded via strokeColor alpha */}
      {coords.length >= 2 && (
        <>
          <Polyline
            coordinates={coords}
            strokeColor={shadowColor}
            strokeWidth={9}
            zIndex={zBase}
            lineCap="round"
            lineJoin="round"
          />
          <Polyline
            coordinates={coords}
            strokeColor={mainColor}
            strokeWidth={5}
            zIndex={zBase + 1}
            lineCap="round"
            lineJoin="round"
          />
        </>
      )}

      {/* Stop markers — always mounted, faded via opacity */}
      {routeStops?.map((stop, index) => {
        const isFocused = fade === 1 && stop.stopId === selectedStopId;
        const size = isFocused ? FOCUSED_DOT_SIZE : DOT_SIZE;
        const borderWidth = isFocused ? 2.5 : 1.5;

        return (
          <Marker
            key={`${routeId}-${stop.stopId}-${index}`}
            coordinate={{ latitude: stop.lat, longitude: stop.lon }}
            anchor={{ x: 0.5, y: 0.5 }}
            tracksViewChanges={false}
            zIndex={zBase + 2}
            opacity={markerOpacity}
            onPress={() => onStopPress?.(stop.stopId)}
          >
            <View
              style={[
                styles.stopDot,
                {
                  width: size,
                  height: size,
                  borderRadius: size / 2,
                  borderWidth,
                  backgroundColor: color,
                  borderColor: lighten(color, 0.5),
                },
                isFocused && styles.stopDotFocused,
              ]}
            />
          </Marker>
        );
      })}
    </>
  );
}

const MemoizedSingleRouteOverlay = React.memo(SingleRouteOverlay);

// ---------------------------------------------------------------------------
// RouteOverlay — always renders all routes, toggles visibility via props
// ---------------------------------------------------------------------------

interface RouteOverlayProps {
  onStopPress?: (stopId: string) => void;
}

function RouteOverlay({ onStopPress }: RouteOverlayProps) {
  const selectedRouteId = useAppSelector((state) => state.ui.selectedRouteId);
  const selectedStopId = useAppSelector((state) => state.ui.selectedStopId);

  const routes = useAppSelector((state) => state.routes.list);
  const shapes = useAppSelector((state) => state.routes.shapes);
  const stops = useAppSelector((state) => state.routes.stops);

  // Build route color lookup
  const routeColorMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => {
      const color = r.routeColor
        ? `#${r.routeColor.replace(/^#/, '')}`
        : FALLBACK_COLOR;
      map.set(r.routeId, color);
    });
    return map;
  }, [routes]);

  // Static zBase per route: alphabetical by longName, highest name = highest z.
  // Each route uses 3 z-levels (shadow, main, stops), so stride by 3.
  // Computed once from static route data — never changes.
  const zBaseMap = useMemo(() => {
    const sorted = [...routes].sort((a, b) => a.longName.localeCompare(b.longName));
    const map = new Map<string, number>();
    sorted.forEach((r, i) => map.set(r.routeId, (i + 1) * 3));
    return map;
  }, [routes]);

  return (
    <>
      {routes.map((route) => {
        const coords = shapes[route.routeId];
        if (!coords || coords.length < 2) return null;

        const visible = !selectedRouteId || selectedRouteId === route.routeId;

        return (
          <MemoizedSingleRouteOverlay
            key={route.routeId}
            routeId={route.routeId}
            color={routeColorMap.get(route.routeId) || FALLBACK_COLOR}
            coords={coords}
            routeStops={stops[route.routeId]}
            selectedStopId={selectedStopId}
            visible={visible}
            zBase={zBaseMap.get(route.routeId) || 1}
            onStopPress={onStopPress}
          />
        );
      })}
    </>
  );
}

/** Lighten a hex color by mixing it toward white by the given amount (0–1) */
function lighten(hex: string, amount: number): string {
  const clean = hex.replace(/^#/, '');
  const r = Math.round(parseInt(clean.substring(0, 2), 16) + (255 - parseInt(clean.substring(0, 2), 16)) * amount);
  const g = Math.round(parseInt(clean.substring(2, 4), 16) + (255 - parseInt(clean.substring(2, 4), 16)) * amount);
  const b = Math.round(parseInt(clean.substring(4, 6), 16) + (255 - parseInt(clean.substring(4, 6), 16)) * amount);
  return `rgb(${r}, ${g}, ${b})`;
}

/** Apply opacity to a hex color string, returning rgba */
function applyOpacity(hex: string, opacity: number): string {
  const clean = hex.replace(/^#/, '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

const styles = StyleSheet.create({
  stopDot: {},
  stopDotFocused: {
    ...Platform.select({
      ios: {
        shadowColor: 'rgba(12, 35, 64, 1)',
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.4,
        shadowRadius: 6,
      },
      android: {
        elevation: 6,
      },
    }),
  },
});

export default React.memo(RouteOverlay);
