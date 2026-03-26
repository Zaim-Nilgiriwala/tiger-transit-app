/**
 * MapScreen - Full-screen map with live bus markers and draggable bottom sheet
 *
 * The primary map screen for Tiger Transit. Renders:
 * - Auburn campus center (~32.606, -85.487)
 * - Live bus markers (route-colored, directional heading) updated every 5s
 * - Route polyline + stop markers when a route is selected (RouteOverlay)
 * - Blue dot for user location (if permission granted)
 * - BottomSheet with three snap points (collapsed, half, full)
 * - FloatingLocationButton above the collapsed sheet
 *
 * Data flow:
 * - useStaticData() loads ROUTES into Redux on mount
 * - useVehicleSubscription() subscribes to Supabase Realtime for push-based vehicle updates
 * - dispatches positions to Redux on each Realtime change notification
 * - useAppSelector reads vehicle positions, route list, and sheet position
 * - BusMarker rendered per vehicle as a child of MapView
 * - RouteOverlay rendered inside MapView when a route is selected
 * - mapPadding adjusts dynamically based on sheet snap position
 *
 * Route selection behavior:
 * - Auto-fit: map fits to show all stops + buses for selected route
 * - Stop centering: tapping a stop in the list centers the map on it
 * - Bus dimming: non-selected route buses dim to 30% opacity
 * - Back (deselect): overlays removed, bus opacity restored, camera stays
 *
 * Render order: MapView (fills screen) -> RouteOverlay (polyline/stops) ->
 *   BusMarkers (map children) -> BottomSheet (draggable) ->
 *   FloatingLocationButton (above sheet)
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import MapView from 'react-native-maps';

import { colors } from '../theme';
import { useAppSelector } from '../store';
import { useLocation } from '../hooks/useLocation';
import { useStaticData } from '../hooks/useStaticData';
import { useStaticRouteData } from '../hooks/useStaticRouteData';
import { useVehicleSubscription } from '../hooks/useVehicleSubscription';
import FloatingLocationButton from '../components/map/FloatingLocationButton';
import BottomSheet from '../components/sheet/BottomSheet';
import RouteList from '../components/sheet/RouteList';
import BusMarker from '../components/map/BusMarker';
import RouteOverlay from '../components/map/RouteOverlay';

/** Fallback marker color when routeId is not found in ROUTES */
const FALLBACK_COLOR = '#FF8934';

/** Auburn University campus center */
const AUBURN_CAMPUS = {
  latitude: 32.606,
  longitude: -85.487,
  latitudeDelta: 0.025,
  longitudeDelta: 0.025,
};

export default function MapScreen() {
  const mapRef = useRef<MapView>(null);
  const { height: screenHeight } = useWindowDimensions();
  const { location, permissionDenied } = useLocation();

  // -----------------------------------------------------------------------
  // Data hooks: load static routes and start real-time polling
  // -----------------------------------------------------------------------
  useStaticData();
  useStaticRouteData();
  useVehicleSubscription();

  // -----------------------------------------------------------------------
  // Read vehicle positions, route list, and UI state from Redux
  // -----------------------------------------------------------------------
  const positions = useAppSelector((state) => state.vehicles.positions);
  const routes = useAppSelector((state) => state.routes.list);
  const routesLoading = useAppSelector((state) => state.routes.loading);
  const sheetPosition = useAppSelector((state) => state.ui.sheetPosition);

  // Route selection state
  const selectedRouteId = useAppSelector((state) => state.ui.selectedRouteId);
  const selectedStopId = useAppSelector((state) => state.ui.selectedStopId);
  const routeStops = useAppSelector((state) =>
    selectedRouteId ? state.routes.stops[selectedRouteId] : undefined
  );

  // Memoized route color lookup: routeId -> '#RRGGBB'
  const routeColorMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => map.set(r.routeId, r.routeColor));
    return map;
  }, [routes]);

  // -----------------------------------------------------------------------
  // Auto-fit map when a route is selected (MAP-07)
  // -----------------------------------------------------------------------
  useEffect(() => {
    // Only fit when a route is newly selected, not on deselect (camera stays)
    if (!selectedRouteId) return;

    const allCoords: { latitude: number; longitude: number }[] = [];

    // Add stop coordinates
    if (routeStops) {
      routeStops.forEach((stop) => {
        allCoords.push({ latitude: stop.lat, longitude: stop.lon });
      });
    }

    // Add active bus positions for this route
    positions
      .filter((v) => v.routeId === selectedRouteId)
      .forEach((v) => {
        allCoords.push({ latitude: v.lat, longitude: v.lon });
      });

    // Need at least 2 coordinates for fitToCoordinates
    if (allCoords.length >= 2) {
      mapRef.current?.fitToCoordinates(allCoords, {
        edgePadding: {
          top: 60,
          right: 40,
          bottom: Math.round(screenHeight * 0.45) + 20,
          left: 40,
        },
        animated: true,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRouteId]);

  // -----------------------------------------------------------------------
  // Center map on tapped stop (ROUTE-09)
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!selectedStopId || !routeStops) return;

    const stop = routeStops.find((s) => s.stopId === selectedStopId);
    if (stop) {
      mapRef.current?.animateToRegion(
        {
          latitude: stop.lat,
          longitude: stop.lon,
          latitudeDelta: 0.008,
          longitudeDelta: 0.008,
        },
        500
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStopId]);

  // -----------------------------------------------------------------------
  // Dynamic map padding based on sheet position
  // -----------------------------------------------------------------------
  const mapPadding = useMemo(() => {
    let bottom: number;
    switch (sheetPosition) {
      case 'half':
        bottom = Math.round(screenHeight * 0.45);
        break;
      case 'full':
        bottom = Math.round(screenHeight * 0.90);
        break;
      case 'collapsed':
      default:
        bottom = 80;
        break;
    }
    return { top: 0, right: 0, bottom, left: 0 };
  }, [sheetPosition, screenHeight]);

  return (
    <View style={styles.container}>
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        initialRegion={AUBURN_CAMPUS}
        rotateEnabled={true}
        pitchEnabled={true}
        showsUserLocation={true}
        showsMyLocationButton={false}
        mapPadding={mapPadding}
      >
        {/* Route polyline + stop markers (rendered before buses so buses are on top) */}
        <RouteOverlay />

        {/* Bus markers with opacity dimming for non-selected routes */}
        {positions.map((vehicle) => (
          <BusMarker
            key={vehicle.vehicleId}
            vehicle={vehicle}
            routeColor={routeColorMap.get(vehicle.routeId) || FALLBACK_COLOR}
            zIndex={vehicle.timestamp}
            opacity={
              selectedRouteId
                ? vehicle.routeId === selectedRouteId
                  ? 1
                  : 0.3
                : 1
            }
          />
        ))}
      </MapView>
      <BottomSheet loading={routesLoading}>
        <RouteList />
      </BottomSheet>
      <FloatingLocationButton
        mapRef={mapRef}
        location={location}
        permissionDenied={permissionDenied}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
});
