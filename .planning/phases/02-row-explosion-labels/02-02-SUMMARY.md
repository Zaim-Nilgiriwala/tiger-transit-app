---
phase: 02-row-explosion-labels
plan: 02
subsystem: data-pipeline
tags: [label-join, merge-asof, temporal-split, train-val-test, parquet]
dependency-graph:
  requires: [02-01, 01-02]
  provides: [labeled.parquet, train.parquet, val.parquet, test.parquet]
  affects: [03]
tech-stack:
  added: []
  patterns: [merge_asof forward join, temporal splitting with gap days]
key-files:
  created: [scripts/label_join.py, scripts/temporal_split.py]
  modified: []
decisions:
  - Label join uses merge_asof(direction='forward', tolerance=2h) for ground truth
  - Per-route 99.5th percentile outlier removal
  - Temporal splits with 1-day gap to prevent leakage
  - Data ends Dec 13 (not Dec 20); test split has 4 days not 11
metrics:
  duration: ~3m
  completed: 2026-02-03
---

# Phase 2 Plan 2: Label Join & Temporal Split Summary

Ground truth labels via merge_asof forward join (88.8% success rate, 2.08M rows), temporal train/val/test split with consistent label distributions across all splits.

## What Was Built

### Task 1: Label Join via merge_asof
Created `scripts/label_join.py` that joins 2.34M exploded telemetry rows with 232K actual arrival records using `pd.merge_asof(direction='forward', tolerance=2h)` on `[route_id, target_stop_id, vehicle_id]` keys.

**Key results:**
- 90.1% raw match rate (2,112,104 / 2,343,861)
- After filtering: 2,080,635 labeled rows (88.8% success rate)
- No timezone spike (0.00% in 3540-3660s range)
- Label distribution: median 1081s, mean 1147s, std 751s
- All 23 routes represented with reasonable per-route distributions

**Filters applied:**
| Filter | Rows Removed |
|--------|-------------|
| No match (NaT) | 231,757 |
| Negative/zero | 13,627 |
| Too close (<=10s) | 7,403 |
| Too far (>7200s) | 0 |
| Per-route outliers (>99.5th) | 10,439 |

### Task 2: Temporal Train/Val/Test Split
Created `scripts/temporal_split.py` with strict temporal boundaries and 1-day gaps.

**Split results:**
| Split | Date Range | Days | Rows | Pct | Mean Label | Median Label |
|-------|-----------|------|------|-----|-----------|-------------|
| Train | Nov 6 - Dec 1 | 16 | 1,206,181 | 58.0% | 1146s | 1078s |
| Val | Dec 3 - Dec 8 | 5 | 384,002 | 18.5% | 1149s | 1087s |
| Test | Dec 10 - Dec 13 | 4 | 296,608 | 14.3% | 1148s | 1086s |
| Gap | (Dec 2, Dec 9) | 2 | 193,844 | 9.3% | -- | -- |

- All 23 routes in every split
- Label distributions nearly identical across splits (no distribution shift)
- ~98.7% weekday rows across all splits
- is_weekday flag added for model features

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| merge_asof direction='forward' with 2h tolerance | Forward finds next arrival after observation; 2h covers longest routes |
| Per-route 99.5th percentile outlier removal | Route-specific thresholds rather than global to handle route length variation |
| 1-day gap between splits | Prevents any trip from spanning split boundaries |
| Data ends Dec 13, not Dec 20 | Raw data coverage shorter than estimated; test split has 4 days (sufficient) |
| 13,627 negative-label rows dropped | merge_asof matched same-vehicle arrivals where timestamp precision caused forward match to align with concurrent arrival |

## Deviations from Plan

None -- plan executed exactly as written.

**Note:** The plan estimated data through Dec 20, but actual data ends Dec 13. This means the test split covers Dec 10-13 (4 days) rather than Dec 10-20 (11 days). The 296,608 test rows are sufficient for evaluation.

## Output Artifacts

| Artifact | Rows | Size | Key Columns Added |
|----------|------|------|-------------------|
| labeled.parquet | 2,080,635 | 47.9 MB | actual_arrival, time_to_arrival_seconds |
| train.parquet | 1,206,181 | 27.7 MB | date, is_weekday |
| val.parquet | 384,002 | 8.9 MB | date, is_weekday |
| test.parquet | 296,608 | 6.9 MB | date, is_weekday |

## Commits

| Hash | Message |
|------|---------|
| 9e4f128 | feat(02-02): label join via merge_asof |
| c6d6ab5 | feat(02-02): temporal train/val/test split |

## Next Phase Readiness

Phase 2 is now complete. Phase 3 (model training) can proceed with:
- `train.parquet` (1.2M rows) for training
- `val.parquet` (384K rows) for validation/tuning
- `test.parquet` (297K rows) for final evaluation
- All splits have consistent label distributions and all 23 routes
- `time_to_arrival_seconds` is the regression target (continuous, 11-5496s range)
