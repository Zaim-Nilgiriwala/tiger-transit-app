import React from 'react';
import { View, ScrollView, StyleSheet, ViewStyle } from 'react-native';
import { Colors } from '../../theme';

interface ScreenContainerProps {
  children: React.ReactNode;
  scroll?: boolean;
  style?: ViewStyle;
}

const ScreenContainer: React.FC<ScreenContainerProps> = ({ children, scroll = false, style }) => {
  if (scroll) {
    return (
      <ScrollView style={[styles.container, style]} contentContainerStyle={styles.scrollContent}>
        {children}
      </ScrollView>
    );
  }

  return <View style={[styles.container, style]}>{children}</View>;
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scrollContent: {
    flexGrow: 1,
  },
});

export default ScreenContainer;
