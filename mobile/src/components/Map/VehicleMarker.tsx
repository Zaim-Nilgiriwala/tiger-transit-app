import React, { useRef, useEffect } from 'react';
import { View, Text, StyleSheet, Animated as RNAnimated } from 'react-native';
import { MarkerAnimated, AnimatedRegion, Callout } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';
import { Vehicle } from '../../hooks/useVehicles';
import Badge from '../Common/Badge';
import LoadBar from '../Common/LoadBar';
import { Colors, Typography, Radius, Shadows, Spacing } from '../../theme';

interface VehicleMarkerProps {
  vehicle: Vehicle;
  routeColor?: string;
  routeName?: string;
}

const ANIMATION_DURATION = 1000;

const VehicleMarker: React.FC<VehicleMarkerProps> = ({
  vehicle,
  routeColor = Colors.navy,
  routeName,
}) => {
  // AnimatedRegion for smooth coordinate interpolation
  const animatedCoordinate = useRef(
    new AnimatedRegion({
      latitude: vehicle.lat,
      longitude: vehicle.lon,
      latitudeDelta: 0,
      longitudeDelta: 0,
    })
  ).current;

  // Animated.Value for smooth heading rotation
  const animatedHeading = useRef(new RNAnimated.Value(vehicle.heading)).current;

  // Track current heading for shortest-path wraparound calculation
  const currentHeadingRef = useRef(vehicle.heading);

  // Track previous vehicleId to detect marker reuse (defensive)
  const prevVehicleIdRef = useRef(vehicle.vehicleId);

  // Track whether this is the first render (skip animation on mount)
  const isFirstRender = useRef(true);

  useEffect(() => {
    // Skip animation on first render -- marker should appear at its initial position
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    // If vehicleId changed (marker recycled for different bus), snap immediately
    if (prevVehicleIdRef.current !== vehicle.vehicleId) {
      animatedCoordinate.setValue({
        latitude: vehicle.lat,
        longitude: vehicle.lon,
        latitudeDelta: 0,
        longitudeDelta: 0,
      });
      animatedHeading.setValue(vehicle.heading);
      currentHeadingRef.current = vehicle.heading;
      prevVehicleIdRef.current = vehicle.vehicleId;
      return;
    }

    // Animate coordinate smoothly over 1 second
    // toValue is required by TimingAnimationConfig types but ignored by AnimatedRegion
    // which reads latitude/longitude directly from the config object
    animatedCoordinate
      .timing({
        latitude: vehicle.lat,
        longitude: vehicle.lon,
        latitudeDelta: 0,
        longitudeDelta: 0,
        toValue: 0,
        duration: ANIMATION_DURATION,
        useNativeDriver: false,
      })
      .start();

    // Animate heading with shortest-path wraparound
    // Compute shortest angular distance to avoid 350-degree spins
    const currentHeading = currentHeadingRef.current;
    let delta = vehicle.heading - currentHeading;
    if (delta > 180) delta -= 360;
    if (delta < -180) delta += 360;
    const targetHeading = currentHeading + delta;

    RNAnimated.timing(animatedHeading, {
      toValue: targetHeading,
      duration: ANIMATION_DURATION,
      useNativeDriver: false,
    }).start();

    currentHeadingRef.current = targetHeading;
    prevVehicleIdRef.current = vehicle.vehicleId;
  }, [vehicle.lat, vehicle.lon, vehicle.heading, vehicle.vehicleId]);

  const formatEta = (seconds: number) => {
    if (seconds <= 0) return 'Arriving';
    const minutes = Math.ceil(seconds / 60);
    return `${minutes} min`;
  };

  return (
    <MarkerAnimated
      coordinate={animatedCoordinate as any}
      rotation={animatedHeading as any}
      anchor={{ x: 0.5, y: 0.5 }}
      flat={true}
      tracksViewChanges={true}
    >
      {/* Custom bus marker - compact circle with Ionicons bus */}
      <View style={[styles.busCircle, { backgroundColor: routeColor }]}>
        <Ionicons name="bus" size={16} color={Colors.white} />
      </View>

      {/* Callout with vehicle info */}
      <Callout tooltip>
        <View style={styles.calloutContainer}>
          <View style={styles.calloutHeader}>
            <Text style={styles.vehicleId}>Bus {vehicle.vehicleId}</Text>
            {vehicle.isDelayed && <Badge label="DELAYED" variant="delayed" />}
          </View>

          {routeName && (
            <Text style={styles.routeName}>{routeName}</Text>
          )}

          <View style={styles.calloutRow}>
            <Text style={styles.label}>Passengers:</Text>
            <Text style={styles.loadText}>
              {vehicle.load}/{vehicle.capacity}
            </Text>
          </View>
          <LoadBar load={vehicle.load} capacity={vehicle.capacity} width={120} />

          {vehicle.nextStopId && vehicle.etaSeconds > 0 && (
            <View style={styles.calloutRow}>
              <Text style={styles.label}>Next Stop ETA:</Text>
              <Text style={styles.etaText}>{formatEta(vehicle.etaSeconds)}</Text>
            </View>
          )}

          {vehicle.speed > 0 && (
            <View style={styles.calloutRow}>
              <Text style={styles.label}>Speed:</Text>
              <Text style={styles.speedText}>{Math.round(vehicle.speed)} mph</Text>
            </View>
          )}
        </View>
      </Callout>
    </MarkerAnimated>
  );
};

const styles = StyleSheet.create({
  busCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2.5,
    borderColor: Colors.white,
    ...Shadows.sm,
  },
  calloutContainer: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    minWidth: 180,
    maxWidth: 220,
    ...Shadows.md,
  },
  calloutHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.xs,
  },
  vehicleId: {
    fontSize: Typography.size.lg,
    fontWeight: Typography.weight.bold,
    color: Colors.textPrimary,
  },
  routeName: {
    fontSize: Typography.size.sm,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  calloutRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 6,
  },
  label: {
    fontSize: Typography.size.xs,
    color: Colors.textSecondary,
  },
  loadText: {
    fontSize: Typography.size.xs,
    fontWeight: Typography.weight.semibold,
    color: Colors.textPrimary,
  },
  etaText: {
    fontSize: Typography.size.xs,
    fontWeight: Typography.weight.semibold,
    color: Colors.orange,
  },
  speedText: {
    fontSize: Typography.size.xs,
    color: Colors.textPrimary,
  },
});

export default VehicleMarker;
