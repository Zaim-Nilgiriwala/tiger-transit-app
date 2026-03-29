import { getText, parseCsv, parseRoutes, unzipGtfs } from "@/services/gtfsParser";
import { downloadGtfs } from "@/services/gtfsService";
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";
import MapView, { Marker, Polyline } from "react-native-maps";

export default function Index() {
  
  //state for storing route lines
  const [routes, setRoutes] = useState<any[]>([]);

  useEffect(() => {
    // Fetch route lines from the backend API
    fetch("http://10.1.83.155:3000/api/route-lines")
      .then((response) => response.json())
      .then((data) => setRoutes(data))
      .catch((error) => console.error("Error fetching routes:", error));
  }, []);

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
        {/* Render route lines on the map */}
        {routes.map((route, i) => (
          <Polyline
            key={i}
            coordinates={route.coordinates}
            strokeColor="black"
            strokeWidth={4}
          />
        ))}
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

