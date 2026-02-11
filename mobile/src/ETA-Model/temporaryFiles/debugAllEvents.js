// Debug ALL socket events to find replay data event
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AxV5gLtnnu3ItpCkCMgNz6J2dknkEXoqo.mWjc17aRJrrr8PIS%2FhDX7t7soEORx4pSfVjnrH7%2BOE0; etastat=1";

const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

// Track all unique event names
const eventCounts = {};

socket.onAny((event, ...args) => {
  eventCounts[event] = (eventCounts[event] || 0) + 1;

  // Log IRM events and first occurrence of each event type
  if (event.includes("IRM") || event.includes("rpt") || event.includes("Pkt") || event.includes("replay")) {
    if (eventCounts[event] === 1) {
      console.log(`[${event}] FIRST:`, JSON.stringify(args).slice(0, 300));
    } else if (eventCounts[event] % 100 === 0) {
      console.log(`[${event}] #${eventCounts[event]}`);
    }
  }

  // Also log first occurrence of any unknown event
  if (eventCounts[event] === 1 && !["sysRpt", "serverTimeUpdate", "inventory", "setGUID", "news"].includes(event)) {
    console.log(`[NEW EVENT: ${event}]`, JSON.stringify(args).slice(0, 200));
  }
});

socket.on("connect", () => {
  console.log("Connected\n");
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", () => {
  console.log("\nStarting playback...\n");
  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);
  socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

setTimeout(() => {
  console.log("\n=== ALL EVENT COUNTS ===");
  Object.entries(eventCounts)
    .sort((a, b) => b[1] - a[1])
    .forEach(([event, count]) => {
      console.log(`  ${event}: ${count}`);
    });
  socket.disconnect();
  process.exit(0);
}, 30000);
