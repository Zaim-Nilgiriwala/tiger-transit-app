// Quick test of fixed batch collector protocol
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AxV5gLtnnu3ItpCkCMgNz6J2dknkEXoqo.mWjc17aRJrrr8PIS%2FhDX7t7soEORx4pSfVjnrH7%2BOE0; etastat=1";

// Request Jan 7, 2026 at noon CST (recent date with data)
const requestTime = Date.parse("2026-01-07T18:00:00.000Z");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packets = [];
let frameStart, frameEnd;

socket.on("connect", () => {
  console.log("Connected");
  console.log(`Requesting: ${new Date(requestTime).toISOString()}`);
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  frameStart = data.startTimeStamp;
  frameEnd = data.endTimeStamp;
  console.log(`\nFrame: ${new Date(frameStart).toISOString()} - ${new Date(frameEnd).toISOString()}`);

  // Set speed to 20x
  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);

  // FIXED: Use IRM_play_auburn.etaspot.com (no payload)
  console.log("Sending IRM_play_auburn.etaspot.com");
  socket.emit("IRM_play_auburn.etaspot.com");
});

socket.on("IRM_currentSpeed", (idx) => {
  console.log(`Speed: ${[1,5,10,20][idx]}x`);
});

// FIXED: Listen for IRM_rptPkt (not sysRpt)
socket.on("IRM_rptPkt", (pkt) => {
  packets.push(pkt);

  if (packets.length === 1) {
    console.log("\n=== FIRST IRM_rptPkt PACKET ===");
    console.log("Keys:", Object.keys(pkt).join(", "));
    const t = pkt.t || pkt.ts;
    console.log(`Timestamp: ${t} => ${new Date(t).toISOString()}`);
    console.log(`Year: ${new Date(t).getFullYear()}`);
    console.log(`Vehicle: ${pkt.vid || pkt.eID}`);
    console.log(`Position: ${pkt.lt}, ${pkt.ln}`);
    console.log();

    // Check if timestamp is historical (within frame)
    const isHistorical = t >= frameStart && t <= frameEnd;
    console.log(`Is historical (within frame)? ${isHistorical ? "YES!" : "NO"}`);
  }

  if (packets.length % 100 === 0) {
    process.stdout.write(`\r  ${packets.length} packets...`);
  }
});

socket.on("IRM_rptEnd", () => {
  console.log(`\n\n=== IRM_rptEnd ===`);
  console.log(`Total packets: ${packets.length}`);

  if (packets.length > 0) {
    const timestamps = packets.map(p => p.t || p.ts).filter(Boolean);
    console.log(`Timestamp range:`);
    console.log(`  Min: ${new Date(Math.min(...timestamps)).toISOString()}`);
    console.log(`  Max: ${new Date(Math.max(...timestamps)).toISOString()}`);

    const inFrame = timestamps.filter(t => t >= frameStart && t <= frameEnd).length;
    console.log(`\nPackets in historical frame: ${inFrame}/${timestamps.length}`);
  }

  socket.disconnect();
  process.exit(0);
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

// Timeout after 60 seconds
setTimeout(() => {
  console.log(`\n\n=== Timeout ===`);
  console.log(`Total packets: ${packets.length}`);
  socket.disconnect();
  process.exit(0);
}, 60000);
