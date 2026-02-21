import { StyleSheet, View } from "react-native";
import MapView, { Marker } from "react-native-maps";

export default function Index() {
  return (
    <View style={styles.container}>
      <MapView
        style={StyleSheet.absoluteFill}
        initialRegion={{
          latitude: 32.6025,
          longitude: -85.4808,
          latitudeDelta: 0.05,
          longitudeDelta: 0.05,
        }}
      >
        <Marker
          coordinate={{ latitude: 32.6025, longitude: -85.4808 }}
          title="Auburn University"
        />
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});

