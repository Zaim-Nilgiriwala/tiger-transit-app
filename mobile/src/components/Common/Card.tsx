import React from 'react';
import { View, ViewStyle, StyleSheet } from 'react-native';
import { Colors, Radius, Shadows, Spacing } from '../../theme';

interface CardProps {
  children: React.ReactNode;
  variant?: 'default' | 'flat';
  style?: ViewStyle;
}

const Card: React.FC<CardProps> = ({ children, variant = 'default', style }) => {
  return (
    <View style={[styles.base, variant === 'default' && Shadows.sm, style]}>
      {children}
    </View>
  );
};

const styles = StyleSheet.create({
  base: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.md,
    padding: Spacing.lg,
  },
});

export default Card;
