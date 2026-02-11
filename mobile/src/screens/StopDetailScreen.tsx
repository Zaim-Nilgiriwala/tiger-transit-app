import React, { useMemo } from 'react';
import { StyleSheet, View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { RouteProp, useRoute, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import MapView, { Marker } from 'react-native-maps';
import { useGetStopDetailQuery, useGetStopRoutesQuery } from '../store/api/transitApi';
import { useStopArrivals } from '../hooks/useVehicles';
import { RootStackParamList } from '../types/navigation.types';
import Badge from '../components/Common/Badge';
import LoadBar from '../components/Common/LoadBar';
import { Colors, Typography, Radius, Shadows, Spacing } from '../theme';

type StopDetailRouteProp = RouteProp<RootStackParamList, 'StopDetail'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const StopDetailScreen: React.FC = () => {
  const route = useRoute<StopDetailRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { stopId } = route.params;

  const { data: stopDetail, isLoading: stopLoading } = useGetStopDetailQuery(stopId);
  const { data: routes, isLoading: routesLoading } = useGetStopRoutesQuery(stopId);
  const { arrivals, connected } = useStopArrivals(stopId);

  const routeInfo = useMemo(() => {
    if (!routes) return {};
    return routes.reduce((acc, r) => {
      acc[r.id] = {
        color: r.color ? `#${r.color}` : Colors.navy,
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
        <ActivityIndicator size="large" color={Colors.orange} />
      </View>
    );
  }

  if (!stopDetail) {
    return (
      <View style={styles.centerContainer}>
        <Ionicons name="alert-circle-outline" size={40} color={Colors.error} />
        <Text style={styles.errorText}>Error loading stop</Text>
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
      {/* Stop Header - lighter style */}
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
            pinColor={Colors.orange}
          />
        </MapView>
      </View>

      {/* Live Arrivals Section */}
      {connected && arrivals.length > 0 && (
        <View style={styles.arrivalsSection}>
          <View style={styles.arrivalsSectionHeader}>
            <Badge label="LIVE" variant="live" />
            <Text style={styles.sectionTitle}>Arriving Buses</Text>
          </View>
          {arrivals.slice(0, 5).map((arrival) => {
            const info = routeInfo[arrival.routeId];
            const etaMinutes = formatEta(arrival.etaSeconds);

            return (
              <View key={arrival.vehicleId} style={styles.arrivalCard}>
                <View style={[styles.arrivalColorIndicator, { backgroundColor: info?.color || Colors.navy }]} />
                <View style={styles.arrivalInfo}>
                  <View style={styles.arrivalTopRow}>
                    <Text style={styles.arrivalRouteName}>
                      {info?.shortName || `Route ${arrival.routeId}`}
                    </Text>
                    {arrival.isDelayed && <Badge label="DELAYED" variant="delayed" />}
                  </View>
                  <Text style={styles.arrivalBusInfo}>
                    Bus {arrival.vehicleId} • {arrival.load}/{arrival.capacity} passengers
                  </Text>
                  <View style={styles.loadBarContainer}>
                    <LoadBar load={arrival.load} capacity={arrival.capacity} />
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
          <Ionicons name="wifi-outline" size={18} color="#856404" style={{ marginRight: Spacing.sm }} />
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
        {routes?.map((r) => {
          const bgColor = r.color ? `#${r.color}` : Colors.navy;

          return (
            <TouchableOpacity
              key={r.id}
              style={styles.routeCard}
              onPress={() => navigation.navigate('RouteDetail', { routeId: r.id })}
              activeOpacity={0.7}
            >
              <View style={[styles.routeColorIndicator, { backgroundColor: bgColor }]} />
              <View style={styles.routeInfo}>
                <Text style={styles.routeShortName}>{r.shortName}</Text>
                <Text style={styles.routeLongName}>{r.longName}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={Colors.gray400} />
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
    backgroundColor: Colors.surface,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  stopName: {
    fontSize: Typography.size['2xl'],
    fontWeight: Typography.weight.bold,
    color: Colors.textPrimary,
    textAlign: 'center',
  },
  stopCode: {
    fontSize: Typography.size.md,
    color: Colors.orange,
    marginTop: Spacing.xs,
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
  routesSection: {
    padding: Spacing.lg,
  },
  sectionTitle: {
    fontSize: Typography.size.xl,
    fontWeight: Typography.weight.bold,
    color: Colors.textPrimary,
    marginBottom: Spacing.md,
    marginLeft: Spacing.sm,
  },
  routeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    paddingRight: Spacing.md,
    ...Shadows.sm,
  },
  routeColorIndicator: {
    width: 4,
    alignSelf: 'stretch',
    borderTopLeftRadius: Radius.md,
    borderBottomLeftRadius: Radius.md,
  },
  routeInfo: {
    flex: 1,
    padding: Spacing.lg,
  },
  routeShortName: {
    fontSize: Typography.size.lg,
    fontWeight: Typography.weight.bold,
    color: Colors.textPrimary,
  },
  routeLongName: {
    fontSize: Typography.size.sm,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  arrivalsSection: {
    padding: Spacing.lg,
    backgroundColor: Colors.surface,
    marginHorizontal: Spacing.lg,
    marginTop: Spacing.lg,
    borderRadius: Radius.lg,
    ...Shadows.md,
  },
  arrivalsSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  arrivalCard: {
    flexDirection: 'row',
    backgroundColor: Colors.gray50,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    overflow: 'hidden',
  },
  arrivalColorIndicator: {
    width: 4,
  },
  arrivalInfo: {
    flex: 1,
    padding: Spacing.md,
  },
  arrivalTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  arrivalRouteName: {
    fontSize: Typography.size.md,
    fontWeight: Typography.weight.bold,
    color: Colors.textPrimary,
  },
  arrivalBusInfo: {
    fontSize: Typography.size.xs,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  loadBarContainer: {
    marginTop: 6,
  },
  etaContainer: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.lg,
    minWidth: 60,
  },
  etaMinutes: {
    fontSize: Typography.size['2xl'],
    fontWeight: Typography.weight.bold,
    color: Colors.orange,
  },
  etaLabel: {
    fontSize: Typography.size.xs,
    color: Colors.textSecondary,
  },
  noLiveDataBanner: {
    marginHorizontal: Spacing.lg,
    marginTop: Spacing.lg,
    padding: Spacing.lg,
    backgroundColor: '#FFF3CD',
    borderRadius: Radius.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  noLiveDataText: {
    color: '#856404',
    fontSize: Typography.size.sm,
  },
  noArrivalsBanner: {
    marginHorizontal: Spacing.lg,
    marginTop: Spacing.lg,
    padding: Spacing.lg,
    backgroundColor: Colors.surfaceSecondary,
    borderRadius: Radius.md,
    alignItems: 'center',
  },
  noArrivalsText: {
    color: Colors.textSecondary,
    fontSize: Typography.size.sm,
  },
});

export default StopDetailScreen;
