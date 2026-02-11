// Export Stop Coordinates from Backend API
// Creates stops.json for training data processing

import fs from "fs";

const API_BASE = "http://localhost:3001";

async function exportStops() {
  console.log("Fetching stops from API...");

  try {
    const response = await fetch(`${API_BASE}/stops?limit=500`);

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();

    if (!data.success || !data.data) {
      throw new Error("Invalid API response format");
    }

    const stops = data.data.map(stop => ({
      id: stop.id,
      name: stop.name,
      lat: stop.lat,
      lon: stop.lon,
      code: stop.code,
    }));

    // Write to file
    fs.writeFileSync("./stops.json", JSON.stringify(stops, null, 2));

    console.log(`Exported ${stops.length} stops to stops.json`);

    // Show sample
    console.log("\nSample stops:");
    stops.slice(0, 5).forEach(s => {
      console.log(`  ${s.id}: ${s.name} (${s.lat}, ${s.lon})`);
    });

  } catch (error) {
    console.error("Error fetching stops:", error.message);
    console.log("\nMake sure the backend is running on http://localhost:3001");
    process.exit(1);
  }
}

exportStops();
