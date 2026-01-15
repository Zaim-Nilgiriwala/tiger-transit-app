import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = '@tiger_transit_route_visibility';

interface StoredPreferences {
  visible: string[];
  allVisible: boolean;
}

interface RoutePreferencesContextType {
  visibleRouteIds: Set<string>;
  isLoaded: boolean;
  allRoutesVisible: boolean;
  initializeRoutes: (routeIds: string[]) => void;
  toggleRoute: (routeId: string) => void;
  toggleAll: (routeIds: string[]) => void;
  isRouteVisible: (routeId: string) => boolean;
  areAllVisible: (routeIds: string[]) => boolean;
}

const RoutePreferencesContext = createContext<RoutePreferencesContextType | null>(null);

interface RoutePreferencesProviderProps {
  children: ReactNode;
}

export const RoutePreferencesProvider: React.FC<RoutePreferencesProviderProps> = ({ children }) => {
  const [visibleRouteIds, setVisibleRouteIds] = useState<Set<string>>(new Set());
  const [isLoaded, setIsLoaded] = useState(false);
  const [allRoutesVisible, setAllRoutesVisible] = useState(true);
  const initializedRef = useRef(false);

  // Load preferences from storage on mount
  useEffect(() => {
    loadPreferences();
  }, []);

  const loadPreferences = async () => {
    try {
      const stored = await AsyncStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed: StoredPreferences = JSON.parse(stored);
        setVisibleRouteIds(new Set(parsed.visible));
        setAllRoutesVisible(parsed.allVisible ?? true);
      }
    } catch (error) {
      console.error('Failed to load route preferences:', error);
    } finally {
      setIsLoaded(true);
    }
  };

  const savePreferences = async (visible: Set<string>, allVisible: boolean) => {
    try {
      const data: StoredPreferences = {
        visible: Array.from(visible),
        allVisible,
      };
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (error) {
      console.error('Failed to save route preferences:', error);
    }
  };

  // Initialize routes with all visible by default (only called once)
  const initializeRoutes = useCallback((routeIds: string[]) => {
    if (!isLoaded || initializedRef.current) return;

    initializedRef.current = true;

    // If no stored preferences exist, default all routes to visible
    if (visibleRouteIds.size === 0) {
      const allIds = new Set(routeIds);
      setVisibleRouteIds(allIds);
      setAllRoutesVisible(true);
      savePreferences(allIds, true);
    }
  }, [isLoaded, visibleRouteIds.size]);

  const toggleRoute = useCallback((routeId: string) => {
    setVisibleRouteIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(routeId)) {
        newSet.delete(routeId);
      } else {
        newSet.add(routeId);
      }
      // When manually toggling individual routes, allRoutesVisible should reflect actual state
      setAllRoutesVisible(false);
      savePreferences(newSet, false);
      return newSet;
    });
  }, []);

  const toggleAll = useCallback((routeIds: string[]) => {
    const newAllVisible = !allRoutesVisible;
    const newSet = newAllVisible ? new Set(routeIds) : new Set<string>();
    setVisibleRouteIds(newSet);
    setAllRoutesVisible(newAllVisible);
    savePreferences(newSet, newAllVisible);
  }, [allRoutesVisible]);

  const isRouteVisible = useCallback((routeId: string) => {
    // If not loaded yet, default to visible
    if (!isLoaded) return true;
    // If no routes have been initialized yet, default to visible
    if (visibleRouteIds.size === 0 && !initializedRef.current) return true;
    return visibleRouteIds.has(routeId);
  }, [isLoaded, visibleRouteIds]);

  // Check if all routes in the given list are visible
  const areAllVisible = useCallback((routeIds: string[]) => {
    if (routeIds.length === 0) return true;
    return routeIds.every(id => visibleRouteIds.has(id));
  }, [visibleRouteIds]);

  const value: RoutePreferencesContextType = {
    visibleRouteIds,
    isLoaded,
    allRoutesVisible,
    initializeRoutes,
    toggleRoute,
    toggleAll,
    isRouteVisible,
    areAllVisible,
  };

  return (
    <RoutePreferencesContext.Provider value={value}>
      {children}
    </RoutePreferencesContext.Provider>
  );
};

export const useRoutePreferences = (): RoutePreferencesContextType => {
  const context = useContext(RoutePreferencesContext);
  if (!context) {
    throw new Error('useRoutePreferences must be used within a RoutePreferencesProvider');
  }
  return context;
};
