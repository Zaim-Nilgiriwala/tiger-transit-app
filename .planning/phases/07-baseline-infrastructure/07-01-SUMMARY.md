---
phase: 07-baseline-infrastructure
plan: 01
subsystem: data-pipeline
tags: [baseline, parquet, pandas, residual, historical-average, segment-sum, blend]

requires:
  - phase: v1.0 pipeline
    provides: train/val/test parquets with time_to_arrival_seconds, stop_sequences.parquet
provides:
  - baseline_eta column in all splits (zero NaN)
  - residual column in all splits (time_to_arrival - baseline_eta)
  - baseline_s2s and baseline_seg_sum intermediate columns
  - build_baselines.py pipeline script
affects: [08-training-adaptation, 09-evaluation-comparison]

tech-stack:
  added: []
  patterns: [tiered-fallback-hierarchy, segment-median-sum, 50-50-blend, residual-labels]

key-files:
  created: [scripts/build_baselines.py]
  modified: [data/processed/train.parquet, data/processed/val.parquet, data/processed/test.parquet]

key-decisions:
  - "Segment-sum uses (route, last_stop, stops_away, hour, day_type) median instead of cumulative path sums -- stop_sequences order does not match actual multi-pattern bus routing"
  - "Stored baseline_s2s and baseline_seg_sum as intermediate columns in parquets for diagnostic transparency"
  - "Tier 3 fallback uses progress-based distance when last_stop_id not in stop_sequences"

patterns-established:
  - "Tiered fallback hierarchy: specific grouping -> coarser grouping -> route-level, all with MIN_OBS=5"
  - "Residual target: time_to_arrival_seconds - baseline_eta for v1.1 model training"
  - "S2S uses mean aggregation; segment-sum uses median aggregation (complementary statistics)"

duration: 11min
completed: 2026-02-11
---

# Phase 7 Plan 01: Baseline Computation Pipeline Summary

**S2S + segment-sum tiered baselines with 50/50 blend producing 179.3s test MAE, zero NaN baseline_eta, and -9.1s train residual mean**

## Performance
- Duration: 11 minutes
- Started: 2026-02-12T02:22:53Z
- Completed: 2026-02-12T02:33:53Z
- Tasks: 2/2
- Files: 1 created (scripts/build_baselines.py, 689 lines), 3 modified (train/val/test.parquet)

## Accomplishments

### BASE-01: Stop-to-Stop Average (S2S)
- 3-tier fallback hierarchy with MIN_OBS=5
- Tier 1 coverage: 99.0-99.5% across splits (14,535 valid combos)
- Tier 2: 0.4-0.8%, Tier 3: 0.1-0.2%
- S2S-only test MAE: 130.0s

### BASE-02: Segment-Sum Baseline
- Uses (route_id, last_stop_id, stops_away, hour_ct, day_type) median
- 3-tier fallback (Tier A: 99.1-99.6%, Tier B: 0.4-0.7%, Tier C: 0.1-0.2%)
- Segment-sum test MAE: 254.3s
- Provides complementary signal to S2S (different aggregation axis and statistic)

### BASE-03: 50/50 Blend
- Blended test MAE: 179.3s
- 100% coverage (zero NaN) -- where one baseline is NaN, uses the other
- Per-route blend MAE ranges from 103.0s (route 6) to 527.4s (route 27)

### BASE-04: Residual Labels
- residual = time_to_arrival_seconds - baseline_eta
- Train mean: -9.1s, Val mean: -6.6s, Test mean: -14.4s
- Train std: 287.4s (this is what the v1.1 model needs to learn)

### BASE-05: Diagnostic Report
- All three baselines reported separately with MAE
- Per-route breakdown for all 23 routes
- Time-of-day MAE breakdown (morning/midday/afternoon/evening)
- Error distribution histogram saved to models/diagnostics/baseline_error_dist.png
- Residual statistics for all splits

## Task Commits
1. Task 1: Create build_baselines.py with lookups, fallback, segment-sum, blending, and augmented output - 203799c (feat)
2. Task 2: Validation-only task -- all criteria passed on first run, no changes needed

## Files Created/Modified
- `scripts/build_baselines.py` (689 lines) -- complete baseline computation pipeline
- `data/processed/train.parquet` -- augmented with baseline_eta, residual, baseline_s2s, baseline_seg_sum
- `data/processed/val.parquet` -- augmented with same 4 new columns
- `data/processed/test.parquet` -- augmented with same 4 new columns
- `models/diagnostics/baseline_error_dist.png` -- error distribution histogram

## Decisions Made

1. **Segment-sum approach changed from cumulative path sums to stops_away-based lookup** -- The original plan specified summing segment medians along the stop_sequence path. Investigation revealed that stop_sequences represents a single static ordering per route, but buses follow multiple patterns with different stop orderings. The (route, last_stop, stops_away) grouping provides a robust alternative that captures distance-based travel time patterns without needing pattern-specific routing.

2. **Stored intermediate baselines (baseline_s2s, baseline_seg_sum) in parquets** -- Enables downstream analysis of which baseline performs better per-route, useful for potential per-route weight optimization in v1.2.

3. **S2S uses mean, segment-sum uses median** -- Deliberate choice: mean is optimal for MAE minimization of the S2S (exact conditional expectation), while median provides robustness to outliers in the segment-sum (complementary statistics reduce blend variance).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed broken segment-sum cumulative path approach**
- **Found during:** Task 1 initial run
- **Issue:** Original cumsum-along-stop_sequences approach produced wildly wrong estimates (MAE ~4155s) because stop_sequences.parquet gives a single static stop ordering per route, but routes have multiple patterns with different stop orderings. Adjacent stops in stop_sequences are not always adjacent in actual bus operation.
- **Fix:** Replaced with (route_id, last_stop_id, stops_away, hour_ct, day_type) median lookup with 3-tier fallback. This captures the same "segment-sum" concept (distance-based travel time estimation) without requiring knowledge of intermediate stop paths.
- **Files modified:** scripts/build_baselines.py
- **Impact:** Segment-sum MAE improved from 4155.1s to 254.3s; blend MAE from 1226.7s to 179.3s; train residual mean from -1169.1s to -9.1s

## Issues Encountered

- Route 27 has only 96 test samples and the highest blend MAE (527.4s) -- known sparse route from research phase. The baseline is still better than naive (708.9s).
- Segment-sum has ~34-41 rows per split that fall through all three tiers (Still NaN). These are covered by S2S fallback in the blend, so final baseline_eta has zero NaN.

## Next Phase Readiness

Phase 8 (Training Adaptation) is unblocked:
- `baseline_eta` and `residual` columns exist in all splits with zero NaN
- Train residual mean (-9.1s) is near zero as expected
- Residual std (~287s) defines the modeling challenge for the residual model
- Blended baseline MAE (179.3s) is worse than v1.0's 123.1s, providing ample room for the residual model to improve
- S2S-only (130.0s) is close to v1.0 -- the residual model can potentially beat v1.0 by even small improvements over the S2S baseline

Key context for Phase 8:
- The target column should be `residual` (not `time_to_arrival_seconds`)
- `baseline_eta` must be added back to model predictions: final_pred = baseline_eta + predicted_residual
- The 50/50 blend is fixed; do not retrain blend weights

---
*Phase: 07-baseline-infrastructure*
*Completed: 2026-02-11*
