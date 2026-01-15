import React from 'react';
import { Marker } from 'react-native-maps';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Stop } from '../../types/gtfs.types';
import { RootStackParamList } from '../../types/navigation.types';

interface StopMarkerProps {
  stop: Stop;
  color?: string;
}

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const StopMarker: React.FC<StopMarkerProps> = ({ stop, color = '#0C2340' }) => {
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
      pinColor={color}
      style={{ transform: [{ scale: 0.7 }] }}
    />
  );
};

export default StopMarker;
