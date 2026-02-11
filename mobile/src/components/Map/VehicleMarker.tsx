import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Marker, Callout } from 'react-native-maps';
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

const VehicleMarker: React.FC<VehicleMarkerProps> = ({
  vehicle,
  routeColor = Colors.navy,
  routeName,
}) => {
  const formatEta = (seconds: number) => {
    if (seconds <= 0) return 'Arriving';
    const minutes = Math.ceil(seconds / 60);
    return `${minutes} min`;
  };

  return (
    <Marker
      coordinate={{
        latitude: vehicle.lat,
        longitude: vehicle.lon,
      }}
      rotation={vehicle.heading}
      anchor={{ x: 0.5, y: 0.5 }}
      flat={true}
      tracksViewChanges={false}
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
    </Marker>
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
