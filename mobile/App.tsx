import React from 'react';
import { Provider } from 'react-redux';
import { store } from './src/store';
import { RoutePreferencesProvider } from './src/hooks/useRoutePreferences';
import RootNavigator from './src/navigation/RootNavigator';

export default function App() {
  return (
    <Provider store={store}>
      <RoutePreferencesProvider>
        <RootNavigator />
      </RoutePreferencesProvider>
    </Provider>
  );
}
