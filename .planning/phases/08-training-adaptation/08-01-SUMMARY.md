---
phase: 08-training-adaptation
plan: 01
subsystem: ml-pipeline
tags: [xgboost, feature-engineering, residual-target, baseline-features, parquet]

# Dependency graph
requires:
  - phase: 07-baseline-infrastructure
    provides: "baseline_s2s, baseline_seg_sum, baseline_eta, residual columns in train/val/test.parquet"
provides:
  - "v1.1 featured parquets with 45 features, residual target, and reconstruction columns"
  - "FEATURE_COLS_V2 constant (45 features) and BASELINE_FEATURE_COLS constant"
  - "TARGET_COL = residual (model learns deviation from baseline)"
  - "KEEP_EXTRA preserves time_to_arrival_seconds and baseline_eta for evaluation reconstruction"
affects: [08-02 Optuna tuning, 08-03 evaluation, 09-deployment]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Residual target pattern: model predicts residual, final_pred = baseline_eta + predicted_residual"
    - "Feature deduplication: baseline_eta in both FEATURE_COLS_V2 and KEEP_EXTRA, deduped in save_v2_parquet"

key-files:
  created: []
  modified:
    - "scripts/build_differentiator_features.py"
    - "data/processed/train_featured_v2.parquet"
    - "data/processed/val_featured_v2.parquet"
    - "data/processed/test_featured_v2.parquet"

key-decisions:
  - "Removed lateness_now from feature set (zero variance, confirmed in Phase 5)"
  - "Added 3 baseline features (baseline_s2s, baseline_seg_sum, baseline_eta) as features 43-45"
  - "Changed TARGET_COL to residual -- model learns baseline deviation instead of raw seconds"
  - "Preserved time_to_arrival_seconds and baseline_eta in KEEP_EXTRA for downstream reconstruction"
  - "Left lateness_now computation in compute_phase3_features (harmless, minimizes diff)"

patterns-established:
  - "Reconstruction pattern: final_pred = baseline_eta + predicted_residual (evaluation scripts use this)"
  - "Feature versioning: FEATURE_COLS_V2 is authoritative list, BASELINE_FEATURE_COLS added as sub-group"

# Metrics
duration: 2min
completed: 2026-02-17
---

# Phase 8 Plan 01: Feature Pipeline v1.1 Summary

**Updated feature pipeline to 45 features (drop lateness_now, add 3 baselines), residual target, and reconstruction columns in all three featured parquets**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-17T19:49:23Z
- **Completed:** 2026-02-17T19:51:50Z
- **Tasks:** 2
- **Files modified:** 1 (script) + 3 (parquets, gitignored)

## Accomplishments
- FEATURE_COLS_V2 updated to 45 features: 14 phase3 + 28 phase4 + 3 baselines
- TARGET_COL changed from time_to_arrival_seconds to residual
- All three splits rebuilt with correct schema and row counts preserved
- Train residual: mean=-9.1s, std=287.4s (matches Phase 7 exactly)

## Task Commits

Each task was committed atomically:

1. **Task 1: Update feature constants, target, and save logic** - `4e38eb2` (feat)
2. **Task 2: Rebuild featured parquets and validate schema** - No commit (gitignored data artifacts; pipeline execution verified)

## Files Created/Modified
- `scripts/build_differentiator_features.py` - Updated PHASE3_FEATURE_COLS (14), added BASELINE_FEATURE_COLS, updated FEATURE_COLS_V2 (45), TARGET_COL=residual, KEEP_EXTRA with reconstruction columns
- `data/processed/train_featured_v2.parquet` - 1,206,181 rows, 48 columns (45 features + residual + stops_away + time_to_arrival_seconds)
- `data/processed/val_featured_v2.parquet` - 384,002 rows, 48 columns
- `data/processed/test_featured_v2.parquet` - 296,608 rows, 48 columns

## Validation Results

| Split | Rows | Features | residual NaN | baseline_eta NaN | baseline_seg_sum NaN | lateness_now |
|-------|------|----------|-------------|------------------|---------------------|--------------|
| train | 1,206,181 | 45/45 | 0 | 0 | 41 | absent |
| val | 384,002 | 45/45 | 0 | 0 | 32 | absent |
| test | 296,608 | 45/45 | 0 | 0 | 34 | absent |

Train residual stats: mean=-9.1s, std=287.4s, min=-2921s, max=4815s

## Decisions Made
- Removed lateness_now from feature list (14 phase3 features, down from 15) since it has zero variance in EtaSpot data
- Left lateness_now computation in compute_phase3_features to minimize diff -- it's computed but not saved to parquet
- baseline_eta appears in both FEATURE_COLS_V2 (as feature) and KEEP_EXTRA (for reconstruction); the save logic deduplicates via `if c not in out_cols`
- Val and test row counts (384,002 and 296,608) differ from plan estimates (~339,561 and ~279,289) -- these were approximate; actual counts from Phase 7 source parquets are correct

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Featured parquets ready for Plan 08-02 (Optuna tuning with XGBoost on residual target)
- Reconstruction workflow confirmed: final_pred = baseline_eta + predicted_residual
- All 45 features available including 3 baseline features for XGBoost to learn correction patterns
- No blockers for next plan

---
*Phase: 08-training-adaptation*
*Completed: 2026-02-17*
