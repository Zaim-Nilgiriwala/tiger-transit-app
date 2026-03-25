/**
 * MapScreen - Full-screen map centered on Auburn campus
 *
 * The primary and only screen in Phase 1.
 * Renders react-native-maps MapView with:
 * - Auburn campus center (~32.606, -85.487)
 * - Free rotation and 3D tilt enabled
 * - Blue dot for user location (if permission granted)
 * - FloatingLocationButton and GlassBottomBar overlaid
 */
import React, { useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView from 'react-native-maps';

import { colors } from '../theme';
import { useLocation } from '../hooks/useLocation';

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
