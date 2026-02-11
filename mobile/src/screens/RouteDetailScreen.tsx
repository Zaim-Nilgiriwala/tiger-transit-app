import React from 'react';
import { StyleSheet, View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { RouteProp, useRoute, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import MapView, { Polyline, Marker } from 'react-native-maps';
import { useGetRouteDetailQuery, useGetRouteShapeQuery } from '../store/api/transitApi';
import { RootStackParamList } from '../types/navigation.types';
import { Colors, Typography, Radius, Shadows, Spacing } from '../theme';

type RouteDetailRouteProp = RouteProp<RootStackParamList, 'RouteDetail'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const RouteDetailScreen: React.FC = () => {
  const route = useRoute<RouteDetailRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { routeId } = route.params;

  const { data: routeDetail, isLoading, error } = useGetRouteDetailQuery(routeId);
  const { data: routeShape } = useGetRouteShapeQuery({ routeId });

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={Colors.orange} />
      </View>
    );
  }

  if (error || !routeDetail) {
    return (
      <View style={styles.centerContainer}>
        <Ionicons name="alert-circle-outline" size={40} color={Colors.error} />
        <Text style={styles.errorText}>Error loading route</Text>
      </View>
    );
  }

  if (!routeDetail.stops || routeDetail.stops.length === 0) {
    return (
      <View style={styles.centerContainer}>
        <Ionicons name="location-outline" size={40} color={Colors.gray400} />
        <Text style={styles.errorText}>No stops available for this route</Text>
      </View>
    );
  }

  const routeColor = routeDetail.color ? `#${routeDetail.color}` : Colors.navy;

  const stops = routeDetail.stops;
  const lats = stops.map(s => s.lat);
  const lons = stops.map(s => s.lon);
  const region = {
    latitude: (Math.min(...lats) + Math.max(...lats)) / 2,
    longitude: (Math.min(...lons) + Math.max(...lons)) / 2,
    latitudeDelta: (Math.max(...lats) - Math.min(...lats)) * 1.2,
    longitudeDelta: (Math.max(...lons) - Math.min(...lons)) * 1.2,
  };

  const polylineCoords = routeShape?.coordinates?.map(coord => ({
    latitude: coord.lat,
    longitude: coord.lon,
  })) || [];

  return (
    <ScrollView style={styles.container}>
      {/* Route Header */}
      <View style={[styles.header, { backgroundColor: routeColor }]}>
        <Text style={styles.routeShortName}>{routeDetail.shortName}</Text>
        <Text style={styles.routeLongName}>{routeDetail.longName}</Text>
      </View>

      {/* Map */}
      <View style={styles.mapContainer}>
        <MapView
          style={styles.map}
          initialRegion={region}
          scrollEnabled={false}
          zoomEnabled={false}
        >
          {polylineCoords.length > 0 && (
            <Polyline
              coordinates={polylineCoords}
              strokeColor={routeColor}
              strokeWidth={3.5}
            />
          )}

          {stops.map((stop) => (
            <Marker
              key={stop.id}
              coordinate={{
                latitude: stop.lat,
                longitude: stop.lon,
              }}
              pinColor={routeColor}
            />
          ))}
        </MapView>
      </View>

      {/* Stops List */}
      <View style={styles.stopsSection}>
        <Text style={styles.sectionTitle}>Stops ({stops.length})</Text>
        {stops.map((stop, index) => (
          <TouchableOpacity
            key={stop.id}
            style={styles.stopItem}
            onPress={() => navigation.navigate('StopDetail', { stopId: stop.id })}
            activeOpacity={0.7}
          >
            <View style={styles.stopNumber}>
              <Text style={styles.stopNumberText}>{index + 1}</Text>
            </View>
            <View style={styles.stopInfo}>
              <Text style={styles.stopName}>{stop.name}</Text>
              {stop.code && <Text style={styles.stopCode}>Stop #{stop.code}</Text>}
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.gray400} />
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
  },
  errorText: {
    fontSize: Typography.size.md,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
  },
  header: {
    paddingVertical: Spacing.xl,
    paddingHorizontal: Spacing.lg,
    alignItems: 'center',
  },
  routeShortName: {
    fontSize: Typography.size['3xl'],
    fontWeight: Typography.weight.bold,
    color: Colors.white,
  },
  routeLongName: {
    fontSize: Typography.size.lg,
    color: Colors.white,
    marginTop: Spacing.sm,
    textAlign: 'center',
    opacity: 0.9,
  },
  mapContainer: {
    height: 220,
    margin: Spacing.lg,
    borderRadius: Radius.lg,
    overflow: 'hidden',
    ...Shadows.md,
  },
  map: {
    flex: 1,
  },
  stopsSection: {
    padding: Spacing.lg,
  },
  sectionTitle: {
    fontSize: Typography.size.xl,
    fontWeight: Typography.weight.bold,
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },
  stopItem: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    padding: Spacing.lg,
    marginBottom: Spacing.sm,
    borderRadius: Radius.md,
    alignItems: 'center',
    ...Shadows.sm,
  },
  stopNumber: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: Colors.gray300,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: Spacing.md,
  },
  stopNumberText: {
    color: Colors.gray700,
    fontWeight: Typography.weight.bold,
    fontSize: Typography.size.sm,
  },
  stopInfo: {
    flex: 1,
  },
  stopName: {
    fontSize: Typography.size.md,
    fontWeight: Typography.weight.semibold,
    color: Colors.textPrimary,
  },
  stopCode: {
    fontSize: Typography.size.xs,
    color: Colors.textSecondary,
    marginTop: 2,
  },
});

export default RouteDetailScreen;
