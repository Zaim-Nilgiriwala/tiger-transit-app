// Live Data Collector for ETA Prediction Training
// Runs continuously to collect real-time vehicle data
// Use: node liveCollector.js
// Stop: Ctrl+C (gracefully saves and exits)

import { io } from "socket.io-client";
import fs from "fs";
import path from "path";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

const CONFIG = {
  outputDir: "./live_data",
  statsIntervalMs: 60000,      // Log stats every minute
  reconnectDelayMs: 5000,      // Wait 5s before reconnecting
  flushIntervalMs: 10000,      // Flush to disk every 10s
};

// State
let socket = null;
let currentDate = null;
let currentStream = null;
let packetCount = 0;
let sessionPackets = 0;
let startTime = Date.now();
let lastPacketTime = null;
let isShuttingDown = false;

// Get current date string in CST
function getCurrentDateCST() {
  const now = new Date();
  // Adjust for CST (UTC-6)
  const cst = new Date(now.getTime() - 6 * 60 * 60 * 1000);
  return cst.toISOString().split('T')[0];
}

// Get or create output stream for current date
function getOutputStream() {
  const dateStr = getCurrentDateCST();

  if (dateStr !== currentDate) {
    // Close previous stream if exists
    if (currentStream) {
      currentStream.end();
      console.log(`\nClosed file for ${currentDate}`);
    }

    // Create new stream
    currentDate = dateStr;
    const filePath = path.join(CONFIG.outputDir, `live_${dateStr}.jsonl`);
    currentStream = fs.createWriteStream(filePath, { flags: "a" });
    console.log(`\nOpened file for ${dateStr}: ${filePath}`);
  }

  return currentStream;
}

// Write packet to file
function writePacket(packet) {
  const stream = getOutputStream();
  stream.write(JSON.stringify(packet) + "\n");
  packetCount++;
  sessionPackets++;
  lastPacketTime = Date.now();
}

// Format duration
function formatDuration(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h ${minutes % 60}m`;
  if (hours > 0) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

// Log statistics
function logStats() {
  const elapsed = Date.now() - startTime;
  const rate = sessionPackets / (elapsed / 1000 / 60); // packets per minute
  const sinceLastPacket = lastPacketTime ? Math.round((Date.now() - lastPacketTime) / 1000) : "N/A";

  console.log(`\n--- Stats @ ${new Date().toISOString()} ---`);
  console.log(`  Runtime: ${formatDuration(elapsed)}`);
  console.log(`  Session packets: ${sessionPackets}`);
  console.log(`  Rate: ${rate.toFixed(1)} packets/min`);
  console.log(`  Last packet: ${sinceLastPacket}s ago`);
  console.log(`  Current file: live_${currentDate}.jsonl`);
}

// Connect to ETA SPOT
function connect() {
  if (isShuttingDown) return;

  console.log("Connecting to ETA SPOT...");

  socket = io(BASE, {
    transports: ["websocket"],
    extraHeaders: { Cookie: COOKIE },
    reconnection: false, // We handle reconnection manually
  });

  socket.on("connect", () => {
    console.log(`Connected! Socket ID: ${socket.id}`);
  });

  socket.on("disconnect", (reason) => {
    console.log(`Disconnected: ${reason}`);
    if (!isShuttingDown) {
      console.log(`Reconnecting in ${CONFIG.reconnectDelayMs / 1000}s...`);
      setTimeout(connect, CONFIG.reconnectDelayMs);
    }
  });

  socket.on("connect_error", (err) => {
    console.error(`Connection error: ${err.message}`);
    if (!isShuttingDown) {
      console.log(`Reconnecting in ${CONFIG.reconnectDelayMs / 1000}s...`);
      setTimeout(connect, CONFIG.reconnectDelayMs);
    }
  });

  socket.on("sysRpt", (packet) => {
    writePacket(packet);

    // Log progress every 100 packets
    if (sessionPackets % 100 === 0) {
      process.stdout.write(`\r  Packets: ${sessionPackets}`);
    }
  });

  // Keep connection alive
  socket.on("IRM_heartBeat", () => {
    socket.emit("IRM_backBeat_auburn.etaspot.com", {});
  });
}

// Graceful shutdown
function shutdown() {
  if (isShuttingDown) return;
  isShuttingDown = true;

  console.log("\n\nShutting down...");

  // Final stats
  logStats();

  // Close socket
  if (socket) {
    socket.disconnect();
  }

  // Close file stream
  if (currentStream) {
    currentStream.end(() => {
      console.log("File stream closed.");
      process.exit(0);
    });
  } else {
    process.exit(0);
  }
}

// Main
async function main() {
  console.log("=".repeat(60));
  console.log("ETA SPOT Live Data Collector");
  console.log("=".repeat(60));
  console.log(`Started: ${new Date().toISOString()}`);
  console.log(`Output directory: ${CONFIG.outputDir}`);
  console.log(`Press Ctrl+C to stop\n`);

  // Create output directory
  if (!fs.existsSync(CONFIG.outputDir)) {
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
  }

  // Handle shutdown signals
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  // Connect
  connect();

  // Periodic stats logging
  setInterval(() => {
    if (!isShuttingDown) {
      logStats();
    }
  }, CONFIG.statsIntervalMs);

  // Periodic flush (ensure data is written to disk)
  setInterval(() => {
    if (currentStream && !isShuttingDown) {
      // Node streams auto-flush, but we can force it
      currentStream.cork();
      currentStream.uncork();
    }
  }, CONFIG.flushIntervalMs);
}

main().catch(console.error);
