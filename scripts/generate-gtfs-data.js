/**
 * GTFS Data Generator
 *
 * One-time script that reads GTFS CSV files and generates typed TypeScript
 * constant files for bundling into the React Native app.
 *
 * Outputs:
 *   src/data/stops.ts       - All 178 stops as Stop[]
 *   src/data/shapes.ts      - All shapes grouped by shape_id as Record<string, Coordinate[]>
 *   src/data/routeStops.ts  - Route-to-stop-sequence and route-to-shape mappings
 *
 * Usage: node scripts/generate-gtfs-data.js
 */
const fs = require('fs');
const path = require('path');

const GTFS_DIR = path.join(__dirname, '..', 'ETA-Model', 'gtfs_data');
const OUT_DIR = path.join(__dirname, '..', 'src', 'data');

/** Parse a CSV file into an array of objects keyed by header row. Handles quoted fields. */
function parseCSV(filePath) {
  const raw = fs.readFileSync(filePath, 'utf-8').trim();
  const lines = raw.split('\n');
  const headers = parseLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = parseLine(lines[i]);
    const obj = {};
    for (let j = 0; j < headers.length; j++) {
      obj[headers[j]] = vals[j] || '';
    }
    rows.push(obj);
  }
  return rows;
}

/** Parse a single CSV line, handling quoted fields. */
function parseLine(line) {
  const fields = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      fields.push(current.trim());
      current = '';
    } else if (ch === '\r') {
      // skip carriage return
    } else {
      current += ch;
    }
  }
  fields.push(current.trim());
  return fields;
}

