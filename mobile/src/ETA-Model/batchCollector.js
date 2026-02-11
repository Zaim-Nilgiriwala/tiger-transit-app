// Batch Historical Data Collector for ETA Prediction Training
// Pulls historical data from ETA SPOT's IRM (Instant Replay Manager) API
// npm i socket.io-client

import { io } from "socket.io-client";
import fs from "fs";
import path from "path";
import zlib from "zlib";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AzoLEaoFvxBy21W1cDbOkFPIq8TqPH7yP.PTwfMlsgBlVfeQbESXlyVI8bMHliN%2BaYxOOEQ016rOQ; etastat=1";

// Configuration
const CONFIG = {
  // Date range yyyy-mm-dd
  startDate: "2026-01-29",
  endDate: "2026-02-06",

  // Service hours: 6am-10pm CST (one continuous stream per day)
  serviceStartHour: 6,
  serviceEndHour: 22,

  // Playback speed index: 0=1x, 1=5x, 2=10x, 3=20x
  speedIndex: 3,

  // Safety timeout (70 min) - should never hit this if end time works
  maxTimeout: 4200000,

  // Output directory
  outputDir: "./raw_data",
};

// Helper to convert CST to UTC timestamp
function cstToUtcTimestamp(dateStr, hour, minute = 0) {
  // CST is UTC-6; setUTCHours handles values >= 24 by rolling the date forward
  const utcHour = hour + 6;
  const date = new Date(`${dateStr}T00:00:00.000Z`);
  date.setUTCHours(utcHour, minute, 0, 0);
  return date.getTime();
}

// Generate all dates in range
function generateDateRange(startDate, endDate) {
  const dates = [];
  const current = new Date(startDate);
  const end = new Date(endDate);

  while (current <= end) {
    dates.push(current.toISOString().split('T')[0]);
    current.setDate(current.getDate() + 1);
  }

  return dates;
}

// Sleep helper
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Collect data for a full day - ONE request, stops when endTime reached
function collectDay(dateStr, outputStream) {
  return new Promise((resolve, reject) => {
    const startTimestamp = cstToUtcTimestamp(dateStr, CONFIG.serviceStartHour);
    const endTimestamp = cstToUtcTimestamp(dateStr, CONFIG.serviceEndHour);

    let packetCount = 0;
    let frameCount = 0;

    const socket = io(BASE, {
      transports: ["websocket"],
      extraHeaders: { Cookie: COOKIE },
      reconnection: false,
    });

    const startTime = Date.now();

    // Safety timeout
    const timeout = setTimeout(() => {
      console.log(`\n  Safety timeout after ${Math.round((Date.now() - startTime) / 1000)}s`);
      socket.disconnect();
      resolve({ packetCount, frameCount });
    }, CONFIG.maxTimeout);

    socket.on("connect", () => {
      console.log(`  Starting at ${CONFIG.serviceStartHour}:00 CST`);
      console.log(`  Will stop at ${CONFIG.serviceEndHour}:00 CST`);
      socket.emit("IRM_request_auburn.etaspot.com", startTimestamp);
    });

    socket.on("connect_error", (err) => {
      clearTimeout(timeout);
      socket.disconnect();
      reject(new Error(`Connection error: ${err.message}`));
    });

    // When frame data arrives, continue playback
    socket.on("IRM_replayFrameData", (data) => {
      frameCount++;
      const start = new Date(data.startTimeStamp).toISOString();
      const end = new Date(data.endTimeStamp).toISOString();
      console.log(`\n  Frame ${frameCount}: ${start.slice(11, 19)} - ${end.slice(11, 19)} UTC`);

      socket.emit("IRM_setSpeed_auburn.etaspot.com", CONFIG.speedIndex);
      socket.emit("IRM_play_auburn.etaspot.com");
    });

    socket.on("IRM_currentSpeed", (speedIndex) => {
      const speeds = [1, 5, 10, 20];
      console.log(`  Speed: ${speeds[speedIndex] || speedIndex}x`);
    });

    // Stream packets - STOP when we exceed endTimestamp
    socket.on("IRM_rptPkt", (msg) => {
      const packetTime = msg.t || msg.ts;
      const vehicleId = msg.vid || msg.eID || "";

      // Skip jAUnt and Shuttle vehicles
      if (vehicleId.toLowerCase().includes("jaunt") || vehicleId.toLowerCase().includes("shuttle")) {
        return;
      }

      // Stop if we've passed the end time
      if (packetTime >= endTimestamp) {
        clearTimeout(timeout);
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        console.log(`\n  Reached ${CONFIG.serviceEndHour}:00 CST - stopping`);
        console.log(`  Collected ${packetCount} packets in ${elapsed}s (${frameCount} frames)`);
        socket.disconnect();
        resolve({ packetCount, frameCount });
        return;
      }

      // Write raw packet (all data preserved)
      outputStream.write(JSON.stringify(msg) + "\n");
      packetCount++;

      if (packetCount % 5000 === 0) {
        const timeStr = new Date(packetTime).toISOString().slice(11, 19);
        process.stdout.write(`\r  ${packetCount} packets... current time: ${timeStr} UTC`);
      }
    });

    socket.on("IRM_rptEnd", () => {
      clearTimeout(timeout);
      console.log(`\n  Replay ended: ${packetCount} packets`);
      socket.disconnect();
      resolve({ packetCount, frameCount });
    });

    socket.on("IRM_error", (msg) => {
      clearTimeout(timeout);
      socket.disconnect();
      reject(new Error(`IRM error: ${msg}`));
    });

    socket.on("IRM_heartBeat", () => {
      socket.emit("IRM_backBeat_auburn.etaspot.com", {});
    });
  });
}

