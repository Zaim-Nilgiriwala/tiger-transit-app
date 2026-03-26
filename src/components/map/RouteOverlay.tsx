/**
 * RouteOverlay - Polyline and stop markers for the selected route
 *
 * Renders as children of MapView when a route is selected:
 * - A shadow polyline (wider, navy-tinted) for depth effect
 * - A main polyline in the route's color showing the path
 * - Marker-based circular stop dots (12px default, 20px when focused)
 *
 * All state is read from Redux (no props required).
 * Returns null when no route is selected.
 */
import React from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { Marker, Polyline } from 'react-native-maps';

import { useAppSelector } from '../../store';

/** Fallback route color when route is not found in list */
const FALLBACK_COLOR = '#FF8934';

/** Default stop marker size (diameter in px) */
const DOT_SIZE = 12;

/** Focused stop marker size (diameter in px) */
const FOCUSED_DOT_SIZE = 20;

function RouteOverlay() {
  const selectedRouteId = useAppSelector((state) => state.ui.selectedRouteId);
  const selectedStopId = useAppSelector((state) => state.ui.selectedStopId);

  const routes = useAppSelector((state) => state.routes.list);
  const shapes = useAppSelector((state) => state.routes.shapes);
  const stops = useAppSelector((state) => state.routes.stops);

  // Nothing to render when no route is selected
  if (!selectedRouteId) return null;

  const shapeCoordinates = shapes[selectedRouteId];
  const routeStops = stops[selectedRouteId];

  // Determine route color from route list, fallback to orange
  const route = routes.find((r) => r.routeId === selectedRouteId);
  const routeColor = route?.routeColor
    ? `#${route.routeColor.replace(/^#/, '')}`
    : FALLBACK_COLOR;

  return (
    <>
      {/* Shadow polyline: wider, navy-tinted, renders behind main polyline */}
      {shapeCoordinates && shapeCoordinates.length >= 2 && (
        <Polyline
          coordinates={shapeCoordinates}
          strokeColor="rgba(12, 35, 64, 0.25)"
          strokeWidth={9}
          zIndex={0}
          lineCap="round"
          lineJoin="round"
        />
      )}

      {/* Main polyline: route color, on top of shadow */}
      {shapeCoordinates && shapeCoordinates.length >= 2 && (
        <Polyline
          coordinates={shapeCoordinates}
          strokeColor={routeColor}
          strokeWidth={5}
          zIndex={1}
          lineCap="round"
          lineJoin="round"
        />
      )}

      {/* Stop markers: small circles at each stop position */}
      {routeStops?.map((stop) => {
        const isFocused = stop.stopId === selectedStopId;
        const size = isFocused ? FOCUSED_DOT_SIZE : DOT_SIZE;
        const borderWidth = isFocused ? 2.5 : 1.5;

        return (
          <Marker
            key={stop.stopId}
            coordinate={{ latitude: stop.lat, longitude: stop.lon }}
            anchor={{ x: 0.5, y: 0.5 }}
            tracksViewChanges={false}
            zIndex={2}
          >
            <View
              style={[
                styles.stopDot,
                {
                  width: size,
                  height: size,
                  borderRadius: size / 2,
                  borderWidth,
                  backgroundColor: routeColor,
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

const styles = StyleSheet.create({
  stopDot: {
    borderColor: '#FFFFFF',
  },
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
