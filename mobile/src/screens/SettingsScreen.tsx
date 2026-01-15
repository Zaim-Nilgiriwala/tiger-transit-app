import React from 'react';
import { StyleSheet, View, Text } from 'react-native';

const SettingsScreen: React.FC = () => {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Settings (Coming Soon)</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
  },
  text: {
    fontSize: 18,
    color: '#666',
  },
});

export default SettingsScreen;