// Process a single date - ONE continuous collection
async function processDate(dateStr) {
  const outputFile = path.join(CONFIG.outputDir, `raw_data_${dateStr}.jsonl.gz`);
  const hours = CONFIG.serviceEndHour - CONFIG.serviceStartHour;

  console.log(`\nCollecting ${dateStr} (${hours} hours: ${CONFIG.serviceStartHour}:00-${CONFIG.serviceEndHour}:00 CST)`);

  // Use gzip compression for smaller file sizes
  const gzip = zlib.createGzip({ level: 9 });
  const fileStream = fs.createWriteStream(outputFile, { flags: "w" });
  gzip.pipe(fileStream);

  try {
    const result = await collectDay(dateStr, gzip);

    // Properly close the gzip stream and wait for file to finish writing
    await new Promise((resolve, reject) => {
      gzip.end();
      fileStream.on("finish", resolve);
      fileStream.on("error", reject);
    });

    console.log(`\n${dateStr} complete:`);
    console.log(`  Packets: ${result.packetCount}`);
    console.log(`  Frames: ${result.frameCount}`);
    console.log(`  Output: ${outputFile}`);

    return { dateStr, packets: result.packetCount, frames: result.frameCount };
  } catch (error) {
    gzip.end();
    throw error;
  }
}

// Main function
async function main() {
  console.log("=".repeat(60));
  console.log("ETA SPOT Historical Data Collector");
  console.log("=".repeat(60));

  // Create output directory
  if (!fs.existsSync(CONFIG.outputDir)) {
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
  }

  const dates = generateDateRange(CONFIG.startDate, CONFIG.endDate);
  const speedStr = [1, 5, 10, 20][CONFIG.speedIndex];
  const hours = CONFIG.serviceEndHour - CONFIG.serviceStartHour;
  const estMinutes = Math.ceil((hours * 60) / speedStr);

  console.log(`\nDate range: ${CONFIG.startDate} to ${CONFIG.endDate} (${dates.length} days)`);
  console.log(`Service hours: ${CONFIG.serviceStartHour}:00 - ${CONFIG.serviceEndHour}:00 CST (${hours} hours)`);
  console.log(`Playback speed: ${speedStr}x`);
  console.log(`Estimated time per day: ~${estMinutes} minutes`);

  const results = [];

  for (let i = 0; i < dates.length; i++) {
    const dateStr = dates[i];
    console.log(`\n${"=".repeat(60)}`);
    console.log(`Day ${i + 1}/${dates.length}: ${dateStr}`);
    console.log("=".repeat(60));

    try {
      const result = await processDate(dateStr);
      results.push(result);
    } catch (error) {
      console.error(`Error processing ${dateStr}: ${error.message}`);
      results.push({ dateStr, packets: 0, frames: 0, error: error.message });
    }

    // Delay between days
    if (i < dates.length - 1) {
      console.log("\nWaiting 3 seconds before next day...");
      await sleep(3000);
    }
  }

  // Summary
  console.log("\n" + "=".repeat(60));
  console.log("COLLECTION COMPLETE");
  console.log("=".repeat(60));

  let totalPackets = 0;
  for (const r of results) {
    totalPackets += r.packets || 0;
    console.log(`  ${r.dateStr}: ${r.packets} packets`);
  }

  console.log(`\nTotal: ${totalPackets} packets`);
  console.log(`Output: ${CONFIG.outputDir}`);

  // Save summary
  const summaryPath = path.join(CONFIG.outputDir, "collection_summary.json");
  fs.writeFileSync(summaryPath, JSON.stringify({
    config: CONFIG,
    results,
    totalPackets,
    collectedAt: new Date().toISOString(),
  }, null, 2));
}

// Run
main().catch(console.error);
