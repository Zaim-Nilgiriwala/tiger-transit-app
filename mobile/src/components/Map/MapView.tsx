import React, { useRef, useState, useMemo, useEffect, useCallback } from 'react';
import { StyleSheet, View, Text } from 'react-native';
import MapView, { Region } from 'react-native-maps';
import { AUBURN_COORDS } from '../../config/api.config';
import { useGetStopsQuery, useGetRoutesQuery, useGetStopRouteMappingsQuery } from '../../store/api/transitApi';
import { useVehicles } from '../../hooks/useVehicles';
import { useRoutePreferences } from '../../hooks/useRoutePreferences';
import StopMarker from './StopMarker';
import RoutePolyline from './RoutePolyline';
import VehicleMarker from './VehicleMarker';
import { Colors, Typography, Radius, Shadows, Spacing } from '../../theme';

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

  // Map ETASpot numeric route IDs to GTFS compound route IDs
  // e.g. ETASpot routeID 215 -> GTFS "215_202_201_156" (South Auburn)
  const resolveRouteId = useCallback((etaRouteId: string) => {
    if (!routes) return etaRouteId;
    // Direct match first
    const direct = routes.find(r => r.id === etaRouteId);
    if (direct) return direct.id;
    // Check compound IDs (e.g. "215_202_201_156" contains "215")
    const compound = routes.find(r => {
      const parts = r.id.split('_').filter(Boolean);
      return parts.includes(etaRouteId);
    });
    return compound ? compound.id : etaRouteId;
  }, [routes]);

  // Create lookup maps for route info
  const routeInfo = useMemo(() => {
    if (!routes) return {};
    return routes.reduce((acc, route) => {
      acc[route.id] = {
        color: route.color ? `#${route.color}` : Colors.navy,
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
    return vehicles.filter(vehicle => isRouteVisible(resolveRouteId(vehicle.routeId)));
  }, [vehicles, isRouteVisible, resolveRouteId]);

  // Filter stops to only show those that serve at least one visible route
  const visibleStopsWithColors = useMemo(() => {
    if (!stops || !stopRouteMappings) return [];
    if (visibleRouteIds.size === 0) return [];

    return stops
      .map(stop => {
        const routeIds = stopRouteMappings[stop.id];
        if (!routeIds || routeIds.length === 0) return null;

        const visibleRouteId = routeIds.find(routeId => isRouteVisible(routeId));
        if (!visibleRouteId) return null;

        const color = routeInfo[visibleRouteId]?.color || Colors.navy;

        return { stop, color };
      })
      .filter((item): item is { stop: typeof stops[0]; color: string } => item !== null);
  }, [stops, stopRouteMappings, visibleRouteIds, isRouteVisible, routeInfo]);

  return (
    <View style={styles.container}>
      {/* Connection status banner */}
      {!connected && (
        <View style={styles.connectionBanner}>
          <View style={[styles.statusDot, { backgroundColor: error ? Colors.error : Colors.warning }]} />
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
        {visibleRoutes.map((route) => (
          <RoutePolyline key={route.id} route={route} />
        ))}

        {visibleStopsWithColors.map(({ stop, color }) => (
          <StopMarker key={stop.id} stop={stop} color={color} />
        ))}

        {visibleVehicles.map((vehicle) => {
          const gtfsRouteId = resolveRouteId(vehicle.routeId);
          return (
            <VehicleMarker
              key={vehicle.vehicleId}
              vehicle={vehicle}
              routeColor={routeInfo[gtfsRouteId]?.color}
              routeName={routeInfo[gtfsRouteId]?.name}
            />
          );
        })}
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
    backgroundColor: Colors.surface,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: Radius.md,
    flexDirection: 'row',
    alignItems: 'center',
    zIndex: 1000,
    ...Shadows.md,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: Spacing.sm,
  },
  connectionText: {
    fontSize: Typography.size.sm,
    color: Colors.gray700,
  },
  liveIndicator: {
    position: 'absolute',
    top: 10,
    right: 10,
    backgroundColor: Colors.surface,
    paddingVertical: 6,
    paddingHorizontal: Spacing.md,
    borderRadius: Radius.full,
    flexDirection: 'row',
    alignItems: 'center',
    zIndex: 1000,
    ...Shadows.md,
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.success,
    marginRight: 6,
  },
  liveText: {
    fontSize: Typography.size.xs,
    fontWeight: Typography.weight.semibold,
    color: Colors.success,
  },
});

export default TransitMapView;
