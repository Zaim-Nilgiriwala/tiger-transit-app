// Test Collector - Run a quick test with just a few chunks
// Use this to verify the collector works before running the full batch

import { io } from "socket.io-client";
import fs from "fs";
import path from "path";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

// Test config - just 4 chunks (2 hours)
const CONFIG = {
  testDate: "2025-10-17",  // First day of collection range
  startHour: 12, // 12pm CST
  endHour: 14,   // 2pm CST
  chunkMinutes: 30,
  delayBetweenRequests: 2000,
  chunkTimeout: 45000,
  outputDir: "./raw_data",
};

function cstToUtcTimestamp(dateStr, hour, minute = 0) {
  const utcHour = hour + 6;
  const date = new Date(`${dateStr}T${String(utcHour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00.000Z`);
  return date.getTime();
}

function generateChunks() {
  const chunks = [];
  for (let hour = CONFIG.startHour; hour < CONFIG.endHour; hour++) {
    for (let minute = 0; minute < 60; minute += CONFIG.chunkMinutes) {
      const timestamp = cstToUtcTimestamp(CONFIG.testDate, hour, minute);
      chunks.push({
        timestamp,
        label: `${CONFIG.testDate} ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} CST`
      });
    }
  }
  return chunks;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function fetchChunk(timestamp, label) {
  return new Promise((resolve, reject) => {
    const packets = [];

    const socket = io(BASE, {
      transports: ["websocket"],
      extraHeaders: { Cookie: COOKIE },
      reconnection: false,
    });

    const timeout = setTimeout(() => {
      socket.disconnect();
      resolve({ packets, label, timedOut: true });
    }, CONFIG.chunkTimeout);

    socket.on("connect", () => {
      console.log(`  Requesting: ${label}`);
      socket.emit("IRM_request_auburn.etaspot.com", timestamp);
    });

    socket.on("connect_error", (err) => {
      clearTimeout(timeout);
      socket.disconnect();
      reject(new Error(`Connection error: ${err.message}`));
    });

    socket.on("IRM_replayFrameData", (data) => {
      console.log(`  Frame: ${new Date(data.startTimeStamp).toISOString()} - ${new Date(data.endTimeStamp).toISOString()}`);
    });

    socket.on("sysRpt", (msg) => {
      packets.push(msg);
    });

    socket.on("IRM_rptEnd", () => {
      clearTimeout(timeout);
      socket.disconnect();
      resolve({ packets, label, timedOut: false });
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

async function main() {
  console.log("=".repeat(60));
  console.log("TEST COLLECTOR - Quick Test Run");
  console.log("=".repeat(60));

  if (!fs.existsSync(CONFIG.outputDir)) {
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
  }

  const chunks = generateChunks();
  console.log(`\nTest date: ${CONFIG.testDate}`);
  console.log(`Time range: ${CONFIG.startHour}:00 - ${CONFIG.endHour}:00 CST`);
  console.log(`Chunks to fetch: ${chunks.length}`);

  const outputFile = path.join(CONFIG.outputDir, `raw_data_${CONFIG.testDate}.jsonl`);
  const out = fs.createWriteStream(outputFile, { flags: "w" });

  let totalPackets = 0;

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];

    try {
      const result = await fetchChunk(chunk.timestamp, chunk.label);

      for (const packet of result.packets) {
        out.write(JSON.stringify(packet) + "\n");
      }

      totalPackets += result.packets.length;
      console.log(`  [${i + 1}/${chunks.length}] Got ${result.packets.length} packets${result.timedOut ? ' (timeout)' : ''}`);

    } catch (error) {
      console.error(`  [${i + 1}/${chunks.length}] Error: ${error.message}`);
    }

    if (i < chunks.length - 1) {
      await sleep(CONFIG.delayBetweenRequests);
    }
  }

  out.end();

  console.log("\n" + "=".repeat(60));
  console.log("TEST COMPLETE");
  console.log("=".repeat(60));
  console.log(`Total packets: ${totalPackets}`);
  console.log(`Output: ${outputFile}`);

  if (totalPackets > 0) {
    console.log("\n✅ Test successful! The collector is working.");
    console.log("You can now run the full batch collector (batchCollector.js)");
  } else {
    console.log("\n⚠️ No packets received. Check your connection and credentials.");
  }
}

main().catch(console.error);
