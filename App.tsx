import { useCallback } from 'react';
import { StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { Provider } from 'react-redux';

import { store } from './src/store';
import { useCustomFonts } from './src/hooks/useFonts';
import MapScreen from './src/screens/MapScreen';

// Keep the splash screen visible while fonts load
SplashScreen.preventAutoHideAsync();

function AppContent() {
  const { fontsLoaded, fontError } = useCustomFonts();

  const onLayoutRootView = useCallback(async () => {
    if (fontsLoaded || fontError) {
      await SplashScreen.hideAsync();
    }
  }, [fontsLoaded, fontError]);

  // Do NOT render MapScreen until fonts are loaded.
  // User sees: splash -> fonts load -> splash hides -> map appears.
  if (!fontsLoaded && !fontError) {
    return null;
  }

  return (
    <View style={styles.container} onLayout={onLayoutRootView}>
      <MapScreen />
      <StatusBar style="dark" />
    </View>
  );
}

export default function App() {
  return (
    <GestureHandlerRootView style={styles.container}>
      <Provider store={store}>
        <AppContent />
      </Provider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
