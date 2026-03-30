/**
 * FloatingLocationButton - Glass-panel my_location FAB
 *
 * Positioned bottom-right above the collapsed bottom bar.
 * Uses BlurView for glassmorphism backdrop blur.
 * Tapping centers the map on the user's GPS position.
 * No-op if location permission was denied.
 */
import React, { useCallback } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { BlurView } from 'expo-blur';
import { MaterialIcons } from '@expo/vector-icons';
import MapView from 'react-native-maps';

import { textColors, shadows, spacing, EDGE_MARGIN } from '../../theme';
import type { LocationCoords } from '../../hooks/useLocation';

/** Bottom bar height (80px) + gap above it */
const BOTTOM_OFFSET = 80 + spacing.s2;
const BUTTON_SIZE = 48;

interface FloatingLocationButtonProps {
  mapRef: React.RefObject<MapView | null>;
  location: LocationCoords | null;
  permissionDenied: boolean;
}

export default function FloatingLocationButton({
  mapRef,
  location,
  permissionDenied,
}: FloatingLocationButtonProps) {
  const handlePress = useCallback(() => {
    // No-op if permission denied or location unavailable
    if (permissionDenied || !location) return;

    mapRef.current?.animateToRegion(
      {
        latitude: location.latitude,
        longitude: location.longitude,
        latitudeDelta: 0.01,
        longitudeDelta: 0.01,
      },
      500
    );
  }, [mapRef, location, permissionDenied]);

  return (
    <View style={styles.container}>
      <Pressable
        onPress={handlePress}
        style={({ pressed }) => [
          styles.pressable,
          pressed && styles.pressed,
        ]}
        accessibilityLabel="Center map on my location"
        accessibilityRole="button"
      >
        <BlurView intensity={20} tint="light" style={styles.blur}>
          <View style={styles.iconContainer}>
            <MaterialIcons
              name="my-location"
              size={24}
              color={textColors.onSurface}
            />
          </View>
        </BlurView>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    bottom: BOTTOM_OFFSET,
    right: EDGE_MARGIN,
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    borderRadius: BUTTON_SIZE / 2,
    overflow: 'hidden',
    ...shadows.ambient,
  },
  pressable: {
    flex: 1,
  },
  pressed: {
    opacity: 0.7,
  },
  blur: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
  },
  iconContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
