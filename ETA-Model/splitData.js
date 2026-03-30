// Split a multi-day raw_data .jsonl.gz file into per-day files
// Usage: node splitData.js [input-file]
// Default input: ./raw_data/raw_data_2026-01-07.jsonl.gz

import fs from "fs";
import path from "path";
import zlib from "zlib";
import readline from "readline";

const INPUT = process.argv[2] || "./raw_data/raw_data_2026-01-07.jsonl.gz";
const OUTPUT_DIR = "./raw_data/split_output";

// CST offset in ms (UTC-6)
const CST_OFFSET_MS = 6 * 3600 * 1000;

async function main() {
  console.log(`Splitting: ${INPUT}`);
  console.log(`Output dir: ${OUTPUT_DIR}\n`);

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  if (!fs.existsSync(INPUT)) {
    console.error(`File not found: ${INPUT}`);
    process.exit(1);
  }

  // Map of dateStr -> { gzip, fileStream, count }
  const writers = {};
  let totalCount = 0;
  let errorCount = 0;

  function getWriter(dateStr) {
    if (!writers[dateStr]) {
      const outPath = path.join(OUTPUT_DIR, `raw_data_${dateStr}.jsonl.gz`);
      const gzipStream = zlib.createGzip({ level: 6 });
      const fileStream = fs.createWriteStream(outPath);
      gzipStream.pipe(fileStream);
      writers[dateStr] = { gzip: gzipStream, fileStream, count: 0, path: outPath };
    }
    return writers[dateStr];
  }

  function processLine(line) {
    if (!line.trim()) return;
    try {
      const obj = JSON.parse(line);
      const t = obj.t || obj.ts;
      if (!t) {
        errorCount++;
        return;
      }

      // Convert UTC timestamp to CST date
      const cstDate = new Date(t - CST_OFFSET_MS);
      const dateStr = cstDate.toISOString().split("T")[0];

      const writer = getWriter(dateStr);
      writer.gzip.write(line + "\n");
      writer.count++;
      totalCount++;

      if (totalCount % 500000 === 0) {
        process.stdout.write(`\r  Processed ${totalCount} packets...`);
      }
    } catch (e) {
      errorCount++;
    }
  }

  // Use event-based readline to handle truncated gzip files gracefully
  await new Promise((resolve) => {
    const gunzip = zlib.createGunzip();
    // On truncated gzip, just stop processing — we keep what we got
    gunzip.on("error", () => {
      console.log("\n  (gzip stream truncated — processing available data)");
    });

    const input = fs.createReadStream(INPUT).pipe(gunzip);
    const rl = readline.createInterface({ input, crlfDelay: Infinity });

    rl.on("line", processLine);
    rl.on("close", resolve);
    rl.on("error", resolve); // resolve on error too (truncated file)
  });

  console.log(`\r  Processed ${totalCount} packets total.`);
  if (errorCount > 0) console.log(`  Skipped ${errorCount} unparseable lines.`);

  // Close all writers and wait for them to finish
  console.log("\nClosing output files...");
  const closePromises = Object.entries(writers).map(
    ([dateStr, w]) =>
      new Promise((resolve, reject) => {
        w.gzip.end();
        w.fileStream.on("finish", () => resolve(dateStr));
        w.fileStream.on("error", reject);
      })
  );

  await Promise.all(closePromises);

  // Report
  console.log("\nResults:");
  console.log("-".repeat(45));

  const sorted = Object.entries(writers).sort(([a], [b]) => a.localeCompare(b));
  let lastDate = null;
  for (const [dateStr, w] of sorted) {
    const size = fs.statSync(w.path).size;
    const sizeMB = (size / 1024 / 1024).toFixed(1);
    console.log(`  ${dateStr}: ${w.count.toLocaleString().padStart(10)} packets  (${sizeMB} MB)`);
    lastDate = dateStr;
  }

  console.log("-".repeat(45));
  console.log(`  Total: ${totalCount.toLocaleString()} packets across ${sorted.length} days`);

  if (lastDate) {
    // Calculate the next date after the last complete day
    const last = new Date(lastDate);
    last.setDate(last.getDate() + 1);
    const nextDate = last.toISOString().split("T")[0];
    console.log(`\nLast date with data: ${lastDate}`);
    console.log(`Suggested CONFIG.startDate for resuming: "${nextDate}"`);
    console.log(`\nTo use the split files, move them from ${OUTPUT_DIR}/ to ./raw_data/:`);
    console.log(`  mv ${OUTPUT_DIR}/raw_data_*.jsonl.gz ./raw_data/`);
  }
}

main().catch(console.error);
