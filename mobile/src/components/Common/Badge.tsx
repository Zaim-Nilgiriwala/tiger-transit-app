import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Typography, Radius } from '../../theme';

type BadgeVariant = 'live' | 'delayed' | 'info';

interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, { bg: string; text: string }> = {
  live: { bg: Colors.success, text: Colors.white },
  delayed: { bg: Colors.error, text: Colors.white },
  info: { bg: Colors.gray200, text: Colors.gray700 },
};

const Badge: React.FC<BadgeProps> = ({ label, variant = 'info' }) => {
  const { bg, text } = variantStyles[variant];

  return (
    <View style={[styles.pill, { backgroundColor: bg }]}>
      {variant === 'live' && <View style={styles.dot} />}
      <Text style={[styles.label, { color: text }]}>{label}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: Radius.full,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: Colors.white,
    marginRight: 4,
  },
  label: {
    fontSize: Typography.size.xs,
    fontWeight: Typography.weight.bold,
  },
});

export default Badge;
