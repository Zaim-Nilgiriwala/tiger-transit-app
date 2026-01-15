import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Marker, Callout } from 'react-native-maps';
import { Vehicle } from '../../hooks/useVehicles';

interface VehicleMarkerProps {
  vehicle: Vehicle;
  routeColor?: string;
  routeName?: string;
}

const VehicleMarker: React.FC<VehicleMarkerProps> = ({
  vehicle,
  routeColor = '#0C2340',
  routeName,
}) => {
  const loadPercent = vehicle.capacity > 0
    ? Math.round((vehicle.load / vehicle.capacity) * 100)
    : 0;

  // Determine load status color
  const getLoadColor = () => {
    if (loadPercent >= 80) return '#E74C3C'; // Red - nearly full
    if (loadPercent >= 50) return '#F39C12'; // Orange - filling up
    return '#27AE60'; // Green - plenty of room
  };

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
      {/* Custom bus marker */}
      <View style={styles.markerContainer}>
        <View style={[styles.busCircle, { backgroundColor: routeColor }]}>
          <Text style={styles.busIcon}>🚌</Text>
        </View>
        {/* Direction indicator (arrow) */}
        <View style={[styles.directionArrow, { borderBottomColor: routeColor }]} />
      </View>

      {/* Callout with vehicle info */}
      <Callout tooltip>
        <View style={styles.calloutContainer}>
          <View style={styles.calloutHeader}>
            <Text style={styles.vehicleId}>Bus {vehicle.vehicleId}</Text>
            {vehicle.isDelayed && (
              <View style={styles.delayedBadge}>
                <Text style={styles.delayedText}>DELAYED</Text>
              </View>
            )}
          </View>

          {routeName && (
            <Text style={styles.routeName}>{routeName}</Text>
          )}

          <View style={styles.calloutRow}>
            <Text style={styles.label}>Passengers:</Text>
            <View style={styles.loadContainer}>
              <Text style={[styles.loadText, { color: getLoadColor() }]}>
                {vehicle.load}/{vehicle.capacity}
              </Text>
              <View style={styles.loadBar}>
                <View
                  style={[
                    styles.loadFill,
                    {
                      width: `${loadPercent}%`,
                      backgroundColor: getLoadColor(),
                    },
                  ]}
                />
              </View>
            </View>
          </View>

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
  markerContainer: {
    alignItems: 'center',
  },
  busCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 3,
    borderColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    elevation: 5,
  },
  busIcon: {
    fontSize: 20,
  },
  directionArrow: {
    width: 0,
    height: 0,
    borderLeftWidth: 8,
    borderRightWidth: 8,
    borderBottomWidth: 12,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    marginTop: -4,
  },
  calloutContainer: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    minWidth: 180,
    maxWidth: 220,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 5,
  },
  calloutHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  vehicleId: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#0C2340',
  },
  delayedBadge: {
    backgroundColor: '#E74C3C',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  delayedText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: 'bold',
  },
  routeName: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  calloutRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 6,
  },
  label: {
    fontSize: 12,
    color: '#666',
  },
  loadContainer: {
    alignItems: 'flex-end',
  },
  loadText: {
    fontSize: 12,
    fontWeight: '600',
  },
  loadBar: {
    width: 60,
    height: 4,
    backgroundColor: '#E0E0E0',
    borderRadius: 2,
    marginTop: 2,
    overflow: 'hidden',
  },
  loadFill: {
    height: '100%',
    borderRadius: 2,
  },
  etaText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#E87722',
  },
  speedText: {
    fontSize: 12,
    color: '#0C2340',
  },
});

export default VehicleMarker;
