import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import TabNavigator from './TabNavigator';
import RouteDetailScreen from '../screens/RouteDetailScreen';
import StopDetailScreen from '../screens/StopDetailScreen';
import { RootStackParamList } from '../types/navigation.types';
import { Colors, Typography } from '../theme';

const Stack = createNativeStackNavigator<RootStackParamList>();

const RootNavigator: React.FC = () => {
  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerStyle: {
            backgroundColor: Colors.navy,
          },
          headerTintColor: Colors.white,
          headerTitleStyle: {
            fontWeight: Typography.weight.bold,
          },
          headerShadowVisible: false,
        }}
      >
        <Stack.Screen
          name="Main"
          component={TabNavigator}
          options={{ headerShown: false }}
        />
        <Stack.Screen
          name="RouteDetail"
          component={RouteDetailScreen}
          options={{ title: 'Route Details' }}
        />
        <Stack.Screen
          name="StopDetail"
          component={StopDetailScreen}
          options={{ title: 'Stop Details' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default RootNavigator;
