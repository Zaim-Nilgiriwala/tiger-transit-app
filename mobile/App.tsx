import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { Provider } from 'react-redux';
import { store } from './src/store';
import { RoutePreferencesProvider } from './src/hooks/useRoutePreferences';
import RootNavigator from './src/navigation/RootNavigator';

export default function App() {
  return (
    <Provider store={store}>
      <RoutePreferencesProvider>
        <StatusBar style="light" />
        <RootNavigator />
      </RoutePreferencesProvider>
    </Provider>
  );
}
