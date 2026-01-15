import React, { useState, useEffect } from 'react';
import { StyleSheet, FlatList, View, Text, TouchableOpacity, TextInput, Pressable } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useGetRoutesQuery } from '../store/api/transitApi';
import { useRoutePreferences } from '../hooks/useRoutePreferences';
import { Route } from '../types/gtfs.types';
import { RootStackParamList } from '../types/navigation.types';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const RoutesScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { data: routes, isLoading, error } = useGetRoutesQuery();
  const [searchQuery, setSearchQuery] = useState('');
  const {
    isLoaded,
    initializeRoutes,
    toggleRoute,
    toggleAll,
    isRouteVisible,
    areAllVisible,
  } = useRoutePreferences();

  // Initialize route visibility when routes are loaded
  useEffect(() => {
    if (routes && isLoaded) {
      initializeRoutes(routes.map(r => r.id));
    }
  }, [routes, isLoaded, initializeRoutes]);

  const filteredRoutes = routes?.filter(route => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return route.longName.toLowerCase().includes(query);
  });

  const handleRoutePress = (routeId: string) => {
    navigation.navigate('RouteDetail', { routeId });
  };

  const handleToggleVisibility = (routeId: string) => {
    toggleRoute(routeId);
  };

  const handleToggleAll = () => {
    if (routes) {
      toggleAll(routes.map(r => r.id));
    }
  };

  const allVisible = routes ? areAllVisible(routes.map(r => r.id)) : true;

  const renderToggleAllRow = () => (
    <View style={styles.toggleAllCard}>
      {/* Visibility Toggle */}
      <Pressable
        style={styles.toggleButton}
        onPress={handleToggleAll}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
      >
        <View
          style={[
            styles.visibilityCircle,
            {
              backgroundColor: allVisible ? '#0C2340' : 'transparent',
              borderColor: '#0C2340',
            },
          ]}
        />
      </Pressable>

      {/* Label */}
      <Text style={styles.toggleAllText}>Toggle All Routes</Text>

      {/* Star Placeholder */}
      <Pressable style={styles.starButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
        <Text style={styles.starIcon}>☆</Text>
      </Pressable>
    </View>
  );

  const renderRoute = ({ item }: { item: Route }) => {
    const routeColor = item.color ? `#${item.color}` : '#0C2340';
    const isVisible = isRouteVisible(item.id);

    return (
      <TouchableOpacity
        style={[styles.routeCard, !isVisible && styles.routeCardHidden]}
        onPress={() => handleRoutePress(item.id)}
        activeOpacity={0.7}
      >
        {/* Color Bar */}
        <View style={[styles.colorIndicator, { backgroundColor: routeColor }]} />

        {/* Visibility Toggle */}
        <Pressable
          style={styles.toggleButton}
          onPress={() => handleToggleVisibility(item.id)}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <View
            style={[
              styles.visibilityCircle,
              {
                backgroundColor: isVisible ? routeColor : 'transparent',
                borderColor: routeColor,
              },
            ]}
          />
        </Pressable>

        {/* Route Name */}
        <View style={styles.routeInfo}>
          <Text style={[styles.routeName, !isVisible && styles.routeNameHidden]}>
            {item.longName}
          </Text>
        </View>

        {/* Star Toggle (placeholder) */}
        <Pressable style={styles.starButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Text style={styles.starIcon}>☆</Text>
        </Pressable>
      </TouchableOpacity>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <Text>Loading routes...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centerContainer}>
        <Text>Error loading routes</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder="Search routes..."
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholderTextColor="#999"
        />
      </View>

      {/* Routes List */}
      <FlatList
        data={filteredRoutes}
        renderItem={renderRoute}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContainer}
        ListHeaderComponent={renderToggleAllRow}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No routes found</Text>
          </View>
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  searchContainer: {
    padding: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  searchInput: {
    height: 40,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    paddingHorizontal: 14,
    fontSize: 15,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContainer: {
    padding: 12,
  },
  emptyContainer: {
    padding: 32,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: '#666',
  },
  toggleAllCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#e8e8e8',
    borderRadius: 8,
    marginBottom: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  toggleAllText: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
    color: '#0C2340',
  },
  routeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'white',
    borderRadius: 8,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 2,
    elevation: 2,
  },
  routeCardHidden: {
    opacity: 0.5,
  },
  colorIndicator: {
    width: 6,
    alignSelf: 'stretch',
    borderTopLeftRadius: 8,
    borderBottomLeftRadius: 8,
  },
  toggleButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  visibilityCircle: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
  },
  routeInfo: {
    flex: 1,
    paddingVertical: 12,
    paddingRight: 8,
  },
  routeName: {
    fontSize: 15,
    fontWeight: '500',
    color: '#0C2340',
  },
  routeNameHidden: {
    color: '#999',
  },
  starButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  starIcon: {
    fontSize: 22,
    color: '#CCCCCC',
  },
});

export default RoutesScreen;
