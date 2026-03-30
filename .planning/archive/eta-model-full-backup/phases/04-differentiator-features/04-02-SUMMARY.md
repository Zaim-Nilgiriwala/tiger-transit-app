---
phase: 04-differentiator-features
plan: 02
subsystem: feature-engineering
tags: [timepoints, speed-ratio, xgboost, parquet, vectorized]

requires:
  - phase: 03-baseline-model
    provides: Phase 3 feature pipeline (15 features), train/val/test splits
  - phase: 04-01
    provides: Rolling speed features, historical segment/dwell aggregates

provides:
  - v2 featured parquets with 43 features (15 Phase 3 + 28 Phase 4)
  - Timepoint features (is_timepoint, scheduled_departure_seconds, timepoints_remaining, time_until_next_timepoint_departure, timepoint_adherence)
  - Speed ratio feature (current speed / historical median)
  - is_rush_hour feature
  - load_featured_v2() API for training script
  - FEATURE_COLS_V2, CATEGORICAL_COLS_V2 exports

affects: [04-03, 05-advanced-training]

tech-stack:
  added: []
  patterns:
    - "Vectorized timepoint lookup via numpy searchsorted"
    - "Historical speed lookup built from training pings only (no leakage)"
    - "Multi-key left merge with row count assertions"

key-files:
  created:
    - "data/processed/train_featured_v2.parquet"
    - "data/processed/val_featured_v2.parquet"
    - "data/processed/test_featured_v2.parquet"
  modified:
    - "scripts/build_differentiator_features.py"

key-decisions:
  - "Median scheduled time per (route, stop) used as representative timepoint departure"
  - "is_timepoint set to NaN (not 0) for routes 27/235 to distinguish missing-data from non-timepoint"
  - "Speed ratio uses historical median GPS speed per (route, stop, hour, day_type) from training pings"
  - "target_dwell features have 98% NaN -- acceptable because only 58/119 target stops have dwell data with sufficient observations"

patterns-established:
  - "v2 featured parquets are the canonical input for Phase 5 training"
  - "load_featured_v2(split) restores category dtypes for XGBoost compatibility"

duration: 5min
completed: 2026-02-04
---

# Phase 4 Plan 02: Timepoint Features and v2 Assembly Summary

**Timepoint schedule features + speed ratio + full v2 parquet assembly with 43 features across train/val/test splits**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-04T20:55:46Z
- **Completed:** 2026-02-04T21:00:05Z
- **Tasks:** 2
- **Files modified:** 1 (script), 3 (parquets generated)

## Accomplishments

- Implemented 5 timepoint features fully vectorized using numpy searchsorted -- no .apply() on 1.2M rows
- Built historical speed lookup from training pings for speed_ratio computation
- Assembled complete v2 parquets combining all 15 Phase 3 features + 28 Phase 4 features
- Row counts verified unchanged after all merges (no row explosion)
- Routes 27/235 correctly get NaN for all timepoint features

## Task Commits

1. **Task 1+2: Timepoint features, speed ratio, and v2 assembly** - `1ccaab1` (feat)

**Plan metadata:** pending

## Files Created/Modified

- `scripts/build_differentiator_features.py` - Extended with timepoint features, speed ratio, is_rush_hour, Phase 3 feature inlining, full assembly pipeline, save_v2_parquet(), load_featured_v2(), FEATURE_COLS_V2/CATEGORICAL_COLS_V2 exports
- `data/processed/train_featured_v2.parquet` - 1,206,181 rows, 45 columns (43 features + target + stops_away)
- `data/processed/val_featured_v2.parquet` - 384,002 rows, 45 columns
- `data/processed/test_featured_v2.parquet` - 296,608 rows, 45 columns

## Decisions Made

- **Median scheduled time as representative:** Each timepoint stop has multiple scheduled departures throughout the day. Used median as a single representative value for scheduled_departure_seconds.
- **is_timepoint = NaN for no-timepoint routes:** Routes 27 and 235 have no timepoint data at all. Setting is_timepoint to NaN (not 0) distinguishes "no data" from "not a timepoint stop", which XGBoost handles natively.
- **Speed ratio from training pings only:** Historical median GPS speed computed per (route_id, last_stop_id, hour_ct, day_type) from training pings only. Applied to all splits for speed_ratio computation. No data leakage.
- **target_dwell 98% NaN is acceptable:** Only 58 of 119 target stops appear in historical dwell data (with >= 10 observations). XGBoost handles NaN natively, and the feature provides signal where available.
- **Phase 3 features inlined:** Rather than importing from build_features.py (which has side effects and different save patterns), Phase 3 feature computation is inlined in the v2 pipeline for self-contained execution.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- v2 featured parquets ready for Phase 4 Plan 03 (retrain XGBoost with expanded features)
- FEATURE_COLS_V2 (43 features) and CATEGORICAL_COLS_V2 exported for training script
- load_featured_v2() API available for downstream consumers
- Key NaN rates documented: speed_std_30s ~100% (expected from 60s ping intervals), target_dwell ~98% (sparse coverage), scheduled_departure_seconds ~87% (only timepoint target stops)

---
*Phase: 04-differentiator-features*
*Completed: 2026-02-04*
