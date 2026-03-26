/**
 * MapScreen - Full-screen map with live bus markers and draggable bottom sheet
 *
 * The primary map screen for Tiger Transit. Renders:
 * - Auburn campus center (~32.606, -85.487)
 * - Live bus markers (route-colored, directional heading) updated every 5s
 * - Blue dot for user location (if permission granted)
 * - BottomSheet with three snap points (collapsed, half, full)
 * - FloatingLocationButton above the collapsed sheet
 *
 * Data flow:
 * - useStaticData() loads ROUTES into Redux on mount
 * - useGtfsPolling() starts 5s polling lifecycle, dispatches positions to Redux
 * - useAppSelector reads vehicle positions, route list, and sheet position
 * - BusMarker rendered per vehicle as a child of MapView
 * - mapPadding adjusts dynamically based on sheet snap position
 *
 * Render order: MapView (fills screen) -> BusMarkers (map children) ->
 *   BottomSheet (draggable) -> FloatingLocationButton (above sheet)
 */
import React, { useMemo, useRef } from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import MapView from 'react-native-maps';

import { colors } from '../theme';
import { useAppSelector } from '../store';
import { useLocation } from '../hooks/useLocation';
import { useStaticData } from '../hooks/useStaticData';
import { useGtfsPolling } from '../hooks/useGtfsPolling';
import FloatingLocationButton from '../components/map/FloatingLocationButton';
import BottomSheet from '../components/sheet/BottomSheet';
import RouteList from '../components/sheet/RouteList';
import BusMarker from '../components/map/BusMarker';

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
  useGtfsPolling();

  // -----------------------------------------------------------------------
  // Read vehicle positions, route list, and UI state from Redux
  // -----------------------------------------------------------------------
  const positions = useAppSelector((state) => state.vehicles.positions);
  const routes = useAppSelector((state) => state.routes.list);
  const routesLoading = useAppSelector((state) => state.routes.loading);
  const sheetPosition = useAppSelector((state) => state.ui.sheetPosition);

  // Memoized route color lookup: routeId -> '#RRGGBB'
  const routeColorMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => map.set(r.routeId, r.routeColor));
    return map;
  }, [routes]);

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
        {positions.map((vehicle) => (
          <BusMarker
            key={vehicle.vehicleId}
            vehicle={vehicle}
            routeColor={routeColorMap.get(vehicle.routeId) || FALLBACK_COLOR}
            zIndex={vehicle.timestamp}
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
