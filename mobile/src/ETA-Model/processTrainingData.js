// Training Data Processor for ETA Prediction
// Converts raw JSONL files into training CSV with features
// Calculates actual arrival times by tracking when vehicles pass stops

import fs from "fs";
import path from "path";
import readline from "readline";

// Configuration
const CONFIG = {
  inputDir: "./raw_data",
  outputFile: "./training_data.csv",
  stopsFile: "./stops.json",  // Stop coordinates lookup
};

// Haversine formula to calculate distance between two coordinates (in meters)
function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371000; // Earth's radius in meters
  const phi1 = lat1 * Math.PI / 180;
  const phi2 = lat2 * Math.PI / 180;
  const deltaPhi = (lat2 - lat1) * Math.PI / 180;
  const deltaLambda = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
            Math.cos(phi1) * Math.cos(phi2) *
            Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
}

// Load stop coordinates
function loadStops(stopsFile) {
  if (!fs.existsSync(stopsFile)) {
    console.error(`Stops file not found: ${stopsFile}`);
    console.log("Please run exportStops.js first or create stops.json with stop coordinates.");
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(stopsFile, "utf-8"));
  const stopsMap = new Map();

  for (const stop of data) {
    stopsMap.set(String(stop.id), { lat: stop.lat, lon: stop.lon, name: stop.name });
  }

  console.log(`Loaded ${stopsMap.size} stops`);
  return stopsMap;
}

