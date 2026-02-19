// Test IRM_rptPkt event for historical data
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

// Request Oct 21 at noon CST
const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packetCount = 0;
let frameStart, frameEnd;

socket.on("connect", () => {
  console.log("Connected");
  console.log(`Requesting replay for: ${new Date(requestTime).toISOString()}`);
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  frameStart = data.startTimeStamp;
  frameEnd = data.endTimeStamp;
  console.log(`\nFrame: ${new Date(frameStart).toISOString()} to ${new Date(frameEnd).toISOString()}`);

  // Set speed to 20x
  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);

  // Start playback
  console.log("Starting playback at 20x...\n");
  socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
});

socket.on("IRM_currentSpeed", (idx) => {
  console.log(`Speed: ${[1,5,10,20][idx]}x`);
});

// THIS IS THE KEY - historical data comes through IRM_rptPkt!
socket.on("IRM_rptPkt", (pkt) => {
  packetCount++;

  if (packetCount === 1) {
    console.log("\n=== FIRST IRM_rptPkt PACKET ===");
    console.log("Keys:", Object.keys(pkt).join(", "));
    console.log("t field:", pkt.t, pkt.t ? new Date(pkt.t).toISOString() : null);
    console.log("ts field:", pkt.ts, pkt.ts ? new Date(pkt.ts).toISOString() : null);
    console.log("vid:", pkt.vid);
    console.log("lat/lon:", pkt.lt, pkt.ln);
    console.log();
  }

  if (packetCount % 100 === 0) {
    const pktTime = pkt.t ? new Date(pkt.t).toISOString() : "no t";
    console.log(`[IRM_rptPkt #${packetCount}] t=${pktTime}`);
  }
});

// Also log sysRpt for comparison
let sysRptCount = 0;
socket.on("sysRpt", () => {
  sysRptCount++;
});

socket.on("IRM_rptEnd", () => {
  console.log("\n=== IRM_rptEnd received ===");
  console.log(`IRM_rptPkt packets: ${packetCount}`);
  console.log(`sysRpt packets: ${sysRptCount}`);
  socket.disconnect();
  process.exit(0);
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

// Timeout
setTimeout(() => {
  console.log(`\n=== Timeout ===`);
  console.log(`IRM_rptPkt packets: ${packetCount}`);
  console.log(`sysRpt packets: ${sysRptCount}`);
  socket.disconnect();
  process.exit(0);
}, 120000);
