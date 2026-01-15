import React from 'react';
import { StyleSheet, View } from 'react-native';
import TransitMapView from '../components/Map/MapView';

const MapScreen: React.FC = () => {
  return (
    <View style={styles.container}>
      <TransitMapView />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});

export default MapScreen;