// Parse a JSONL file and return array of packets
async function parseJsonlFile(filePath) {
  const packets = [];

  const fileStream = fs.createReadStream(filePath);
  const rl = readline.createInterface({
    input: fileStream,
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    if (line.trim()) {
      try {
        packets.push(JSON.parse(line));
      } catch (e) {
        // Skip malformed lines
      }
    }
  }

  return packets;
}

// Get time of day in minutes from midnight (CST)
function getTimeOfDay(timestamp) {
  const date = new Date(timestamp);
  // Convert to CST (UTC-6)
  const cstOffset = -6 * 60; // minutes
  const utcMinutes = date.getUTCHours() * 60 + date.getUTCMinutes();
  let cstMinutes = utcMinutes + cstOffset;
  if (cstMinutes < 0) cstMinutes += 24 * 60;
  return cstMinutes;
}

// Get day of week (0=Sunday, 6=Saturday)
function getDayOfWeek(timestamp) {
  const date = new Date(timestamp);
  return date.getUTCDay();
}

// Process packets for a single vehicle to generate training examples
function processVehiclePackets(vehiclePackets, stopsMap) {
  const trainingExamples = [];

  // Sort by timestamp
  vehiclePackets.sort((a, b) => a.ts - b.ts);

  // Track arrivals: when lastStop.stopID changes, vehicle arrived at that stop
  let prevLastStopId = null;
  let prevLastStopTime = null;

  for (let i = 0; i < vehiclePackets.length; i++) {
    const packet = vehiclePackets[i];

    // Skip packets without route assignment
    if (!packet.serviceState?.rID) continue;

    const currentLastStopId = packet.lastStop?.stopID ? String(packet.lastStop.stopID) : null;
    const currentLastStopTime = packet.lastStop?.time || packet.ts;

    // Detect arrival: lastStop changed
    if (currentLastStopId && currentLastStopId !== prevLastStopId && prevLastStopId !== null) {
      // Vehicle arrived at currentLastStopId
      // Look back at previous packets that were heading to this stop
      for (let j = 0; j < i; j++) {
        const prevPacket = vehiclePackets[j];

        // Skip if already processed or not heading to this stop
        if (!prevPacket.eta?.stopID) continue;
        if (String(prevPacket.eta.stopID) !== currentLastStopId) continue;

        // Calculate actual arrival time (seconds from observation to arrival)
        const actualArrivalSeconds = (currentLastStopTime - prevPacket.ts) / 1000;

        // Skip unrealistic values (negative or too long)
        if (actualArrivalSeconds < 0 || actualArrivalSeconds > 3600) continue;

        // Get stop coordinates for distance calculation
        const stopCoords = stopsMap.get(currentLastStopId);
        if (!stopCoords) continue;

        // Calculate distance to stop at time of observation
        const distanceToStop = haversineDistance(
          prevPacket.lt, prevPacket.ln,
          stopCoords.lat, stopCoords.lon
        );

        // Create training example
        const example = {
          timestamp: prevPacket.ts,
          vehicleId: prevPacket.vid,
          routeId: String(prevPacket.serviceState.rID),
          stopId: currentLastStopId,
          lat: prevPacket.lt,
          lon: prevPacket.ln,
          heading: prevPacket.h || 0,
          speed: prevPacket.v || 0,
          distanceToStop: Math.round(distanceToStop),
          timeOfDay: getTimeOfDay(prevPacket.ts),
          dayOfWeek: getDayOfWeek(prevPacket.ts),
          passengerLoad: prevPacket.load || 0,
          predictedETA: prevPacket.eta?.eta || 0,
          scheduledETA: prevPacket.eta?.seta || 0,
          onTime: prevPacket.eta?.onTime || 0,
          isDelayed: prevPacket.isDelayed ? 1 : 0,
          progressToStop: prevPacket.serviceState?.nextStopPercentProgress || 0,
          actualArrivalSeconds: Math.round(actualArrivalSeconds),
        };

        trainingExamples.push(example);
      }
    }

    prevLastStopId = currentLastStopId;
    prevLastStopTime = currentLastStopTime;
  }

  return trainingExamples;
}

// Process all raw data files
async function processAllData(inputDir, stopsMap) {
  const allExamples = [];

  // Find all JSONL files
  const files = fs.readdirSync(inputDir)
    .filter(f => f.startsWith("raw_data_") && f.endsWith(".jsonl"))
    .sort();

  console.log(`Found ${files.length} data files to process`);

  for (const file of files) {
    const filePath = path.join(inputDir, file);
    console.log(`\nProcessing: ${file}`);

    const packets = await parseJsonlFile(filePath);
    console.log(`  Loaded ${packets.length} packets`);

    // Group packets by vehicle
    const vehiclePackets = new Map();
    for (const packet of packets) {
      const vid = packet.vid;
      if (!vid) continue;

      if (!vehiclePackets.has(vid)) {
        vehiclePackets.set(vid, []);
      }
      vehiclePackets.get(vid).push(packet);
    }

    console.log(`  Found ${vehiclePackets.size} unique vehicles`);

    // Process each vehicle's packets
    let fileExamples = 0;
    for (const [vid, vPackets] of vehiclePackets) {
      const examples = processVehiclePackets(vPackets, stopsMap);
      allExamples.push(...examples);
      fileExamples += examples.length;
    }

    console.log(`  Generated ${fileExamples} training examples`);
  }

  return allExamples;
}

// Write training data to CSV
function writeTrainingCsv(examples, outputFile) {
  const headers = [
    "timestamp",
    "vehicleId",
    "routeId",
    "stopId",
    "lat",
    "lon",
    "heading",
    "speed",
    "distanceToStop",
    "timeOfDay",
    "dayOfWeek",
    "passengerLoad",
    "predictedETA",
    "scheduledETA",
    "onTime",
    "isDelayed",
    "progressToStop",
    "actualArrivalSeconds",
  ];

  const out = fs.createWriteStream(outputFile);

  // Write header
  out.write(headers.join(",") + "\n");

  // Write data rows
  for (const example of examples) {
    const row = headers.map(h => example[h] ?? "");
    out.write(row.join(",") + "\n");
  }

  out.end();
  console.log(`\nWrote ${examples.length} examples to ${outputFile}`);
}

// Main
async function main() {
  console.log("=".repeat(60));
  console.log("ETA Training Data Processor");
  console.log("=".repeat(60));

  // Load stop coordinates
  const stopsMap = loadStops(CONFIG.stopsFile);

  // Process all data files
  const examples = await processAllData(CONFIG.inputDir, stopsMap);

  if (examples.length === 0) {
    console.log("\nNo training examples generated!");
    console.log("Make sure you have raw data files in the input directory.");
    return;
  }

  // Sort by timestamp
  examples.sort((a, b) => a.timestamp - b.timestamp);

  // Write to CSV
  writeTrainingCsv(examples, CONFIG.outputFile);

  // Statistics
  console.log("\n" + "=".repeat(60));
  console.log("PROCESSING COMPLETE - STATISTICS");
  console.log("=".repeat(60));

  console.log(`\nTotal training examples: ${examples.length}`);

  // Unique counts
  const uniqueVehicles = new Set(examples.map(e => e.vehicleId)).size;
  const uniqueRoutes = new Set(examples.map(e => e.routeId)).size;
  const uniqueStops = new Set(examples.map(e => e.stopId)).size;

  console.log(`Unique vehicles: ${uniqueVehicles}`);
  console.log(`Unique routes: ${uniqueRoutes}`);
  console.log(`Unique stops: ${uniqueStops}`);

  // ETA accuracy preview
  const etaErrors = examples.map(e => Math.abs(e.predictedETA - e.actualArrivalSeconds));
  const avgError = etaErrors.reduce((a, b) => a + b, 0) / etaErrors.length;
  const medianError = etaErrors.sort((a, b) => a - b)[Math.floor(etaErrors.length / 2)];

  console.log(`\nETA Prediction Accuracy (current system):`);
  console.log(`  Average error: ${Math.round(avgError)} seconds (${Math.round(avgError / 60)} min)`);
  console.log(`  Median error: ${Math.round(medianError)} seconds (${Math.round(medianError / 60)} min)`);

  // Distance distribution
  const distances = examples.map(e => e.distanceToStop);
  const avgDistance = distances.reduce((a, b) => a + b, 0) / distances.length;
  const maxDistance = Math.max(...distances);

  console.log(`\nDistance to stop (at observation time):`);
  console.log(`  Average: ${Math.round(avgDistance)}m`);
  console.log(`  Max: ${Math.round(maxDistance)}m`);

  // Time distribution
  const times = examples.map(e => e.actualArrivalSeconds);
  const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
  const maxTime = Math.max(...times);

  console.log(`\nActual arrival time:`);
  console.log(`  Average: ${Math.round(avgTime)} seconds (${Math.round(avgTime / 60)} min)`);
  console.log(`  Max: ${Math.round(maxTime)} seconds (${Math.round(maxTime / 60)} min)`);
}

main().catch(console.error);
