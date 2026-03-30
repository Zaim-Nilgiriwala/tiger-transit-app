// Debug packet structure to find historical timestamp
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packets = [];
let frameStart, frameEnd;

socket.on("connect", () => {
  console.log("Connected");
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  frameStart = data.startTimeStamp;
  frameEnd = data.endTimeStamp;
  console.log(`Frame: ${new Date(frameStart).toISOString()} to ${new Date(frameEnd).toISOString()}`);
  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);
  socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
});

socket.on("sysRpt", (pkt) => {
  packets.push(pkt);
  if (packets.length === 1) {
    console.log("\nFirst packet structure:");
    console.log("Keys:", Object.keys(pkt).join(", "));
    console.log("\nTimestamp fields:");
    console.log("  ts:", pkt.ts, pkt.ts ? new Date(pkt.ts).toISOString() : null);
    console.log("  t:", pkt.t, pkt.t ? new Date(pkt.t).toISOString() : null);
    console.log("  time:", pkt.time, pkt.time ? new Date(pkt.time).toISOString() : null);
    console.log("\nFull packet:");
    console.log(JSON.stringify(pkt, null, 2).slice(0, 1500));
  }
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

socket.on("IRM_rptEnd", () => {
  console.log("\n=== IRM_rptEnd received ===");
});

setTimeout(() => {
  console.log(`\n=== ANALYSIS ===`);
  console.log(`Total packets: ${packets.length}`);

  if (packets.length > 0) {
    // Check all timestamp fields across packets
    const tsValues = packets.map(p => p.ts).filter(Boolean);
    const tValues = packets.map(p => p.t).filter(Boolean);

    if (tsValues.length) {
      console.log(`\nts field range: ${new Date(Math.min(...tsValues)).toISOString()} - ${new Date(Math.max(...tsValues)).toISOString()}`);
    }
    if (tValues.length) {
      console.log(`t field range: ${new Date(Math.min(...tValues)).toISOString()} - ${new Date(Math.max(...tValues)).toISOString()}`);
    }

    // Check if t field is within the frame range
    const tInFrame = tValues.filter(t => t >= frameStart && t <= frameEnd);
    console.log(`\nPackets with t in frame range: ${tInFrame.length} / ${tValues.length}`);
  }

  socket.disconnect();
  process.exit(0);
}, 30000);
