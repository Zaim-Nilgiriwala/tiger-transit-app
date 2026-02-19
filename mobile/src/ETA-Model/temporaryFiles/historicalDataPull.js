// npm i socket.io-client
import { io } from "socket.io-client";
import fs from "fs";

const BASE = "https://auburn.etaspot.com";
const COOKIE = "express.sid=s%3AyuzlhNle2Drle3hJWPU7KEfT3JPzyeFW.C%2F5WoNSwwl8FiNOXLPB5zWT%2BsoW2cyEMPlN8Ly3VecA; etastat=1" // e.g. "express.sid=...; etastat=1"

const socket = io(BASE, {
  transports: ["websocket"],
  extraHeaders: COOKIE ? { Cookie: COOKIE } : undefined,
});

const out = fs.createWriteStream(`replay_${Date.now()}.jsonl`, { flags: "a" });

socket.on("connect", () => {
  console.log("connected", socket.id);
  // Request replay from Jan 13 2026 12:00 CST
  const ts = Date.parse("2026-01-13T18:00:00.000Z"); // 12:00 CST = 18:00Z
  console.log("Requesting replay from:", new Date(ts).toISOString());
  socket.emit("IRM_request_auburn.etaspot.com", ts);
});

socket.on("connect_error", (err) => console.error("connect_error", err.message));

// --- Replay listeners ---
socket.on("IRM_replayFrameData", (data) => {
  console.log("Replay frame:", data);
});

socket.on("IRM_rptPkt", (pkt) => {
  console.log("Got packet:", pkt.vid || pkt);
  out.write(JSON.stringify(pkt) + "\n");
});

socket.on("IRM_rptEnd", () => {
  console.log("Replay ended");
  out.end();
  socket.disconnect();
});

socket.on("IRM_error", (msg) => {
  console.error("Replay error:", msg);
});

socket.on("IRM_heartBeat", () => {
  console.log("Heartbeat received");
  socket.emit("IRM_backBeat_auburn.etaspot.com", {});
});

// Replay data comes through sysRpt events - save them!
let packetCount = 0;
socket.on("sysRpt", (msg) => {
  packetCount++;
  if (packetCount % 10 === 0) console.log(`Received ${packetCount} packets...`);
  out.write(JSON.stringify(msg) + "\n");
});

// Timeout after 30 seconds if nothing happens
setTimeout(() => {
  console.log(`Timeout - disconnecting. Total packets: ${packetCount}`);
  out.end();
  socket.disconnect();
  process.exit(0);
}, 30000);