import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Colors, Radius } from '../../theme';

interface LoadBarProps {
  load: number;
  capacity: number;
  height?: number;
  width?: number;
}

const getLoadColor = (percent: number): string => {
  if (percent >= 80) return Colors.error;
  if (percent >= 50) return Colors.warning;
  return Colors.success;
};

const LoadBar: React.FC<LoadBarProps> = ({ load, capacity, height = 4, width }) => {
  const percent = capacity > 0 ? Math.round((load / capacity) * 100) : 0;

  return (
    <View style={[styles.track, { height }, width ? { width } : undefined]}>
      <View
        style={[
          styles.fill,
          {
            width: `${Math.min(percent, 100)}%`,
            backgroundColor: getLoadColor(percent),
            height,
          },
        ]}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  track: {
    backgroundColor: Colors.gray200,
    borderRadius: Radius.full,
    overflow: 'hidden',
  },
  fill: {
    borderRadius: Radius.full,
  },
});

export default LoadBar;
