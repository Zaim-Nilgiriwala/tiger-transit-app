import React, { useMemo } from 'react';
import { StyleSheet, View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { RouteProp, useRoute, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import MapView, { Marker } from 'react-native-maps';
import { useGetStopDetailQuery, useGetStopRoutesQuery } from '../store/api/transitApi';
import { useStopArrivals } from '../hooks/useVehicles';
import { RootStackParamList } from '../types/navigation.types';

type StopDetailRouteProp = RouteProp<RootStackParamList, 'StopDetail'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const StopDetailScreen: React.FC = () => {
  const route = useRoute<StopDetailRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { stopId } = route.params;

  const { data: stopDetail, isLoading: stopLoading } = useGetStopDetailQuery(stopId);
  const { data: routes, isLoading: routesLoading } = useGetStopRoutesQuery(stopId);
  const { arrivals, connected } = useStopArrivals(stopId);

  // Create route info lookup
  const routeInfo = useMemo(() => {
    if (!routes) return {};
    return routes.reduce((acc, r) => {
      acc[r.id] = {
        color: r.color ? `#${r.color}` : '#0C2340',
        shortName: r.shortName,
        longName: r.longName,
      };
      return acc;
    }, {} as Record<string, { color: string; shortName: string | null; longName: string }>);
  }, [routes]);

  const formatEta = (seconds: number) => {
    if (seconds <= 60) return '<1';
    return Math.ceil(seconds / 60).toString();
  };

  if (stopLoading || routesLoading) {
    return (
      <View style={styles.centerContainer}>
        <Text>Loading stop details...</Text>
      </View>
    );
  }

  if (!stopDetail) {
    return (
      <View style={styles.centerContainer}>
        <Text>Error loading stop</Text>
      </View>
    );
  }

  const region = {
    latitude: stopDetail.lat,
    longitude: stopDetail.lon,
    latitudeDelta: 0.01,
    longitudeDelta: 0.01,
  };

  return (
    <ScrollView style={styles.container}>
      {/* Stop Header */}
      <View style={styles.header}>
        <Text style={styles.stopName}>{stopDetail.name}</Text>
        {stopDetail.code && (
          <Text style={styles.stopCode}>Stop #{stopDetail.code}</Text>
        )}
      </View>

      {/* Map */}
      <View style={styles.mapContainer}>
        <MapView
          style={styles.map}
          initialRegion={region}
          scrollEnabled={false}
          zoomEnabled={false}
        >
          <Marker
            coordinate={{
              latitude: stopDetail.lat,
              longitude: stopDetail.lon,
            }}
            pinColor="#E87722"
          />
        </MapView>
      </View>

      {/* Live Arrivals Section */}
      {connected && arrivals.length > 0 && (
        <View style={styles.arrivalsSection}>
          <View style={styles.arrivalsSectionHeader}>
            <View style={styles.liveIndicator}>
              <View style={styles.liveDot} />
              <Text style={styles.liveLabel}>LIVE</Text>
            </View>
            <Text style={styles.sectionTitle}>Arriving Buses</Text>
          </View>
          {arrivals.slice(0, 5).map((arrival) => {
            const info = routeInfo[arrival.routeId];
            const etaMinutes = formatEta(arrival.etaSeconds);
            const loadPercent = arrival.capacity > 0
              ? Math.round((arrival.load / arrival.capacity) * 100)
              : 0;

            return (
              <View key={arrival.vehicleId} style={styles.arrivalCard}>
                <View style={[styles.arrivalColorIndicator, { backgroundColor: info?.color || '#0C2340' }]} />
                <View style={styles.arrivalInfo}>
                  <View style={styles.arrivalTopRow}>
                    <Text style={styles.arrivalRouteName}>
                      {info?.shortName || `Route ${arrival.routeId}`}
                    </Text>
                    {arrival.isDelayed && (
                      <View style={styles.delayedBadge}>
                        <Text style={styles.delayedText}>DELAYED</Text>
                      </View>
                    )}
                  </View>
                  <Text style={styles.arrivalBusInfo}>
                    Bus {arrival.vehicleId} • {arrival.load}/{arrival.capacity} passengers
                  </Text>
                  <View style={styles.loadBarContainer}>
                    <View style={styles.loadBar}>
                      <View
                        style={[
                          styles.loadFill,
                          {
                            width: `${loadPercent}%`,
                            backgroundColor: loadPercent >= 80 ? '#E74C3C' : loadPercent >= 50 ? '#F39C12' : '#27AE60',
                          },
                        ]}
                      />
                    </View>
                  </View>
                </View>
                <View style={styles.etaContainer}>
                  <Text style={styles.etaMinutes}>{etaMinutes}</Text>
                  <Text style={styles.etaLabel}>min</Text>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* No Live Data Banner */}
      {!connected && (
        <View style={styles.noLiveDataBanner}>
          <Text style={styles.noLiveDataText}>Connecting to live data...</Text>
        </View>
      )}

      {connected && arrivals.length === 0 && (
        <View style={styles.noArrivalsBanner}>
          <Text style={styles.noArrivalsText}>No buses currently approaching this stop</Text>
        </View>
      )}

      {/* Routes Serving This Stop */}
      <View style={styles.routesSection}>
        <Text style={styles.sectionTitle}>Routes ({routes?.length || 0})</Text>
        {routes?.map((route) => {
          const backgroundColor = route.color ? `#${route.color}` : '#0C2340';

          return (
            <TouchableOpacity
              key={route.id}
              style={styles.routeCard}
              onPress={() => navigation.navigate('RouteDetail', { routeId: route.id })}
            >
              <View style={[styles.colorIndicator, { backgroundColor }]} />
              <View style={styles.routeInfo}>
                <Text style={styles.routeShortName}>{route.shortName}</Text>
                <Text style={styles.routeLongName}>{route.longName}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
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
    backgroundColor: '#0C2340',
    alignItems: 'center',
  },
  stopName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    textAlign: 'center',
  },
  stopCode: {
    fontSize: 16,
    color: '#E87722',
    marginTop: 4,
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
  routesSection: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#0C2340',
    marginBottom: 12,
  },
  routeCard: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 8,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  colorIndicator: {
    width: 8,
    borderTopLeftRadius: 8,
    borderBottomLeftRadius: 8,
  },
  routeInfo: {
    flex: 1,
    padding: 16,
  },
  routeShortName: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#0C2340',
  },
  routeLongName: {
    fontSize: 14,
    color: '#666',
    marginTop: 4,
  },
  arrivalsSection: {
    padding: 16,
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  arrivalsSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  liveIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#27AE60',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    marginRight: 10,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#fff',
    marginRight: 4,
  },
  liveLabel: {
    color: '#fff',
    fontSize: 10,
    fontWeight: 'bold',
  },
  arrivalCard: {
    flexDirection: 'row',
    backgroundColor: '#f9f9f9',
    borderRadius: 8,
    marginBottom: 10,
    overflow: 'hidden',
  },
  arrivalColorIndicator: {
    width: 6,
  },
  arrivalInfo: {
    flex: 1,
    padding: 12,
  },
  arrivalTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  arrivalRouteName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#0C2340',
  },
  delayedBadge: {
    backgroundColor: '#E74C3C',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    marginLeft: 8,
  },
  delayedText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: 'bold',
  },
  arrivalBusInfo: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  loadBarContainer: {
    marginTop: 6,
  },
  loadBar: {
    height: 4,
    backgroundColor: '#E0E0E0',
    borderRadius: 2,
    overflow: 'hidden',
  },
  loadFill: {
    height: '100%',
    borderRadius: 2,
  },
  etaContainer: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
    backgroundColor: '#E87722',
    minWidth: 70,
  },
  etaMinutes: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  etaLabel: {
    fontSize: 12,
    color: '#fff',
    opacity: 0.9,
  },
  noLiveDataBanner: {
    marginHorizontal: 16,
    marginTop: 16,
    padding: 16,
    backgroundColor: '#FFF3CD',
    borderRadius: 8,
    alignItems: 'center',
  },
  noLiveDataText: {
    color: '#856404',
    fontSize: 14,
  },
  noArrivalsBanner: {
    marginHorizontal: 16,
    marginTop: 16,
    padding: 16,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    alignItems: 'center',
  },
  noArrivalsText: {
    color: '#666',
    fontSize: 14,
  },
});

export default StopDetailScreen;
