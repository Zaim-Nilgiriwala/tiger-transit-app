// Debug script to understand replay API behavior
// Waits much longer and logs all events

import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AxV5gLtnnu3ItpCkCMgNz6J2dknkEXoqo.mWjc17aRJrrr8PIS%2FhDX7t7soEORx4pSfVjnrH7%2BOE0; etastat=1";

// Request a 30-min window from Oct 21 at noon CST
const requestTime = Date.parse("2025-10-21T18:00:00.000Z"); // 12:00 CST

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packetCount = 0;
let lastPacketTime = Date.now();

socket.on("connect", () => {
  console.log("Connected:", socket.id);
  console.log("Requesting replay from:", new Date(requestTime).toISOString());
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("connect_error", (err) => {
  console.error("Connection error:", err.message);
});

// Log ALL events
socket.onAny((event, ...args) => {
  if (event === "sysRpt") {
    packetCount++;
    lastPacketTime = Date.now();
    if (packetCount % 100 === 0) {
      console.log(`[sysRpt] ${packetCount} packets received...`);
    }
  } else {
    console.log(`[${event}]`, JSON.stringify(args).slice(0, 200));
  }
});

// Status update every 10 seconds
const statusInterval = setInterval(() => {
  const timeSinceLastPacket = Math.round((Date.now() - lastPacketTime) / 1000);
  console.log(`--- Status: ${packetCount} packets, ${timeSinceLastPacket}s since last packet ---`);
}, 10000);

// Wait 3 minutes to see full behavior
setTimeout(() => {
  clearInterval(statusInterval);
  console.log("\n=== FINAL RESULTS ===");
  console.log(`Total packets: ${packetCount}`);
  console.log("Disconnecting...");
  socket.disconnect();
  process.exit(0);
}, 180000); // 3 minutes

console.log("Waiting up to 3 minutes to observe replay behavior...");
