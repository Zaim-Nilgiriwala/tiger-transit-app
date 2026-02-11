import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Marker } from 'react-native-maps';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Stop } from '../../types/gtfs.types';
import { RootStackParamList } from '../../types/navigation.types';
import { Colors } from '../../theme';

interface StopMarkerProps {
  stop: Stop;
  color?: string;
}

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const StopMarker: React.FC<StopMarkerProps> = ({ stop, color = Colors.navy }) => {
  const navigation = useNavigation<NavigationProp>();

  const handlePress = () => {
    navigation.navigate('StopDetail', { stopId: stop.id });
  };

  return (
    <Marker
      coordinate={{
        latitude: stop.lat,
        longitude: stop.lon,
      }}
      title={stop.name}
      description={stop.code || undefined}
      onPress={handlePress}
      anchor={{ x: 0.5, y: 0.5 }}
      tracksViewChanges={false}
    >
      <View style={[styles.dot, { backgroundColor: color }]} />
    </Marker>
  );
};

const styles = StyleSheet.create({
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.white,
  },
});

export default StopMarker;
