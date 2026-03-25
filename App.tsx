import { useCallback, useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { Provider } from 'react-redux';

import { store } from './src/store';
import { useCustomFonts } from './src/hooks/useFonts';
import { colors, typography } from './src/theme';

// Keep the splash screen visible while fonts load
SplashScreen.preventAutoHideAsync();

function AppContent() {
  const { fontsLoaded, fontError } = useCustomFonts();

  const onLayoutRootView = useCallback(async () => {
    if (fontsLoaded || fontError) {
      await SplashScreen.hideAsync();
    }
  }, [fontsLoaded, fontError]);

  if (!fontsLoaded && !fontError) {
    return null;
  }

  return (
    <View style={styles.container} onLayout={onLayoutRootView}>
      <Text style={styles.title}>Tiger Transit</Text>
      <StatusBar style="dark" />
    </View>
  );
}

export default function App() {
  return (
    <Provider store={store}>
      <AppContent />
    </Provider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    ...typography.headlineLG,
    color: colors.primary,
  },
});
