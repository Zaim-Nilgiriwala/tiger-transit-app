import React, { useRef, useState, useMemo, useEffect } from 'react';
import { StyleSheet, View, Text } from 'react-native';
import MapView, { Region } from 'react-native-maps';
import { AUBURN_COORDS } from '../../config/api.config';
import { useGetStopsQuery, useGetRoutesQuery, useGetStopRouteMappingsQuery } from '../../store/api/transitApi';
import { useVehicles } from '../../hooks/useVehicles';
import { useRoutePreferences } from '../../hooks/useRoutePreferences';
import StopMarker from './StopMarker';
import RoutePolyline from './RoutePolyline';
import VehicleMarker from './VehicleMarker';

const TransitMapView: React.FC = () => {
  const mapRef = useRef<MapView>(null);
  const [region, setRegion] = useState<Region>(AUBURN_COORDS);

  const { data: stops, isLoading: stopsLoading } = useGetStopsQuery({ limit: 200 });
  const { data: routes, isLoading: routesLoading } = useGetRoutesQuery();
  const { data: stopRouteMappings } = useGetStopRouteMappingsQuery();
  const { vehicles, connected, error } = useVehicles();
  const { isRouteVisible, isLoaded, initializeRoutes, visibleRouteIds } = useRoutePreferences();

  // Initialize route preferences when routes load
  useEffect(() => {
    if (routes && isLoaded) {
      initializeRoutes(routes.map(r => r.id));
    }
  }, [routes, isLoaded, initializeRoutes]);

  const handleRegionChange = (newRegion: Region) => {
    setRegion(newRegion);
  };

  // Create lookup maps for route info
  const routeInfo = useMemo(() => {
    if (!routes) return {};
    return routes.reduce((acc, route) => {
      acc[route.id] = {
        color: route.color ? `#${route.color}` : '#0C2340',
        name: route.shortName || route.longName,
      };
      return acc;
    }, {} as Record<string, { color: string; name: string }>);
  }, [routes]);

  // Filter routes based on visibility preferences
  const visibleRoutes = useMemo(() => {
    if (!routes) return [];
    return routes.filter(route => isRouteVisible(route.id));
  }, [routes, isRouteVisible]);

  // Filter vehicles to only show those on visible routes
  const visibleVehicles = useMemo(() => {
    return vehicles.filter(vehicle => isRouteVisible(vehicle.routeId));
  }, [vehicles, isRouteVisible]);

  // Filter stops to only show those that serve at least one visible route
  // Also calculate the color for each stop based on visible routes
  const visibleStopsWithColors = useMemo(() => {
    // Wait for both stops and mappings to load before showing any stops
    if (!stops || !stopRouteMappings) return [];
    // If no routes are visible, show no stops
    if (visibleRouteIds.size === 0) return [];

    return stops
      .map(stop => {
        const routeIds = stopRouteMappings[stop.id];
        if (!routeIds || routeIds.length === 0) return null;

        // Find the first visible route this stop serves
        const visibleRouteId = routeIds.find(routeId => isRouteVisible(routeId));
        if (!visibleRouteId) return null;

        // Get the color from the route info
        const color = routeInfo[visibleRouteId]?.color || '#0C2340';

        return { stop, color };
      })
      .filter((item): item is { stop: typeof stops[0]; color: string } => item !== null);
  }, [stops, stopRouteMappings, visibleRouteIds, isRouteVisible, routeInfo]);

  return (
    <View style={styles.container}>
      {/* Connection status banner */}
      {!connected && (
        <View style={styles.connectionBanner}>
          <View style={[styles.statusDot, { backgroundColor: error ? '#E74C3C' : '#F39C12' }]} />
          <Text style={styles.connectionText}>
            {error ? 'Connection error' : 'Connecting to live data...'}
          </Text>
        </View>
      )}

      {/* Live vehicles count indicator */}
      {connected && visibleVehicles.length > 0 && (
        <View style={styles.liveIndicator}>
          <View style={styles.liveDot} />
          <Text style={styles.liveText}>{visibleVehicles.length} buses active</Text>
        </View>
      )}

      <MapView
        ref={mapRef}
        style={styles.map}
        initialRegion={AUBURN_COORDS}
        onRegionChangeComplete={handleRegionChange}
        showsUserLocation
        showsMyLocationButton
        showsCompass
      >
        {/* Render route polylines (only visible routes) */}
        {visibleRoutes.map((route) => (
          <RoutePolyline key={route.id} route={route} />
        ))}

        {/* Render stop markers (only for visible routes, color-coded) */}
        {visibleStopsWithColors.map(({ stop, color }) => (
          <StopMarker key={stop.id} stop={stop} color={color} />
        ))}

        {/* Render live vehicle markers (only on visible routes) */}
        {visibleVehicles.map((vehicle) => (
          <VehicleMarker
            key={vehicle.vehicleId}
            vehicle={vehicle}
            routeColor={routeInfo[vehicle.routeId]?.color}
            routeName={routeInfo[vehicle.routeId]?.name}
          />
        ))}
      </MapView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  map: {
    width: '100%',
    height: '100%',
  },
  connectionBanner: {
    position: 'absolute',
    top: 10,
    left: 10,
    right: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
    zIndex: 1000,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 8,
  },
  connectionText: {
    fontSize: 14,
    color: '#333',
  },
  liveIndicator: {
    position: 'absolute',
    top: 10,
    right: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    zIndex: 1000,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#27AE60',
    marginRight: 6,
  },
  liveText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#27AE60',
  },
});

export default TransitMapView;
