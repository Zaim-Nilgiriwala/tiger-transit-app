---
phase: 03-baseline-model
plan: 01
subsystem: feature-engineering
tags: [features, xgboost, parquet, weather, stop-sequences]

requires:
  - "02-01: Row explosion with stop_sequences.parquet"
  - "02-02: Temporal train/val/test splits"
provides:
  - "15-column feature-enriched parquets for XGBoost training"
  - "build_features.py with load_featured() helper for downstream consumers"
affects:
  - "03-02: Baseline XGBoost training (consumes featured parquets)"
  - "04-*: Differentiator features (extends FEATURE_COLS list)"

tech-stack:
  added: []
  patterns:
    - "Feature columns computed identically across splits via shared function"
    - "Weather merge via hourly floor + left join"
    - "load_featured() helper guarantees category dtype on any pandas version"
    - "pyarrow dictionary encoding for categorical parquet storage"

key-files:
  created:
    - scripts/build_features.py
    - data/processed/train_featured.parquet
    - data/processed/val_featured.parquet
    - data/processed/test_featured.parquet
  modified: []

key-decisions:
  - id: "03-01-D1"
    decision: "lateness_now has zero variance (scheduled_eta_seconds == eta_seconds in all data)"
    rationale: "EtaSpot API returns identical values for both fields. Feature retained for structural correctness; model will learn to ignore it."
  - id: "03-01-D2"
    decision: "Use load_featured() helper to guarantee category dtypes"
    rationale: "Pandas 2.3.3 does not restore category dtype from parquet roundtrip. Helper function casts on load."
  - id: "03-01-D3"
    decision: "scheduled_time_to_target uses scheduled_eta_seconds directly (clipped >= 0)"
    rationale: "Per research notes, this is the best available proxy for scheduled remaining time."

metrics:
  duration: "4m"
  completed: "2026-02-04"
---

# Phase 3 Plan 1: Feature Engineering Summary

**One-liner:** 15 core feature columns (distance, speed, time, weather, categorical) computed from stop_sequences and weather data across 1.89M rows in 3 temporal splits.

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~4 minutes |
| Script lines | 305 |
| Train rows | 1,206,181 |
| Val rows | 384,002 |
| Test rows | 296,608 |
| Feature columns | 15 |
| Critical NaN count | 0 |
| Categorical columns | 3 (day_of_week, route_id, pattern_id) |

## Accomplishments

1. Created `scripts/build_features.py` (305 lines) implementing all 15 features from FEAT-01 through FEAT-08
2. Produced three feature-enriched parquet files preserving exact row counts from input splits
3. Zero NaN values in any feature column after weather merge fill
4. Weather merge achieved full coverage (no NaN in precipitation_mm or temperature_c after fill)
5. Added `load_featured()` public API for downstream consumers to ensure correct dtypes

## Feature Column Summary

| Group | Columns | Source |
|-------|---------|--------|
| FEAT-01 | distance_to_target | (target_stop_progress - progress) * max_shape_dist |
| FEAT-02 | scheduled_time_to_target | scheduled_eta_seconds clipped >= 0 |
| FEAT-03 | current_speed, route_progress, stops_remaining, stop_index | Direct renames from speed, progress, stops_away, target_stop_sequence |
| FEAT-04 | lateness_now | scheduled_eta_seconds - eta_seconds (zero variance) |
| FEAT-05 | minutes_since_midnight, day_of_week | Timestamp decomposition |
| FEAT-06 | pattern_id, route_id | Cast to category dtype |
| FEAT-07 | precipitation_mm, temperature_c | Hourly weather merge |
| FEAT-08 | passenger_load, is_idle | load rename + speed <= 2 binary |

## Task Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 06cef2f | feat(03-01): create build_features.py with all 15 core feature columns |

## Files Created/Modified

**Created:**
- `scripts/build_features.py` -- Feature engineering pipeline (305 lines)
- `data/processed/train_featured.parquet` -- 1,206,181 rows, 17 columns
- `data/processed/val_featured.parquet` -- 384,002 rows, 17 columns
- `data/processed/test_featured.parquet` -- 296,608 rows, 17 columns

## Decisions Made

1. **lateness_now zero variance** (03-01-D1): The EtaSpot API returns identical values for `scheduled_eta_seconds` and `eta_seconds`, making `lateness_now` always 0. Feature retained for structural completeness -- XGBoost will assign it zero importance. If future data sources provide distinct scheduled vs. actual ETAs, this feature will become useful without code changes.

2. **load_featured() helper for dtype safety** (03-01-D2): Pandas 2.3.3 does not restore category dtype from parquet files. The `load_featured()` function in `build_features.py` handles this, and all downstream consumers (training script) should use it.

3. **scheduled_time_to_target = scheduled_eta_seconds** (03-01-D3): Used the API's scheduled ETA directly as the scheduled time-to-target proxy. Values range 420-1274 seconds, consistent with bus transit windows.

## Deviations from Plan

### Data Discovery

**1. [Rule 1 - Bug] lateness_now zero variance**
- **Found during:** Task 1 verification
- **Issue:** `scheduled_eta_seconds` and `eta_seconds` are identical in all EtaSpot data, producing a constant-zero feature
- **Fix:** Retained the feature (structurally correct, model will ignore), documented the finding
- **Impact:** One of 15 features has zero predictive power. The remaining 14 features provide sufficient signal.

### Technical Adaptation

**2. [Rule 3 - Blocking] Pandas category dtype not preserved in parquet roundtrip**
- **Found during:** Task 1 verification
- **Issue:** Pandas 2.3.3 does not restore category dtype from parquet files, even with pyarrow dictionary encoding
- **Fix:** Added `load_featured()` helper function that casts categorical columns after load
- **Files modified:** scripts/build_features.py

## Issues Encountered

None beyond the deviations documented above.

## Next Phase Readiness

**Ready for 03-02 (Baseline XGBoost Training):**
- All three featured parquet files exist with correct schema
- FEATURE_COLS, CATEGORICAL_COLS, and TARGET_COL constants exported from build_features.py
- load_featured() helper available for training script to import
- No blockers identified
