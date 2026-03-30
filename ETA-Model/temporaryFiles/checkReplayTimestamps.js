// Check if sysRpt packets during replay have historical timestamps
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

// Oct 21, 2025 at noon CST - frame should be Oct 21 17:45-18:15 UTC
const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let frameStart, frameEnd;
let packets = [];
let playbackStarted = false;

socket.on("connect", () => {
  console.log("Connected\n");
  console.log(`Requesting replay for: ${new Date(requestTime).toISOString()}`);
  console.log(`Expected historical time: Oct 21, 2025 ~17:45-18:15 UTC\n`);
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  frameStart = data.startTimeStamp;
  frameEnd = data.endTimeStamp;
  console.log(`Frame range: ${new Date(frameStart).toISOString()} to ${new Date(frameEnd).toISOString()}`);
  console.log(`Frame year: ${new Date(frameStart).getFullYear()}\n`);

  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);
  socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
  playbackStarted = true;
});

socket.on("sysRpt", (pkt) => {
  if (!playbackStarted) return;

  packets.push(pkt);

  if (packets.length === 1) {
    console.log("=== First sysRpt after playback started ===");
    console.log("All timestamp-like fields:");

    // Check all numeric fields that could be timestamps
    for (const [key, value] of Object.entries(pkt)) {
      if (typeof value === "number" && value > 1600000000000 && value < 1900000000000) {
        const date = new Date(value);
        console.log(`  ${key}: ${value} => ${date.toISOString()} (year: ${date.getFullYear()})`);
      }
    }

    // Check nested objects
    if (pkt.lastStop?.time) {
      console.log(`  lastStop.time: ${pkt.lastStop.time} => ${new Date(pkt.lastStop.time).toISOString()}`);
    }
    if (pkt.eta?.eta) {
      console.log(`  eta.eta: ${pkt.eta.eta} (seconds, not timestamp)`);
    }

    console.log("\nIs this data from 2025?", new Date(pkt.t || pkt.ts).getFullYear() === 2025 ? "YES!" : "NO");
  }

  if (packets.length % 50 === 0) {
    const t = pkt.t || pkt.ts;
    console.log(`Packet #${packets.length}: t=${new Date(t).toISOString()}`);
  }
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

setTimeout(() => {
  console.log(`\n=== Analysis of ${packets.length} packets ===`);

  if (packets.length > 0) {
    const timestamps = packets.map(p => p.t || p.ts).filter(Boolean);
    const minTs = Math.min(...timestamps);
    const maxTs = Math.max(...timestamps);

    console.log(`Timestamp range in packets:`);
    console.log(`  Min: ${new Date(minTs).toISOString()}`);
    console.log(`  Max: ${new Date(maxTs).toISOString()}`);
    console.log(`  Year: ${new Date(minTs).getFullYear()}`);

    console.log(`\nExpected frame (historical):`);
    console.log(`  Start: ${new Date(frameStart).toISOString()}`);
    console.log(`  End: ${new Date(frameEnd).toISOString()}`);

    const inFrame = timestamps.filter(t => t >= frameStart && t <= frameEnd).length;
    console.log(`\nPackets with timestamps in historical frame: ${inFrame}/${timestamps.length}`);
  }

  socket.disconnect();
  process.exit(0);
}, 30000);
