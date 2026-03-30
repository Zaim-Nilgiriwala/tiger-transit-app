// Test different speed command formats
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

console.log("Testing speed commands...\n");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packetCount = 0;
let startTime;

// Log all events
socket.onAny((event, ...args) => {
  if (event === "sysRpt") {
    packetCount++;
    if (packetCount % 100 === 0) {
      const elapsed = Math.round((Date.now() - startTime) / 1000);
      console.log(`[sysRpt] ${packetCount} packets (${elapsed}s)`);
    }
  } else if (event !== "serverTimeUpdate") {
    console.log(`[${event}]`, JSON.stringify(args).slice(0, 150));
  }
});

socket.on("connect", () => {
  console.log("Connected\n");
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  startTime = Date.now();
  console.log("\nFrame received. Trying speed commands...\n");

  // Try multiple speed command formats
  console.log("1. Trying: IRM_replaySpeed_auburn.etaspot.com with 3");
  socket.emit("IRM_replaySpeed_auburn.etaspot.com", 3);

  setTimeout(() => {
    console.log("2. Trying: IRM_speed_auburn.etaspot.com with 3");
    socket.emit("IRM_speed_auburn.etaspot.com", 3);
  }, 500);

  setTimeout(() => {
    console.log("3. Trying: IRM_setSpeed_auburn.etaspot.com with 3");
    socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);
  }, 1000);

  setTimeout(() => {
    console.log("4. Trying: replaySpeed with 3");
    socket.emit("replaySpeed", 3);
  }, 1500);

  setTimeout(() => {
    console.log("\nStarting playback...");
    socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
  }, 2000);

  // Try changing speed after playback starts
  setTimeout(() => {
    console.log("\n5. Trying speed change after playback: IRM_replaySpeed_auburn.etaspot.com with 3");
    socket.emit("IRM_replaySpeed_auburn.etaspot.com", 3);
  }, 5000);
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

socket.on("IRM_rptEnd", () => {
  console.log(`\nReplay complete! ${packetCount} packets`);
  socket.disconnect();
  process.exit(0);
});

setTimeout(() => {
  console.log(`\nTimeout. ${packetCount} packets`);
  socket.disconnect();
  process.exit(0);
}, 30000);
