import { getText, parseCsv, parseRoutes, unzipGtfs } from "@/services/gtfsParser";
import { downloadGtfs } from "@/services/gtfsService";
import { StyleSheet, View } from "react-native";
import MapView, { Marker } from "react-native-maps";

export default async function Index() {
  /*const zip = await downloadGtfs();
  const files = unzipGtfs(zip);
  const routes = parseRoutes(files);
  console.log(routes);*/
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

