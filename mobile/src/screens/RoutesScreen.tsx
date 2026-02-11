import React, { useState, useEffect } from 'react';
import { StyleSheet, FlatList, View, Text, TouchableOpacity, TextInput, Pressable, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { useGetRoutesQuery } from '../store/api/transitApi';
import { useRoutePreferences } from '../hooks/useRoutePreferences';
import { Route } from '../types/gtfs.types';
import { RootStackParamList } from '../types/navigation.types';
import { Colors, Typography, Radius, Shadows, Spacing } from '../theme';

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
      <Pressable
        style={styles.toggleButton}
        onPress={handleToggleAll}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
      >
        <Ionicons
          name={allVisible ? 'checkmark-circle' : 'ellipse-outline'}
          size={22}
          color={Colors.navy}
        />
      </Pressable>

      <Text style={styles.toggleAllText}>Toggle All Routes</Text>

      <Pressable style={styles.starButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
        <Ionicons name="star-outline" size={20} color={Colors.gray400} />
      </Pressable>
    </View>
  );

  const renderRoute = ({ item }: { item: Route }) => {
    const routeColor = item.color ? `#${item.color}` : Colors.navy;
    const isVisible = isRouteVisible(item.id);

    return (
      <TouchableOpacity
        style={[styles.routeCard, !isVisible && styles.routeCardHidden]}
        onPress={() => handleRoutePress(item.id)}
        activeOpacity={0.7}
      >
        <View style={[styles.colorIndicator, { backgroundColor: routeColor }]} />

        <Pressable
          style={styles.toggleButton}
          onPress={() => handleToggleVisibility(item.id)}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons
            name={isVisible ? 'eye' : 'eye-off-outline'}
            size={20}
            color={isVisible ? routeColor : Colors.gray400}
          />
        </Pressable>

        <View style={styles.routeInfo}>
          <Text style={[styles.routeName, !isVisible && styles.routeNameHidden]}>
            {item.longName}
          </Text>
        </View>

        <Pressable style={styles.starButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="star-outline" size={20} color={Colors.gray400} />
        </Pressable>
      </TouchableOpacity>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={Colors.orange} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centerContainer}>
        <Ionicons name="alert-circle-outline" size={40} color={Colors.error} />
        <Text style={styles.errorText}>Error loading routes</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <View style={styles.searchInputWrapper}>
          <Ionicons name="search" size={18} color={Colors.gray400} style={styles.searchIcon} />
          <TextInput
            style={styles.searchInput}
            placeholder="Search routes..."
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholderTextColor={Colors.textTertiary}
          />
        </View>
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
            <Ionicons name="bus-outline" size={40} color={Colors.gray400} />
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
    backgroundColor: Colors.background,
  },
  searchContainer: {
    padding: Spacing.md,
    backgroundColor: Colors.surface,
  },
  searchInputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.gray100,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
  },
  searchIcon: {
    marginRight: Spacing.sm,
  },
  searchInput: {
    flex: 1,
    height: 42,
    fontSize: Typography.size.md,
    color: Colors.textPrimary,
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
  listContainer: {
    padding: Spacing.md,
  },
  emptyContainer: {
    padding: Spacing['3xl'],
    alignItems: 'center',
  },
  emptyText: {
    fontSize: Typography.size.lg,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
  },
  toggleAllCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surfaceSecondary,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },
  toggleAllText: {
    flex: 1,
    fontSize: Typography.size.md,
    fontWeight: Typography.weight.semibold,
    color: Colors.textPrimary,
  },
  routeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    ...Shadows.sm,
  },
  routeCardHidden: {
    opacity: 0.5,
  },
  colorIndicator: {
    width: 4,
    alignSelf: 'stretch',
    borderTopLeftRadius: Radius.md,
    borderBottomLeftRadius: Radius.md,
  },
  toggleButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  routeInfo: {
    flex: 1,
    paddingVertical: Spacing.md,
    paddingRight: Spacing.sm,
  },
  routeName: {
    fontSize: Typography.size.md,
    fontWeight: Typography.weight.medium,
    color: Colors.textPrimary,
  },
  routeNameHidden: {
    color: Colors.textTertiary,
  },
  starButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
});

export default RoutesScreen;
