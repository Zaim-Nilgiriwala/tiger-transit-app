/**
 * MapScreen - Full-screen map with live bus markers
 *
 * The primary map screen for Tiger Transit. Renders:
 * - Auburn campus center (~32.606, -85.487)
 * - Live bus markers (route-colored, directional heading) updated every 5s
 * - Blue dot for user location (if permission granted)
 * - FloatingLocationButton and GlassBottomBar overlaid
 *
 * Data flow:
 * - useStaticData() loads ROUTES into Redux on mount
 * - useGtfsPolling() starts 5s polling lifecycle, dispatches positions to Redux
 * - useAppSelector reads vehicle positions and route list from Redux
 * - BusMarker rendered per vehicle as a child of MapView
 *
 * Render order: MapView (fills screen) -> BusMarkers (map children) ->
 *   GlassBottomBar (bottom) -> FloatingLocationButton (bottom-left above bar)
 */
import React, { useMemo, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView from 'react-native-maps';

import { colors } from '../theme';
import { useAppSelector } from '../store';
import { useLocation } from '../hooks/useLocation';
import { useStaticData } from '../hooks/useStaticData';
import { useGtfsPolling } from '../hooks/useGtfsPolling';
import FloatingLocationButton from '../components/map/FloatingLocationButton';
import GlassBottomBar from '../components/map/GlassBottomBar';
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
  const { location, permissionDenied } = useLocation();

  // -----------------------------------------------------------------------
  // Data hooks: load static routes and start real-time polling
  // -----------------------------------------------------------------------
  useStaticData();
  useGtfsPolling();

  // -----------------------------------------------------------------------
  // Read vehicle positions and route list from Redux
  // -----------------------------------------------------------------------
  const positions = useAppSelector((state) => state.vehicles.positions);
  const routes = useAppSelector((state) => state.routes.list);

  // Memoized route color lookup: routeId -> '#RRGGBB'
  const routeColorMap = useMemo(() => {
    const map = new Map<string, string>();
    routes.forEach((r) => map.set(r.routeId, r.routeColor));
    return map;
  }, [routes]);

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
        mapPadding={{ top: 0, right: 0, bottom: 80, left: 0 }}
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
      <GlassBottomBar />
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
