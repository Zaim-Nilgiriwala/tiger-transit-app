/**
 * Location Hook
 *
 * Requests foreground location permission once on mount.
 * If granted: tracks GPS position via watchPositionAsync.
 * If denied: silently sets permissionDenied, no re-prompt, no banner.
 *
 * Treats disabled location services the same as denied permission.
 */
import { useEffect, useRef, useState } from 'react';
import * as Location from 'expo-location';

export interface LocationCoords {
  latitude: number;
  longitude: number;
}

interface UseLocationResult {
  /** Current GPS coordinates, or null if unavailable */
  location: LocationCoords | null;
  /** True if user denied location permission (or services disabled) */
  permissionDenied: boolean;
  /** True while initial permission check is in progress */
  loading: boolean;
}

export function useLocation(): UseLocationResult {
  const [location, setLocation] = useState<LocationCoords | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [loading, setLoading] = useState(true);
  const watcherRef = useRef<Location.LocationSubscription | null>(null);

  useEffect(() => {
    let mounted = true;

    async function initLocation() {
      try {
        // Check if location services are enabled at the OS level
        const servicesEnabled = await Location.hasServicesEnabledAsync();
        if (!servicesEnabled) {
          if (mounted) {
            setPermissionDenied(true);
            setLoading(false);
          }
          return;
        }

        // Request foreground permission once
        const { status } = await Location.requestForegroundPermissionsAsync();

        if (status !== 'granted') {
          if (mounted) {
            setPermissionDenied(true);
            setLoading(false);
          }
          return;
        }

        // Get initial position
        try {
          const currentPosition = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.Balanced,
          });

          if (mounted) {
            setLocation({
              latitude: currentPosition.coords.latitude,
              longitude: currentPosition.coords.longitude,
            });
          }
        } catch {
          // Initial position fetch can fail on some devices; continue to watcher
        }

        if (mounted) {
          setLoading(false);
        }

        // Start watching position
        const subscription = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.Balanced,
            distanceInterval: 10, // meters before update fires
          },
          (newLocation) => {
            if (mounted) {
              setLocation({
                latitude: newLocation.coords.latitude,
                longitude: newLocation.coords.longitude,
              });
            }
          }
        );

        watcherRef.current = subscription;
      } catch {
        // Any unexpected error — treat as denied
        if (mounted) {
          setPermissionDenied(true);
          setLoading(false);
        }
      }
    }

    initLocation();

    return () => {
      mounted = false;
      if (watcherRef.current) {
        watcherRef.current.remove();
        watcherRef.current = null;
      }
    };
  }, []);

  return { location, permissionDenied, loading };
}
