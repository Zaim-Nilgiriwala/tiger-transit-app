import React from 'react';
import { Polyline } from 'react-native-maps';
import { Route } from '../../types/gtfs.types';
import { useGetRouteShapeQuery } from '../../store/api/transitApi';
import { Colors } from '../../theme';

interface RoutePolylineProps {
  route: Route;
  strokeWidth?: number;
}

const RoutePolyline: React.FC<RoutePolylineProps> = ({
  route,
  strokeWidth = 3.5
}) => {
  const { data: shape } = useGetRouteShapeQuery({
    routeId: route.id
  });

  if (!shape || !shape.coordinates) {
    return null;
  }

  const coordinates = shape.coordinates.map(coord => ({
    latitude: coord.lat,
    longitude: coord.lon,
  }));

  const color = route.color ? `#${route.color}` : Colors.navy;

  return (
    <Polyline
      coordinates={coordinates}
      strokeColor={color}
      strokeWidth={strokeWidth}
      lineCap="round"
      lineJoin="round"
    />
  );
};

export default RoutePolyline;
