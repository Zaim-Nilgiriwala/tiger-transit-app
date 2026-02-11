// Quick test of a single 30-min chunk with proper replay flow
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AxV5gLtnnu3ItpCkCMgNz6J2dknkEXoqo.mWjc17aRJrrr8PIS%2FhDX7t7soEORx4pSfVjnrH7%2BOE0; etastat=1";

// Oct 21 at noon CST
const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

console.log("Testing single chunk with proper replay flow...");
console.log(`Requesting: ${new Date(requestTime).toISOString()}`);

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packetCount = 0;
let startTime = Date.now();

socket.on("connect", () => {
  console.log("Connected, requesting replay...");
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  console.log(`Frame: ${new Date(data.startTimeStamp).toISOString()} - ${new Date(data.endTimeStamp).toISOString()}`);

  // Set speed to 20x (IRM_setSpeed is the correct command)
  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);

  // Start playback
  console.log("Starting playback at 20x speed...");
  socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
});

socket.on("IRM_currentSpeed", (idx) => {
  console.log(`Speed confirmed: ${[1,5,10,20][idx]}x`);
});

socket.on("sysRpt", () => {
  packetCount++;
  if (packetCount % 500 === 0) {
    console.log(`... ${packetCount} packets (${Math.round((Date.now() - startTime) / 1000)}s elapsed)`);
  }
});

socket.on("IRM_rptEnd", () => {
  const elapsed = Math.round((Date.now() - startTime) / 1000);
  console.log(`\n✅ Replay complete!`);
  console.log(`Total packets: ${packetCount}`);
  console.log(`Time elapsed: ${elapsed}s`);
  socket.disconnect();
  process.exit(0);
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

// Timeout after 3 minutes
setTimeout(() => {
  const elapsed = Math.round((Date.now() - startTime) / 1000);
  console.log(`\n⏱️ Timeout after ${elapsed}s`);
  console.log(`Total packets: ${packetCount}`);
  socket.disconnect();
  process.exit(0);
}, 180000);
