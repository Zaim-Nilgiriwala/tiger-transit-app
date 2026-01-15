import React from 'react';
import { StyleSheet, View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { RouteProp, useRoute, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import MapView, { Polyline, Marker } from 'react-native-maps';
import { useGetRouteDetailQuery, useGetRouteShapeQuery } from '../store/api/transitApi';
import { RootStackParamList } from '../types/navigation.types';

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
        <Text>Loading route details...</Text>
      </View>
    );
  }

  if (error || !routeDetail) {
    return (
      <View style={styles.centerContainer}>
        <Text>Error loading route</Text>
      </View>
    );
  }

  if (!routeDetail.stops || routeDetail.stops.length === 0) {
    return (
      <View style={styles.centerContainer}>
        <Text>No stops available for this route</Text>
      </View>
    );
  }

  const routeColor = routeDetail.color ? `#${routeDetail.color}` : '#0C2340';

  // Calculate map region from stops
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
          {/* Route polyline */}
          {polylineCoords.length > 0 && (
            <Polyline
              coordinates={polylineCoords}
              strokeColor={routeColor}
              strokeWidth={4}
            />
          )}

          {/* Stop markers */}
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
          >
            <View style={styles.stopNumber}>
              <Text style={styles.stopNumberText}>{index + 1}</Text>
            </View>
            <View style={styles.stopInfo}>
              <Text style={styles.stopName}>{stop.name}</Text>
              {stop.code && <Text style={styles.stopCode}>Stop #{stop.code}</Text>}
            </View>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    padding: 20,
    alignItems: 'center',
  },
  routeShortName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
  },
  routeLongName: {
    fontSize: 18,
    color: '#fff',
    marginTop: 8,
    textAlign: 'center',
  },
  mapContainer: {
    height: 250,
    margin: 16,
    borderRadius: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  map: {
    flex: 1,
  },
  stopsSection: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#0C2340',
    marginBottom: 12,
  },
  stopItem: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    padding: 16,
    marginBottom: 8,
    borderRadius: 8,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  stopNumber: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#E87722',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  stopNumberText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 14,
  },
  stopInfo: {
    flex: 1,
  },
  stopName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#0C2340',
  },
  stopCode: {
    fontSize: 12,
    color: '#666',
    marginTop: 2,
  },
});

export default RouteDetailScreen;