// ─── 1. Generate stops.ts ────────────────────────────────────────────
function generateStops() {
  const rows = parseCSV(path.join(GTFS_DIR, 'stops.txt'));
  console.log(`Parsed ${rows.length} stops`);

  const lines = [];
  lines.push(`/**`);
  lines.push(` * Bundled Static GTFS Stop Data`);
  lines.push(` *`);
  lines.push(` * Converted from ETA-Model/gtfs_data/stops.txt into typed TypeScript constants.`);
  lines.push(` * Synchronous import -- no async loading required. Stop changes require an app update`);
  lines.push(` * (Auburn changes stops ~2x per year).`);
  lines.push(` *`);
  lines.push(` * All ${rows.length} stops from the GTFS feed.`);
  lines.push(` */`);
  lines.push(`import { Stop } from '../types/gtfs.types';`);
  lines.push(``);
  lines.push(`export const STOPS: Stop[] = [`);

  for (const row of rows) {
    const stopId = row.stop_id;
    const stopName = row.stop_name.replace(/'/g, "\\'");
    const lat = parseFloat(row.stop_lat);
    const lon = parseFloat(row.stop_lon);
    const stopCode = row.stop_code;
    lines.push(`  { stopId: '${stopId}', stopName: '${stopName}', lat: ${lat}, lon: ${lon}, stopCode: '${stopCode}' },`);
  }

  lines.push(`];`);
  lines.push(``);
  lines.push(`/** O(1) lookup map: stopId -> Stop */`);
  lines.push(`export const STOPS_BY_ID: Record<string, Stop> = Object.fromEntries(`);
  lines.push(`  STOPS.map((s) => [s.stopId, s])`);
  lines.push(`);`);
  lines.push(``);

  fs.writeFileSync(path.join(OUT_DIR, 'stops.ts'), lines.join('\n'), 'utf-8');
  console.log(`  -> src/data/stops.ts (${rows.length} stops)`);
}

// ─── 2. Generate shapes.ts ───────────────────────────────────────────
function generateShapes() {
  const rows = parseCSV(path.join(GTFS_DIR, 'shapes.txt'));
  console.log(`Parsed ${rows.length} shape points`);

  // Group by shape_id, ordered by shape_pt_sequence
  const grouped = {};
  for (const row of rows) {
    const id = row.shape_id;
    if (!grouped[id]) grouped[id] = [];
    grouped[id].push({
      seq: parseInt(row.shape_pt_sequence, 10),
      lat: parseFloat(row.shape_pt_lat),
      lon: parseFloat(row.shape_pt_lon),
    });
  }

  // Sort each group by sequence
  for (const id of Object.keys(grouped)) {
    grouped[id].sort((a, b) => a.seq - b.seq);
  }

  const shapeIds = Object.keys(grouped).sort();
  console.log(`  ${shapeIds.length} distinct shapes`);

  const lines = [];
  lines.push(`/**`);
  lines.push(` * Bundled Static GTFS Shape Data`);
  lines.push(` *`);
  lines.push(` * Converted from ETA-Model/gtfs_data/shapes.txt into a typed TypeScript constant.`);
  lines.push(` * Synchronous import -- no async loading required.`);
  lines.push(` *`);
  lines.push(` * ${rows.length} points across ${shapeIds.length} shapes, ordered by shape_pt_sequence.`);
  lines.push(` */`);
  lines.push(`import { Coordinate } from '../types/gtfs.types';`);
  lines.push(``);
  lines.push(`export const SHAPES: Record<string, Coordinate[]> = {`);

  for (const shapeId of shapeIds) {
    const points = grouped[shapeId];
    lines.push(`  '${shapeId}': [`);
    for (const pt of points) {
      lines.push(`    { latitude: ${pt.lat}, longitude: ${pt.lon} },`);
    }
    lines.push(`  ],`);
  }

  lines.push(`};`);
  lines.push(``);

  fs.writeFileSync(path.join(OUT_DIR, 'shapes.ts'), lines.join('\n'), 'utf-8');
  console.log(`  -> src/data/shapes.ts (${shapeIds.length} shapes)`);
}

// ─── 3. Generate routeStops.ts ───────────────────────────────────────
function generateRouteStops() {
  const trips = parseCSV(path.join(GTFS_DIR, 'trips.txt'));
  const stopTimes = parseCSV(path.join(GTFS_DIR, 'stop_times.txt'));
  console.log(`Parsed ${trips.length} trips, ${stopTimes.length} stop_times`);

  // Build routeId -> first tripId, tripId -> shapeId
  const routeFirstTrip = {};  // routeId -> tripId (first encountered)
  const tripShape = {};       // tripId -> shapeId
  const routeShape = {};      // routeId -> shapeId (from first trip)

  for (const trip of trips) {
    const routeId = trip.route_id;
    const tripId = trip.trip_id;
    const shapeId = trip.shape_id;

    tripShape[tripId] = shapeId;

    if (!routeFirstTrip[routeId]) {
      routeFirstTrip[routeId] = tripId;
      routeShape[routeId] = shapeId;
    }
  }

  // Build tripId -> ordered stop_ids
  const tripStops = {};
  for (const st of stopTimes) {
    const tripId = st.trip_id;
    if (!tripStops[tripId]) tripStops[tripId] = [];
    tripStops[tripId].push({
      stopId: String(st.stop_id),
      seq: parseInt(st.stop_sequence, 10),
    });
  }

  // Sort each trip's stops by sequence
  for (const tripId of Object.keys(tripStops)) {
    tripStops[tripId].sort((a, b) => a.seq - b.seq);
  }

  // Build routeId -> ordered stopId[]
  const routeStopSeq = {};
  for (const routeId of Object.keys(routeFirstTrip)) {
    const tripId = routeFirstTrip[routeId];
    const stops = tripStops[tripId];
    if (stops) {
      routeStopSeq[routeId] = stops.map((s) => s.stopId);
    }
  }

  const routeIds = Object.keys(routeStopSeq).sort();
  console.log(`  ${routeIds.length} routes with stop sequences`);

  const lines = [];
  lines.push(`/**`);
  lines.push(` * Bundled Route-to-Stop-Sequence and Route-to-Shape Mappings`);
  lines.push(` *`);
  lines.push(` * Derived from ETA-Model/gtfs_data/trips.txt + stop_times.txt.`);
  lines.push(` * For each route, one canonical trip is selected and its ordered stop sequence`);
  lines.push(` * is used as the route's stop list.`);
  lines.push(` *`);
  lines.push(` * ${routeIds.length} routes mapped.`);
  lines.push(` */`);
  lines.push(``);
  lines.push(`/** routeId -> ordered array of stopIds for that route */`);
  lines.push(`export const ROUTE_STOP_SEQUENCE: Record<string, string[]> = {`);

  for (const routeId of routeIds) {
    const stopIds = routeStopSeq[routeId];
    lines.push(`  '${routeId}': [${stopIds.map((s) => `'${s}'`).join(', ')}],`);
  }

  lines.push(`};`);
  lines.push(``);
  lines.push(`/** routeId -> shapeId for polyline lookup in SHAPES */`);
  lines.push(`export const ROUTE_SHAPE_ID: Record<string, string> = {`);

  for (const routeId of routeIds) {
    const shapeId = routeShape[routeId];
    if (shapeId) {
      lines.push(`  '${routeId}': '${shapeId}',`);
    }
  }

  lines.push(`};`);
  lines.push(``);

  fs.writeFileSync(path.join(OUT_DIR, 'routeStops.ts'), lines.join('\n'), 'utf-8');
  console.log(`  -> src/data/routeStops.ts (${routeIds.length} routes)`);
}

// ─── Run ─────────────────────────────────────────────────────────────
console.log('Generating GTFS TypeScript data files...\n');
generateStops();
generateShapes();
generateRouteStops();
console.log('\nDone!');
