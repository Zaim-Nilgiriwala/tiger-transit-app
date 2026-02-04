---
phase: 04-differentiator-features
plan: 03
subsystem: ml-training
tags: [xgboost, shap, eta-prediction, feature-importance, model-evaluation]

# Dependency graph
requires:
  - phase: 04-differentiator-features (04-02)
    provides: v2 featured parquets with 43 features (train/val/test)
  - phase: 03-baseline-model (03-02)
    provides: baseline_metrics.json with MAE 394.7s for comparison
provides:
  - Trained differentiator XGBoost model (175.7s MAE, 55.5% over baseline)
  - Full metrics JSON with baseline comparison, sliced metrics, SHAP rankings
  - SHAP feature importance analysis identifying top Phase 4 contributors
affects: [05-advanced-training, 06-evaluation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Differentiator training follows identical baseline pattern with expanded features"
    - "SHAP pred_contribs color-coded by phase origin (Phase 3 blue, Phase 4 red)"

key-files:
  created:
    - scripts/train_differentiator.py
    - models/differentiator_v1.ubj
    - models/differentiator_metrics.json
    - models/differentiator_shap.png
  modified: []

key-decisions:
  - "Kept all hyperparameters identical to baseline (reg_lambda=5.0) to isolate feature impact"
  - "Increased num_boost_round to 3000 (from 2000) -- model used all 3000, still improving"
  - "time_until_next_timepoint_departure is the #2 most important feature (SHAP=145.11)"

patterns-established:
  - "Model comparison pattern: load baseline_metrics.json, compute per-route/per-bucket deltas"

# Metrics
duration: ~12min
completed: 2026-02-04
---

# Phase 4 Plan 3: Differentiator Model Training Summary

**XGBoost retrained with 43 Phase 4 features achieves 175.7s MAE (55.5% improvement over 394.7s baseline), with timepoint departure time as #2 SHAP feature**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-02-04T21:08:00Z
- **Completed:** 2026-02-04T21:23:58Z
- **Tasks:** 1/1
- **Files created:** 4

## Accomplishments

- Differentiator MAE 175.7s vs baseline 394.7s (55.5% improvement, 219.0s reduction)
- Progressive chain: naive 708.9s -> baseline 394.7s -> differentiator 175.7s (75.2% vs naive)
- 5 new Phase 4 features in SHAP top 10: time_until_next_timepoint_departure (#2), segment_travel_median (#5), segment_travel_p25 (#6), segment_travel_p75 (#7), speed_mean_180s (#10)
- All 23 routes improved; largest gains on routes 26 (-296.7s), 100 (-273.7s), 7 (-270.1s), 93 (-270.4s)
- Every stops_away bucket improved: 1-stop (-234.9s), 2-3 (-225.8s), 4-6 (-211.2s), 7+ (-184.9s)

## Key Results

| Metric | Naive | Baseline (P3) | Differentiator (P4) |
|--------|-------|---------------|---------------------|
| MAE    | 708.9s | 394.7s       | 175.7s              |
| RMSE   | 883.4s | 514.9s       | 279.7s              |
| vs Naive | --  | 44.3%         | 75.2%               |

### Top 10 Features (SHAP)

| Rank | Feature | SHAP | Phase |
|------|---------|------|-------|
| 1 | pattern_id | 153.31 | P3 |
| 2 | time_until_next_timepoint_departure | 145.11 | P4 |
| 3 | stop_index | 120.07 | P3 |
| 4 | distance_to_target | 61.21 | P3 |
| 5 | segment_travel_median | 53.39 | P4 |
| 6 | segment_travel_p25 | 53.38 | P4 |
| 7 | segment_travel_p75 | 52.07 | P4 |
| 8 | route_progress | 50.99 | P3 |
| 9 | route_id | 45.78 | P3 |
| 10 | speed_mean_180s | 41.29 | P4 |

## Task Commits

1. **Task 1: Create differentiator training script and retrain model** - `d02331e` (feat)

**Plan metadata:** pending

## Files Created/Modified

- `scripts/train_differentiator.py` - Training script for v2 model with 43 features
- `models/differentiator_v1.ubj` - Trained XGBoost model (10.5MB, 3000 trees)
- `models/differentiator_metrics.json` - Full metrics with baseline comparison
- `models/differentiator_shap.png` - SHAP bar chart (red=P4, blue=P3)

## Decisions Made

- Kept all hyperparameters identical to baseline to isolate feature impact (same reg_lambda=5.0, max_depth=5, learning_rate=0.05)
- Increased num_boost_round from 2000 to 3000; model used all 3000 rounds without early stopping, suggesting further training could help (Phase 5 Optuna tuning)
- MAPE is 73.7% which is high due to very short trips (near-zero targets inflate percentage); MAE/RMSE are the primary metrics

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Distance bucket slicing showed all test rows in "<1km" bucket because distance_to_target is measured in shape_dist units (meters along route shape), and most observations are close to their target stop. Not a bug -- the feature has valid continuous values, but the bucketing thresholds need route-length-aware tuning. Does not affect model quality.
- Model did not trigger early stopping at 3000 rounds (val MAE still declining at 173.1s). Phase 5 Optuna tuning should explore higher learning rates and more rounds.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4 gate PASSED: 175.7s < 394.7s baseline
- Model still under-trained at 3000 rounds -- Phase 5 Optuna tuning should find optimal configuration
- differentiator_metrics.json available for Phase 5/6 comparison baseline
- SHAP analysis reveals timepoint features are extremely valuable -- validate these survive in Phase 5 tuned model

---
*Phase: 04-differentiator-features*
*Completed: 2026-02-04*
