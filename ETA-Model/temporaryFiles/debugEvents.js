// Debug all IRM events during replay
import { io } from "socket.io-client";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1";

const requestTime = Date.parse("2025-10-21T18:00:00.000Z");

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: { Cookie: COOKIE },
});

let packetCount = 0;
let lastTs = null;

// Log ALL IRM events
socket.onAny((event, ...args) => {
  if (event === "sysRpt") {
    packetCount++;
    const ts = args[0]?.ts;
    if (packetCount === 1 || packetCount % 50 === 0) {
      const tsStr = ts ? new Date(ts).toISOString() : "no ts";
      console.log(`[sysRpt #${packetCount}] ts=${tsStr}`);
    }
    lastTs = ts;
  } else if (event.startsWith("IRM_") || event === "replayEnd" || event === "replay") {
    console.log(`[${event}]`, JSON.stringify(args).slice(0, 200));
  }
});

socket.on("connect", () => {
  console.log("Connected");
  socket.emit("IRM_request_auburn.etaspot.com", requestTime);
});

socket.on("IRM_replayFrameData", (data) => {
  console.log(`\nFrame: ${new Date(data.startTimeStamp).toISOString()} to ${new Date(data.endTimeStamp).toISOString()}`);
  console.log(`Duration: ${(data.endTimeStamp - data.startTimeStamp) / 1000 / 60} minutes\n`);

  socket.emit("IRM_setSpeed_auburn.etaspot.com", 3);
  socket.emit("IRM_replayPlay_auburn.etaspot.com", {});
});

socket.on("IRM_heartBeat", () => {
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

// Stop after 2 minutes
setTimeout(() => {
  if (lastTs) {
    console.log(`\nLast packet timestamp: ${new Date(lastTs).toISOString()}`);
  }
  console.log(`Total packets: ${packetCount}`);
  socket.disconnect();
  process.exit(0);
}, 120000);
