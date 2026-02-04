---
phase: 02-row-explosion-labels
plan: 01
subsystem: data-pipeline
tags: [stop-sequences, telemetry, downsample, explosion, parquet]
dependency-graph:
  requires: [01-01, 01-02]
  provides: [stop_sequences.parquet, exploded.parquet]
  affects: [02-02]
tech-stack:
  added: []
  patterns: [chunked-by-day-processing, pyarrow-predicate-pushdown, vectorized-merge-explosion]
key-files:
  created: [scripts/build_stop_sequences.py, scripts/explode_rows.py]
  modified: []
decisions:
  - canonical-shape-selection: "Most trips per shape_id selects canonical shape per route"
  - explosion-count-lower: "2.34M rows vs 4-6M estimate; avg 3.2 stops ahead per observation (many vehicles near end of route)"
metrics:
  duration: ~3m
  completed: 2026-02-04
---

# Phase 2 Plan 1: Stop Sequences & Explosion Summary

Per-route stop sequences built from GTFS shape_dist_traveled, telemetry downsampled from 13.47M to 732K rows (60s buckets), then exploded into 2.34M per-stop rows with up to 8 remaining stops per observation.

## What Was Built

### Task 1: Stop Sequences (scripts/build_stop_sequences.py)
- Loads GTFS stop_times and shapes to build per-route ordered stop lists
- Selects canonical shape per route (shape_id with most trips)
- Computes `stop_progress = shape_dist_traveled / max_shape_dist` (0.0-1.0 range)
- Extracts numeric route_id from compound GTFS strings (e.g., "215_202_201_156" -> 215)
- Deduplicates stops per route (keeps first occurrence by stop_sequence)
- Output: 39 routes, 202 total stop-route pairs, 2-12 stops per route

### Task 2: Downsample & Explode (scripts/explode_rows.py)
- Chunked-by-day processing with PyArrow predicate pushdown (31 days)
- Filters idle vehicles (progress==0 & speed==0) and no-trip rows (next_stop_id==0)
- Excludes Route 237 (no GTFS data)
- Downsamples to 60-second buckets per (vehicle_id, route_id) -- keeps last observation
- Vectorized merge+filter explosion: joins with stop_sequences, keeps stops ahead, ranks top 8
- 23 routes represented in output (all telemetry routes with GTFS data)

## Key Metrics

| Metric | Value |
|--------|-------|
| Raw telemetry rows | 13,471,208 |
| After downsample (60s) | 732,436 |
| After explosion | 2,343,861 |
| Expansion factor | 3.2x |
| Routes in stop_sequences | 39 |
| Routes in exploded output | 23 |
| Processing time | ~18s |
| Output file size | 27.1 MB |

### Stops_away Distribution
| stops_away | Rows |
|------------|------|
| 1 | 494,506 |
| 2 | 428,921 |
| 3 | 382,709 |
| 4 | 330,464 |
| 5 | 274,601 |
| 6 | 219,116 |
| 7 | 160,547 |
| 8 | 52,997 |

## Decisions Made

1. **Canonical shape by trip count**: Selected shape_id with most trips (not most stops) as the canonical shape per route. Trip count better represents the "typical" route variant.

2. **Explosion count lower than estimate**: 2.34M rows vs. 4-6M estimated. The average stops ahead per observation is 3.2 rather than 8, because many vehicles are partway through routes with only a few stops remaining. This is correct behavior and still provides ample training data.

3. **Two days with zero exploded rows**: Nov 29 and Nov 30 had zero downsampled rows after filtering (likely holiday/no-service days where all vehicles were idle). These are correctly excluded.

## Deviations from Plan

None -- plan executed exactly as written.

## Artifacts

| Artifact | Path | Rows | Key Columns |
|----------|------|------|-------------|
| stop_sequences.parquet | data/processed/stop_sequences.parquet | 202 | route_id, stop_id, stop_sequence, shape_dist_traveled, max_shape_dist, stop_progress |
| exploded.parquet | data/processed/exploded.parquet | 2,343,861 | all telemetry fields + target_stop_id, target_stop_sequence, target_stop_progress, stops_away |

## Next Phase Readiness

Plan 02-02 (label join) can proceed:
- exploded.parquet provides the (vehicle_observation, target_stop) pairs
- Each row has target_stop_id and target_stop_progress for matching against arrivals
- 2.34M rows is manageable for merge_asof label join
- 23 routes with known stop sequences are ready for labeling

## Commits

| Hash | Message |
|------|---------|
| acf3660 | feat(02-01): build per-route stop sequences with progress fractions |
| 0686404 | feat(02-01): downsample telemetry and explode into per-stop rows |
